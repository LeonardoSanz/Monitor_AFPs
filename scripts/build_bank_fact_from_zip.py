from __future__ import annotations

from pathlib import Path
import argparse
import zipfile
import pandas as pd

from build_processed_from_zip import (
    AFP_NOMBRES, USECOLS, clean_string, load_dictionary, classify, BANK_RULES
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ZIP = PROJECT_ROOT / "data" / "raw" / "chistAFP.zip"
OUT_DIR = PROJECT_ROOT / "data" / "processed"
PART_DIR = OUT_DIR / "bank_parts"
PART_DIR.mkdir(parents=True, exist_ok=True)


def vector_bank_name(series: pd.Series) -> pd.Series:
    s = series.fillna("").astype(str).str.upper()
    out = pd.Series("", index=s.index, dtype="object")
    for token, canonical in BANK_RULES:
        mask = out.eq("") & s.str.contains(token, regex=False, na=False)
        if canonical is None:
            out.loc[mask] = "__EXCLUDE__"
        else:
            out.loc[mask] = canonical
    return out.replace("__EXCLUDE__", "")


def process_file(zip_path: Path, name: str) -> pd.DataFrame:
    dic = load_dictionary()
    parts = []
    with zipfile.ZipFile(zip_path) as z:
        for chunk in pd.read_csv(
            z.open(name), sep=";", usecols=USECOLS, chunksize=250_000, dtype=str,
            encoding="latin-1", on_bad_lines="skip",
        ):
            chunk["fecha_raw"] = clean_string(chunk["fecha"])
            chunk = chunk.loc[chunk["fecha_raw"].str.match(r"^\d{8}$", na=False)].copy()
            if chunk.empty:
                continue
            chunk["nombre_del_emisor"] = clean_string(chunk["nombre_del_emisor"]).str.upper()
            chunk["banco_nombre"] = vector_bank_name(chunk["nombre_del_emisor"])
            chunk = chunk.loc[chunk["banco_nombre"].ne("")].copy()
            if chunk.empty:
                continue
            chunk["fecha"] = pd.to_datetime(chunk["fecha_raw"], format="%Y%m%d", errors="coerce")
            chunk["afp"] = clean_string(chunk["afp"]).str.lower()
            chunk["afp_nombre"] = chunk["afp"].map(AFP_NOMBRES).fillna(chunk["afp"].str.upper())
            chunk["tipo_de_fondo"] = clean_string(chunk["tipo_de_fondo"]).str.upper()
            chunk["tipo_de_instrumento"] = clean_string(chunk["tipo_de_instrumento"]).str.upper()
            chunk["nacionalidad_del_emisor"] = clean_string(chunk["nacionalidad_del_emisor"]).str.upper()
            chunk["unidad_de_reajuste_de_moneda"] = clean_string(chunk["unidad_de_reajuste_de_moneda"]).str.upper()
            chunk["moneda_contrato_forward"] = clean_string(chunk["moneda_contrato_forward"]).str.upper()
            chunk["moneda_objeto_forward"] = clean_string(chunk["moneda_objeto_forward"]).str.upper()
            chunk["origen"] = chunk["nacionalidad_del_emisor"].eq("E").map({True: "Extranjero", False: "Nacional"})
            chunk["origen_banco"] = chunk["origen"]
            chunk["inversion"] = pd.to_numeric(clean_string(chunk["inversion"]), errors="coerce")
            chunk = chunk.loc[chunk["inversion"].notna()].copy()
            if chunk.empty:
                continue
            chunk = classify(chunk, dic)
            chunk["inversion_abs"] = chunk["inversion"].abs()
            chunk["n_registros"] = 1
            gb = chunk.groupby(
                [
                    "fecha", "afp", "afp_nombre", "tipo_de_fondo", "tipo_de_instrumento", "instrumento_bancario",
                    "familia_instrumento", "derivado_tipo", "bucket_reporte", "nombre_del_emisor", "banco_nombre", "origen_banco",
                ],
                dropna=False, as_index=False,
            ).agg(
                inversion_neta_clp=("inversion", "sum"),
                inversion_abs_clp=("inversion_abs", "sum"),
                n_registros=("n_registros", "sum"),
            )
            parts.append(gb)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)
    cols = [c for c in out.columns if c not in {"inversion_neta_clp", "inversion_abs_clp", "n_registros"}]
    return out.groupby(cols, as_index=False, dropna=False).agg(
        inversion_neta_clp=("inversion_neta_clp", "sum"),
        inversion_abs_clp=("inversion_abs_clp", "sum"),
        n_registros=("n_registros", "sum"),
    )


def combine_parts() -> None:
    files = sorted(PART_DIR.glob("bank_part_*.csv.gz"))
    if not files:
        raise FileNotFoundError("No hay partes bank_part_*.csv.gz para combinar")
    df = pd.concat([pd.read_csv(f, parse_dates=["fecha"]) for f in files], ignore_index=True)
    cols = [c for c in df.columns if c not in {"inversion_neta_clp", "inversion_abs_clp", "n_registros"}]
    fact = df.groupby(cols, as_index=False, dropna=False).agg(
        inversion_neta_clp=("inversion_neta_clp", "sum"),
        inversion_abs_clp=("inversion_abs_clp", "sum"),
        n_registros=("n_registros", "sum"),
    ).sort_values(["fecha", "afp", "tipo_de_fondo", "instrumento_bancario", "banco_nombre"])
    fact.to_csv(OUT_DIR / "fact_contrapartes_bancarias_agg.csv.gz", index=False, compression="gzip", encoding="utf-8")
    print(f"OK bank fact combinado: {len(fact):,} filas")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--year", type=str, default="")
    parser.add_argument("--combine", action="store_true")
    args = parser.parse_args()
    if args.combine:
        combine_parts()
        return
    if not args.zip.exists():
        raise FileNotFoundError(args.zip)
    with zipfile.ZipFile(args.zip) as z:
        files = sorted([n for n in z.namelist() if n.lower().endswith(".csv")])
    if args.year:
        files = [n for n in files if args.year in n]
    for name in files:
        year = ''.join([c for c in name if c.isdigit()])[-4:]
        out = process_file(args.zip, name)
        out_path = PART_DIR / f"bank_part_{year}.csv.gz"
        out.to_csv(out_path, index=False, compression="gzip", encoding="utf-8")
        print(f"OK {name}: {len(out):,} filas agregadas")

if __name__ == "__main__":
    main()
