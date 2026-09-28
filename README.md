# Draken SEO Suite

Plataforma SEO autoalojada: investigación de keywords, auditoría técnica,
seguimiento de posiciones, análisis de backlinks, **un motor de adquisición de
enlaces con 355 fuentes gratuitas catalogadas**, y **medición de visibilidad en
asistentes de IA**.

Un proceso, un puerto, sin paso de compilación. Funciona sin ninguna clave de
API; cada clave que añades sustituye una estimación por un dato real.

---

## Arranque rápido

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e "backend[dev]"

cp .env.example .env
draken init-db          # tablas + catálogo de 355 fuentes
draken serve            # http://127.0.0.1:8000
```

O con Docker:

```bash
docker compose up -d
```

Abre el panel, crea un proyecto con tu dominio y Draken puntúa inmediatamente
las 355 fuentes del catálogo para ese dominio concreto, dejándote una cola de
oportunidades ordenada por prioridad.

---

## Qué hace

### Investigación
- **Keywords.** Expansión desde semillas usando los endpoints de autocompletado
  públicos, con estimadores explicables de volumen, dificultad y oportunidad, y
  clasificación de intención. Cada volumen lleva su nivel de confianza.
- **Clústeres y mapa de temas.** Agrupación determinista por tokens núcleo, con
  el tipo de página recomendado para cada clúster y la estructura pilar/apoyo
  para el enlazado interno.
- **Posiciones.** Seguimiento con histórico, índice de visibilidad, distribución
  de posiciones y destacado de las keywords a tiro (11-20).
- **Gap de keywords.** Dónde posiciona la competencia y tú no.

### Sitio
- **Auditoría técnica.** Rastreador que obedece `robots.txt` y `Crawl-delay`,
  con ~25 reglas agrupadas por tipo (37 páginas sin título, no 37 filas) y una
  puntuación de salud ponderada por gravedad.
- **Análisis on-page.** Puntúa una URL contra una keyword objetivo y devuelve
  cambios concretos, no una nota.

### Backlinks
- **Perfil.** Dominios de referencia, autoridad, reparto de anchors contra rangos
  sanos, velocidad de ganados/perdidos, y toxicidad con el motivo de cada punto.
- **Descubrimiento.** Verificación por rastreo real (lee el `rel` y el anchor de
  la página), búsqueda de menciones, reconocimiento de la competencia, Common
  Crawl e importación de CSV de cualquier herramienta.
- **Oportunidades.** Catálogo de 355 fuentes puntuado para tu proyecto, más link
  intersect contra competidores y menciones sin enlace.
- **Envíos.** Prepara cada alta con los datos de tu ficha canónica y genera un
  guion listo para pegar. Con simulación, aprobación y topes diarios.
- **Outreach.** 13 plantillas, búsqueda de contactos, y borradores que marcan
  explícitamente los huecos que solo una persona puede rellenar.

### Visibilidad en IA (GEO)
- Conjuntos de preguntas que escribiría un comprador real, en español o inglés.
- Medición en Anthropic, OpenAI, Perplexity y Gemini.
- Tasa de mención, posición, tasa de cita, competidores nombrados y tono.
- **Qué dominios cita cada motor**: tu lista de objetivos de enlaces para IA.
- Generadores de `llms.txt` y JSON-LD, y comprobación de consistencia de entidad.

---

## Documentación

| Documento | Contenido |
|---|---|
| **[Estudio de backlinks](docs/ESTUDIO-BACKLINKS.md)** | El documento estratégico: modelo de tres niveles, catálogo de tácticas con conversiones realistas, estrategia de anchors, qué no hacer y por qué, y un plan de 90 días |
| **[Visibilidad en IA](docs/VISIBILIDAD-IA.md)** | Cómo funciona realmente que un asistente te recomiende, las siete palancas por impacto, y un plan de 30 días |
| **[Arquitectura](docs/ARQUITECTURA.md)** | Estructura, decisiones de diseño y modelo de datos |
| **[Despliegue](docs/DESPLIEGUE.md)** | Local, Docker y VPS propio con nginx, systemd y cron |

---

## El catálogo de fuentes

355 sitios donde conseguir enlaces y citaciones gratis, en 19 categorías:

| Categoría | Nº | Ejemplos |
|---|---|---|
| Citaciones locales | 111 | Páginas Amarillas, QDQ, 11870, Yell, Gelbe Seiten, JustDial |
| Directorios | 47 | Directorios de IA, verticales de salud, legal, inmobiliaria |
| Perfiles sociales | 25 | LinkedIn, YouTube, Reddit, Medium, Crunchbase |
| Perfiles de desarrollador | 22 | GitHub, Stack Overflow, PyPI, npm, Hugging Face |
| Listados de producto | 20 | Product Hunt, AlternativeTo, SaaSHub, BetaList |
| Marketplaces | 20 | WordPress.org, Zapier, Chrome Web Store, Shopify |
| Plataformas de reseñas | 15 | G2, Capterra, Trustpilot, Clutch |
| Datos y académico | 14 | arXiv, Zenodo, Kaggle, Hugging Face Datasets |
| …y 11 categorías más | | agregadores, blogs, comunidades, prensa, podcasts, wiki |

Cada fuente lleva autoridad, tipo de enlace, esfuerzo (1-5), si es automatizable,
países, sectores, campos requeridos y **peso de citación en IA**.

Es un fichero JSON editable: `data/seeds/link_sources.json`. Añade las tuyas y
pulsa "Recargar catálogo". Se regenera con
`python3 scripts/build_link_source_seed.py`.

---

## Línea de comandos

Todo lo del panel está disponible sin navegador, para cron:

```bash
draken project add --name "Acme" --domain acme.com --country ES --language es \
                   --industry software --competitor competidor.com
