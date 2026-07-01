# AFP Streamlit Monitor v17

Versión enfocada en navegación ejecutiva y performance: menos filtros finos, más subsecciones fijas y gráficos específicos para analizar composición, apertura de instrumentos y contrapartes bancarias.

## Cambios v17

- Pestaña de contrapartes bancarias reorganizada como informe navegable.
- Menos filtros interactivos para mejorar velocidad.
- Nuevas subsecciones bancarias:
  - Resumen sistema.
  - Bancos nacionales.
  - Bancos extranjeros.
  - Por AFP.
  - Banco × instrumento.
  - Evolutivos.
- Mantiene ranking total, nacional y extranjero.
- Mantiene matriz AFP × banco.
- Mantiene apertura de banco específico por instrumento, código, AFP, fondo y bucket.
- Agrega evolutivos fijos para origen bancario, instrumento bancario y top bancos.

## Fuente

La app usa los ZIP/CSV anuales de cartera desde:

```text
data/raw/chistAFP/
```

con archivos tipo:

```text
cartera_mensual_2016.zip
...
cartera_mensual_2026.zip
```

La app procesa automáticamente hacia `data/processed/` si la data procesada no existe o si cambian los archivos raw.

## Ejecución local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Login

Para usar login local, crear `.streamlit/secrets.toml` con:

```toml
APP_PASSWORD = "tu_clave"
```

No subir `secrets.toml` a GitHub. En Streamlit Cloud configurar la clave en Settings → Secrets.
