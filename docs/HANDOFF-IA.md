# Traspaso a otra IA

Este fichero es el briefing completo para que otro asistente (Claude Code,
Cursor, Copilot, lo que sea) continúe el proyecto sin preguntar nada. Está
escrito para que se lea entero antes de tocar una línea.

Léelo junto con `CLAUDE.md` (reglas cortas del repo) y `docs/ARQUITECTURA.md`.

### Qué pegarle a la nueva IA para empezar

> Vas a continuar un proyecto ya existente: **Draken SEO Suite**, una plataforma
> SEO autoalojada con motor de backlinks y medición de visibilidad en asistentes
> de IA. El repositorio es `https://github.com/Teoremadepierre/Draken` y se
> trabaja en la rama `claude/backlinks-seo-tool-study-2tlk0x`.
>
> Antes de tocar nada: clona el repo, y lee `docs/HANDOFF-IA.md` entero, después
> `CLAUDE.md` y `docs/ARQUITECTURA.md`. En `docs/HANDOFF-IA.md` está el mapa del
> código, las reglas del proyecto, las conexiones externas con su variable de
> entorno, dónde viven los secretos, los errores ya corregidos que no hay que
> reintroducir y la lista de lo que queda por hacer.
>
> Arranca con `bash scripts/empezar.sh` y comprueba que `pytest backend/tests -q`
> da 204 en verde y `ruff check backend/ scripts/` está limpio antes de cambiar
> nada, para saber que partes de un estado sano.
>
> No me pidas contraseñas ni claves de API por chat: dame los comandos y los
> ejecuto yo.

---

## 1. Qué es Draken

Plataforma SEO autoalojada, equivalente interno a SEMrush, con dos cosas que las
suites comerciales no traen:

1. **Motor de adquisición de backlinks** sobre un catálogo de **355 fuentes
   gratuitas** (directorios, perfiles, citaciones locales, comunidades,
   agregadores), puntuadas para cada proyecto concreto.
2. **Medición de visibilidad en asistentes de IA** (GEO): qué dicen de tu marca
   ChatGPT, Claude, Perplexity y Gemini, y qué mueve esa aguja.

Un solo proceso FastAPI sirve la API y el panel en el mismo puerto. Sin bundler,
sin paso de compilación, sin broker de colas, sin Redis.

**Estado actual:** funcional de punta a punta. ~16.500 líneas de Python,
~6.300 de JavaScript, 102 endpoints, 22 vistas, 204 pruebas en verde, ruff
limpio. Nada de esto necesita red para pasar los tests.

---

## 2. Arranque en tres comandos

```bash
git clone -b claude/backlinks-seo-tool-study-2tlk0x https://github.com/Teoremadepierre/Draken.git
cd Draken
bash scripts/empezar.sh          # instala, configura, prepara la base, abre el navegador
```

Panel en `http://127.0.0.1:8000`. Para desarrollo:

```bash
source .venv/bin/activate
pip install -e "backend[dev]"    # extras de desarrollo (pytest, ruff)
pytest backend/tests -q          # 204 pruebas, sin acceso a red
ruff check backend/ scripts/
draken serve                     # API + panel
draken init-db                   # tablas + catálogo de 355 fuentes
python3 scripts/build_link_source_seed.py   # regenera data/seeds/link_sources.json
```

**Repositorio:** https://github.com/Teoremadepierre/Draken
**Rama de trabajo:** `claude/backlinks-seo-tool-study-2tlk0x`
(todo el trabajo va aquí; no se ha fusionado a `main`)

---

## 3. Mapa del código

