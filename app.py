from __future__ import annotations

from pathlib import Path
from html import escape
import json
import os
import re
import subprocess
import sys
import base64
from io import StringIO

import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(
    page_title="CMF - Monitor AFP",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="collapsed",
)

PROJECT_ROOT = Path(__file__).resolve().parent
ASSETS_DIR = PROJECT_ROOT / "assets"
CMF_LOGO_PATH = ASSETS_DIR / "cmf_logo.png"
CMF_BG_PATH = ASSETS_DIR / "cmf_bg.jpg"
RAW_CSV_DIR = PROJECT_ROOT / "data" / "raw" / "chistAFP"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
AGE_BALANCE_DIR = RAW_DIR / "edad_saldo"
FACT_PATH = PROJECT_ROOT / "data" / "processed" / "fact_cartera_mensual_agg.csv.gz"
BANK_FACT_PATH = PROJECT_ROOT / "data" / "processed" / "fact_contrapartes_bancarias_agg.csv.gz"
DICT_PATH = PROJECT_ROOT / "data" / "dictionaries" / "diccionario_tipo_instrumento.csv"
DIAG_PATH = PROJECT_ROOT / "data" / "processed" / "diagnostico_carga.csv"
RESUMEN_PATH = PROJECT_ROOT / "data" / "processed" / "resumen_carga.json"

VALUE_COL = "inversion_neta_clp"

MONTH_ES = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
}

ORIGEN_ORDER = ["Nacional", "Extranjero"]
CLASE_ORDER = ["Renta Variable", "Renta Fija", "Otros Nacionales", "Otros Extranjeros"]
BUCKET_ORDER = [
    "RF Nacional / Instrumentos estatales",
    "RF Nacional / Bonos",
    "RF Nacional / Depósitos",
    "RF Nacional / Otros",
    "RF Extranjera",
    "RV Nacional / Acciones",
    "RV Nacional / Fondos y otros",
    "RV Extranjera / Fondos mutuos",
    "RV Extranjera / Otros",
    "Alternativos",
    "Derivados / Forwards",
    "Derivados / Swaps",
    "Derivados / Opciones",
    "Derivados / Futuros",
    "Caja / Otros",
]
DERIV_ALT_BUCKETS = [
    "Alternativos",
    "Derivados / Forwards",
    "Derivados / Swaps",
    "Derivados / Opciones",
    "Derivados / Futuros",
]


DETAIL_ORDER = [
    "Bancarios",
    "Gobierno / Banco Central / TGR",
    "Corporativos / empresas",
    "Fondos de inversión / fondos mutuos",
    "Acciones / ETF / ADR",
    "Alternativos - capital privado",
    "Alternativos - deuda privada",
    "Alternativos - inmobiliario / infraestructura",
    "Derivados - forwards",
    "Derivados - swaps",
    "Derivados - opciones",
    "Derivados - futuros",
    "Caja / cuentas corrientes",
    "Securitizados / hipotecarios",
    "Otros / revisar",
]

GOV_CODES = {
    "BBC", "BCD", "BCO", "BCP", "BCU", "BCX", "BEC", "BTP", "BTU", "BRP",
    "PCX", "PDC", "PRC", "PRD", "PTG", "CERO", "XERO", "ZERO",
}
BANK_DEBT_CODES = {"BEF", "BSF", "BHM", "LHF", "LTP", "DPF", "CDE", "TBE", "TBI", "TDP"}
CORP_DEBT_CODES = {"DEB", "BEE", "BCE", "BFI", "BVL", "ECO", "ECE", "ELN", "BCA", "BME"}
SECURITIZED_CODES = {"BCS", "BSE", "ECS", "BHM", "LHF", "LTP", "MHE"}
FUND_CODES = {"CFID", "CFIV", "CFMD", "CFMV", "CIED", "CIEV", "CMED", "CMEV", "FICE"}
EQUITY_CODES = {"ACC", "ADR", "AEE", "ADD", "ETFA", "EPA", "SPA", "ASC"}
PRIVATE_EQUITY_CODES = {"ACPE", "KCPE", "CCPE", "VCPE"}
PRIVATE_DEBT_CODES = {"ADPE", "KDPE", "CDPE", "VDPE", "CSIN", "CDCS"}
REAL_ASSET_CODES = {"RAIZ", "CLEA", "CREN"}
CASH_CODES = {"CC2", "CC3", "OVN"}
BANK_INSTR_ORDER = [
    "Derivados / Forwards",
    "Derivados / Swaps",
    "Derivados / Opciones",
    "Bonos y deuda bancaria",
    "Depósitos / intermediación bancaria",
    "Caja / cuenta corriente bancaria",
    "Otros instrumentos bancarios",
]

CHILEAN_BANK_NAMES = {
    "BCI",
    "Banco BICE",
    "Banco Consorcio",
    "Banco Estado",
    "Banco Falabella",
    "Banco Ripley",
    "Banco Security",
    "Banco de Chile",
}


CMF_SEQ = [
    "#8B3DFF",  # morado principal
    "#58C7F3",  # cian
    "#3E7BFA",  # azul vivo
    "#B56CFF",  # morado claro
    "#7AD3F7",  # cian claro
    "#274C9B",  # azul oscuro
    "#F06BFF",  # magenta suave
]

px.defaults.template = "plotly_dark"
px.defaults.color_discrete_sequence = CMF_SEQ


