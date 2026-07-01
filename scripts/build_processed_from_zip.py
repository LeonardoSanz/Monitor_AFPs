from __future__ import annotations

from pathlib import Path
import argparse
import re
import zipfile
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ZIP = PROJECT_ROOT / "data" / "raw" / "chistAFP.zip"
DICT_PATH = PROJECT_ROOT / "data" / "dictionaries" / "diccionario_tipo_instrumento.csv"
OUT_DIR = PROJECT_ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

AFP_NOMBRES = {
    "apo": "APORTA", "arm": "ARMONIZA", "bsa": "BANSANDER", "cap": "CAPITAL",
    "cup": "CUPRUM", "fom": "FOMENTA", "fut": "FUTURO", "hab": "HABITAT",
    "mag": "MAGISTER", "mod": "MODELO", "pli": "PLANVITAL", "prt": "PROTECCION",
    "prv": "PROVIDA", "qua": "QUALITAS", "sta": "SANTA MARIA", "sum": "SUMMA",
    "uni": "UNION", "uno": "UNO", "val": "VALORA",
}

USECOLS = [
    "fecha", "afp", "tipo_de_fondo", "tipo_de_instrumento", "nemotecnico_del_instrumento",
    "nombre_del_emisor", "nacionalidad_del_emisor", "unidad_de_reajuste_de_moneda", "inversion",
    "moneda_contrato_forward", "moneda_objeto_forward",
]

DERIV_FORWARD_PREFIX = ("W", "X", "Y")
ALT_CODES = {
    "ACPE", "ADPE", "CCPE", "CDPE", "KCPE", "KDPE", "VCPE", "VDPE",
    "VIPE", "VRPE", "AIPE", "ARPE", "RAIZ", "CREN", "CLEA", "MHE", "PFI", "CDCS", "CSIN",
}
ALT_PATTERN = re.compile(
    r"CAPITAL PRIVADO|DEUDA PRIVADA|COINVERSION|COINVERSIÓN|VEHICULO|VEHÍCULO|"
    r"BIENES RAICES|BIENES RAÍCES|ARRENDAMIENTO|LEASING|MUTUOS HIPOTECARIOS|"
    r"CREDITO SINDICADO|CRÉDITO SINDICADO|PROMESAS DE SUSCRIPCION|PROMESAS DE SUSCRIPCIÓN|"
    r"ACTIVO ALTERNATIVO",
    re.IGNORECASE,
)

BANK_RULES = [
    ("BANCO CENTRAL", None),
    ("TESORERIA GENERAL", None),
    ("BANK OF AMERICA", "Bank of America"),
    ("JPMORGAN", "JP Morgan"),
    ("JP MORGAN", "JP Morgan"),
    ("MORGAN STANLEY", "Morgan Stanley"),
    ("GOLDMAN SACHS", "Goldman Sachs"),
    ("BNP PARIBAS", "BNP Paribas"),
    ("HSBC", "HSBC"),
    ("CITIBANK", "Citi"),
    ("CITI", "Citi"),
    ("SCOTIABANK", "Scotiabank"),
    ("NOVA SCOTIA", "Scotiabank"),
    ("SANTANDER", "Santander"),
    ("CREDITO E INVERSIONES", "BCI"),
    ("BANCO BCI", "BCI"),
    ("BCI", "BCI"),
    ("BANCO DE CHILE", "Banco de Chile"),
    ("BANCO DEL ESTADO", "Banco Estado"),
    ("BANCO ESTADO", "Banco Estado"),
    ("ITAU", "Itaú"),
    ("ITAÚ", "Itaú"),
    ("BTG PACTUAL", "BTG Pactual"),
    ("BANCO BICE", "Banco BICE"),
    ("BANCO SECURITY", "Banco Security"),
    ("FALABELLA", "Banco Falabella"),
    ("RIPLEY", "Banco Ripley"),
    ("CONSORCIO", "Banco Consorcio"),
    ("BARCLAYS", "Barclays"),
    ("DEUTSCHE", "Deutsche Bank"),
    ("UBS", "UBS"),
    ("CREDIT SUISSE", "Credit Suisse"),
    ("SOCIETE GENERALE", "Société Générale"),
    ("CREDIT AGRICOLE", "Crédit Agricole"),
    ("STANDARD CHARTERED", "Standard Chartered"),
    ("STATE STREET", "State Street"),
    ("RABOBANK", "Rabobank"),
    ("MIZUHO", "Mizuho"),
    ("SUMITOMO", "SMBC / Sumitomo"),
    ("SMBC", "SMBC / Sumitomo"),
    ("MUFG", "MUFG"),
    ("NOMURA", "Nomura"),
    ("NATWEST", "NatWest"),
    ("ROYAL BANK", "Royal Bank of Canada"),
    ("RBC", "Royal Bank of Canada"),
    ("BBVA", "BBVA"),
    ("BANCO", "Otros bancos"),
    ("BANK", "Otros bancos"),
]


