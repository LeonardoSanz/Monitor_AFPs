# AFP SP - Monitor de cartera de Fondos de Pensiones

Dashboard Streamlit para revisar la composición de la cartera de los Fondos de Pensiones usando bases públicas de la Superintendencia de Pensiones.

## Versión 12

Cambios principales:

- Lee data raw desde `data/raw/chistAFP/`.
- Soporta archivos anuales `cartera_mensual_YYYY.zip` o `cartera_mensual_YYYY.csv`.
- Procesa automáticamente hacia `data/processed/` al ejecutar la app.
- No usa Excel externo.
- Modo oscuro con identidad visual azul/morada tipo CMF.
- Tabla tipo SP corregida para modo oscuro.
- Soporte para logo en `assets/cmf_logo.png`.
- Login opcional con clave mediante `APP_PASSWORD`.

## Estructura esperada

```text
afp_streamlit_monitor/
├── .streamlit/
│   ├── config.toml
│   └── secrets.example.toml
├── assets/
│   ├── cmf_logo.png      # opcional, lo agregas tú
│   └── cmf_bg.jpg        # opcional
├── data/
│   ├── raw/
│   │   └── chistAFP/
│   │       ├── cartera_mensual_2016.zip
│   │       ├── cartera_mensual_2017.zip
│   │       └── ...
│   ├── processed/
│   └── dictionaries/
├── scripts/
├── app.py
└── requirements.txt
```

## Ejecutar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Activar clave local

Copia:

```text
.streamlit/secrets.example.toml
```

como:

```text
.streamlit/secrets.toml
```

Y cambia la clave:

```toml
APP_PASSWORD = "mi_clave_segura"
```

`secrets.toml` está en `.gitignore` para no subirlo a GitHub público.

## Activar clave en Streamlit Cloud

En la app publicada:

1. Settings.
2. Secrets.
3. Agregar:

```toml
APP_PASSWORD = "mi_clave_segura"
```

Si `APP_PASSWORD` no está configurado, el dashboard corre sin login.

## Fuente de datos

La app usa la base histórica de cartera de la SP. Los archivos originales esperados son `cartera_mensual_YYYY.zip` o `cartera_mensual_YYYY.csv`. El campo base de monto es `inversion`, procesado como `inversion_neta_clp`.

## Nota sobre GitHub público

Puedes subir el código y los ZIP anuales si cada archivo cumple con los límites de GitHub web. Si algún archivo es muy pesado, sube la data en tandas o usa Git desde consola/Git LFS.
