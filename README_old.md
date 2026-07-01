# AFP SP - Cartera de Fondos de Pensiones

## Versión 10

Esta versión permite trabajar sin un ZIP gigante. La app procesa automáticamente archivos anuales separados en `data/raw/chistAFP/`.

Formatos soportados:

```text
data/raw/chistAFP/cartera_mensual_2016.csv
data/raw/chistAFP/cartera_mensual_2017.csv
...
data/raw/chistAFP/cartera_mensual_2026.csv
```

o bien:

```text
data/raw/chistAFP/cartera_mensual_2016.zip
data/raw/chistAFP/cartera_mensual_2017.zip
...
data/raw/chistAFP/cartera_mensual_2026.zip
```

Cada ZIP anual debe contener su respectivo CSV, por ejemplo:

```text
cartera_mensual_2016.zip
└── cartera_mensual_2016.csv
```

La app busca primero en:

```text
data/raw/chistAFP/
```

y, si no encuentra nada, busca directamente en:

```text
data/raw/
```

## Flujo automático

Al ejecutar:

```bash
streamlit run app.py
```

la app revisa si existen las bases procesadas:

```text
data/processed/fact_cartera_mensual_agg.csv.gz
data/processed/fact_contrapartes_bancarias_agg.csv.gz
```

Si no existen, o si los archivos raw son más recientes, procesa automáticamente los CSV/ZIP anuales y genera las facts en `data/processed/`.

## Estructura recomendada

```text
afp_streamlit_monitor/
├── .streamlit/
├── app.py
├── README.md
├── requirements.txt
├── scripts/
│   ├── build_processed_from_csv.py
│   └── build_processed_from_zip.py
└── data/
    ├── raw/
    │   └── chistAFP/
    │       ├── cartera_mensual_2016.zip
    │       ├── cartera_mensual_2017.zip
    │       ├── ...
    │       └── cartera_mensual_2026.zip
    ├── processed/
    └── dictionaries/
```

## Instalación

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Fuente de datos

Base de Cartera de los Fondos de Pensiones de la Superintendencia de Pensiones. La estructura esperada de los archivos es `cartera_mensual_YYYY.csv`, delimitado por `;`, con campos como `fecha`, `afp`, `tipo_de_fondo`, `tipo_de_instrumento`, `nombre_del_emisor`, `nacionalidad_del_emisor` e `inversion`.