```
backend/draken/
  core/
    config.py        todas las variables DRAKEN_*, pydantic-settings
    models.py        el esquema entero: 24 tablas SQLAlchemy 2.0
    database.py      motor, sesión, WAL + foreign_keys ON en SQLite
    http.py          PoliteClient: ÚNICA salida HTTP del proyecto
    urls.py          normalize_domain y compañía (ojo: muy parcheado, ver §9)
    security.py      PBKDF2 + tokens de sesión firmados con HMAC
    schemas.py       modelos Pydantic de entrada/salida
  engines/           lógica pura: sin base de datos, sin FastAPI, testeable sola
    keywords/        expansión, métricas, clustering, intención
    serp/            fetcher con 6 proveedores y cadena de reserva; authority
    crawler/         robots, parser, crawler, checks (las ~25 reglas de auditoría)
    backlinks/       discovery, profile, toxicity
    onpage/          analyzer
    opportunities/   generator, scoring
    submissions/     runner (topes y aprobación viven AQUÍ, en servidor), adapters
    outreach/        engine y plantillas
    geo/             engines (Anthropic/OpenAI/Perplexity/Gemini), visibility, assets
    providers/       search_console.py, bing_webmaster.py (datos reales)
    scheduler/       jobs.py (runner asíncrono sobre la base), handlers.py
  services/          ÚNICA capa que toca la base de datos
    scanner.py       full_scan + build_report: el botón de un clic
    realdata.py      importación de GSC y Bing, niveles de calidad de datos
    assistant.py     briefings para la IA de arreglos
    accounts.py      usuarios, roles, invitaciones, enlaces compartidos
    diagnostics.py   sondas de conectividad por host
    portability.py   export/import de proyectos
    keywords.py audits.py backlinks.py opportunities.py geo.py
  api/routes/        routers finos: proyectos, keywords, auditorías, backlinks,
                     oportunidades, outreach, geo, jobs, auth, users, scan
  cli/main.py        serve, init-db, hash-password, project, keywords, audit,
                     opportunities, submissions, ai, sweep, report, export, import
frontend/
  js/main.js         router hash, arranque, cambio de idioma
  js/api.js          único envoltorio de fetch (auth, errores, query)
  js/ui.js           sistema de componentes (tablas, gráficas, modales, toasts)
  js/i18n.js         es/en
  js/views/*.js      22 vistas, una por pantalla
  css/app.css        sistema de diseño a mano, 489 líneas
data/seeds/
  link_sources.json  el catálogo de 355 fuentes (GENERADO - ver abajo)
scripts/
  empezar.sh                 arranque local en un comando
  check-hosting.sh           diagnóstico de un servidor ajeno, solo lectura
  build_link_source_seed.py  FICHERO DE AUTORÍA del catálogo
```

**Importante:** `data/seeds/link_sources.json` es un artefacto generado. Para
añadir o cambiar fuentes se edita `scripts/build_link_source_seed.py` y se
regenera. Editar el JSON a mano se pierde en la siguiente regeneración.

---

## 4. Reglas que no se negocian

Están en `CLAUDE.md`; las repito porque romperlas rompe cosas silenciosamente.

- **Todo el tráfico saliente pasa por `core/http.PoliteClient`.** Nada de
  `httpx` directo: se salta el throttle por host y el user-agent compartido.
- **Los logs van a stderr.** stdout está reservado al JSON de la CLI. Un
  `print()` de depuración en stdout corrompe la salida de `draken report`.
- **Las estimaciones se etiquetan** (`volume_confidence`, `serp_approximate`).
  Nunca presentes una heurística como una medición.
- **El scoring siempre devuelve `score_breakdown`.** Un 0-100 sin desglose no
  sirve para decidir nada.
- **Los límites de envíos se comprueban en `engines/submissions/runner.py`**, en
  el servidor. No los muevas a la interfaz.
- **Una regla de auditoría nueva** = una función en `engines/crawler/checks.py`
  más su entrada en `page_issues` o `site_issues`.
- **Una vista nueva** = `frontend/js/views/x.js` que exporte `meta`
  (`{ id, icon, group }`) y `async render(ctx)`, más su `import` y su entrada en
  la lista de `frontend/js/main.js`. Sin eso no aparece en el menú.

### Qué NO se implementa, nunca

Resolución de CAPTCHAs, creación de cuentas con identidades falsas, rotación de
IP para ocultar el origen, hilado de contenido (spinning), y compra o
intercambio de enlaces a escala. El razonamiento completo está en
`docs/ESTUDIO-BACKLINKS.md` §7. No es mojigatería: son las tácticas que
convierten un perfil de enlaces en una penalización, y además el catálogo está
construido sobre fuentes donde el alta legítima funciona.

Dos rieles de seguridad que vienen puestos y deben seguir puestos por defecto:
`DRAKEN_SUBMISSIONS_DRY_RUN=true` y `DRAKEN_SUBMISSIONS_REQUIRE_APPROVAL=true`.

---

## 5. Conexiones externas: qué hay, qué cuesta, dónde se consigue

Draken **funciona sin ninguna clave**. Cada clave sustituye una estimación por
un dato real. Ninguna está incluida en el repositorio, y ninguna debe estarlo.

