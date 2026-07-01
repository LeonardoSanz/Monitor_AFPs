# AFP Streamlit v15

Monitor Streamlit para cartera de Fondos de Pensiones usando bases públicas de la Superintendencia de Pensiones.

## Cambios v15

- Se elimina el módulo **AUM por grupo etario ajustado** porque la consulta web del cuadro edad/saldo de la SP puede ser bloqueada en Streamlit Cloud con error 403.
- Se mantiene **AUM total por fondo** calculado 100% desde la cartera cargada en `data/raw/chistAFP/`.
- Se agrega **evolutivo AUM por fondo** para el rango global seleccionado.
- Se agrega tabla resumida descargable del evolutivo AUM por fondo.
- No usa Excel externo.

## Fuente de datos

La app lee archivos anuales ZIP o CSV desde:

```text
data/raw/chistAFP/
├── cartera_mensual_2016.zip
├── cartera_mensual_2017.zip
└── ...
```

Cada ZIP anual debe contener su CSV `cartera_mensual_YYYY.csv`.

## Login

La clave no va en GitHub. En Streamlit Cloud configurar:

```toml
APP_PASSWORD = "tu_clave"
```

Si no se configura `APP_PASSWORD`, la app corre sin login.
