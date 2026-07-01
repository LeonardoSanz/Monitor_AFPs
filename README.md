# AFP Streamlit v16

Monitor de composición de cartera, apertura granular, contrapartes bancarias y AUM de Fondos de Pensiones, con estilo CMF oscuro.

## Cambios v16

- Renombra `Detalle mínimo` a **Apertura de cartera**.
- Mantiene apertura por bucket, segmento granular, código de instrumento, fondo y AFP.
- Refuerza la pestaña **Contrapartes bancarias** con filtros por tipo de banco, AFP, bucket e instrumento.
- Agrega análisis banco × instrumento, matriz AFP × banco, evolutivo bancario y tabla granular descargable.
- Mantiene AUM total por fondo y evolutivo AUM por fondo.

## Fuente

La app lee los ZIP/CSV anuales desde:

```text
data/raw/chistAFP/cartera_mensual_YYYY.zip
```

y procesa automáticamente hacia:

```text
data/processed/
```

## Streamlit Cloud

No subir `.streamlit/secrets.toml`. Configurar la clave en Secrets:

```toml
APP_PASSWORD = "tu_clave"
```
