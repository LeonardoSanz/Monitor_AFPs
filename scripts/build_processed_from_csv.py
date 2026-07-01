from __future__ import annotations

from pathlib import Path
import argparse
import zipfile
import pandas as pd

from build_processed_from_zip import (
    PROJECT_ROOT,
    OUT_DIR,
    AFP_NOMBRES,
    USECOLS,
    clean_string,
    load_dictionary,
    classify,
    bank_name,
)

DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "chistAFP"


def find_raw_files(raw_dir: Path) -> list[Path]:
    """Encuentra archivos cartera_mensual_YYYY.csv o cartera_mensual_YYYY.zip.

    Estructuras soportadas:
    - data/raw/chistAFP/cartera_mensual_2016.csv
    - data/raw/chistAFP/cartera_mensual_2016.zip, con un CSV dentro
    - data/raw/cartera_mensual_2016.csv o .zip como fallback
    """
    raw_dir = Path(raw_dir)
    files: list[Path] = []
    if raw_dir.exists():
        patterns = [
            "cartera_mensual_*.csv",
            "cartera_mensual_*.zip",
            "*.csv",
            "*.zip",
        ]
        for pat in patterns:
            files.extend(sorted(raw_dir.glob(pat)))

    seen = set()
    out = []
    for f in files:
        if not f.is_file():
            continue
        key = f.resolve()
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def csv_members_from_zip(path: Path) -> list[str]:
    """Lista miembros CSV útiles dentro de un ZIP anual."""
    with zipfile.ZipFile(path) as z:
        names = [
            n for n in z.namelist()
            if not n.endswith("/")
            and Path(n).name.lower().endswith(".csv")
            and (Path(n).name.lower().startswith("cartera_mensual_") or len(z.namelist()) == 1)
        ]
        if not names:
            names = [n for n in z.namelist() if not n.endswith("/") and Path(n).name.lower().endswith(".csv")]
    return names


def iter_raw_csv_chunks(path: Path):
    """Itera chunks de un CSV directo o de los CSV contenidos en un ZIP."""
    read_kwargs = dict(
        sep=";",
        usecols=USECOLS,
        chunksize=250_000,
        dtype=str,
        encoding="latin-1",
        on_bad_lines="skip",
    )

    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            members = csv_members_from_zip(path)
            if not members:
                raise FileNotFoundError(f"El ZIP {path.name} no contiene archivos CSV.")
            for member in members:
                with z.open(member) as fh:
                    for chunk in pd.read_csv(fh, **read_kwargs):
                        yield f"{path.name}:{Path(member).name}", chunk
    else:
        for chunk in pd.read_csv(path, **read_kwargs):
            yield path.name, chunk