def clean_string(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.replace('"', "", regex=False).str.strip()


def derive_dictionary_fields(dic: pd.DataFrame) -> pd.DataFrame:
    dic = dic.copy()
    dic["tipo_de_instrumento"] = clean_string(dic["tipo_de_instrumento"]).str.upper()
    dic["descripcion"] = clean_string(dic.get("descripcion", pd.Series("", index=dic.index))).str.upper()

    def derivado_tipo(row) -> str:
        code = row["tipo_de_instrumento"]
        desc = row["descripcion"]
        if "SWAP" in desc or code in {"SEI", "SEM", "SET", "SIN", "SNI", "SNM", "SNT", "XSET", "XSEI", "XSEM", "XSNT", "XSNI", "XSNM", "YSET", "YSEI", "YSEM", "YSNT", "YSNI", "YSNM"}:
            return "Swaps"
        if "FORWARD" in desc or (code.startswith(DERIV_FORWARD_PREFIX) and code not in {"XERO", "ZERO"}):
            return "Forwards"
        if "FUTURO" in desc or code.startswith("F"):
            return "Futuros"
        if "OPCION" in desc or "OPCIÓN" in desc or code.startswith("O"):
            return "Opciones"
        return "No derivado"

    dic["derivado_tipo"] = dic.apply(derivado_tipo, axis=1)
    dic["es_derivado"] = dic["derivado_tipo"].ne("No derivado")
    dic["es_alternativo"] = dic.apply(
        lambda r: bool(r["tipo_de_instrumento"] in ALT_CODES or ALT_PATTERN.search(r["descripcion"])), axis=1
    )

    def familia(row) -> str:
        if row["es_derivado"]:
            return "Derivados"
        if row["es_alternativo"]:
            return "Alternativos"
        return "Tradicionales"

    dic["familia_instrumento"] = dic.apply(familia, axis=1)
    return dic


def load_dictionary() -> pd.DataFrame:
    dic = pd.read_csv(DICT_PATH, dtype=str).fillna("")
    return derive_dictionary_fields(dic)


def final_bucket(row) -> str:
    if bool(row.get("es_derivado", False)):
        return f"Derivados / {row.get('derivado_tipo', 'Otros derivados')}"
    if bool(row.get("es_alternativo", False)):
        return "Alternativos"

    origen = row.get("origen", "")
    clase = row.get("clase", "")
    sub = row.get("subclase", "")

    if origen == "Nacional" and clase == "Renta Variable" and sub == "Acciones":
        return "RV Nacional / Acciones"
    if origen == "Nacional" and clase == "Renta Variable":
        return "RV Nacional / Fondos y otros"
    if origen == "Nacional" and clase == "Renta Fija" and sub == "Instrumentos Estatales":
        return "RF Nacional / Instrumentos estatales"
    if origen == "Nacional" and clase == "Renta Fija" and sub == "Bonos":
        return "RF Nacional / Bonos"
    if origen == "Nacional" and clase == "Renta Fija" and sub == "Depósitos":
        return "RF Nacional / Depósitos"
    if origen == "Nacional" and clase == "Renta Fija":
        return "RF Nacional / Otros"
    if origen == "Extranjero" and clase == "Renta Variable" and sub == "Fondos Mutuos":
        return "RV Extranjera / Fondos mutuos"
    if origen == "Extranjero" and clase == "Renta Variable":
        return "RV Extranjera / Otros"
    if origen == "Extranjero" and clase == "Renta Fija":
        return "RF Extranjera"
    return "Caja / Otros"


def macro_bucket(row) -> str:
    bucket = row.get("bucket_reporte", "")
    if bucket.startswith("Derivados"):
        return "Derivados"
    if bucket == "Alternativos":
        return "Alternativos"
    if bucket.startswith("RV Nacional"):
        return "Renta variable nacional"
    if bucket.startswith("RV Extranjera"):
        return "Renta variable extranjera"
    if bucket.startswith("RF Nacional"):
        return "Renta fija nacional"
    if bucket.startswith("RF Extranjera"):
        return "Renta fija extranjera"
    return "Caja / Otros"


def bank_name(emisor: str) -> str:
    e = (emisor or "").upper()
    for token, canonical in BANK_RULES:
        if token in e:
            return canonical or ""
    return ""


def instrumento_bancario(row) -> str:
    if bool(row.get("es_derivado", False)):
        return f"Derivados / {row.get('derivado_tipo', 'Otros derivados')}"
    code = row.get("tipo_de_instrumento", "")
    desc = row.get("descripcion", "")
    if code in {"DPF", "CDE", "OVN", "TDP"} or "DEPOSITO" in desc or "DEPÓSITO" in desc:
        return "Depósitos / intermediación bancaria"
    if code in {"BEF", "BSF", "BHM", "TBE", "TBI"} or "BANC" in desc or "BANK" in desc:
        return "Bonos y deuda bancaria"
    if code in {"CC2", "CC3"}:
        return "Caja / cuenta corriente bancaria"
    return "Otros instrumentos bancarios"


def classify(df: pd.DataFrame, dic: pd.DataFrame) -> pd.DataFrame:
    df = df.merge(dic, on="tipo_de_instrumento", how="left")
    is_ext = df["origen"].eq("Extranjero")

    df["clase"] = df["clase_si_nacional"]
    df.loc[is_ext, "clase"] = df.loc[is_ext, "clase_si_extranjero"]
    df["subclase"] = df["subclase_si_nacional"]
    df.loc[is_ext, "subclase"] = df.loc[is_ext, "subclase_si_extranjero"]
    df["bucket_reporte_sp"] = df["bucket_si_nacional"]
    df.loc[is_ext, "bucket_reporte_sp"] = df.loc[is_ext, "bucket_si_extranjero"]

    for c in ["clase", "subclase", "bucket_reporte_sp", "derivado_tipo", "familia_instrumento"]:
        df[c] = df[c].fillna("").replace("", "Sin clasificar")
    for c in ["es_derivado", "es_alternativo"]:
        df[c] = df[c].fillna(False).astype(bool)

    df["bucket_reporte"] = "Caja / Otros"
    df.loc[(df["origen"].eq("Nacional")) & (df["clase"].eq("Renta Variable")) & (df["subclase"].eq("Acciones")), "bucket_reporte"] = "RV Nacional / Acciones"
    df.loc[(df["origen"].eq("Nacional")) & (df["clase"].eq("Renta Variable")) & (~df["subclase"].eq("Acciones")), "bucket_reporte"] = "RV Nacional / Fondos y otros"
    df.loc[(df["origen"].eq("Nacional")) & (df["clase"].eq("Renta Fija")) & (df["subclase"].eq("Instrumentos Estatales")), "bucket_reporte"] = "RF Nacional / Instrumentos estatales"
    df.loc[(df["origen"].eq("Nacional")) & (df["clase"].eq("Renta Fija")) & (df["subclase"].eq("Bonos")), "bucket_reporte"] = "RF Nacional / Bonos"
    df.loc[(df["origen"].eq("Nacional")) & (df["clase"].eq("Renta Fija")) & (df["subclase"].eq("Depósitos")), "bucket_reporte"] = "RF Nacional / Depósitos"
    df.loc[(df["origen"].eq("Nacional")) & (df["clase"].eq("Renta Fija")) & (~df["subclase"].isin(["Instrumentos Estatales", "Bonos", "Depósitos"])), "bucket_reporte"] = "RF Nacional / Otros"
    df.loc[(df["origen"].eq("Extranjero")) & (df["clase"].eq("Renta Variable")) & (df["subclase"].eq("Fondos Mutuos")), "bucket_reporte"] = "RV Extranjera / Fondos mutuos"
    df.loc[(df["origen"].eq("Extranjero")) & (df["clase"].eq("Renta Variable")) & (~df["subclase"].eq("Fondos Mutuos")), "bucket_reporte"] = "RV Extranjera / Otros"
    df.loc[(df["origen"].eq("Extranjero")) & (df["clase"].eq("Renta Fija")), "bucket_reporte"] = "RF Extranjera"
    df.loc[df["es_alternativo"], "bucket_reporte"] = "Alternativos"
    df.loc[df["es_derivado"], "bucket_reporte"] = "Derivados / " + df.loc[df["es_derivado"], "derivado_tipo"].astype(str)

    df["macro_bucket"] = "Caja / Otros"
    df.loc[df["bucket_reporte"].str.startswith("RV Nacional"), "macro_bucket"] = "Renta variable nacional"
    df.loc[df["bucket_reporte"].str.startswith("RV Extranjera"), "macro_bucket"] = "Renta variable extranjera"
    df.loc[df["bucket_reporte"].str.startswith("RF Nacional"), "macro_bucket"] = "Renta fija nacional"
    df.loc[df["bucket_reporte"].str.startswith("RF Extranjera"), "macro_bucket"] = "Renta fija extranjera"
    df.loc[df["bucket_reporte"].eq("Alternativos"), "macro_bucket"] = "Alternativos"
    df.loc[df["bucket_reporte"].str.startswith("Derivados"), "macro_bucket"] = "Derivados"

    df["instrumento_bancario"] = "Otros instrumentos bancarios"
    is_dep = df["tipo_de_instrumento"].isin(["DPF", "CDE", "OVN", "TDP"]) | df["descripcion"].str.contains("DEPOSITO|DEPÓSITO", na=False, regex=True)
    is_deuda_bco = df["tipo_de_instrumento"].isin(["BEF", "BSF", "BHM", "TBE", "TBI"]) | df["descripcion"].str.contains("BANC|BANK", na=False, regex=True)
    is_caja = df["tipo_de_instrumento"].isin(["CC2", "CC3"])
    df.loc[is_dep, "instrumento_bancario"] = "Depósitos / intermediación bancaria"
    df.loc[is_deuda_bco, "instrumento_bancario"] = "Bonos y deuda bancaria"
    df.loc[is_caja, "instrumento_bancario"] = "Caja / cuenta corriente bancaria"
    df.loc[df["es_derivado"], "instrumento_bancario"] = "Derivados / " + df.loc[df["es_derivado"], "derivado_tipo"].astype(str)
    return df


def main(zip_path: Path = RAW_ZIP) -> None:
    if not zip_path.exists():
        raise FileNotFoundError(f"No encontré {zip_path}. Copia chistAFP.zip en data/raw/ o modifica RAW_ZIP.")

    dic = load_dictionary()
    aggregated = []
    bank_aggregated = []
    diagnostics = []

    with zipfile.ZipFile(zip_path) as z:
        files = sorted([n for n in z.namelist() if n.lower().endswith(".csv")])
        for name in files:
            total_rows = 0
            bad_date_rows = 0
            bad_inversion_rows = 0
            kept_rows = 0

            for chunk in pd.read_csv(
                z.open(name), sep=";", usecols=USECOLS, chunksize=250_000, dtype=str,
                encoding="latin-1", on_bad_lines="skip",
            ):
                total_rows += len(chunk)
                chunk["fecha_raw"] = clean_string(chunk["fecha"])
                valid_date = chunk["fecha_raw"].str.match(r"^\d{8}$", na=False)
                bad_date_rows += int((~valid_date).sum())
                chunk = chunk.loc[valid_date].copy()

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
                "filas_leidas": total_rows,
                "filas_fecha_invalida": bad_date_rows,
                "filas_inversion_invalida": bad_inversion_rows,
                "filas_usadas": kept_rows,
            })
            print(f"Procesado {name}: {kept_rows:,} filas usadas")

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
        "version": "v1",
    }
    pd.Series(resumen).to_json(OUT_DIR / "resumen_carga.json", indent=2, force_ascii=False)
    dic.to_csv(DICT_PATH, index=False, encoding="utf-8-sig")
    print("OK: facts v1 generados")
    print(resumen)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, default=RAW_ZIP, help="Ruta al archivo chistAFP.zip")
    args = parser.parse_args()
    main(args.zip)
