# Draken SEO Suite - notas para agentes

## Qué es
Plataforma SEO autoalojada: keywords, auditoría, posiciones, backlinks, motor de
adquisición de enlaces y medición de visibilidad en asistentes de IA. Un proceso
FastAPI que sirve API y panel en el mismo puerto, sin paso de compilación.

## Comandos
```bash
pip install -e "backend[dev]"
pytest backend/tests -q                 # 130 pruebas, sin acceso a red
ruff check backend/ scripts/
draken serve                            # API + panel
draken init-db                          # tablas + catálogo de fuentes
python3 scripts/build_link_source_seed.py   # regenera data/seeds/link_sources.json
```

## Estructura
- `backend/draken/engines/` — lógica pura, sin base de datos ni FastAPI. Testeable
  sin ninguna de las dos.
- `backend/draken/services/` — la única capa que toca la base de datos. La usan
  por igual la API, los handlers de tareas y la CLI.
- `backend/draken/api/` — routers finos.
- `frontend/` — módulos ES y CSS servidos tal cual. Sin bundler.
- `data/seeds/` — datasets JSON editables. `link_sources.json` es el catálogo de
  355 fuentes y su fichero de autoría es `scripts/build_link_source_seed.py`.

## Convenciones
- Todo el tráfico saliente pasa por `core/http.PoliteClient`. No hagas peticiones
  con `httpx` directamente: saltaría el throttle por host y el user-agent.
- Los logs van a **stderr**; stdout está reservado para el JSON de la CLI.
- Las estimaciones se etiquetan como tales (`volume_confidence`,
  `serp_approximate`). No presentes una heurística como una medición.
- El scoring devuelve siempre `score_breakdown`. Un 0-100 sin desglose no sirve.
- Los límites de los envíos se comprueban en `engines/submissions/runner.py`, en
  el servidor. No los muevas a la interfaz.
- Añadir una regla de auditoría = una función en `engines/crawler/checks.py` más
  su entrada en `page_issues` o `site_issues`.

## Qué no implementar
Resolución de CAPTCHAs, creación de cuentas con identidades falsas, rotación de
IP para ocultar origen, hilado de contenido, o compra/intercambio de enlaces a
escala. El razonamiento está en `docs/ESTUDIO-BACKLINKS.md`, sección 7.
