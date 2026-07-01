from __future__ import annotations
from pathlib import Path
import pandas as pd

from build_processed_from_zip import load_dictionary, classify

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FACT_PATH = PROJECT_ROOT / "data" / "processed" / "fact_cartera_mensual_agg.csv.gz"
DICT_PATH = PROJECT_ROOT / "data" / "dictionaries" / "diccionario_tipo_instrumento.csv"
OUT_PATH = FACT_PATH


def main() -> None:
    old = pd.read_csv(FACT_PATH, parse_dates=["fecha"])
    # Keep the original v0 classification as SP-like classification before recreating visual buckets.
    old = old.rename(columns={"bucket_reporte": "bucket_reporte_sp_v0", "clase": "clase_v0", "subclase": "subclase_v0"})
    dic = load_dictionary()
    dic.to_csv(DICT_PATH, index=False, encoding="utf-8-sig")
    work = old[["fecha", "afp", "afp_nombre", "tipo_de_fondo", "tipo_de_instrumento", "origen", "inversion_neta_clp", "inversion_abs_clp", "n_registros"]].copy()
    # classify expects raw-ish columns and picks class from dictionary based on origin.
    work = classify(work, dic)
    keep = [
        "fecha", "afp", "afp_nombre", "tipo_de_fondo", "origen", "macro_bucket", "clase", "subclase",
        "bucket_reporte", "bucket_reporte_sp", "familia_instrumento", "derivado_tipo",
        "es_derivado", "es_alternativo", "tipo_de_instrumento", "instrumento_bancario",
        "inversion_neta_clp", "inversion_abs_clp", "n_registros",
    ]
    fact = work[keep].groupby([c for c in keep if c not in {"inversion_neta_clp", "inversion_abs_clp", "n_registros"}], as_index=False, dropna=False).agg(
        inversion_neta_clp=("inversion_neta_clp", "sum"),
        inversion_abs_clp=("inversion_abs_clp", "sum"),
        n_registros=("n_registros", "sum"),
    )
    fact.to_csv(OUT_PATH, index=False, compression="gzip", encoding="utf-8")
    print(f"OK general fact v1: {len(fact):,} filas")

if __name__ == "__main__":
    main()
