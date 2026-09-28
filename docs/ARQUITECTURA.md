# Arquitectura

## Principio de diseño

Draken es una herramienta interna para un equipo, no un SaaS multiinquilino. Eso
permite decisiones que simplifican mucho la operación:

- **Un solo proceso.** API y panel en el mismo servicio y el mismo puerto.
- **Sin paso de compilación.** El frontend son módulos ES y CSS servidos tal cual.
  No hay `node_modules`, ni bundler, ni build que pueda fallar en despliegue.
- **SQLite por defecto.** Cero configuración. Se cambia a Postgres con una
  variable de entorno cuando haga falta.
- **Sin broker de colas.** Las tareas en segundo plano son `asyncio` respaldadas
  por una tabla. No hay Redis ni Celery que mantener.
- **Degradación explícita.** Todo funciona sin ninguna clave de API. Cada clave
  que añades sustituye una estimación por un dato real, y la interfaz siempre
  dice cuál está usando.

## Mapa del repositorio

```
backend/draken/
  core/          config, base de datos, modelos, esquemas, HTTP, URLs, seguridad
  data/          cargador de los datasets JSON de data/seeds
  engines/       la lógica de dominio, sin dependencias de la base de datos
    keywords/      expansión, métricas, clustering
    serp/          obtención de SERP, estimación de autoridad
    crawler/       robots, parser, reglas de auditoría, rastreador
    backlinks/     descubrimiento, toxicidad, análisis de perfil
    opportunities/ scoring, generación
    submissions/   adaptadores y runner con sus límites
    outreach/      plantillas, contactos, envío
    geo/           motores de IA, medición de visibilidad, generadores de activos
    onpage/        analizador de una URL
    scheduler/     runner de tareas y handlers
  services/      orquestación: engines + base de datos
  api/           routers FastAPI y dependencias
  cli/           interfaz de línea de comandos
frontend/        panel (HTML + CSS + módulos ES)
data/seeds/      datasets editables (catálogo de fuentes, plantillas, reglas)
docs/            estudios y guías
deploy/          Docker, nginx, systemd
scripts/         herramienta de autoría del catálogo
```

## Las cuatro capas

```
  CLI  ─┐
        ├─→  services/  ─→  engines/  ─→  core/http  ─→  internet
  API  ─┘         │
                  └──────→  core/models (SQLAlchemy) ─→ SQLite/Postgres
```

1. **`engines/`** es lógica pura: recibe datos, devuelve datos. No importa
   SQLAlchemy ni FastAPI. Por eso se puede testear sin base de datos y sin red.
2. **`services/`** es lo único que sabe de persistencia. Lo usan por igual la API,
   los handlers de tareas y la CLI, así que no hay tres implementaciones de la
   misma orquestación.
3. **`api/`** son routers finos: validan, delegan, serializan.
4. **`cli/`** ofrece las mismas operaciones sin navegador, para cron.

## Decisiones que conviene conocer

### Todo el tráfico saliente pasa por `core/http.PoliteClient`
Un único punto donde se aplican user-agent, tiempos de espera, reintentos
acotados y limitación por host. Eso significa que la etiqueta de rastreo se
cumple por construcción, no por disciplina: no hay forma de hacer una petición
que se salte el throttle sin escribirla a mano.

### El rastreador obedece robots.txt por defecto
`DRAKEN_RESPECT_ROBOTS=true`. Además, si el `robots.txt` declara `Crawl-delay`,
el rastreador **aumenta** su propio retardo hasta ese valor.

### Las estimaciones se marcan como estimaciones
`volume_confidence` acompaña a cada volumen de búsqueda. El proveedor de SERP
activo se muestra en la cabecera y el panel avisa cuando es aproximado. Un número
que se presenta como medición cuando es una heurística es peor que no tenerlo.

### El scoring es auditable
`score_breakdown` viaja con cada oportunidad y el panel lo dibuja. Un número
0-100 sin desglose no permite decidir nada; con desglose puedes ver que algo
puntúa alto por autoridad pero bajo por relevancia, y actuar en consecuencia.

### Los límites del runner de envíos están en el servidor
Simulación, aprobación y topes diarios se comprueban en
`engines/submissions/runner.py`, no en la interfaz. Llamar a la API directamente
no los evita.

### El registro de actividad es de solo añadir
Todo lo que toca el exterior escribe en `activity_log`: qué se preparó, qué se
ejecutó, con qué resultado. Es lo que permite responder a "¿qué envió esto en mi
nombre?".

## Modelo de datos

| Grupo | Tablas |
|---|---|
| Proyectos | `projects`, `business_profiles` |
| Keywords | `keywords`, `keyword_clusters` |
| SERP | `rank_snapshots`, `serp_results` |
| Auditoría | `site_audits`, `crawled_pages`, `audit_issues` |
| Enlaces | `backlinks`, `competitor_backlinks` |
| Adquisición | `link_sources`, `link_opportunities`, `campaigns`, `submissions` |
| Outreach | `outreach_templates`, `outreach_messages` |
| IA | `ai_prompts`, `ai_visibility_runs` |
| Sistema | `jobs`, `activity_log` |

`link_sources` es un catálogo global (compartido entre proyectos);
`link_opportunities` es la instancia puntuada **para un proyecto concreto**. Esa
separación es lo que permite que la misma fuente puntúe 83 para un proyecto de
software y 31 para una clínica dental.

## Tareas en segundo plano

```
enqueue() ─→ fila en `jobs` (pending)
spawn()   ─→ asyncio.create_task
             ├─ running  → progreso y mensaje
             ├─ succeeded → resultado JSON
             └─ failed    → error con traza recortada
```

Al arrancar, `resume_pending()` recupera las tareas que quedaron en `pending` y
devuelve a `pending` las que quedaron marcadas como `running` (un proceso que se
reinició no las estaba ejecutando).

Tipos registrados: `site_audit`, `keyword_research`, `rank_tracking`,
`competitor_prospecting`, `unlinked_mentions`, `backlink_discovery`,
`backlink_recheck`, `run_submissions`, `verify_submissions`, `ai_visibility` y
`full_sweep`.

## Proveedores externos y su alternativa

| Dato | Con clave | Sin clave |
|---|---|---|
| Sugerencias de keywords | — | Autocompletado público de Google, Bing, DuckDuckGo |
| Volumen de búsqueda | SerpApi / DataForSEO | Estimación explicable, con confianza declarada |
| Posiciones | SerpApi / DataForSEO | DuckDuckGo HTML, marcado como aproximado |
| Autoridad de dominio | Open PageRank | Estimación estructural |
| Backlinks | — | Verificación por rastreo, búsqueda de menciones, Common Crawl, import CSV |
| Visibilidad IA | Anthropic / OpenAI / Perplexity / Gemini | No medible: el módulo lo dice en vez de inventarlo |

## Pruebas

130 pruebas, ninguna necesita acceso a internet.

- `test_core.py` — normalización de URL y dominio, seguridad, integridad de los
  datasets.
- `test_engines.py` — cada estimador y clasificador por separado.
- `test_api.py` — contrato de la API con una base de datos en memoria.
- `test_crawler_integration.py` — **sirve un sitio de pruebas con defectos
  plantados sobre HTTP real** y comprueba que la auditoría detecta cada uno: 404,
  título duplicado, doble H1, H1 ausente, contenido escaso, página huérfana,
  imagen sin alt y baja cobertura de datos estructurados. También verifica que la
  comprobación de enlaces lee el `rel=nofollow` y el anchor de la página real.