| Variable | Qué aporta | Coste | Dónde se saca |
|---|---|---|---|
| `DRAKEN_GSC_SERVICE_ACCOUNT_JSON` (o `_FILE`) + `DRAKEN_GSC_SITE_URL` | Impresiones, clics, CTR y posiciones **medidas** por Google para tu sitio. La mayor subida de calidad disponible. | gratis | [Google Cloud Console](https://console.cloud.google.com) → activar Search Console API → cuenta de servicio → descargar JSON → añadir su email como usuario en [Search Console](https://search.google.com/search-console) |
| `DRAKEN_BING_WEBMASTER_API_KEY` + `DRAKEN_BING_SITE_URL` | Tus backlinks reales. Es el dato que las suites de pago cobran más caro. | gratis | [Bing Webmaster Tools](https://www.bing.com/webmasters) → Settings → API access |
| `DRAKEN_ANTHROPIC_API_KEY` | Asistente de arreglos en el panel + medición de visibilidad en Claude | de pago, por uso | [console.anthropic.com](https://console.anthropic.com) |
| `DRAKEN_PERPLEXITY_API_KEY` | Visibilidad en Perplexity. La más informativa: devuelve sus fuentes. | de pago | [perplexity.ai/settings/api](https://www.perplexity.ai/settings/api) |
| `DRAKEN_OPENAI_API_KEY` / `DRAKEN_GEMINI_API_KEY` | Visibilidad en ChatGPT / Gemini | de pago | [platform.openai.com](https://platform.openai.com) / [aistudio.google.com](https://aistudio.google.com) |
| `DRAKEN_SERPAPI_KEY` | Posiciones exactas de Google | de pago | [serpapi.com](https://serpapi.com) |
| `DRAKEN_DATAFORSEO_LOGIN` + `_PASSWORD` | Alternativa más barata a SerpApi | de pago | [dataforseo.com](https://dataforseo.com) |
| `DRAKEN_BRAVE_API_KEY` | SERP de un índice independiente | gratis hasta 2.000 consultas/mes | [brave.com/search/api](https://brave.com/search/api/) |
| `DRAKEN_SEARXNG_URL` | Tu propio metabuscador, sin límites | gratis, autoalojado | [searxng.org](https://docs.searxng.org) (requiere `json` en `search.formats`) |
| `DRAKEN_OPENPAGERANK_KEY` | Autoridad de dominio medida | gratis con límites | [domcop.com/openpagerank](https://www.domcop.com/openpagerank/) |
| `DRAKEN_SMTP_*` | Envío real de outreach | el de tu proveedor | tu servidor de correo |

Sin ninguna clave de SERP se usan, por este orden: SerpApi → DataForSEO → Brave
→ SearXNG → DuckDuckGo HTML → Mojeek. Los dos últimos son gratis y sin cuenta,
pero aproximados, y por eso todo lo que sale de ahí va marcado
`serp_approximate: true`.

**Diagnóstico:** el panel, en **Fuentes de datos → Diagnóstico de conectividad**,
prueba cada host
uno a uno y dice qué deja de funcionar por cada fallo. Si el escáner no
encuentra competencia, mira ahí antes de tocar código: casi siempre es la red
del sitio donde corre, no un bug.

---

## 6. Contraseñas y secretos: dónde están y cómo se tratan

**En el repositorio no hay ni una sola credencial, y no debe haberla.** Hay una
prueba que lo vigila: `test_deploy_templates_carry_no_real_secrets`. Otra impide
que la API devuelva jamás una clave de IA guardada.

Dónde vive cada cosa:

| Qué | Dónde | Cómo se recupera si se pierde |
|---|---|---|
| Configuración local (todas las claves) | `.env` en la raíz del proyecto. Está en `.gitignore`, permisos 600. | Se vuelve a crear desde `.env.example`; las claves de terceros se regeneran en cada proveedor. |
| Clave secreta de sesiones | `DRAKEN_SECRET_KEY` en el `.env`. `scripts/empezar.sh` la genera con `secrets.token_hex(32)`. | Genera otra. Efecto: las sesiones abiertas se invalidan, nada más. |
| Contraseña del panel | `DRAKEN_ADMIN_PASSWORD_HASH` (preferido) o `DRAKEN_ADMIN_PASSWORD`. | `draken hash-password "la-nueva"` y pega el resultado en el `.env`. Reinicia. |
| Contraseña en Render / Fly | Variable de entorno en el panel del proveedor, marcada `sync: false`. Nunca en el repo. | Se cambia en el panel del proveedor y se redespliega. |
| Base de datos | `data/draken.db` (SQLite) o el Postgres del proveedor. Está en `.gitignore`. | Copia de seguridad: `draken export`. Ver §7. |

Regla de trabajo, y esto va también para la IA que continúe:

> **Nunca pegues una contraseña ni una clave de API en un chat**, tampoco en uno
> con un asistente. Queda en el historial. Las claves se escriben en el `.env` o
> en el panel del proveedor, siempre por la persona, nunca a través de un
> mensaje. Si una IA te pide credenciales para "hacerlo por ti", la respuesta es
> que te dé los comandos y los ejecutes tú.

Para uso puramente local (`127.0.0.1`), `scripts/empezar.sh` deja
`DRAKEN_AUTH_ENABLED=false` a propósito: el puerto no es accesible desde fuera
de la máquina. **En cuanto eso se publique en cualquier sitio con URL, hay que
poner `DRAKEN_AUTH_ENABLED=true` y una contraseña.** El arranque avisa por
stderr cuando sirve sin autenticación.

---

## 7. Mover el proyecto a otra cuenta del mismo ordenador

Tres cosas se mueven por separado: **el código**, **los datos** y **la
configuración**.

```bash
# --- en la cuenta vieja ---
cd ~/Draken
.venv/bin/draken export -o ~/Descargas/draken-copia.json   # datos
cp .env ~/Descargas/draken-env.txt                         # configuración (contiene claves)

# --- en la cuenta nueva ---
git clone -b claude/backlinks-seo-tool-study-2tlk0x https://github.com/Teoremadepierre/Draken.git
cd Draken
bash scripts/empezar.sh        # arranca; Ctrl+C cuando veas que sube
cp ~/Descargas/draken-env.txt .env && chmod 600 .env
.venv/bin/draken import ~/Descargas/draken-copia.json
bash scripts/empezar.sh        # otra vez, ya con todo dentro
```

Notas:

- El fichero de export **no lleva claves ni contraseñas**: solo el trabajo
  (proyectos, keywords, clústeres, backlinks, oportunidades con su estado,
  campañas, envíos, prompts de IA). Por eso el `.env` se copia aparte.
- `draken import` reasigna todos los identificadores y vuelve a resolver las
  fuentes del catálogo por su `slug`, así que la instalación de destino puede
  estar recién hecha.
- Alternativa perezosa si es el mismo ordenador y el mismo disco: copiar la
  carpeta entera incluyendo `data/draken.db` y `.env`, y borrar `.venv` (se
  regenera). Funciona, pero deja permisos de la otra cuenta; hay que hacer
  `chown -R tuusuario .`.
- **Borra las copias intermedias** cuando termines: `draken-env.txt` contiene
  tus claves en claro.

---

## 8. Publicar (si se quiere URL pública)

| Camino | Fichero | Resultado |
|---|---|---|
| VPS propio | `install.sh` | `https://tudominio.com`, systemd + Caddy + HTTPS + cron semanal |
| Render (gratis) | `render.yaml` → `docs/RENDER.md` | `https://draken-xxx.onrender.com` |
| Fly.io | `fly.toml` | `https://draken.fly.dev` |
| Railway | `railway.json` | URL de Railway |
| Túnel temporal | `cloudflared tunnel --url http://localhost:8000` | URL temporal sin servidor |
| Docker | `Dockerfile`, `docker-compose.yml`, `deploy/entrypoint.sh` | lo que montes |

Guías: `docs/PUBLICAR.md` (todas las opciones), `docs/RENDER.md` (gratis, clic a
clic), `docs/EMPEZAR.md` (solo en tu ordenador).

Contexto que ahorra tiempo: **el hosting compartido tipo Hostinger no sirve**
para esto. Draken necesita un proceso Python vivo escuchando en un puerto, y un
plan compartido mata los procesos de fondo y no deja abrir puertos.
`scripts/check-hosting.sh` lo comprueba en un minuto, solo leyendo, sin pedir
credenciales a nadie.

---

## 9. Errores ya corregidos — no los reintroduzcas

Cada uno costó su rato de depuración y todos tienen prueba de regresión:

- `normalize_domain("127.0.0.1")` devolvía `"0.1"`. Las IP y los literales IPv6
  se detectan antes de aplicar la lógica de dominio público.
- Una URL vacía o de espacios se convertía en `"/"` y se aceptaba como dominio:
  un escaneo en blanco creaba proyecto. Ahora se exige al menos un carácter
  alfanumérico.
- TLD desconocidos: `www.a.example` no era lo mismo que `a.example`. Reserva a
  las dos últimas etiquetas.
- `sqlite:///:memory:` se resolvía a ruta y creaba un fichero llamado
  literalmente `:memory:` dentro del repo.
- El CSS pisaba el atributo `[hidden]`, así que un backdrop de modal invisible
  se comía **todos** los clics del panel. Hay una regla global
  `[hidden] { display: none !important; }`: no la quites.
- El clustering colapsaba 156 keywords en 2 grupos (el coeficiente de solape
  dejaba que una firma de un token se lo tragara todo). Reescrito con firmas de
  tokens núcleo + fusión por Jaccard.
- Los modificadores se comparaban sin stemmizar contra tokens stemmizados, así
  que "gratis" nunca casaba y se colaba en las etiquetas.
- Borrar clústeres violaba la FK porque las keywords seguían apuntando. Se
  desenganchan primero, y la FK es `ondelete="SET NULL"`.
- Los logs iban a stdout y corrompían el JSON de la CLI.
- `import_project` perdía el `source_id` de todas las oportunidades cuando la
  instalación de destino no tenía catálogo cargado. Ahora lo carga antes de
  resolver los slugs.
- Teléfonos: `+34 910...` y `0034 910...` se trataban como distintos al comparar
  citaciones. Se comparan los últimos 9 dígitos.

---

## 10. Qué queda por hacer

Nada bloqueante. Ideas por orden de valor, no por orden de dificultad:

1. **Verificación automática de altas.** Hoy `submissions` prepara el alta y
   genera el guion; comprobar que el enlace apareció se hace a mano o con
   `verify_submissions`. Falta cerrar el bucle con reintentos sensatos.
2. **Histórico de visibilidad en IA.** Se guardan las respuestas, pero no hay
   vista de evolución temporal como la de posiciones.
3. **Migraciones de esquema.** Hoy es `create_all`. En cuanto haya datos reales
   en producción, esto quiere Alembic.
4. **Export incremental.** El actual es completo; para bases grandes conviene
   exportar por rango de fechas.
5. **Más fuentes en el catálogo.** 355 es un buen comienzo; el generador está
   hecho para crecer por sectores y países (edita
   `scripts/build_link_source_seed.py`).
6. **Fusionar la rama a `main`** cuando el proyecto se dé por estable.

---

## 11. Antes de cada commit

```bash
pytest backend/tests -q          # 204 en verde
ruff check backend/ scripts/     # limpio
```

Y si tocaste el panel, ábrelo y haz clic: hay bugs de interfaz que ninguna
prueba de Python ve (el del backdrop invisible es el ejemplo perfecto).

Git: se trabaja en `claude/backlinks-seo-tool-study-2tlk0x`, se empuja con
`git push -u origin claude/backlinks-seo-tool-study-2tlk0x`. Mensajes de commit
que expliquen **por qué**, no qué; el qué ya está en el diff.

---

## 12. Índice de documentación

| Fichero | Para qué |
|---|---|
| `CLAUDE.md` | Reglas cortas del repo. Léelo siempre. |
| `README.md` | Qué hace y cómo se arranca. |
| `docs/EMPEZAR.md` | Correrlo en tu ordenador (Mac, Linux, Windows, Docker). |
| `docs/PUBLICAR.md` | Conseguir una URL. Todas las opciones. |
| `docs/RENDER.md` | La opción gratuita, clic a clic. |
| `docs/ARQUITECTURA.md` | Por qué está montado así. |
| `docs/DESPLIEGUE.md` | Detalle de servidor: systemd, nginx, Caddy, cron. |
| `docs/ESTUDIO-BACKLINKS.md` | El estudio de fondo: qué funciona en enlaces y qué no, y por qué. 454 líneas. |
| `docs/VISIBILIDAD-IA.md` | Cómo se aparece recomendado en ChatGPT, Claude y Perplexity. |
| `docs/GUIA-VISUAL.md` | Guía para principiantes, pantalla por pantalla. |
| `docs/GUION-VIDEO.md` | Guion listo para grabar un vídeo de demostración. |
| `docs/HANDOFF-IA.md` | Este fichero. |