def process_raw_files(raw_files: list[Path]) -> None:
    if not raw_files:
        raise FileNotFoundError(
            "No encontré archivos de cartera. Deja cartera_mensual_YYYY.csv o cartera_mensual_YYYY.zip en data/raw/chistAFP/."
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dic = load_dictionary()
    aggregated = []
    bank_aggregated = []
    diagnostics = []

    for path in raw_files:
        name = path.name
        total_rows = 0
        bad_date_rows = 0
        bad_inversion_rows = 0
        kept_rows = 0

        for source_name, chunk in iter_raw_csv_chunks(path):
            total_rows += len(chunk)
            chunk["fecha_raw"] = clean_string(chunk["fecha"])
            valid_date = chunk["fecha_raw"].str.match(r"^\d{8}$", na=False)
            bad_date_rows += int((~valid_date).sum())
            chunk = chunk.loc[valid_date].copy()
            if chunk.empty:
                continue

            chunk["fecha"] = pd.to_datetime(chunk["fecha_raw"], format="%Y%m%d", errors="coerce")
            chunk["afp"] = clean_string(chunk["afp"]).str.lower()
            chunk["afp_nombre"] = chunk["afp"].map(AFP_NOMBRES).fillna(chunk["afp"].str.upper())
            chunk["tipo_de_fondo"] = clean_string(chunk["tipo_de_fondo"]).str.upper()
            chunk["tipo_de_instrumento"] = clean_string(chunk["tipo_de_instrumento"]).str.upper()
            chunk["nombre_del_emisor"] = clean_string(chunk["nombre_del_emisor"]).str.upper()
            chunk["nacionalidad_del_emisor"] = clean_string(chunk["nacionalidad_del_emisor"]).str.upper()
            chunk["unidad_de_reajuste_de_moneda"] = clean_string(chunk["unidad_de_reajuste_de_moneda"]).str.upper()
            chunk["moneda_contrato_forward"] = clean_string(chunk["moneda_contrato_forward"]).str.upper()
            chunk["moneda_objeto_forward"] = clean_string(chunk["moneda_objeto_forward"]).str.upper()
            chunk["origen"] = chunk["nacionalidad_del_emisor"].eq("E").map({True: "Extranjero", False: "Nacional"})
            chunk["origen_banco"] = chunk["origen"]
            chunk["inversion"] = pd.to_numeric(clean_string(chunk["inversion"]), errors="coerce")
            bad_inversion_rows += int(chunk["inversion"].isna().sum())
            chunk = chunk.loc[chunk["inversion"].notna()].copy()
            if chunk.empty:
                continue
            kept_rows += len(chunk)

            chunk = classify(chunk, dic)
            chunk["inversion_abs"] = chunk["inversion"].abs()
            chunk["n_registros"] = 1
            chunk["banco_nombre"] = chunk["nombre_del_emisor"].apply(bank_name)
            chunk["es_contraparte_bancaria"] = chunk["banco_nombre"].ne("")

            common_group = [
                "fecha", "afp", "afp_nombre", "tipo_de_fondo", "origen", "macro_bucket", "clase", "subclase",
                "bucket_reporte", "bucket_reporte_sp", "familia_instrumento", "derivado_tipo",
                "es_derivado", "es_alternativo", "tipo_de_instrumento", "instrumento_bancario",
            ]
            g = chunk.groupby(common_group, dropna=False, as_index=False).agg(
                inversion_neta_clp=("inversion", "sum"),
                inversion_abs_clp=("inversion_abs", "sum"),
                n_registros=("n_registros", "sum"),
            )
            aggregated.append(g)

            bank = chunk.loc[chunk["es_contraparte_bancaria"]].copy()
            if len(bank):
                gb = bank.groupby(
                    [
                        "fecha", "afp", "afp_nombre", "tipo_de_fondo", "tipo_de_instrumento", "instrumento_bancario",
                        "familia_instrumento", "derivado_tipo", "bucket_reporte", "nombre_del_emisor", "banco_nombre", "origen_banco",
                    ],
                    dropna=False,
                    as_index=False,
                ).agg(
                    inversion_neta_clp=("inversion", "sum"),
                    inversion_abs_clp=("inversion_abs", "sum"),
                    n_registros=("n_registros", "sum"),
                )
                bank_aggregated.append(gb)

        diagnostics.append({
            "archivo": name,
            "ruta": str(path),
            "filas_leidas": total_rows,
            "filas_fecha_invalida": bad_date_rows,
            "filas_inversion_invalida": bad_inversion_rows,
            "filas_usadas": kept_rows,
        })
        print(f"Procesado {name}: {kept_rows:,} filas usadas")

    if not aggregated:
        raise RuntimeError("No se generaron registros agregados. Revisa el formato de los CSV.")

    fact = pd.concat(aggregated, ignore_index=True)
    group_cols = [c for c in fact.columns if c not in {"inversion_neta_clp", "inversion_abs_clp", "n_registros"}]
    fact = fact.groupby(group_cols, as_index=False, dropna=False).agg(
        inversion_neta_clp=("inversion_neta_clp", "sum"),
        inversion_abs_clp=("inversion_abs_clp", "sum"),
        n_registros=("n_registros", "sum"),
    ).sort_values(["fecha", "afp", "tipo_de_fondo", "macro_bucket", "bucket_reporte", "tipo_de_instrumento"])

    fact.to_csv(OUT_DIR / "fact_cartera_mensual_agg.csv.gz", index=False, compression="gzip", encoding="utf-8")

    if bank_aggregated:
        bank_fact = pd.concat(bank_aggregated, ignore_index=True)
        bank_cols = [c for c in bank_fact.columns if c not in {"inversion_neta_clp", "inversion_abs_clp", "n_registros"}]
        bank_fact = bank_fact.groupby(bank_cols, as_index=False, dropna=False).agg(
            inversion_neta_clp=("inversion_neta_clp", "sum"),
            inversion_abs_clp=("inversion_abs_clp", "sum"),
            n_registros=("n_registros", "sum"),
        ).sort_values(["fecha", "afp", "tipo_de_fondo", "instrumento_bancario", "banco_nombre"])
        bank_fact.to_csv(OUT_DIR / "fact_contrapartes_bancarias_agg.csv.gz", index=False, compression="gzip", encoding="utf-8")
    else:
        bank_fact = pd.DataFrame()
        # Crear un archivo vacío con columnas esperadas para evitar errores de lectura posterior.
        pd.DataFrame(columns=[
            "fecha", "afp", "afp_nombre", "tipo_de_fondo", "tipo_de_instrumento", "instrumento_bancario",
            "familia_instrumento", "derivado_tipo", "bucket_reporte", "nombre_del_emisor", "banco_nombre",
            "origen_banco", "inversion_neta_clp", "inversion_abs_clp", "n_registros",
        ]).to_csv(OUT_DIR / "fact_contrapartes_bancarias_agg.csv.gz", index=False, compression="gzip", encoding="utf-8")

    pd.DataFrame(diagnostics).to_csv(OUT_DIR / "diagnostico_carga.csv", index=False, encoding="utf-8-sig")
    resumen = {
        "fecha_min": str(fact["fecha"].min().date()),
        "fecha_max": str(fact["fecha"].max().date()),
        "n_fechas": int(fact["fecha"].nunique()),
        "n_afp": int(fact["afp"].nunique()),
        "afp": sorted(fact["afp_nombre"].unique().tolist()),
        "fondos": sorted(fact["tipo_de_fondo"].unique().tolist()),
        "n_tipos_instrumento": int(fact["tipo_de_instrumento"].nunique()),
        "filas_fact_agg": int(len(fact)),
        "filas_fact_bancos_agg": int(len(bank_fact)),
        "fuente_raw": "csv_o_zip_anual",
        "raw_files": [f.name for f in raw_files],
        "version": "v10_csv_zip_anual",
    }
    pd.Series(resumen).to_json(OUT_DIR / "resumen_carga.json", indent=2, force_ascii=False)
    dic.to_csv(PROJECT_ROOT / "data" / "dictionaries" / "diccionario_tipo_instrumento.csv", index=False, encoding="utf-8-sig")
    print("OK: facts generados desde CSV/ZIP anual")
    print(resumen)


def main(raw_dir: Path = DEFAULT_RAW_DIR) -> None:
    raw_dir = Path(raw_dir)
    if not raw_dir.exists() and raw_dir.name.lower() == "chistafp":
        fallback = PROJECT_ROOT / "data" / "raw"
        if fallback.exists():
            raw_dir = fallback
    raw_files = find_raw_files(raw_dir)
    process_raw_files(raw_files)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="Carpeta con cartera_mensual_YYYY.csv o cartera_mensual_YYYY.zip")
    args = parser.parse_args()
    main(args.raw_dir)