draken keywords research 1 "software seo" "herramienta de keywords"
draken keywords track 1
draken audit 1 --max-pages 200
draken opportunities generate 1
draken opportunities prospect 1
draken submissions prepare 1 --limit 20
draken ai generate-prompts 1
draken ai run 1
draken ai assets 1 --llms-txt
draken sweep 1                    # todo lo anterior, para cron semanal
draken report 1                   # informe completo en JSON
```

---

## Sobre la automatización de enlaces

Draken automatiza **encontrar, puntuar, preparar y verificar**. No automatiza
crear cuentas falsas, resolver CAPTCHAs, rotar IPs, hilar contenido ni comprar
enlaces.

La razón no es solo ética: esas técnicas comparten la propiedad de ser baratas a
escala, que es exactamente lo que buscan los sistemas de detección. Lo que sí
hace Draken es convertir un trabajo de 20 minutos por enlace en uno de 2-3
minutos, dejando a la persona solo la parte que requiere criterio.

El razonamiento completo está en la
[sección 7 del estudio de backlinks](docs/ESTUDIO-BACKLINKS.md#7-lo-que-no-vamos-a-hacer-y-por-qué).

Los límites están en el servidor, no en la interfaz:

| Límite | Por defecto |
|---|---|
| Simulación (no envía nada) | Activada |
| Aprobación humana por envío | Requerida |
| Envíos por dominio y día | 1 |
| Envíos totales por día | 25 |
| Envío de emails | Desactivado |
| Obedecer `robots.txt` | Sí |

---

## Desarrollo

```bash
pip install -e "backend[dev]"
pytest backend/tests -q        # 130 pruebas, ninguna necesita internet
ruff check backend/ scripts/
```

Las pruebas de integración levantan un sitio de pruebas con defectos plantados
sobre HTTP real y comprueban que la auditoría detecta cada uno.

---

## Notas

- **El idioma del panel** es español por defecto, con conmutador a inglés. El
  texto de análisis que generan los motores (recomendaciones, descripciones de
  problemas, guiones de envío) está en inglés.
- **Las estimaciones se marcan como estimaciones.** Sin un proveedor de SERP de
  pago, las posiciones vienen de un motor gratuito y el panel lo indica. El
  volumen de búsqueda lleva siempre su nivel de confianza.
- **Es una herramienta interna.** Está pensada para un equipo detrás de tu propio
  proxy, no como SaaS multiinquilino. Activa la autenticación si es accesible
  desde fuera.