def asset_to_base64(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def get_configured_password() -> str:
    """Obtiene clave desde Streamlit secrets o variable de entorno.

    Para repos públicos NO se debe subir .streamlit/secrets.toml con la clave real.
    En Streamlit Cloud se configura como secret APP_PASSWORD.
    """
    try:
        password = st.secrets.get("APP_PASSWORD", "")
    except Exception:
        password = ""
    if not password:
        password = os.environ.get("APP_PASSWORD", "")
    return str(password or "")


def inject_cmf_styles(login: bool = False) -> None:
    bg_b64 = asset_to_base64(CMF_BG_PATH)
    bg_image = f'url("data:image/jpg;base64,{bg_b64}")' if bg_b64 else "none"

    # En login queremos que card + input + botón queden como una sola composición centrada.
    if login:
        block_container_css = """
        .block-container {
            max-width: 620px !important;
            padding-top: 16vh !important;
            padding-bottom: 2rem !important;
        }
        """
        header_css = """
        header[data-testid=\"stHeader\"] {
            background: rgba(0,0,0,0) !important;
        }
        [data-testid=\"stToolbar\"] {
            display: none !important;
        }
        """
    else:
        block_container_css = """
        .block-container {
            padding-top: 2.0rem !important;
            padding-bottom: 3rem !important;
        }
        """
        header_css = """
        header[data-testid=\"stHeader\"] {
            background: rgba(4,31,95,0.15);
        }
        """

    st.markdown(f"""
    <style>
    :root {{
        --cmf-bg: #041F5F;
        --cmf-bg-soft: #082B74;
        --cmf-panel: #081B45;
        --cmf-panel-2: #0B2253;
        --cmf-border: #24498E;
        --cmf-purple: #8B3DFF;
        --cmf-purple-soft: #B56CFF;
        --cmf-cyan: #58C7F3;
        --cmf-text: #F5F7FA;
        --cmf-muted: #BFC9D9;
    }}

    .stApp {{
        background:
            radial-gradient(circle at 15% 10%, rgba(88,199,243,0.12) 0%, rgba(88,199,243,0.00) 30%),
            radial-gradient(circle at 88% 16%, rgba(139,61,255,0.30) 0%, rgba(139,61,255,0.00) 36%),
            radial-gradient(circle at 55% 95%, rgba(88,199,243,0.08) 0%, rgba(88,199,243,0.00) 32%),
            linear-gradient(135deg, #061B56 0%, #071F63 48%, #25145E 100%),
            {bg_image};
        background-size: cover;
        background-position: center;
        color: var(--cmf-text);
    }}

    {header_css}
    {block_container_css}

    h1, h2, h3, h4, h5, h6 {{
        color: var(--cmf-text) !important;
        letter-spacing: -0.02em;
    }}

    p, span, label, div {{
        color: #E8EEF9;
    }}

    .cmf-hero {{
        background: linear-gradient(110deg, rgba(8,27,69,0.96) 0%, rgba(8,43,116,0.92) 55%, rgba(139,61,255,0.28) 100%);
        border: 1px solid rgba(88,199,243,0.26);
        border-radius: 22px;
        padding: 1.35rem 1.55rem;
        box-shadow: 0 10px 34px rgba(0,0,0,0.22);
        margin-bottom: 1.1rem;
    }}

    .cmf-hero-title {{
        font-size: 2.15rem;
        font-weight: 800;
        color: #FFFFFF;
        margin: 0;
    }}

    .cmf-hero-subtitle {{
        color: #C8D8F0;
        font-size: 0.98rem;
        margin-top: 0.30rem;
    }}

    .cmf-logo-inline {{
        max-height: 54px;
        max-width: 260px;
        object-fit: contain;
        margin-bottom: 0.55rem;
    }}

    .cmf-card {{
        background: rgba(8,27,69,0.88);
        border: 1px solid rgba(36,73,142,0.95);
        border-radius: 16px;
        padding: 1rem 1.15rem;
        box-shadow: 0 8px 24px rgba(0,0,0,0.18);
        margin-bottom: 1rem;
    }}

    .stButton > button,
    .stDownloadButton > button {{
        background: linear-gradient(90deg, #673DFF 0%, #9C44FF 100%) !important;
        color: white !important;
        border: 1px solid rgba(255,255,255,0.14) !important;
        border-radius: 11px !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 14px rgba(139,61,255,0.25);
    }}

    .stButton > button:hover,
    .stDownloadButton > button:hover {{
        border-color: #58C7F3 !important;
        box-shadow: 0 6px 22px rgba(88,199,243,0.24);
        filter: brightness(1.06);
    }}

    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px;
        border-bottom: 1px solid rgba(88,199,243,0.20);
    }}

    .stTabs [data-baseweb="tab"] {{
        background: rgba(8,27,69,0.82);
        border: 1px solid rgba(36,73,142,0.95);
        border-radius: 12px 12px 0 0;
        color: #DDE7F7;
        padding: 10px 16px;
    }}

    .stTabs [aria-selected="true"] {{
        background: linear-gradient(90deg, #5D32D8 0%, #8B3DFF 100%) !important;
        color: #FFFFFF !important;
    }}

    [data-testid="stMetric"] {{
        background: rgba(8,27,69,0.88);
        border: 1px solid rgba(36,73,142,0.95);
        border-radius: 15px;
        padding: 12px 14px;
        box-shadow: 0 6px 20px rgba(0,0,0,0.16);
    }}

    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div {{
        background-color: rgba(8,27,69,0.92) !important;
        border: 1px solid rgba(88,199,243,0.24) !important;
        color: #F5F7FA !important;
        border-radius: 10px !important;
    }}

    input {{
        color: #F5F7FA !important;
    }}

    .stRadio [role="radiogroup"] {{
        background: rgba(8,27,69,0.50);
        border: 1px solid rgba(36,73,142,0.75);
        border-radius: 12px;
        padding: 8px 10px;
    }}

    .streamlit-expanderHeader {{
        background-color: rgba(8,27,69,0.92) !important;
        border: 1px solid rgba(36,73,142,0.95) !important;
        border-radius: 12px !important;
        color: #F5F7FA !important;
    }}

    div[data-testid="stExpander"] {{
        border-color: rgba(36,73,142,0.95) !important;
        background: rgba(4,31,95,0.34) !important;
        border-radius: 14px !important;
    }}

    hr {{
        border: none;
        border-top: 1px solid rgba(88,199,243,0.20);
    }}

    .cmf-login-card {{
        width: min(440px, 92vw);
        margin: 0 auto 1.05rem auto;
        padding: 34px 30px 26px 30px;
        border-radius: 22px;
        background: rgba(12, 18, 42, 0.66);
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(14px);
        border: 1px solid rgba(255,255,255,0.15);
        box-shadow: 0 12px 44px rgba(0,0,0,0.38);
        text-align: center;
    }}

    .cmf-login-title {{
        font-size: 1.78rem;
        font-weight: 800;
        color: #FFFFFF;
        margin-top: 0.55rem;
        margin-bottom: 0.25rem;
    }}

    .cmf-login-subtitle {{
        font-size: 0.92rem;
        color: #C8D8F0;
        margin-bottom: 0.15rem;
    }}

    .cmf-login-logo {{
        max-height: 88px;
        max-width: 290px;
        object-fit: contain;
    }}

    .cmf-login-fallback {{
        width: 58px;
        height: 58px;
        margin: 0 auto 0.5rem auto;
        border-radius: 14px;
        background: linear-gradient(135deg, #8B3DFF 0%, #58C7F3 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-weight: 900;
        font-size: 1.05rem;
    }}

    .cmf-login-helper {{
        text-align: center;
        color: #BFC9D9;
        font-size: 0.80rem;
        margin-top: 0.55rem;
    }}
    </style>
    """, unsafe_allow_html=True)


def render_login() -> None:
    inject_cmf_styles(login=True)
    logo_b64 = asset_to_base64(CMF_LOGO_PATH)
    logo_html = (
        f'<img class="cmf-login-logo" src="data:image/png;base64,{logo_b64}" />'
        if logo_b64 else '<div class="cmf-login-fallback">CMF</div>'
    )

    st.markdown(
        f"""
        <div class="cmf-login-card">
            {logo_html}
            <div class="cmf-login-title">Bienvenido</div>
            <div class="cmf-login-subtitle">Monitor AFP · División de Riesgo Financiero · DR</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    password = st.text_input(
        "Clave de acceso",
        type="password",
        label_visibility="collapsed",
        placeholder="Ingresa tu clave",
        key="login_password",
    )
    if st.button("Ingresar", use_container_width=True):
        if password == get_configured_password():
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Clave incorrecta.")

    st.markdown('<div class="cmf-login-helper">Acceso restringido · Uso interno</div>', unsafe_allow_html=True)


def require_authentication() -> None:
    """Activa login solo si APP_PASSWORD está configurado.

    Para GitHub público: no se incluye la clave en el repo. Configura APP_PASSWORD como secret
    en Streamlit Cloud o en .streamlit/secrets.toml local no versionado.
    """
    configured_password = get_configured_password()
    if not configured_password:
        return
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if not st.session_state["authenticated"]:
        render_login()
        st.stop()


def render_cmf_header() -> None:
    logo_b64 = asset_to_base64(CMF_LOGO_PATH)
    logo_html = f'<img class="cmf-logo-inline" src="data:image/png;base64,{logo_b64}" />' if logo_b64 else ""
    st.markdown(
        f"""
        <div class="cmf-hero">
            {logo_html}
            <div class="cmf-hero-title">División de Riesgo Financiero - DR</div>
            <div class="cmf-hero-subtitle">
                Monitor AFP · Cartera de Fondos de Pensiones · Bases públicas de la Superintendencia de Pensiones.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if get_configured_password():
        col_a, col_b = st.columns([6, 1])
        with col_b:
            if st.button("Cerrar sesión", use_container_width=True):
                st.session_state["authenticated"] = False
                st.rerun()






def get_raw_files() -> list[Path]:
    """Busca cartera_mensual_YYYY.csv o cartera_mensual_YYYY.zip.

    Soporta tanto CSV sueltos como ZIP anuales dentro de data/raw/chistAFP/.
    Como fallback, también busca directamente en data/raw/.
    """
    candidates: list[Path] = []
    patterns = ["cartera_mensual_*.csv", "cartera_mensual_*.zip", "*.csv", "*.zip"]
    if RAW_CSV_DIR.exists():
        for pat in patterns:
            candidates.extend(sorted(RAW_CSV_DIR.glob(pat)))
    if not candidates and RAW_DIR.exists():
        for pat in patterns:
            candidates.extend(sorted(RAW_DIR.glob(pat)))
    # Deduplicar preservando orden
    seen = set()
    out = []
    for f in candidates:
        key = f.resolve()
        if key not in seen and f.is_file():
            seen.add(key)
            out.append(f)
    return out


def raw_max_mtime(files: list[Path]) -> float:
    return max((f.stat().st_mtime for f in files), default=0.0)


def run_processing_from_raw() -> tuple[bool, str]:
    """Regenera las bases procesadas desde data/raw/chistAFP/*.csv o *.zip."""
    script = PROJECT_ROOT / "scripts" / "build_processed_from_csv.py"
    raw_files = get_raw_files()
    if not raw_files:
        return False, (
            "No encontré archivos de cartera. Deja los archivos "
            "cartera_mensual_YYYY.csv o cartera_mensual_YYYY.zip en data/raw/chistAFP/ "
            "o directamente en data/raw/."
        )
    if not script.exists():
        return False, f"No encontré el script de procesamiento: {script}."

    raw_dir = RAW_CSV_DIR if RAW_CSV_DIR.exists() else RAW_DIR
    cmd = [sys.executable, str(script), "--raw-dir", str(raw_dir)]
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    output = "\n".join([proc.stdout or "", proc.stderr or ""]).strip()
    return proc.returncode == 0, output


def ensure_processed_data() -> None:
    """Procesa automáticamente CSVs de data/raw/chistAFP cuando falten facts o el raw sea más reciente."""
    processed_exists = FACT_PATH.exists()
    bank_exists = BANK_FACT_PATH.exists()
    raw_files = get_raw_files()
    raw_exists = bool(raw_files)
    raw_newer_than_fact = (
        raw_exists and processed_exists and raw_max_mtime(raw_files) > FACT_PATH.stat().st_mtime
    )
    needs_processing = (not processed_exists) or (not bank_exists) or raw_newer_than_fact

    if not needs_processing:
        return

    if not raw_exists:
        st.error(
            "No encontré archivos `cartera_mensual_YYYY.csv` o `cartera_mensual_YYYY.zip` y no existen bases procesadas en `data/processed/`. "
            "Copia los CSV o ZIP anuales en `data/raw/chistAFP/` y vuelve a ejecutar `streamlit run app.py`."
        )
        st.stop()

    reason = []
    if not processed_exists:
        reason.append("no existe fact cartera")
    if not bank_exists:
        reason.append("no existe fact bancos")
    if raw_newer_than_fact:
        reason.append("los CSV/ZIP anual raw son más recientes que la fact procesada")
    reason_txt = "; ".join(reason) if reason else "regeneración requerida"

    st.info(f"Procesando automáticamente `{len(raw_files)}` CSV/ZIP anual raw porque {reason_txt}. Puede tardar algunos minutos...")
    with st.spinner("Procesando CSV/ZIP anuales y generando data/processed/..."):
        ok, log = run_processing_from_raw()

    if ok:
        st.cache_data.clear()
        st.success("Data procesada correctamente desde los CSV/ZIP anual raw. Recargando app...")
        st.rerun()

    st.error("Falló el procesamiento automático de los CSV/ZIP anuales.")
    st.code(log[-8000:] if log else "Sin log disponible.")
    st.stop()

def fmt_clp(x: float) -> str:
    if pd.isna(x):
        return "-"
    return f"{x/1e12:,.2f} billones CLP".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_mm_clp_from_clp(x: float, decimals: int = 0) -> str:
    if pd.isna(x):
        return "-"
    return f"{x/1e6:,.{decimals}f} MM$".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_mm_clp(x: float, decimals: int = 0) -> str:
    if pd.isna(x):
        return "-"
    return f"{x:,.{decimals}f} MM$".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_num_chile(x: float, decimals: int = 0) -> str:
    if pd.isna(x):
        return "-"
    return f"{x:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def normalize_display_mode(label: str) -> str:
    if label.startswith("Monto"):
        return "mm"
    if label.startswith("% +"):
        return "both"
    return "pct"


def add_display_amounts(df: pd.DataFrame, value_col: str = VALUE_COL) -> pd.DataFrame:
    out = df.copy()
    if value_col in out.columns:
        out["monto_mm_clp"] = out[value_col] / 1_000_000
    return out


def display_axis(display_mode: str, pct_label: str = "% del total") -> tuple[str, str]:
    mode = normalize_display_mode(display_mode)
    if mode == "mm":
        return "monto_mm_clp", "Monto neto MM$"
    return "pct_pp", pct_label


def add_display_label(df: pd.DataFrame, display_mode: str, value_col: str = VALUE_COL) -> pd.DataFrame:
    out = add_display_amounts(df, value_col)
    mode = normalize_display_mode(display_mode)
    if mode == "mm":
        out["display_label"] = out["monto_mm_clp"].map(lambda x: fmt_num_chile(x, 0))
    elif mode == "both":
        out["display_label"] = out.apply(lambda r: f"{fmt_pct_num(r.get('pct_pp', np.nan), 1)} | {fmt_num_chile(r.get('monto_mm_clp', np.nan), 0)} MM$", axis=1)
    else:
        out["display_label"] = out["pct_pp"].map(lambda x: fmt_pct_num(x, 1))
    return out


def chart_title_suffix(display_mode: str) -> str:
    mode = normalize_display_mode(display_mode)
    if mode == "mm":
        return "MM$ netos"
    if mode == "both":
        return "% y MM$ netos"
    return "%"


def fmt_pct_num(x: float, decimals: int = 1) -> str:
    if pd.isna(x):
        return "-"
    return f"{x:.{decimals}f}%".replace(".", ",")


def fmt_pp(x: float) -> str:
    return fmt_pct_num(x, 1)


def fmt_month_label(date: pd.Timestamp) -> str:
    date = pd.Timestamp(date)
    return f"{MONTH_ES[date.month]}-{str(date.year)[-2:]}"


def normalize_bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().isin(["true", "1", "si", "sí"])


@st.cache_data(show_spinner="Cargando base agregada de cartera...")
def load_fact() -> pd.DataFrame:
    if not FACT_PATH.exists():
        st.error("No encontré `data/processed/fact_cartera_mensual_agg.csv.gz`.")
        st.stop()
    df = pd.read_csv(FACT_PATH, parse_dates=["fecha"])
    for c in ["es_derivado", "es_alternativo"]:
        if c in df.columns:
            df[c] = normalize_bool(df[c])
    return df


@st.cache_data(show_spinner="Cargando base de contrapartes bancarias...")
def load_bank_fact() -> pd.DataFrame:
    if not BANK_FACT_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(BANK_FACT_PATH, parse_dates=["fecha"])
    if "origen_banco" not in df.columns:
        # Fallback para versiones antiguas del fact: en v3 la fuente correcta es `nacionalidad_del_emisor`.
        df["origen_banco"] = np.where(df["banco_nombre"].isin(CHILEAN_BANK_NAMES), "Nacional", "Extranjero")
    df["origen_banco"] = df["origen_banco"].fillna("No clasificado")
    return df


@st.cache_data(show_spinner=False)
def load_dictionary() -> pd.DataFrame:
    if not DICT_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(DICT_PATH, dtype=str).fillna("")
    return df


@st.cache_data(show_spinner=False)
def load_resumen() -> dict:
    if RESUMEN_PATH.exists():
        try:
            return json.loads(RESUMEN_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def add_pct(grouped: pd.DataFrame, value_col: str = VALUE_COL, denom_cols: list[str] | None = None) -> pd.DataFrame:
    denom_cols = denom_cols or []
    if denom_cols:
        totals = grouped.groupby(denom_cols, as_index=False)[value_col].sum().rename(columns={value_col: "total"})
        out = grouped.merge(totals, on=denom_cols, how="left")
    else:
        out = grouped.copy()
        out["total"] = out[value_col].sum()
    out["pct"] = np.where(out["total"].abs() > 0, out[value_col] / out["total"], np.nan)
    out["pct_pp"] = out["pct"] * 100
    out["monto_mm_clp"] = out[value_col] / 1_000_000
    return out


def sort_by_order(df: pd.DataFrame, col: str, order: list[str]) -> pd.DataFrame:
    out = df.copy()
    pos = {v: i for i, v in enumerate(order)}
    out["_orden"] = out[col].map(pos).fillna(999).astype(int)
    return out.sort_values(["_orden", col]).drop(columns="_orden")


def download_button(df: pd.DataFrame, label: str, file_name: str, key: str | None = None) -> None:
    st.download_button(
        label=label,
        data=df.to_csv(index=False, encoding="utf-8-sig"),
        file_name=file_name,
        mime="text/csv",
        key=key,
    )


def source_caption(extra: str = "") -> None:
    base = (
        "Fuente explícita: CSV/ZIP anual raw `data/raw/chistAFP/cartera_mensual_YYYY.csv` o `.zip` de la Base de Cartera de los Fondos de Pensiones SP. "
        "Campos usados: `fecha`, `afp`, `tipo_de_fondo`, `tipo_de_instrumento`, `nombre_del_emisor`, "
        "`nacionalidad_del_emisor` e `inversion`. Cálculo siempre neto: se usa `inversion_neta_clp`."
    )
    st.caption(base + (" " + extra if extra else ""))


SP_TABLE_ROWS = [
    ("Nacional", 0, {"origen": "Nacional"}),
    ("Renta Variable", 1, {"origen": "Nacional", "clase": "Renta Variable"}),
    ("Acciones", 2, {"origen": "Nacional", "clase": "Renta Variable", "subclase": "Acciones"}),
    ("Fondos de inversión y Otros", 2, {"origen": "Nacional", "clase": "Renta Variable", "subclase": "Fondos de inversión y Otros"}),
    ("Renta Fija", 1, {"origen": "Nacional", "clase": "Renta Fija"}),
    ("Instrumentos Estatales", 2, {"origen": "Nacional", "clase": "Renta Fija", "subclase": "Instrumentos Estatales"}),
    ("Bonos", 2, {"origen": "Nacional", "clase": "Renta Fija", "subclase": "Bonos"}),
    ("Depósitos", 2, {"origen": "Nacional", "clase": "Renta Fija", "subclase": "Depósitos"}),
    ("Otros", 2, {"origen": "Nacional", "clase": "Renta Fija", "subclase": "Otros"}),
    ("Otros Nacionales", 1, {"origen": "Nacional", "clase": "Otros Nacionales"}),
    ("Extranjero", 0, {"origen": "Extranjero"}),
    ("Renta Variable", 1, {"origen": "Extranjero", "clase": "Renta Variable"}),
    ("Fondos Mutuos", 2, {"origen": "Extranjero", "clase": "Renta Variable", "subclase": "Fondos Mutuos"}),
    ("Otros", 2, {"origen": "Extranjero", "clase": "Renta Variable", "subclase": "Otros"}),
    ("Renta Fija", 1, {"origen": "Extranjero", "clase": "Renta Fija"}),
    ("Otros Extranjeros", 1, {"origen": "Extranjero", "clase": "Otros Extranjeros"}),
    ("Total", 0, {}),
]


def build_sp_like_table(fact: pd.DataFrame, dates: list[pd.Timestamp], display_mode: str = "%") -> pd.DataFrame:
    data = []
    f = fact[fact["fecha"].isin(dates)].copy()
    totals = f.groupby("fecha")[VALUE_COL].sum().to_dict()
    mode = normalize_display_mode(display_mode)
    for label, level, filters in SP_TABLE_ROWS:
        row = {"Tipo de instrumento": label, "_level": level}
        for d in dates:
            if label == "Total":
                val = totals.get(d, np.nan)
            else:
                mask = f["fecha"].eq(d)
                for col, val_filter in filters.items():
                    mask &= f[col].eq(val_filter)
                val = f.loc[mask, VALUE_COL].sum()
            total = totals.get(d, np.nan)
            pct = val / total * 100 if pd.notna(total) and abs(total) > 0 else np.nan
            if mode == "mm":
                cell = fmt_num_chile(val / 1_000_000, 0)
            elif mode == "both":
                cell = f"{fmt_pct_num(pct, 1)} | {fmt_num_chile(val / 1_000_000, 0)}"
            else:
                cell = fmt_pct_num(pct, 1)
            row[fmt_month_label(d)] = cell
        data.append(row)
    return pd.DataFrame(data)


def build_sp_like_table_numeric(fact: pd.DataFrame, dates: list[pd.Timestamp]) -> pd.DataFrame:
    data = []
    f = fact[fact["fecha"].isin(dates)].copy()
    totals = f.groupby("fecha")[VALUE_COL].sum().to_dict()
    for label, level, filters in SP_TABLE_ROWS:
        row = {"Tipo de instrumento": label, "nivel": level}
        for d in dates:
            prefix = pd.Timestamp(d).strftime("%Y-%m-%d")
            if label == "Total":
                val = totals.get(d, np.nan)
            else:
                mask = f["fecha"].eq(d)
                for col, val_filter in filters.items():
                    mask &= f[col].eq(val_filter)
                val = f.loc[mask, VALUE_COL].sum()
            total = totals.get(d, np.nan)
            row[f"{prefix}_pct"] = val / total * 100 if pd.notna(total) and abs(total) > 0 else np.nan
            row[f"{prefix}_MM_CLP"] = val / 1_000_000 if pd.notna(val) else np.nan
            row[f"{prefix}_CLP"] = val
        data.append(row)
    return pd.DataFrame(data)


def render_sp_table(table: pd.DataFrame) -> None:
    """Renderiza la tabla tipo SP con contraste para modo oscuro CMF."""
    html = [
        "<style>",
        ".sp-table-wrap {overflow-x: auto; overflow-y: hidden; width: 100%; border: 1px solid rgba(88,199,243,0.25); border-radius: 12px; background: #061946; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02);}",
        ".sp-table {border-collapse: collapse; width: max-content; min-width: 100%; font-size: 0.95rem; color: #F5F7FA;}",
        ".sp-table th {background: linear-gradient(90deg, #0D3F8A 0%, #133C8B 62%, #6F2DFF 100%); color: #FFFFFF; padding: 9px 10px; border: 1px solid rgba(88,199,243,0.20); text-align: right; font-weight: 800;}",
        ".sp-table th:first-child {text-align: left;}",
        ".sp-table td {padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,0.08); border-right: 1px solid rgba(255,255,255,0.06); text-align: right; background: #081B45; color: #F5F7FA;}",
        ".sp-table tr:nth-child(even) td {background: #0B2253;}",
        ".sp-table td:first-child {text-align: left; color: #F5F7FA;}",
        ".sp-table th:first-child, .sp-table td:first-child {position: sticky; left: 0; z-index: 1; min-width: 240px; box-shadow: 8px 0 12px rgba(0,0,0,0.18);}",
        ".sp-table td:first-child {background: #081B45;}",
        ".sp-table tr:nth-child(even) td:first-child {background: #0B2253;}",
        ".sp-table th:first-child {background: linear-gradient(90deg, #0D3F8A 0%, #133C8B 100%); z-index: 2;}",
        ".sp-row-l0 td {font-weight: 900; border-top: 1.5px solid rgba(88,199,243,0.35); color: #FFFFFF;}",
        ".sp-row-l1 td:first-child {font-weight: 800; padding-left: 26px; color: #EAF2FF;}",
        ".sp-row-l2 td:first-child {padding-left: 48px; color: #BFD2F2;}",
        ".sp-row-total td {font-weight: 900; background: linear-gradient(90deg, #112B67 0%, #1A3473 100%) !important; color: #FFFFFF; border-top: 2px solid rgba(181,108,255,0.70); border-bottom: 2px solid rgba(181,108,255,0.70);}",
        "</style>",
        "<div class='sp-table-wrap'><table class='sp-table'>",
        "<thead><tr>",
    ]
    visible_cols = [c for c in table.columns if c != "_level"]
    for col in visible_cols:
        html.append(f"<th>{escape(str(col))}</th>")
    html.append("</tr></thead><tbody>")
    for _, row in table.iterrows():
        level = int(row["_level"])
        label = row["Tipo de instrumento"]
        cls = f"sp-row-l{level}"
        if label == "Total":
            cls += " sp-row-total"
        html.append(f"<tr class='{cls}'>")
        for col in visible_cols:
            html.append(f"<td>{escape(str(row[col]))}</td>")
        html.append("</tr>")
    html.append("</tbody></table></div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def apply_cmf_layout(fig, height: int | None = None):
    fig.update_layout(
        paper_bgcolor="#041F5F",
        plot_bgcolor="#081B45",
        font=dict(color="#F5F7FA"),
        title_font=dict(color="#F5F7FA", size=19),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#F5F7FA")),
        xaxis=dict(gridcolor="rgba(255,255,255,0.08)", zeroline=False, color="#F5F7FA"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.08)", zeroline=False, color="#F5F7FA"),
    )
    if height is not None:
        fig.update_layout(height=height)
    return fig

def horizontal_bar(df: pd.DataFrame, y_col: str, title: str, height: int = 520, display_mode: str = "%"):
    plot = add_display_label(df, display_mode, VALUE_COL)
    x_col, x_label = display_axis(display_mode, "% del total")
    fig = px.bar(
        plot.sort_values(x_col, ascending=True),
        x=x_col,
        y=y_col,
        orientation="h",
        text="display_label",
        hover_data={"pct_pp": ":.2f", "monto_mm_clp": ":,.0f", VALUE_COL: ":,.0f", "display_label": False},
        title=f"{title} ({chart_title_suffix(display_mode)})",
        labels={x_col: x_label, y_col: "", "monto_mm_clp": "MM$", "pct_pp": "%"},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(height=height, xaxis_title=x_label, yaxis_title="", margin=dict(l=10, r=80, t=70, b=30))
    apply_cmf_layout(fig, height=height)
    return fig


def line_evolution(df: pd.DataFrame, group_col: str, title: str, denom_cols: list[str] | None = None, display_mode: str = "%"):
    denom_cols = denom_cols or ["fecha"]
    g = df.groupby(["fecha", group_col], as_index=False).agg(**{VALUE_COL: (VALUE_COL, "sum")})
    g = add_pct(g, VALUE_COL, denom_cols)
    y_col, y_label = display_axis(display_mode, "% del total")
    fig = px.line(
        g,
        x="fecha",
        y=y_col,
        color=group_col,
        title=f"{title} ({chart_title_suffix(display_mode)})",
        labels={"fecha": "Fecha", y_col: y_label, group_col: "Serie", "monto_mm_clp": "MM$", "pct_pp": "%"},
        hover_data={"pct_pp": ":.2f", "monto_mm_clp": ":,.0f"},
    )
    fig.update_layout(height=620, yaxis_title=y_label)
    apply_cmf_layout(fig, height=620)
    return g, fig


def chart_origin(base_date: pd.DataFrame, selected_date: pd.Timestamp, display_mode: str = "%"):
    g = base_date.groupby("origen", as_index=False).agg(**{VALUE_COL: (VALUE_COL, "sum")})
    g = add_pct(g)
    g = sort_by_order(g, "origen", ORIGEN_ORDER)
    return g, horizontal_bar(g, "origen", f"Nivel 1: Nacional vs extranjero - {selected_date:%Y-%m-%d}", height=390, display_mode=display_mode)


def chart_class_by_origin(base_date: pd.DataFrame, origen: str, selected_date: pd.Timestamp, display_mode: str = "%"):
    d = base_date[base_date["origen"].eq(origen)]
    g = d.groupby("clase", as_index=False).agg(**{VALUE_COL: (VALUE_COL, "sum")})
    g = add_pct(g)
    g = sort_by_order(g, "clase", CLASE_ORDER)
    return g, horizontal_bar(g, "clase", f"Nivel 2: {origen} abierto por clase - {selected_date:%Y-%m-%d}", height=430, display_mode=display_mode)


def chart_bucket(base_date: pd.DataFrame, selected_date: pd.Timestamp, display_mode: str = "%"):
    g = base_date.groupby("bucket_reporte", as_index=False).agg(**{VALUE_COL: (VALUE_COL, "sum")})
    g = add_pct(g)
    g = sort_by_order(g, "bucket_reporte", BUCKET_ORDER)
    return g, horizontal_bar(g, "bucket_reporte", f"Nivel 3: buckets ampliados - {selected_date:%Y-%m-%d}", height=660, display_mode=display_mode)


def apertura_cartera_row(row) -> str:
    """Clasificación visual adicional para abrir buckets sin perder legibilidad.

    Fuente: campo `tipo_de_instrumento` y bucket del diccionario editable. Es una capa analítica,
    no un campo oficial SP; debe validarse con el diccionario si se usa para informes formales.
    """
    code = str(row.get("tipo_de_instrumento", "")).upper().strip()
    bucket = str(row.get("bucket_reporte", ""))
    inst_bancario = str(row.get("instrumento_bancario", ""))
    derivado_tipo = str(row.get("derivado_tipo", ""))

    if bucket.startswith("Derivados") or derivado_tipo in {"Forwards", "Swaps", "Opciones", "Futuros"}:
        if "Forward" in bucket or derivado_tipo == "Forwards":
            return "Derivados - forwards"
        if "Swap" in bucket or derivado_tipo == "Swaps":
            return "Derivados - swaps"
        if "Opcion" in bucket or "Opc" in bucket or derivado_tipo == "Opciones":
            return "Derivados - opciones"
        if "Futuro" in bucket or derivado_tipo == "Futuros":
            return "Derivados - futuros"
        return "Otros / revisar"

    if bucket == "Alternativos":
        if code in PRIVATE_EQUITY_CODES:
            return "Alternativos - capital privado"
        if code in PRIVATE_DEBT_CODES:
            return "Alternativos - deuda privada"
        if code in REAL_ASSET_CODES:
            return "Alternativos - inmobiliario / infraestructura"
        return "Alternativos - capital privado"

    if code in BANK_DEBT_CODES or "bancaria" in inst_bancario.lower():
        return "Bancarios"
    if code in GOV_CODES:
        return "Gobierno / Banco Central / TGR"
    if code in CORP_DEBT_CODES:
        return "Corporativos / empresas"
    if code in SECURITIZED_CODES:
        return "Securitizados / hipotecarios"
    if code in FUND_CODES:
        return "Fondos de inversión / fondos mutuos"
    if code in EQUITY_CODES:
        return "Acciones / ETF / ADR"
    if code in CASH_CODES or "Caja" in bucket:
        return "Caja / cuentas corrientes"
    return "Otros / revisar"


def enrich_with_detail(df: pd.DataFrame, diccionario: pd.DataFrame | None = None) -> pd.DataFrame:
    out = df.copy()
    out["detalle_minimo"] = out.apply(apertura_cartera_row, axis=1)
    if diccionario is not None and not diccionario.empty and "tipo_de_instrumento" in out.columns:
        cols = [c for c in ["tipo_de_instrumento", "descripcion", "comentario", "revisar_diccionario"] if c in diccionario.columns]
        dd = diccionario[cols].drop_duplicates("tipo_de_instrumento").copy()
        out = out.merge(dd, on="tipo_de_instrumento", how="left")
    return out


def build_detail_summary(df: pd.DataFrame, group_cols: list[str], denom_cols: list[str] | None = None) -> pd.DataFrame:
    g = df.groupby(group_cols, dropna=False, as_index=False).agg(**{VALUE_COL: (VALUE_COL, "sum")})
    g = add_pct(g, VALUE_COL, denom_cols or [])
    g = sort_by_order(g, group_cols[-1], DETAIL_ORDER if group_cols[-1] == "detalle_minimo" else []) if group_cols[-1] == "detalle_minimo" else g.sort_values(VALUE_COL, ascending=False)
    return g


def render_detail_table(df: pd.DataFrame, display_mode: str, max_rows: int = 80) -> None:
    mode = normalize_display_mode(display_mode)
    cols = [c for c in ["bucket_reporte", "detalle_minimo", "tipo_de_instrumento", "descripcion", "monto_mm_clp", "pct_pp", VALUE_COL] if c in df.columns]
    show = df[cols].copy().head(max_rows)
    if "monto_mm_clp" in show.columns:
        show["MM$"] = show["monto_mm_clp"].map(lambda x: fmt_num_chile(x, 0))
    if "pct_pp" in show.columns:
        show["%"] = show["pct_pp"].map(lambda x: fmt_pct_num(x, 2))
    order = [c for c in ["bucket_reporte", "detalle_minimo", "tipo_de_instrumento", "descripcion", "%", "MM$"] if c in show.columns]
    st.dataframe(show[order], hide_index=True, use_container_width=True, height=min(520, 70 + 34 * min(len(show), 12)))


def build_aum_from_cartera(fact_df: pd.DataFrame) -> pd.DataFrame:
    """Calcula AUM por fondo desde la fact histórica derivada de los CSV/ZIP anual raw.

    Fuente original: archivos `data/raw/chistAFP/cartera_mensual_YYYY.csv` o `.zip`.
    Campo base: `inversion`, procesado como `inversion_neta_clp`.
    Unidad salida: MM$.
    """
    required = {"fecha", "tipo_de_fondo", VALUE_COL}
    missing = required.difference(fact_df.columns)
    if missing:
        st.warning(f"No pude calcular AUM desde cartera. Faltan columnas: {sorted(missing)}")
        return pd.DataFrame(columns=["fecha", "fondo", "AUM_MM_CLP"])

    out = (
        fact_df.dropna(subset=["fecha", "tipo_de_fondo"])
        .assign(
            fecha=lambda x: pd.to_datetime(x["fecha"], errors="coerce"),
            fondo=lambda x: x["tipo_de_fondo"].astype(str).str.strip().str.upper(),
        )
        .query("fondo in ['A', 'B', 'C', 'D', 'E']")
        .groupby(["fecha", "fondo"], as_index=False)[VALUE_COL]
        .sum()
        .rename(columns={VALUE_COL: "AUM_CLP"})
    )
    out["AUM_MM_CLP"] = out["AUM_CLP"] / 1_000_000
    out = out[["fecha", "fondo", "AUM_MM_CLP"]]
    return out.sort_values(["fecha", "fondo"])


def aum_source_caption(extra: str = "") -> None:
    st.caption(
        "Fuente explícita AUM: CSV/ZIP anual raw `data/raw/chistAFP/cartera_mensual_YYYY.csv` o `.zip`, "
        "procesados en `data/processed/fact_cartera_mensual_agg.csv.gz`. "
        "Columnas usadas: `fecha`, `tipo_de_fondo` e `inversion_neta_clp`. "
        "Cálculo: AUM_MM_CLP = suma(inversion_neta_clp) / 1.000.000 por fecha y fondo. "
        "No se usa Excel externo." + (" " + extra if extra else "")
    )


def chart_aum_by_fund(aum_date: pd.DataFrame, selected_aum_date: pd.Timestamp, display_mode: str = "%"):
    df = aum_date.copy()
    df["Participacion"] = df["AUM_MM_CLP"] / df["AUM_MM_CLP"].sum()
    df["Participacion_pp"] = df["Participacion"] * 100
    mode = normalize_display_mode(display_mode)
    if mode == "pct":
        y_col = "Participacion_pp"
        y_label = "% del total"
        text_col = "Label"
        df[text_col] = df["Participacion_pp"].map(lambda x: fmt_pct_num(x, 1))
    elif mode == "both":
        y_col = "AUM_MM_CLP"
        y_label = "AUM MM$"
        text_col = "Label"
        df[text_col] = df.apply(lambda r: f"{fmt_num_chile(r['AUM_MM_CLP'], 0)} | {fmt_pct_num(r['Participacion_pp'], 1)}", axis=1)
    else:
        y_col = "AUM_MM_CLP"
        y_label = "AUM MM$"
        text_col = "Label"
        df[text_col] = df["AUM_MM_CLP"].map(lambda x: fmt_num_chile(x, 0))
    df["AUM_Label"] = df["AUM_MM_CLP"].map(lambda x: fmt_num_chile(x, 0))
    df["Participacion_Label"] = df["Participacion_pp"].map(lambda x: fmt_pct_num(x, 1))
    fig = px.bar(
        df.sort_values("fondo"),
        x="fondo",
        y=y_col,
        text=text_col,
        custom_data=["AUM_Label", "Participacion_Label"],
        title=f"AUM por fondo desde cartera - {selected_aum_date:%Y-%m-%d} ({chart_title_suffix(display_mode)})",
        labels={"fondo": "Fondo", y_col: y_label},
    )
    fig.update_traces(
        textposition="outside",
        hovertemplate="<b>Fondo %{x}</b><br>AUM: %{customdata[0]} MM$<br>Participación: %{customdata[1]}<extra></extra>",
    )
    fig.update_xaxes(categoryorder="array", categoryarray=["A", "B", "C", "D", "E"])
    fig.update_layout(height=560, yaxis_title=y_label, xaxis_title="Fondo", showlegend=False)
    return df, fig




def chart_aum_evolution_by_fund(aum_period: pd.DataFrame, display_mode: str = "%"):
    """Evolutivo de AUM por fondo desde cartera procesada.

    Usa como fuente la fact derivada de los CSV/ZIP anuales cargados en data/raw/chistAFP/.
    """
    df = aum_period.copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha", "fondo", "AUM_MM_CLP"])
    df = df.sort_values(["fecha", "fondo"])

    total_fecha = df.groupby("fecha", as_index=False)["AUM_MM_CLP"].sum().rename(columns={"AUM_MM_CLP": "AUM_TOTAL_MM_CLP"})
    df = df.merge(total_fecha, on="fecha", how="left")
    df["Participacion"] = np.where(df["AUM_TOTAL_MM_CLP"].ne(0), df["AUM_MM_CLP"] / df["AUM_TOTAL_MM_CLP"], np.nan)
    df["Participacion_pp"] = df["Participacion"] * 100
    df["AUM_Label"] = df["AUM_MM_CLP"].map(lambda x: fmt_num_chile(x, 0))
    df["Participacion_Label"] = df["Participacion_pp"].map(lambda x: fmt_pct_num(x, 1))

    mode = normalize_display_mode(display_mode)
    if mode == "pct":
        y_col = "Participacion_pp"
        y_label = "% del total por fecha"
    else:
        y_col = "AUM_MM_CLP"
        y_label = "AUM MM$"

    fig = px.line(
        df,
        x="fecha",
        y=y_col,
        color="fondo",
        markers=False,
        title=f"Evolución AUM por fondo ({chart_title_suffix(display_mode)})",
        labels={"fecha": "Fecha", "fondo": "Fondo", y_col: y_label},
        custom_data=["AUM_Label", "Participacion_Label"],
        category_orders={"fondo": ["A", "B", "C", "D", "E"]},
    )
    fig.update_traces(
        hovertemplate=(
            "<b>Fondo %{legendgroup}</b><br>"
            "Fecha: %{x|%Y-%m-%d}<br>"
            "AUM: %{customdata[0]} MM$<br>"
            "Participación: %{customdata[1]}<extra></extra>"
        )
    )
    fig.update_layout(height=620, yaxis_title=y_label, xaxis_title="Fecha", legend_title="Fondo")
    return df, fig

def periodo_trimestral_sp(fecha: pd.Timestamp) -> tuple[str, str]:
    """Convierte una fecha al cuadro trimestral SP más cercano hacia atrás.

    La ruta usada en el script original apunta a `aficot/trimestral/{anio}/{mes}/09A.html`,
    por lo que si la fecha de cartera no es trimestral se usa el último trimestre disponible hacia atrás.
    """
    fecha = pd.Timestamp(fecha)
    if fecha.month >= 12:
        return str(fecha.year), "12"
    if fecha.month >= 9:
        return str(fecha.year), "09"
    if fecha.month >= 6:
        return str(fecha.year), "06"
    if fecha.month >= 3:
        return str(fecha.year), "03"
    return str(fecha.year - 1), "12"


@st.cache_data(show_spinner="Consultando cuadro SP de saldo CCI y edad...")
def fetch_age_balance_table(anio: str, mes: str) -> pd.DataFrame:
    """Lee el cuadro SP de edad/saldo.

    Orden de búsqueda:
    1) caché local opcional en data/raw/edad_saldo/edad_saldo_YYYY_MM.csv/html
    2) consulta directa a la SP

    En Streamlit Cloud la SP puede responder 403 Forbidden. En ese caso el dashboard no cae;
    se informa que el cuadro debe cachearse localmente si se quiere mostrar este gráfico.
    """
    AGE_BALANCE_DIR.mkdir(parents=True, exist_ok=True)
    candidates = [
        AGE_BALANCE_DIR / f"edad_saldo_{anio}_{mes}.csv",
        AGE_BALANCE_DIR / f"edad_saldo_{anio}_{mes}.html",
        AGE_BALANCE_DIR / f"09A_{anio}_{mes}.html",
        AGE_BALANCE_DIR / f"09A.html",
    ]
    for local_path in candidates:
        if local_path.exists() and local_path.stat().st_size > 0:
            if local_path.suffix.lower() == ".csv":
                return pd.read_csv(local_path)
            tables = pd.read_html(str(local_path), thousands=".", decimal=",")
            if tables:
                return max(tables, key=lambda x: x.shape[0] * x.shape[1])

    url_indice = (
        "https://www.spensiones.cl/apps/centroEstadisticas/"
        "paginaCuadrosCCEE.php?menu=sci&menuN1=afil&menuN2=sdomovcci"
    )
    url_cuadro_8 = (
        "https://www.spensiones.cl/apps/loadEstadisticas/"
        f"genEstadAfiliadosCotizantes.php?"
        f"id=inf_estadistica/aficot/trimestral/{anio}/{mes}/09A.html"
        f"&p=T&menu=sci&menuN1=afil&menuN2=sdomovcci&orden=80&ext=.html"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
        "Referer": url_indice,
    }
    session = requests.Session()
    session.headers.update(headers)

    # Primero intentamos directo el cuadro: en algunos entornos el índice responde 403.
    errors = []
    for url in [url_cuadro_8, url_indice]:
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 403:
                raise PermissionError(f"403 Forbidden al consultar {url}")
            r.raise_for_status()
            tables = pd.read_html(StringIO(r.text), thousands=".", decimal=",")
            if tables:
                return max(tables, key=lambda x: x.shape[0] * x.shape[1])
        except Exception as exc:
            errors.append(str(exc))

    raise RuntimeError(
        "No fue posible leer el cuadro SP de edad/saldo. "
        "En Streamlit Cloud la SP puede bloquear la consulta remota con 403. "
        "Solución: guardar el cuadro como data/raw/edad_saldo/edad_saldo_YYYY_MM.html o .csv. "
        f"Detalle: {' | '.join(errors[-2:])}"
    )


def limpiar_numero_chileno(x):
    x = str(x).replace(".", "").replace(",", ".")
    nums = re.findall(r"\d+\.?\d*", x)
    return [float(n) for n in nums]


def saldo_medio_desde_tramo(texto):
    nums = limpiar_numero_chileno(texto)
    if len(nums) >= 2:
        return (nums[0] + nums[1]) / 2
    if len(nums) == 1:
        return nums[0]
    return None


def edad_representativa(texto):
    nums = limpiar_numero_chileno(texto)
    if len(nums) >= 2:
        return sum(nums[:2]) / 2
    if len(nums) == 1:
        return nums[0]
    return None


def build_age_aum_adjusted(df_sp_raw: pd.DataFrame, total_aum_oficial_mm: float) -> pd.DataFrame:
    df_sp = df_sp_raw.copy()
    if isinstance(df_sp.columns, pd.MultiIndex):
        df_sp.columns = [" ".join([str(x) for x in col if str(x) != "nan"]).strip() for col in df_sp.columns]
    df_sp.columns = [str(c).strip() for c in df_sp.columns]
    col_saldo = df_sp.columns[0]
    df_sp = df_sp.dropna(subset=[col_saldo])
    df_sp = df_sp[~df_sp[col_saldo].astype(str).str.upper().str.contains("TOTAL")]
    cols_edad = [c for c in df_sp.columns[1:] if "TOTAL" not in str(c).upper()]
    df_long = df_sp.melt(id_vars=[col_saldo], value_vars=cols_edad, var_name="edad_original", value_name="n_afiliados")
    df_long["n_afiliados"] = (
        df_long["n_afiliados"].astype(str)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    df_long["n_afiliados"] = pd.to_numeric(df_long["n_afiliados"], errors="coerce")
    df_long = df_long.dropna(subset=["n_afiliados"])
    df_long["saldo_medio_clp"] = df_long[col_saldo].apply(saldo_medio_desde_tramo)
    df_long["edad_num"] = df_long["edad_original"].apply(edad_representativa)
    df_long = df_long.dropna(subset=["saldo_medio_clp", "edad_num"])
    df_long["AUM_MM_CLP_ESTIMADO"] = df_long["n_afiliados"] * df_long["saldo_medio_clp"] / 1_000_000

    bins = [0, 25, 30, 35, 40, 45, 50, 55, 60, 65, 200]
    labels = ["0-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59", "60-64", "65+"]
    df_long["grupo_etario"] = pd.cut(df_long["edad_num"], bins=bins, labels=labels, right=False)
    df_grafico = df_long.groupby("grupo_etario", observed=False, as_index=False)["AUM_MM_CLP_ESTIMADO"].sum()
    total_estimado = df_grafico["AUM_MM_CLP_ESTIMADO"].sum()
    df_grafico["Participacion_Edad"] = np.where(total_estimado > 0, df_grafico["AUM_MM_CLP_ESTIMADO"] / total_estimado, np.nan)
    df_grafico["AUM_MM_CLP_AJUSTADO"] = df_grafico["Participacion_Edad"] * float(total_aum_oficial_mm)
    return df_grafico


def chart_aum_by_age(df_age: pd.DataFrame, selected_aum_date: pd.Timestamp, display_mode: str = "%"):
    df = df_age.copy()
    df["Participacion_pp"] = df["Participacion_Edad"] * 100
    mode = normalize_display_mode(display_mode)
    if mode == "pct":
        y_col = "Participacion_pp"
        y_label = "% del total"
        text_col = "Label"
        df[text_col] = df["Participacion_pp"].map(lambda x: fmt_pct_num(x, 1))
    elif mode == "both":
        y_col = "AUM_MM_CLP_AJUSTADO"
        y_label = "AUM ajustado MM$"
        text_col = "Label"
        df[text_col] = df.apply(lambda r: f"{fmt_num_chile(r['AUM_MM_CLP_AJUSTADO'], 0)} | {fmt_pct_num(r['Participacion_pp'], 1)}", axis=1)
    else:
        y_col = "AUM_MM_CLP_AJUSTADO"
        y_label = "AUM ajustado MM$"
        text_col = "Label"
        df[text_col] = df["AUM_MM_CLP_AJUSTADO"].map(lambda x: fmt_num_chile(x, 0))
    df["AUM_Label"] = df["AUM_MM_CLP_AJUSTADO"].map(lambda x: fmt_num_chile(x, 0))
    df["Participacion_Label"] = df["Participacion_pp"].map(lambda x: fmt_pct_num(x, 1))
    fig = px.bar(
        df,
        x="grupo_etario",
        y=y_col,
        text=text_col,
        custom_data=["Participacion_Label", "AUM_Label", "AUM_MM_CLP_ESTIMADO"],
        title=f"AUM por grupo etario ajustado al total de cartera - {selected_aum_date:%Y-%m-%d} ({chart_title_suffix(display_mode)})",
        labels={"grupo_etario": "Grupo etario", y_col: y_label},
    )
    fig.update_traces(
        textposition="outside",
        hovertemplate=(
            "<b>%{x}</b><br>"
            "AUM ajustado: %{customdata[1]} MM$<br>"
            "Participación: %{customdata[0]}<br>"
            "AUM estimado previo ajuste: %{customdata[2]:,.0f} MM$<extra></extra>"
        ),
    )
    fig.update_layout(height=560, yaxis_title=y_label, xaxis_title="Grupo etario", showlegend=False)
    return df, fig



inject_cmf_styles(login=False)
require_authentication()
render_cmf_header()
st.caption("Versión 14 · Fuente raw `data/raw/chistAFP/cartera_mensual_YYYY.zip` o `.csv`; la data se procesa automáticamente hacia `data/processed/`, sin Excel externo.")

ensure_processed_data()

fact = load_fact()
bank_fact = load_bank_fact()
dic = load_dictionary()
resumen = load_resumen()

available_dates = pd.to_datetime(sorted(fact["fecha"].drop_duplicates()))

c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
with c1:
    selected_date = st.selectbox(
        "Fecha de corte",
        options=available_dates,
        index=len(available_dates) - 1,
        format_func=lambda x: pd.Timestamp(x).strftime("%Y-%m-%d"),
    )
with c2:
    start_date = st.selectbox(
        "Fecha inicio evolutivos",
        options=available_dates,
        index=0,
        format_func=lambda x: pd.Timestamp(x).strftime("%Y-%m-%d"),
    )
with c3:
    end_date = st.selectbox(
        "Fecha fin evolutivos",
        options=available_dates,
        index=len(available_dates) - 1,
        format_func=lambda x: pd.Timestamp(x).strftime("%Y-%m-%d"),
    )
with c4:
    display_mode = st.radio(
        "Ver valores",
        ["Porcentaje (%)", "Monto (MM$)", "% + MM$"],
        index=0,
        horizontal=False,
        help="Cambia la visualización de gráficos y la tabla tipo SP. Las descargas incluyen porcentajes y montos.",
    )

selected_date = pd.Timestamp(selected_date)
start_date = pd.Timestamp(start_date)
end_date = pd.Timestamp(end_date)
if start_date > end_date:
    st.warning("La fecha de inicio es posterior a la fecha de fin; se invirtió el rango para los evolutivos.")
    start_date, end_date = end_date, start_date

period = fact[(fact["fecha"].ge(start_date)) & (fact["fecha"].le(end_date))].copy()
base_date = fact[fact["fecha"].eq(selected_date)].copy()
if base_date.empty:
    st.warning("No hay datos para la fecha seleccionada.")
    st.stop()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Fecha corte", selected_date.strftime("%Y-%m-%d"))
k2.metric("Patrimonio neto sistema", fmt_clp(base_date[VALUE_COL].sum()))
k3.metric("Rango evolutivo", f"{start_date:%Y-%m-%d} / {end_date:%Y-%m-%d}")
k4.metric("Fechas mensuales", f"{period['fecha'].nunique():,}".replace(",", "."))

with st.expander("Descargas generales", expanded=False):
    d1, d2, d3 = st.columns(3)
    with d1:
        download_button(period, "Descargar cartera neta del rango", "cartera_sistema_periodo_v16.csv", key="dl_period")
    with d2:
        if len(bank_fact):
            bank_period = bank_fact[(bank_fact["fecha"].ge(start_date)) & (bank_fact["fecha"].le(end_date))]
            download_button(bank_period, "Descargar contrapartes bancarias del rango", "contrapartes_bancarias_periodo_v16.csv", key="dl_bank_period")
    with d3:
        if len(dic):
            download_button(dic, "Descargar diccionario de instrumentos", "diccionario_tipo_instrumento_v16.csv", key="dl_dic")

st.divider()

tab_sistema, tab_apertura, tab_fondos, tab_deriv_alt, tab_bancos, tab_aum = st.tabs(
    [
        "1. Sistema total",
        "2. Apertura de cartera",
        "3. Fondos A-E",
        "4. Alternativos y derivados",
        "5. Contrapartes bancarias",
        "6. AUM por fondo",
    ]
)

with tab_sistema:
    st.subheader("Sistema total: composición de la inversión")
    source_caption("La tabla tipo SP usa todas las fechas del rango global seleccionado y se puede recorrer con barra horizontal.")

    table_dates = [d for d in available_dates if pd.Timestamp(d) >= start_date and pd.Timestamp(d) <= end_date]
    if not table_dates:
        table_dates = [selected_date]
    table = build_sp_like_table(fact, table_dates, display_mode)
    table_download = build_sp_like_table_numeric(fact, table_dates)
    st.markdown("#### Tabla tipo SP: cartera total de los Fondos de Pensiones")
    st.caption(f"Meses visibles: {len(table_dates):,}. Usa la barra horizontal inferior para revisar toda la historia del rango seleccionado.".replace(",", "."))
    render_sp_table(table)
    download_button(table_download, "Descargar tabla tipo SP completa", "tabla_sp_sistema_total_v16.csv", key="dl_tabla_sp_sistema")
    st.caption(
        "Nota: Fondos de inversión y Otros (RV) incluye activos alternativos cuando el diccionario los clasifica dentro de esa familia. "
        "Otros Nacionales y Otros Extranjeros incluyen derivados y otros instrumentos."
    )

    st.markdown("#### Composición porcentual para la fecha seleccionada")
    st.caption("Los siguientes gráficos abren la misma cartera en tres niveles: origen, clase y bucket ampliado.")

    with st.expander("Nivel 1 · Nacional vs extranjero", expanded=True):
        origen_data, fig_origen = chart_origin(base_date, selected_date, display_mode)
        st.plotly_chart(fig_origen, use_container_width=True)
        download_button(origen_data, "Descargar data nivel 1", "sistema_nivel_1_origen_v16.csv", key="dl_origen")

    with st.expander("Nivel 2 · Abrir Nacional y Extranjero por clase", expanded=True):
        coln, cole = st.columns(2)
        with coln:
            nacional_data, fig_nacional = chart_class_by_origin(base_date, "Nacional", selected_date, display_mode)
            st.plotly_chart(fig_nacional, use_container_width=True)
            download_button(nacional_data, "Descargar Nacional", "sistema_nacional_clase_v16.csv", key="dl_nacional_clase")
        with cole:
            extranjero_data, fig_extranjero = chart_class_by_origin(base_date, "Extranjero", selected_date, display_mode)
            st.plotly_chart(fig_extranjero, use_container_width=True)
            download_button(extranjero_data, "Descargar Extranjero", "sistema_extranjero_clase_v16.csv", key="dl_extranjero_clase")

    with st.expander("Nivel 3 · Buckets ampliados v1", expanded=True):
        bucket_data, fig_bucket = chart_bucket(base_date, selected_date, display_mode)
        st.plotly_chart(fig_bucket, use_container_width=True)
        download_button(bucket_data, "Descargar data nivel 3", "sistema_buckets_ampliados_v16.csv", key="dl_buckets")

    with st.expander("Evolutivo del sistema total", expanded=True):
        nivel_evo = st.selectbox("Nivel para evolutivo", ["origen", "clase", "bucket_reporte"], format_func=lambda x: {"origen": "Nacional / extranjero", "clase": "Clase", "bucket_reporte": "Bucket ampliado"}[x])
        evo_data, fig_evo = line_evolution(period, nivel_evo, f"Evolución mensual de composición - {start_date:%Y-%m-%d} a {end_date:%Y-%m-%d}", display_mode=display_mode)
        st.plotly_chart(fig_evo, use_container_width=True)
        download_button(evo_data, "Descargar evolutivo sistema", "sistema_evolutivo_v16.csv", key="dl_evo_sistema")


with tab_apertura:
    st.subheader("Apertura de cartera por bucket e instrumento")
    source_caption(
        "Esta pestaña abre los buckets a un nivel adicional usando `tipo_de_instrumento`, `instrumento_bancario` y el diccionario editable. "
        "La clasificación de `detalle_minimo` es analítica y debe validarse si se usa en un informe formal."
    )

    detail_date = enrich_with_detail(base_date, dic)
    detail_period = enrich_with_detail(period, dic)
    buckets_disponibles = [b for b in BUCKET_ORDER if b in detail_date["bucket_reporte"].dropna().unique()]
    if not buckets_disponibles:
        st.info("No hay buckets disponibles para abrir en esta fecha.")
    else:
        cdet1, cdet2, cdet3 = st.columns([1.4, 1, 1])
        with cdet1:
            bucket_sel = st.selectbox("Bucket a abrir", buckets_disponibles, index=buckets_disponibles.index("RF Nacional / Bonos") if "RF Nacional / Bonos" in buckets_disponibles else 0)
        with cdet2:
            corte_detalle = st.selectbox("Vista del corte", ["Segmento granular", "Código de instrumento", "Fondo × segmento", "AFP × segmento"])
        with cdet3:
            top_detalle = st.slider("Top códigos/categorías", 5, 50, 20, 5)

        d_bucket = detail_date[detail_date["bucket_reporte"].eq(bucket_sel)].copy()
        p_bucket = detail_period[detail_period["bucket_reporte"].eq(bucket_sel)].copy()
        total_bucket = d_bucket[VALUE_COL].sum()
        st.metric("Monto neto del bucket", fmt_mm_clp_from_clp(total_bucket, 0))

        if corte_detalle == "Segmento granular":
            resumen_det = build_detail_summary(d_bucket, ["detalle_minimo"])
            resumen_det = add_display_label(resumen_det, display_mode, VALUE_COL)
            fig_det = px.bar(
                resumen_det.sort_values(display_axis(display_mode)[0]),
                x=display_axis(display_mode, "% del bucket")[0],
                y="detalle_minimo",
                orientation="h",
                text="display_label",
                title=f"{bucket_sel}: apertura por segmento granular ({chart_title_suffix(display_mode)})",
                labels={display_axis(display_mode, "% del bucket")[0]: display_axis(display_mode, "% del bucket")[1], "detalle_minimo": ""},
                hover_data={"pct_pp": ":.2f", "monto_mm_clp": ":,.0f"},
            )
            fig_det.update_layout(height=520, yaxis_title="")
            apply_cmf_layout(fig_det, height=520)
            st.plotly_chart(fig_det, use_container_width=True)
            render_detail_table(resumen_det, display_mode)
            download_button(resumen_det, "Descargar segmento granular", f"apertura_cartera_{bucket_sel.replace('/', '_')}.csv", key="dl_segmento_granular")

        elif corte_detalle == "Código de instrumento":
            cols = ["tipo_de_instrumento", "detalle_minimo"]
            code_det = build_detail_summary(d_bucket, cols).sort_values(VALUE_COL, ascending=False).head(top_detalle)
            code_det = add_display_label(code_det, display_mode, VALUE_COL)
            if not dic.empty:
                merge_cols = [c for c in ["tipo_de_instrumento", "descripcion"] if c in dic.columns]
                code_det = code_det.merge(dic[merge_cols].drop_duplicates("tipo_de_instrumento"), on="tipo_de_instrumento", how="left")
            fig_code = px.bar(
                code_det.sort_values(display_axis(display_mode)[0]),
                x=display_axis(display_mode, "% del bucket")[0],
                y="tipo_de_instrumento",
                color="detalle_minimo",
                orientation="h",
                text="display_label",
                title=f"{bucket_sel}: top códigos de instrumento ({chart_title_suffix(display_mode)})",
                labels={display_axis(display_mode, "% del bucket")[0]: display_axis(display_mode, "% del bucket")[1], "tipo_de_instrumento": "Código", "detalle_minimo": "Detalle"},
                hover_data={"pct_pp": ":.2f", "monto_mm_clp": ":,.0f"},
            )
            fig_code.update_layout(height=620, yaxis_title="Código")
            apply_cmf_layout(fig_code, height=620)
            st.plotly_chart(fig_code, use_container_width=True)
            render_detail_table(code_det, display_mode, max_rows=top_detalle)
            download_button(code_det, "Descargar códigos", f"codigos_{bucket_sel.replace('/', '_')}.csv", key="dl_detalle_codigos")

        elif corte_detalle == "Fondo × segmento":
            fd = build_detail_summary(d_bucket, ["tipo_de_fondo", "detalle_minimo"], ["tipo_de_fondo"])
            y_fd, y_fd_label = display_axis(display_mode, "% de cada fondo")
            fig_fd = px.bar(
                fd,
                x="tipo_de_fondo",
                y=y_fd,
                color="detalle_minimo",
                title=f"{bucket_sel}: apertura por fondo y detalle ({chart_title_suffix(display_mode)})",
                labels={"tipo_de_fondo": "Fondo", y_fd: y_fd_label, "detalle_minimo": "Detalle"},
                hover_data={"pct_pp": ":.2f", "monto_mm_clp": ":,.0f"},
            )
            fig_fd.update_layout(height=620, yaxis_title=y_fd_label)
            apply_cmf_layout(fig_fd, height=620)
            st.plotly_chart(fig_fd, use_container_width=True)
            download_button(fd, "Descargar fondo × detalle", f"fondo_segmento_{bucket_sel.replace('/', '_')}.csv", key="dl_fondo_segmento")

        else:
            ad = build_detail_summary(d_bucket, ["afp_nombre", "detalle_minimo"], ["afp_nombre"])
            y_ad2, y_ad2_label = display_axis(display_mode, "% de cada AFP")
            fig_ad2 = px.bar(
                ad,
                x="afp_nombre",
                y=y_ad2,
                color="detalle_minimo",
                title=f"{bucket_sel}: apertura por AFP y detalle ({chart_title_suffix(display_mode)})",
                labels={"afp_nombre": "AFP", y_ad2: y_ad2_label, "detalle_minimo": "Detalle"},
                hover_data={"pct_pp": ":.2f", "monto_mm_clp": ":,.0f"},
            )
            fig_ad2.update_layout(height=620, yaxis_title=y_ad2_label)
            apply_cmf_layout(fig_ad2, height=620)
            st.plotly_chart(fig_ad2, use_container_width=True)
            download_button(ad, "Descargar AFP × detalle", f"afp_segmento_{bucket_sel.replace('/', '_')}.csv", key="dl_afp_segmento")

        with st.expander("Evolutivo del bucket abierto", expanded=True):
            evo_nivel = st.selectbox("Apertura evolutiva", ["detalle_minimo", "tipo_de_instrumento"], format_func=lambda x: {"detalle_minimo": "Segmento granular", "tipo_de_instrumento": "Código de instrumento"}[x])
            evo_detail = p_bucket.groupby(["fecha", evo_nivel], as_index=False).agg(**{VALUE_COL: (VALUE_COL, "sum")})
            totals_bucket_period = p_bucket.groupby("fecha", as_index=False)[VALUE_COL].sum().rename(columns={VALUE_COL: "total"})
            evo_detail = evo_detail.merge(totals_bucket_period, on="fecha", how="left")
            evo_detail["pct_pp"] = np.where(evo_detail["total"].abs() > 0, evo_detail[VALUE_COL] / evo_detail["total"] * 100, np.nan)
            evo_detail["monto_mm_clp"] = evo_detail[VALUE_COL] / 1_000_000
            if evo_nivel == "tipo_de_instrumento":
                top_codes = d_bucket.groupby("tipo_de_instrumento")[VALUE_COL].sum().abs().sort_values(ascending=False).head(top_detalle).index.tolist()
                evo_detail = evo_detail[evo_detail["tipo_de_instrumento"].isin(top_codes)]
            y_evo_det, y_evo_det_label = display_axis(display_mode, "% del bucket")
            fig_evo_det = px.line(
                evo_detail,
                x="fecha",
                y=y_evo_det,
                color=evo_nivel,
                title=f"{bucket_sel}: evolución por {evo_nivel.replace('_', ' ')} ({chart_title_suffix(display_mode)})",
                labels={"fecha": "Fecha", y_evo_det: y_evo_det_label, evo_nivel: "Serie"},
                hover_data={"pct_pp": ":.2f", "monto_mm_clp": ":,.0f"},
            )
            fig_evo_det.update_layout(height=650, yaxis_title=y_evo_det_label)
            apply_cmf_layout(fig_evo_det, height=650)
            st.plotly_chart(fig_evo_det, use_container_width=True)
            download_button(evo_detail, "Descargar evolutivo detalle", f"evolutivo_apertura_{bucket_sel.replace('/', '_')}.csv", key="dl_evo_apertura")


with tab_fondos:
    st.subheader("Composición desagregada por fondo")
    source_caption("Se usa `tipo_de_fondo` para separar fondos A, B, C, D y E. Denominador: total neto de cada fondo.")

    g_fondos = base_date.groupby(["tipo_de_fondo", "bucket_reporte"], as_index=False).agg(**{VALUE_COL: (VALUE_COL, "sum")})
    g_fondos = add_pct(g_fondos, VALUE_COL, ["tipo_de_fondo"])
    g_fondos = sort_by_order(g_fondos, "bucket_reporte", BUCKET_ORDER)

    y_fondos, y_fondos_label = display_axis(display_mode, "% del fondo")
    fig_fondos = px.bar(
        g_fondos,
        x="tipo_de_fondo",
        y=y_fondos,
        color="bucket_reporte",
        title=f"Composición por fondo - {selected_date:%Y-%m-%d} ({chart_title_suffix(display_mode)})",
        labels={"tipo_de_fondo": "Fondo", y_fondos: y_fondos_label, "bucket_reporte": "Bucket", "monto_mm_clp": "MM$", "pct_pp": "%"},
        hover_data={"pct_pp": ":.2f", "monto_mm_clp": ":,.0f"},
    )
    fig_fondos.update_layout(height=650, yaxis_title=y_fondos_label)
    st.plotly_chart(fig_fondos, use_container_width=True)
    download_button(g_fondos, "Descargar data composición por fondo", "fondos_composicion_buckets_v16.csv", key="dl_fondos_comp")

    st.markdown("#### Abrir un fondo en detalle")
    fondos = sorted(base_date["tipo_de_fondo"].dropna().unique())
    fondo_sel = st.selectbox("Fondo", fondos, index=fondos.index("C") if "C" in fondos else 0)
    d_fondo = base_date[base_date["tipo_de_fondo"].eq(fondo_sel)]

    c1, c2 = st.columns(2)
    with c1:
        gf_origen, fig_f_origen = chart_origin(d_fondo, selected_date, display_mode)
        fig_f_origen.update_layout(title=f"Fondo {fondo_sel}: Nacional vs extranjero")
        st.plotly_chart(fig_f_origen, use_container_width=True)
        download_button(gf_origen, "Descargar origen fondo", f"fondo_{fondo_sel}_origen_v16.csv", key="dl_fondo_origen")
    with c2:
        gf_bucket, fig_f_bucket = chart_bucket(d_fondo, selected_date, display_mode)
        fig_f_bucket.update_layout(title=f"Fondo {fondo_sel}: buckets ampliados")
        st.plotly_chart(fig_f_bucket, use_container_width=True)
        download_button(gf_bucket, "Descargar buckets fondo", f"fondo_{fondo_sel}_buckets_v16.csv", key="dl_fondo_bucket")

    with st.expander(f"Evolutivo Fondo {fondo_sel}", expanded=True):
        period_fondo = period[period["tipo_de_fondo"].eq(fondo_sel)]
        nivel_fondo = st.selectbox("Nivel evolutivo del fondo", ["origen", "clase", "bucket_reporte"], index=2, format_func=lambda x: {"origen": "Nacional / extranjero", "clase": "Clase", "bucket_reporte": "Bucket ampliado"}[x])
        evo_fondo, fig_evo_fondo = line_evolution(period_fondo, nivel_fondo, f"Fondo {fondo_sel}: evolución mensual de composición", display_mode=display_mode)
        st.plotly_chart(fig_evo_fondo, use_container_width=True)
        download_button(evo_fondo, "Descargar evolutivo fondo", f"fondo_{fondo_sel}_evolutivo_v16.csv", key="dl_fondo_evo")

with tab_deriv_alt:
    st.subheader("Alternativos y derivados")
    source_caption("Esta sección usa la clasificación editable `diccionario_tipo_instrumento.csv`; derivados se abren en forwards, swaps, opciones y futuros.")

    foco_date = base_date[base_date["bucket_reporte"].isin(DERIV_ALT_BUCKETS)].copy()
    foco_period = period[period["bucket_reporte"].isin(DERIV_ALT_BUCKETS)].copy()

    if foco_date.empty:
        st.info("No hay instrumentos clasificados como alternativos o derivados para la fecha seleccionada.")
    else:
        g_ad = foco_date.groupby("bucket_reporte", as_index=False).agg(**{VALUE_COL: (VALUE_COL, "sum")})
        # Participación contra el sistema completo, no solo contra alternativos + derivados.
        g_ad["total"] = base_date[VALUE_COL].sum()
        g_ad["pct"] = g_ad[VALUE_COL] / g_ad["total"]
        g_ad["pct_pp"] = g_ad["pct"] * 100
        g_ad = sort_by_order(g_ad, "bucket_reporte", DERIV_ALT_BUCKETS)
        fig_ad = horizontal_bar(g_ad, "bucket_reporte", f"Alternativos y derivados - {selected_date:%Y-%m-%d}", height=470, display_mode=display_mode)
        st.plotly_chart(fig_ad, use_container_width=True)
        download_button(g_ad, "Descargar corte alternativos/derivados", "alternativos_derivados_corte_v16.csv", key="dl_ad_corte")

        evo_ad = foco_period.groupby(["fecha", "bucket_reporte"], as_index=False).agg(**{VALUE_COL: (VALUE_COL, "sum")})
        totals_period = period.groupby("fecha", as_index=False)[VALUE_COL].sum().rename(columns={VALUE_COL: "total"})
        evo_ad = evo_ad.merge(totals_period, on="fecha", how="left")
        evo_ad["pct_pp"] = np.where(evo_ad["total"].abs() > 0, evo_ad[VALUE_COL] / evo_ad["total"] * 100, np.nan)
        evo_ad["monto_mm_clp"] = evo_ad[VALUE_COL] / 1_000_000
        y_ad, y_ad_label = display_axis(display_mode, "% del sistema")
        fig_evo_ad = px.line(
            evo_ad,
            x="fecha",
            y=y_ad,
            color="bucket_reporte",
            title=f"Evolución de alternativos y derivados ({chart_title_suffix(display_mode)})",
            labels={"fecha": "Fecha", y_ad: y_ad_label, "bucket_reporte": "Bucket", "monto_mm_clp": "MM$", "pct_pp": "%"},
            hover_data={"pct_pp": ":.2f", "monto_mm_clp": ":,.0f"},
        )
        fig_evo_ad.update_layout(height=620, yaxis_title=y_ad_label)
        st.plotly_chart(fig_evo_ad, use_container_width=True)
        download_button(evo_ad, "Descargar evolutivo alternativos/derivados", "alternativos_derivados_evolutivo_v16.csv", key="dl_ad_evo")

        st.markdown("#### Apertura por código de instrumento")
        fam_sel = st.selectbox("Familia", [b for b in DERIV_ALT_BUCKETS if b in foco_date["bucket_reporte"].unique()])
        detail = foco_date[foco_date["bucket_reporte"].eq(fam_sel)].groupby("tipo_de_instrumento", as_index=False).agg(**{VALUE_COL: (VALUE_COL, "sum")})
        detail = add_pct(detail, VALUE_COL)
        detail = detail.sort_values(VALUE_COL, ascending=False).head(25)
        if len(detail):
            fig_detail = horizontal_bar(detail, "tipo_de_instrumento", f"{fam_sel}: códigos principales", height=560, display_mode=display_mode)
            st.plotly_chart(fig_detail, use_container_width=True)
            download_button(detail, "Descargar detalle códigos", f"{fam_sel.lower().replace(' ', '_').replace('/', '')}_codigos_v16.csv", key="dl_codigos_deriv")

    with st.expander("¿Qué significan SNT, YSET y otros códigos de derivados?", expanded=True):
        if dic.empty:
            st.info("No encontré el diccionario de instrumentos.")
        else:
            ddic = dic.copy()
            if "es_derivado" in ddic.columns:
                ddic = ddic[normalize_bool(ddic["es_derivado"])]
            ddic = ddic[[c for c in ["tipo_de_instrumento", "descripcion", "derivado_tipo", "comentario"] if c in ddic.columns]].copy()
            codes_present = sorted(base_date.loc[base_date["bucket_reporte"].str.startswith("Derivados", na=False), "tipo_de_instrumento"].unique())
            ddic = ddic[ddic["tipo_de_instrumento"].isin(codes_present)] if codes_present else ddic
            ddic = ddic.sort_values(["derivado_tipo", "tipo_de_instrumento"]).head(80)
            st.markdown(
                "Los códigos provienen del campo `tipo_de_instrumento`. La descripción base está en el manual de cartera y en el diccionario editable del proyecto."
            )
            # Render cards instead of a visible table.
            for _, r in ddic.iterrows():
                code = escape(str(r.get("tipo_de_instrumento", "")))
                desc = escape(str(r.get("descripcion", "")))
                dtype = escape(str(r.get("derivado_tipo", "")))
                st.markdown(f"**{code}** · {dtype}: {desc}")
            download_button(ddic, "Descargar diccionario de derivados presentes", "diccionario_derivados_presentes_v16.csv", key="dl_dic_deriv")

with tab_bancos:
    st.subheader("Contrapartes bancarias: concentración, AFP e instrumentos")
    source_caption(
        "Esta sección cruza `nombre_del_emisor` normalizado como banco, AFP, fondo, bucket de cartera, "
        "tipo_de_instrumento e `instrumento_bancario`. Permite responder qué bancos concentran más exposición, "
        "qué instrumentos explican la exposición y cómo cambia en el tiempo. Cálculo siempre neto."
    )

    if bank_fact.empty:
        st.info("No hay fact de contrapartes bancarias procesada.")
    else:
        bank_period_all = bank_fact[(bank_fact["fecha"].ge(start_date)) & (bank_fact["fecha"].le(end_date))].copy()
        bank_date_all = bank_fact[bank_fact["fecha"].eq(selected_date)].copy()

        # Filtros de análisis
        f1, f2, f3, f4 = st.columns([1.1, 1.2, 1.4, 1.4])
        with f1:
            origen_banco_sel = st.selectbox(
                "Tipo de banco",
                ["Todos", "Bancos nacionales", "Bancos extranjeros"],
                index=0,
                key="bank_origen_v16",
            )
        with f2:
            afp_opts = ["Todas"] + sorted([x for x in bank_date_all["afp_nombre"].dropna().unique() if str(x).strip()])
            afp_bank_sel = st.selectbox("AFP", afp_opts, key="bank_afp_v16")
        with f3:
            bucket_opts_bank = ["Todos"] + [b for b in BUCKET_ORDER if b in set(bank_date_all["bucket_reporte"].dropna())]
            bucket_bank_sel = st.selectbox("Bucket de cartera", bucket_opts_bank, key="bank_bucket_v16")
        with f4:
            inst_opts = ["Todos"] + [x for x in BANK_INSTR_ORDER if x in set(bank_date_all["instrumento_bancario"].dropna())]
            inst_bank_sel = st.selectbox("Tipo de instrumento bancario", inst_opts, key="bank_inst_v16")

        bank_date = bank_date_all.copy()
        bank_period = bank_period_all.copy()

        if origen_banco_sel == "Bancos nacionales":
            bank_date = bank_date[bank_date["origen_banco"].eq("Nacional")]
            bank_period = bank_period[bank_period["origen_banco"].eq("Nacional")]
        elif origen_banco_sel == "Bancos extranjeros":
            bank_date = bank_date[bank_date["origen_banco"].eq("Extranjero")]
            bank_period = bank_period[bank_period["origen_banco"].eq("Extranjero")]

        if afp_bank_sel != "Todas":
            bank_date = bank_date[bank_date["afp_nombre"].eq(afp_bank_sel)]
            bank_period = bank_period[bank_period["afp_nombre"].eq(afp_bank_sel)]
        if bucket_bank_sel != "Todos":
            bank_date = bank_date[bank_date["bucket_reporte"].eq(bucket_bank_sel)]
            bank_period = bank_period[bank_period["bucket_reporte"].eq(bucket_bank_sel)]
        if inst_bank_sel != "Todos":
            bank_date = bank_date[bank_date["instrumento_bancario"].eq(inst_bank_sel)]
            bank_period = bank_period[bank_period["instrumento_bancario"].eq(inst_bank_sel)]

        if bank_date.empty:
            st.warning("No hay contrapartes bancarias para los filtros seleccionados.")
        else:
            total_bancos_fecha = bank_date[VALUE_COL].sum()
            n_bancos_fecha = bank_date["banco_nombre"].nunique()
            n_codigos_fecha = bank_date["tipo_de_instrumento"].nunique()
            bmet1, bmet2, bmet3 = st.columns(3)
            bmet1.metric("Exposición bancaria neta", fmt_mm_clp_from_clp(total_bancos_fecha, 0))
            bmet2.metric("Bancos presentes", f"{n_bancos_fecha:,}".replace(",", "."))
            bmet3.metric("Códigos de instrumento", f"{n_codigos_fecha:,}".replace(",", "."))

            top_n = st.slider("Top bancos a mostrar", 5, 30, 12, 1, key="top_banks_v16")
            top_banks = (
                bank_date.groupby(["banco_nombre", "origen_banco"], as_index=False)
                .agg(**{VALUE_COL: (VALUE_COL, "sum"), "n_registros": ("n_registros", "sum")})
            )
            top_banks = add_pct(top_banks, VALUE_COL)
            top_banks = top_banks.sort_values(VALUE_COL, ascending=False).head(top_n)
            x_bank, x_bank_label = display_axis(display_mode, "% de contrapartes bancarias")
            fig_bank = px.bar(
                top_banks.sort_values(x_bank),
                x=x_bank,
                y="banco_nombre",
                color="origen_banco",
                orientation="h",
                text=add_display_label(top_banks.sort_values(x_bank), display_mode, VALUE_COL)["display_label"],
                title=f"Top contrapartes bancarias netas - {selected_date:%Y-%m-%d} ({chart_title_suffix(display_mode)})",
                labels={x_bank: x_bank_label, "banco_nombre": "Banco", "origen_banco": "Origen", "monto_mm_clp": "MM$", "pct_pp": "%"},
                hover_data={"pct_pp": ":.2f", "monto_mm_clp": ":,.0f", "n_registros": ":,.0f"},
            )
            fig_bank.update_layout(height=570, yaxis_title="", xaxis_title=x_bank_label)
            apply_cmf_layout(fig_bank, height=570)
            st.plotly_chart(fig_bank, use_container_width=True)
            download_button(top_banks, "Descargar ranking bancos", "contrapartes_ranking_bancos_v16.csv", key="dl_bank_top_v16")

            st.markdown("#### Matriz AFP × banco")
            st.caption("Lectura sugerida: qué AFP explica la exposición a cada banco y qué bancos son relevantes para cada AFP.")
            afp_bank = (
                bank_date[bank_date["banco_nombre"].isin(top_banks["banco_nombre"])]
                .groupby(["afp_nombre", "banco_nombre"], as_index=False)
                .agg(**{VALUE_COL: (VALUE_COL, "sum")})
            )
            afp_bank = add_pct(afp_bank, VALUE_COL, ["afp_nombre"])
            y_afp_bank, y_afp_bank_label = display_axis(display_mode, "% de cada AFP")
            fig_afp_bank = px.bar(
                afp_bank,
                x="afp_nombre",
                y=y_afp_bank,
                color="banco_nombre",
                title=f"AFP × banco ({chart_title_suffix(display_mode)})",
                labels={"afp_nombre": "AFP", y_afp_bank: y_afp_bank_label, "banco_nombre": "Banco", "monto_mm_clp": "MM$", "pct_pp": "%"},
                hover_data={"pct_pp": ":.2f", "monto_mm_clp": ":,.0f"},
            )
            fig_afp_bank.update_layout(height=620, yaxis_title=y_afp_bank_label)
            apply_cmf_layout(fig_afp_bank, height=620)
            st.plotly_chart(fig_afp_bank, use_container_width=True)
            download_button(afp_bank, "Descargar matriz AFP × banco", "contrapartes_afp_banco_v16.csv", key="dl_afp_bank_v16")

            st.markdown("#### Banco × instrumento")
            cbi1, cbi2 = st.columns([1.2, 1])
            with cbi1:
                banco_opts = ["Top bancos"] + sorted([x for x in bank_date["banco_nombre"].dropna().unique() if str(x).strip()])
                banco_sel = st.selectbox("Banco a abrir", banco_opts, key="bank_open_v16")
            with cbi2:
                nivel_inst_banco = st.selectbox(
                    "Nivel de apertura",
                    ["Tipo de instrumento bancario", "Código de instrumento", "Bucket de cartera", "Fondo", "AFP"],
                    key="bank_open_level_v16",
                )

            bank_open = bank_date.copy()
            if banco_sel == "Top bancos":
                bank_open = bank_open[bank_open["banco_nombre"].isin(top_banks["banco_nombre"])]
                group_col_bank = "banco_nombre"
            else:
                bank_open = bank_open[bank_open["banco_nombre"].eq(banco_sel)]
                group_col_bank = {
                    "Tipo de instrumento bancario": "instrumento_bancario",
                    "Código de instrumento": "tipo_de_instrumento",
                    "Bucket de cartera": "bucket_reporte",
                    "Fondo": "tipo_de_fondo",
                    "AFP": "afp_nombre",
                }[nivel_inst_banco]

            if banco_sel == "Top bancos":
                banco_inst = (
                    bank_open.groupby(["banco_nombre", "instrumento_bancario"], as_index=False)
                    .agg(**{VALUE_COL: (VALUE_COL, "sum")})
                )
                banco_inst = add_pct(banco_inst, VALUE_COL, ["banco_nombre"])
                y_banco_inst, y_banco_inst_label = display_axis(display_mode, "% de cada banco")
                fig_banco_inst = px.bar(
                    banco_inst,
                    x="banco_nombre",
                    y=y_banco_inst,
                    color="instrumento_bancario",
                    title=f"Top bancos abiertos por instrumento bancario ({chart_title_suffix(display_mode)})",
                    labels={"banco_nombre": "Banco", y_banco_inst: y_banco_inst_label, "instrumento_bancario": "Instrumento", "monto_mm_clp": "MM$", "pct_pp": "%"},
                    hover_data={"pct_pp": ":.2f", "monto_mm_clp": ":,.0f"},
                )
                table_bank_open = banco_inst.copy()
            else:
                banco_inst = (
                    bank_open.groupby([group_col_bank], as_index=False)
                    .agg(**{VALUE_COL: (VALUE_COL, "sum"), "n_registros": ("n_registros", "sum")})
                    .sort_values(VALUE_COL, ascending=False)
                    .head(30)
                )
                banco_inst = add_pct(banco_inst, VALUE_COL)
                banco_inst = add_display_label(banco_inst, display_mode, VALUE_COL)
                y_banco_inst, y_banco_inst_label = display_axis(display_mode, "% del banco")
                fig_banco_inst = px.bar(
                    banco_inst.sort_values(y_banco_inst),
                    x=y_banco_inst,
                    y=group_col_bank,
                    orientation="h",
                    text="display_label",
                    title=f"{banco_sel}: apertura por {nivel_inst_banco.lower()} ({chart_title_suffix(display_mode)})",
                    labels={group_col_bank: "Apertura", y_banco_inst: y_banco_inst_label, "monto_mm_clp": "MM$", "pct_pp": "%"},
                    hover_data={"pct_pp": ":.2f", "monto_mm_clp": ":,.0f", "n_registros": ":,.0f"},
                )
                table_bank_open = banco_inst.copy()

            fig_banco_inst.update_layout(height=620, yaxis_title="", xaxis_title=y_banco_inst_label)
            apply_cmf_layout(fig_banco_inst, height=620)
            st.plotly_chart(fig_banco_inst, use_container_width=True)

            with st.expander("Ver tabla de apertura banco × instrumento", expanded=False):
                tbl = table_bank_open.copy()
                if "monto_mm_clp" not in tbl.columns and VALUE_COL in tbl.columns:
                    tbl["monto_mm_clp"] = tbl[VALUE_COL] / 1_000_000
                if "pct_pp" not in tbl.columns:
                    tbl = add_pct(tbl, VALUE_COL)
                tbl["MM$"] = tbl["monto_mm_clp"].map(lambda x: fmt_num_chile(x, 0))
                tbl["%"] = tbl["pct_pp"].map(lambda x: fmt_pct_num(x, 2))
                show_cols = [c for c in ["banco_nombre", "instrumento_bancario", "tipo_de_instrumento", "bucket_reporte", "tipo_de_fondo", "afp_nombre", "MM$", "%", "n_registros"] if c in tbl.columns]
                st.dataframe(tbl[show_cols], hide_index=True, use_container_width=True, height=420)
            download_button(table_bank_open, "Descargar apertura banco × instrumento", "contrapartes_banco_instrumento_v16.csv", key="dl_banco_inst_v16")

            st.markdown("#### Evolutivo de concentración bancaria")
            ce1, ce2, ce3 = st.columns([1.1, 1.1, 1.2])
            with ce1:
                evo_dim = st.selectbox(
                    "Serie evolutiva",
                    ["Banco", "Instrumento bancario", "Bucket de cartera", "AFP", "Fondo"],
                    key="bank_evo_dim_v16",
                )
            with ce2:
                top_evo = st.slider("Series evolutivas", 3, 15, 8, 1, key="bank_top_evo_v16")
            with ce3:
                denom_evo_bank = st.selectbox(
                    "Denominador %",
                    ["Total bancario filtrado", "Total sistema"],
                    key="bank_denom_evo_v16",
                )

            evo_col_map = {
                "Banco": "banco_nombre",
                "Instrumento bancario": "instrumento_bancario",
                "Bucket de cartera": "bucket_reporte",
                "AFP": "afp_nombre",
                "Fondo": "tipo_de_fondo",
            }
            evo_col = evo_col_map[evo_dim]
            evo_bank = bank_period.groupby(["fecha", evo_col], as_index=False).agg(**{VALUE_COL: (VALUE_COL, "sum")})
            if denom_evo_bank == "Total sistema":
                den = period.groupby("fecha", as_index=False)[VALUE_COL].sum().rename(columns={VALUE_COL: "total"})
            else:
                den = bank_period.groupby("fecha", as_index=False)[VALUE_COL].sum().rename(columns={VALUE_COL: "total"})
            evo_bank = evo_bank.merge(den, on="fecha", how="left")
            evo_bank["pct_pp"] = np.where(evo_bank["total"].abs() > 0, evo_bank[VALUE_COL] / evo_bank["total"] * 100, np.nan)
            evo_bank["monto_mm_clp"] = evo_bank[VALUE_COL] / 1_000_000
            top_series = (
                bank_date.groupby(evo_col)[VALUE_COL].sum().abs().sort_values(ascending=False).head(top_evo).index.tolist()
            )
            evo_bank = evo_bank[evo_bank[evo_col].isin(top_series)]
            y_evo_bank, y_evo_bank_label = display_axis(display_mode, "% bancario" if denom_evo_bank == "Total bancario filtrado" else "% sistema")
            fig_evo_bank = px.line(
                evo_bank,
                x="fecha",
                y=y_evo_bank,
                color=evo_col,
                title=f"Evolución por {evo_dim.lower()} ({chart_title_suffix(display_mode)})",
                labels={"fecha": "Fecha", y_evo_bank: y_evo_bank_label, evo_col: evo_dim, "monto_mm_clp": "MM$", "pct_pp": "%"},
                hover_data={"pct_pp": ":.2f", "monto_mm_clp": ":,.0f"},
            )
            fig_evo_bank.update_layout(height=650, yaxis_title=y_evo_bank_label)
            apply_cmf_layout(fig_evo_bank, height=650)
            st.plotly_chart(fig_evo_bank, use_container_width=True)
            download_button(evo_bank, "Descargar evolutivo bancario", "contrapartes_bancarias_evolutivo_v16.csv", key="dl_bank_evo_v16")

            st.markdown("#### Tabla resumen granular")
            st.caption("Tabla pensada para auditoría del gráfico: banco, AFP, fondo, bucket, instrumento y código.")
            granular = (
                bank_date.groupby(["banco_nombre", "afp_nombre", "tipo_de_fondo", "bucket_reporte", "instrumento_bancario", "tipo_de_instrumento"], as_index=False)
                .agg(**{VALUE_COL: (VALUE_COL, "sum"), "n_registros": ("n_registros", "sum")})
                .sort_values(VALUE_COL, ascending=False)
            )
            granular = add_pct(granular, VALUE_COL)
            granular["MM$"] = granular["monto_mm_clp"].map(lambda x: fmt_num_chile(x, 0))
            granular["%"] = granular["pct_pp"].map(lambda x: fmt_pct_num(x, 2))
            with st.expander("Ver tabla granular de contraparte bancaria", expanded=False):
                st.dataframe(
                    granular[["banco_nombre", "afp_nombre", "tipo_de_fondo", "bucket_reporte", "instrumento_bancario", "tipo_de_instrumento", "MM$", "%", "n_registros"]].head(250),
                    hide_index=True,
                    use_container_width=True,
                    height=520,
                )
            download_button(granular, "Descargar tabla granular bancaria", "contrapartes_bancarias_granular_v16.csv", key="dl_bank_granular_v16")


with tab_aum:
    st.subheader("AUM total por fondo")
    aum_source_caption("Este módulo elimina el AUM por grupo etario y usa únicamente la cartera cargada desde los CSV/ZIP anual raw.")

    aum_oficial = build_aum_from_cartera(fact)
    if aum_oficial.empty:
        st.warning("No pude calcular el AUM por fondo desde la cartera procesada.")
    else:
        aum_dates = pd.to_datetime(sorted(aum_oficial["fecha"].drop_duplicates()))
        default_idx = len(aum_dates) - 1
        selected_aum_date = st.selectbox(
            "Fecha de corte AUM desde cartera",
            options=aum_dates,
            index=default_idx,
            format_func=lambda x: pd.Timestamp(x).strftime("%Y-%m-%d"),
            key="selected_aum_date",
        )
        selected_aum_date = pd.Timestamp(selected_aum_date)
        aum_date = aum_oficial[aum_oficial["fecha"].eq(selected_aum_date)].copy()
        total_aum_corte = aum_date["AUM_MM_CLP"].sum()

        aum_period = aum_oficial[
            (aum_oficial["fecha"].ge(start_date)) &
            (aum_oficial["fecha"].le(end_date))
        ].copy()
        total_aum_ini = aum_period[aum_period["fecha"].eq(aum_period["fecha"].min())]["AUM_MM_CLP"].sum() if len(aum_period) else np.nan
        total_aum_fin = aum_period[aum_period["fecha"].eq(aum_period["fecha"].max())]["AUM_MM_CLP"].sum() if len(aum_period) else np.nan
        var_periodo = (total_aum_fin / total_aum_ini - 1) * 100 if pd.notna(total_aum_ini) and total_aum_ini != 0 else np.nan

        a1, a2, a3, a4 = st.columns(4)
        a1.metric("Fecha AUM cartera", selected_aum_date.strftime("%Y-%m-%d"))
        a2.metric("Total cartera", f"{total_aum_corte:,.0f} MM$".replace(",", "."))
        a3.metric("Fondos cargados", f"{aum_date['fondo'].nunique()}")
        a4.metric("Var. rango", "-" if pd.isna(var_periodo) else f"{var_periodo:.1f}%".replace(".", ","))

        st.markdown("#### AUM por fondo para la fecha seleccionada")
        aum_fund_data, fig_aum_fund = chart_aum_by_fund(aum_date, selected_aum_date, display_mode)
        st.plotly_chart(fig_aum_fund, use_container_width=True)
        download_button(aum_fund_data, "Descargar AUM por fondo", "aum_por_fondo_desde_cartera_v16.csv", key="dl_aum_fondo")

        st.markdown("#### Evolución AUM por fondo")
        st.caption(
            "Evolutivo calculado para el rango global seleccionado arriba. "
            "En modo porcentaje, cada fecha suma 100% entre los fondos A-E; en modo MM$, se muestra el monto neto administrado por fondo."
        )
        if aum_period.empty:
            st.warning("No hay datos de AUM para el rango seleccionado.")
        else:
            aum_evo_data, fig_aum_evo = chart_aum_evolution_by_fund(aum_period, display_mode)
            st.plotly_chart(fig_aum_evo, use_container_width=True)
            download_button(aum_evo_data, "Descargar evolución AUM por fondo", "aum_evolutivo_por_fondo_v16.csv", key="dl_aum_evo_fondo")

            with st.expander("Ver tabla resumida AUM por fondo", expanded=False):
                pivot = aum_evo_data.pivot_table(index="fecha", columns="fondo", values="AUM_MM_CLP", aggfunc="sum").reset_index()
                pivot["Total"] = pivot[[c for c in pivot.columns if c in ["A", "B", "C", "D", "E"]]].sum(axis=1)
                show = pivot.copy()
                show["fecha"] = pd.to_datetime(show["fecha"]).dt.strftime("%Y-%m-%d")
                for c in ["A", "B", "C", "D", "E", "Total"]:
                    if c in show.columns:
                        show[c] = show[c].map(lambda x: fmt_num_chile(x, 0))
                st.dataframe(show, hide_index=True, use_container_width=True, height=420)
                download_button(pivot, "Descargar tabla evolutiva AUM", "tabla_aum_evolutivo_por_fondo_v16.csv", key="dl_tabla_aum_evo")


st.divider()
st.caption(
    "Nota v15: la app no usa filtros laterales, siempre calcula con inversión neta y permite visualizar en %, MM$ o ambos formatos. "
    "Para validar buckets y clasificación nacional/extranjero contra tablas oficiales SP, revisar y ajustar `data/dictionaries/diccionario_tipo_instrumento.csv`."
)
