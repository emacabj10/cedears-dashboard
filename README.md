# Cedears Dashboard

Dashboard de alertas técnicas para CEDEARs con actualización automática de cotizaciones.

## Setup

1. Crear repositorio en GitHub llamado `cedears-dashboard`
2. Subir todos los archivos de esta carpeta
3. Activar GitHub Pages: Settings → Pages → Branch: main → / (root)
4. El workflow corre automáticamente lunes a viernes a las 6am y 2pm (hora Argentina)

## URL pública

`https://emacabj10.github.io/cedears-dashboard`

## Archivos

- `index.html` — dashboard principal
- `data.json` — cotizaciones actualizadas por el workflow
- `fetch_quotes.py` — script que corre en GitHub Actions
- `.github/workflows/update-quotes.yml` — workflow de actualización automática
