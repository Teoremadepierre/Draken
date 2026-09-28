# Estudio profundo de backlinks: de cero a un perfil de enlaces defendible

> Documento estratégico de Draken. Se lee una vez entero y después se usa como
> referencia. El plan operativo está en la sección 9 (plan de 90 días).

**Punto de partida asumido:** el sitio tiene **cero backlinks**. Ese es un dato
importante, porque cambia completamente el orden de las prioridades. Casi todo
el contenido que se publica sobre link building está escrito para sitios que ya
tienen un perfil; empezar desde cero tiene una secuencia distinta y mucho más
barata.

---

## 1. Qué es realmente un backlink y por qué sigue importando

Un enlace es, en su origen, un voto de confianza de un editor hacia un recurso.
Los buscadores lo usan como señal porque es costoso de falsificar a escala sin
dejar huella. Todo el juego del link building consiste en esa tensión: **el
enlace vale precisamente porque cuesta conseguirlo**. Cualquier método que lo
haga trivialmente barato destruye su valor y, antes o después, se detecta.

En 2026 el enlace ya no es el único factor dominante, pero sigue siendo:

1. **La señal de descubrimiento.** Sin enlaces externos, una página nueva depende
   exclusivamente del sitemap para ser rastreada, y se rastrea con baja
   frecuencia.
2. **La señal de autoridad de dominio.** Un dominio sin enlaces entrantes tiene
   un techo de posicionamiento muy bajo para términos comerciales, por bueno que
   sea el contenido.
3. **La señal de entidad.** Los enlaces y las menciones consistentes son lo que
   permite a un buscador (y a un modelo de lenguaje) decidir que "Acme",
   "Acme SEO" y `acme.com` son la misma cosa.
4. **Tráfico real.** El mejor enlace es el que trae clientes aunque no aporte
   ningún valor de ranking. Ese criterio, por sí solo, filtra el 90% de las malas
   decisiones.

### Lo que no es

No es un número que haya que subir. Un perfil de 500 enlaces de directorios
basura rinde peor que 30 enlaces de sitios reales del sector, y además introduce
riesgo. La métrica que importa no es "enlaces" sino **dominios de referencia
relevantes y vivos**.

---

## 2. Qué determina el valor de un enlace

Cinco factores, en orden aproximado de peso:

### 2.1 Relevancia temática
Un enlace desde un blog de repostería hacia una empresa de software SEO no
transmite casi nada, por muy alto que sea su DA. La relevancia se evalúa a tres
niveles: dominio, página y párrafo. Un enlace en un párrafo que habla
literalmente de tu problema vale más que uno en una lista de 200 recursos.

**En Draken:** el factor `relevance` del scoring (peso 0,24) cruza país, idioma
y sector del proyecto contra los metadatos de cada fuente. Un directorio vertical
de tu propio sector sube fuerte; uno de otro sector baja.

### 2.2 Autoridad del dominio de origen
Aproximación al PageRank acumulado. Útil como filtro grueso, peligroso como
criterio único: un DA 80 en una página huérfana con 300 enlaces salientes
transmite menos que un DA 40 en un artículo editorial con tres.

**En Draken:** `authority` (peso 0,30). Si configuras `DRAKEN_OPENPAGERANK_KEY`
se usa un dato medido; si no, una estimación estructural explicable (TLD,
longitud del dominio, guiones, cifras, tabla de dominios conocidos).

### 2.3 Colocación y tipo
- **Editorial en el cuerpo del texto:** máximo valor.
- **Ficha de directorio:** valor bajo pero estable y sin riesgo.
- **Footer o sidebar sitewide:** valor muy bajo y, si es comercial, señal de
  enlace pagado.
- **Comentario o firma de foro:** prácticamente nulo.

El atributo `rel` decide si transmite equity: `dofollow` sí; `nofollow`, `ugc` y
`sponsored` no lo transmiten, aunque **sí** cuentan como señal de marca y
aparecen en los corpus que leen los modelos de lenguaje.

**En Draken:** `follow` (peso 0,14). El perfil de enlaces distingue los cuatro
tipos y calcula el ratio dofollow.

### 2.4 Texto ancla
Es la señal más fácil de manipular y por tanto la más vigilada. Ver sección 5.

### 2.5 Evidencia de obtenibilidad
Si tres competidores tienen un enlace desde un dominio y tú no, ese enlace es
**demostrablemente** alcanzable para un sitio como el tuyo. Es el dato más
accionable de todo el análisis competitivo.

**En Draken:** `evidence` (peso 0,16), alimentado por el link intersect.

---

## 3. El modelo de tres niveles

Desde cero, el error más común es empezar por donde hay que terminar: escribir
correos a editores pidiendo enlaces cuando el sitio todavía no existe como
entidad. La secuencia correcta tiene tres niveles y hay que recorrerlos en orden.

### Nivel 1 — Fundación (semanas 1-4, ~30-60 dominios)

Fichas, perfiles y citaciones que **te corresponden por existir**. No hay que
convencer a nadie: hay que rellenar formularios correctamente.

| Grupo | Ejemplos | Esfuerzo | Tipo |
|---|---|---|---|
| Perfiles de mapa y negocio | Google Business Profile, Bing Places, Apple Business Connect | 2-3 | nofollow |
| Perfiles de marca | LinkedIn, X, YouTube, Facebook, Crunchbase | 2 | nofollow |
| Perfiles de desarrollador | GitHub, Stack Overflow, PyPI, npm, Dev.to | 1-2 | mixto |
| Directorios de nicho | Directorios de IA, SaaSHub, AlternativeTo, Product Hunt | 2-4 | mayoría dofollow |
| Citaciones locales | Páginas Amarillas, QDQ, 11870, Cylex, Hotfrog | 2 | mixto |
| Marketplaces de integración | WordPress.org, Zapier, Chrome Web Store, Shopify | 4-5 | mayoría dofollow |
| Plataformas de reseñas | G2, Capterra, Trustpilot, Clutch | 3 | mixto |

**Por qué primero:** son gratis, no se pierden, construyen la entidad, y —esto
es lo importante— los modelos de lenguaje leen precisamente estas fuentes cuando
alguien pregunta "¿cuál es el mejor X?".

**El riesgo real de este nivel no es la penalización, es la inconsistencia.**
Crear 40 fichas con el nombre, el teléfono o la dirección ligeramente distintos
es peor que no crearlas: impide que el grafo de conocimiento consolide la
entidad. Por eso Draken bloquea la preparación de envíos si la ficha de empresa
está por debajo del 50% de completitud.

### Nivel 2 — Prueba (semanas 4-10, ~10-30 dominios)

Enlaces que existen porque **alguien te ha usado o mencionado**. Ya no rellenas
formularios: recuperas o pides algo que está justificado.

- **Menciones sin enlace.** Alguien ya escribió tu nombre sin enlazar. Es la
  táctica con mayor tasa de conversión que existe (habitualmente 30-50%): un
  correo de cuatro líneas y ya está.
- **Proveedores, clientes y socios.** Páginas de "trabajamos con", casos de
  estudio, listados de integraciones, testimonios. Relación comercial existente
  = conversión alta.
- **Enlaces rotos.** Encuentras un 404 en una página relevante, publicas el
  sustituto, avisas. Conviertes bien porque resuelves un problema suyo.
- **Plataformas de peticiones de periodistas** (Featured, Qwoted, SourceBottle).
  Lento, pero produce enlaces editoriales en dominios inalcanzables de otro modo.

### Nivel 3 — Editorial (mes 3 en adelante, continuo)

Enlaces que hay que **merecer**. Es el único nivel que escala sin techo y el
único que no se puede automatizar.

- **Estudio de datos original.** Encuestas, análisis de un dataset propio,
  benchmarks reproducibles. Un solo estudio bueno al trimestre supera un año
  entero de altas en directorios. Es también lo único que hace que te citen como
  **fuente** en vez de mencionarte de pasada.
- **Herramienta gratuita.** Una calculadora, un validador, un generador. Se
  enlaza sola y durante años.
- **Artículos como invitado, de verdad.** En sitios con estándares editoriales
  reales y lectores reales. No en granjas que venden "guest post 50€".
- **Páginas de recursos.** Listas curadas del sector que ya enlazan hacia fuera.

---

## 4. Catálogo de tácticas con expectativas realistas

Estas cifras son órdenes de magnitud a partir de la experiencia habitual del
sector. Úsalas para planificar, no como promesa.

| Táctica | Conversión típica | Esfuerzo/enlace | Tipo | Riesgo |
|---|---|---|---|---|
| Recuperación de menciones sin enlace | 30-50% | 10 min | dofollow | Nulo |
| Fichas y perfiles de marca | 85-95% | 10-20 min | mixto | Nulo |
| Citaciones locales | 70-90% | 10 min | mixto | Nulo |
| Directorios de nicho | 40-70% | 15 min | mayoría dofollow | Bajo |
| Marketplaces de integración | 50-80% | 2-8 h | mayoría dofollow | Nulo |
| Plataformas de reseñas | 60-80% | 1-2 h | mixto | Nulo |
| Socios / clientes / proveedores | 25-40% | 30 min | dofollow | Nulo |
| Enlaces rotos | 5-12% | 45 min | dofollow | Nulo |
| Páginas de recursos | 3-8% | 40 min | dofollow | Nulo |
| Invitado en podcast | 10-20% | 3-5 h | dofollow | Nulo |
| Artículo como invitado | 5-15% | 6-12 h | dofollow | Medio* |
| Estudio de datos / PR digital | n/a (1 estudio → 5-50 enlaces) | 40-120 h | dofollow | Nulo |
| Peticiones de periodistas | 5-15% | 20 min/respuesta | dofollow | Nulo |
| Patrocinio local | 60-80% | 2 h + coste | dofollow | Bajo |

\* Riesgo medio solo si el sitio destino es una granja de contenidos. En un medio
editorial real el riesgo es nulo.

**Lectura del cuadro:** las dos primeras filas son donde debe ir todo tu tiempo
el primer mes. La última fila (estudio de datos) es donde debe ir tu tiempo a
partir del tercer mes. Lo del medio es relleno útil.

---

## 5. Texto ancla: la única parte donde te puedes hacer daño solo

El reparto de anchors es la señal de manipulación más fácil de detectar
automáticamente, porque un perfil natural tiene una forma muy reconocible: la
gente enlaza usando tu **nombre** o la **URL**, no usando tu keyword objetivo.

### Reparto objetivo

| Categoría | Rango sano | Ejemplo |
|---|---|---|
| Marca | 40-65% | "Acme", "Acme SEO" |
| URL desnuda | 10-25% | "acme.com", "https://acme.com" |
| Genérico | 5-20% | "aquí", "más información", "ver web" |
| Coincidencia parcial | 5-20% | "la herramienta SEO de Acme" |
| Coincidencia exacta | **0-8%** | "software seo" |
| Imagen / vacío | 0-10% | (alt de la imagen) |

**En Draken:** la vista *Perfil de enlaces → Anchors* pinta tu reparto real
contra estos rangos, con la marca gris indicando el máximo sano.

### Reglas operativas

1. **Toda ficha de directorio lleva anchor de marca.** Sin excepción. Draken lo
   impone: `suggest_anchor()` devuelve siempre la marca para las categorías de
   listado. Un directorio con anchor de coincidencia exacta es una huella obvia.
2. **La coincidencia exacta solo se usa en enlaces editoriales**, y solo si el
   perfil todavía tiene hueco. Draken comprueba el reparto actual antes de
   sugerirla.
3. **No se corrige hacia atrás.** Si tienes exceso de anchors exactos, no
   persigas a los editores para cambiarlos: diluye con los siguientes 30 enlaces.
   Perseguir cambios deja un rastro peor que el problema.
4. **El anchor lo decide quien enlaza.** En outreach editorial, sugerir el anchor
   está bien; exigirlo es lo que convierte un enlace ganado en un enlace pagado a
   ojos de las directrices.

---

## 6. Velocidad: qué ritmo es natural

No existe un número mágico de "enlaces por mes". Lo que se detecta no es el
volumen sino la **incoherencia entre el volumen y el resto de señales**.

Sano:
- Un sitio sin tráfico, sin marca y sin contenido que gana 400 dominios en un
  mes es incoherente.
- Un sitio que acaba de lanzar y consigue 40 fichas y perfiles en dos semanas es
  perfectamente normal: es lo que hace cualquier empresa nueva.
- Un pico tras un lanzamiento, una ronda de financiación o un estudio viral es
  normal, porque va acompañado de un pico de menciones y de búsquedas de marca.

**Regla práctica:** que el crecimiento de enlaces no supere mucho al crecimiento
de las búsquedas de tu marca. Si nadie te busca por el nombre pero 200 sitios te
enlazan, la incoherencia es el problema, no el número.

**En Draken:** la vista de perfil incluye un gráfico de velocidad (ganados y
perdidos por mes) durante 12 meses.

---

## 7. Lo que no vamos a hacer, y por qué

Esta sección existe porque la petición original era "generar backlinks
automáticamente", y hay que ser explícito sobre dónde está la línea.

### 7.1 Lo que Draken automatiza

- **Descubrir y puntuar** oportunidades (355 fuentes del catálogo + prospección
  desde la competencia + menciones sin enlace).
- **Preparar** cada envío: rellenar los datos desde tu ficha canónica, elegir el
  anchor coherente con tu reparto actual, y generar un guion listo para pegar.
- **Ejecutar** envíos por formulario HTTP en las fuentes que tienen un mapeo de
  campos verificado, con simulación por defecto, aprobación humana y límites
  diarios por dominio y globales.
- **Verificar** después: visitar la ficha publicada, leer el anchor y el `rel`
  reales, e indexar el enlace en tu perfil.
- **Vigilar**: re-comprobar los enlaces existentes y avisar de los que se pierden.
- **Redactar** el outreach personalizado, dejando marcados los huecos que solo
  una persona puede rellenar.

### 7.2 Lo que Draken no hace, deliberadamente

| No hace | Por qué |
|---|---|
| Resolver CAPTCHAs | Es una medida antiabuso explícita. Saltársela es incumplir los términos del sitio y además rompe cada pocas semanas. |
| Crear cuentas con identidades falsas | Convierte una ficha legítima en fraude de suplantación. |
| Rotar IPs o navegadores para ocultar el origen | Evasión de detección. Si hace falta ocultarse, la táctica no era legítima. |
| Publicar comentarios o firmas en foros a escala | Valor cero, riesgo alto, y es spam para las comunidades. |
| Hilar o duplicar contenido para web 2.0 | Es el patrón exacto que buscan los sistemas antispam. |
| Comprar enlaces o participar en esquemas de intercambio | Violación directa de las directrices, con penalización manual como resultado típico. |
| Montar o usar PBNs | Es la técnica con mayor probabilidad de acabar en desindexación. |

La razón práctica, más allá de la ética: **todas estas técnicas comparten la
propiedad de ser baratas a escala**, y esa es exactamente la propiedad que los
sistemas de detección buscan. Una plataforma que las implementara sería una
plataforma que te mete en problemas de forma eficiente.

### 7.3 La consecuencia honesta

No existe un botón que genere 500 backlinks de calidad. Lo que sí existe —y es
lo que Draken construye— es un sistema que:

- elimina el trabajo de **encontrar** dónde conseguir enlaces,
- elimina el trabajo de **decidir** cuál merece la pena primero,
- elimina el trabajo de **preparar** cada envío,
- y deja para la persona solo la parte que requiere juicio: el contenido del
  mensaje y la decisión de enviarlo.

Eso convierte un trabajo de 20 minutos por enlace en uno de 2-3 minutos. Es una
mejora de 7-10x, que es mucho. No es infinito, y quien prometa lo contrario está
vendiendo el riesgo como si fuera un producto.

---

## 8. Cómo encaja con la visibilidad en IA

Los asistentes de IA no "posicionan" páginas: nombran entidades y citan fuentes.
Los enlaces importan, pero de otra forma.

- **Las menciones sin enlace valen.** Un modelo que ha leído tu nombre junto a tu
  categoría en Reddit, Stack Overflow o G2 te nombrará aunque no haya enlace.
- **Los corpus concretos pesan mucho más que la web media.** Wikipedia, Wikidata,
  Reddit, Stack Overflow, GitHub, plataformas de reseñas y repositorios de datos
  aparecen desproporcionadamente como fuentes.
- **Ser citado > ser mencionado.** Que el asistente enlace tu dominio como fuente
  es lo que trae tráfico y lo que se sostiene.

**En Draken:** cada fuente del catálogo lleva `llm_citation_weight` (0-1) y
`ai_training_signal`. El scoring da un bonus por ambos, así que las fuentes que
alimentan respuestas de IA suben en la cola sin que tengas que acordarte.

El estudio completo está en [VISIBILIDAD-IA.md](VISIBILIDAD-IA.md).

---

## 9. Plan de 90 días

Suponiendo una persona dedicando unas 6-8 horas semanales.

### Semanas 1-2 — Cimientos (objetivo: 0 → 25 dominios)

1. Crear el proyecto en Draken con dominio, país, idioma, sector y competidores.
2. **Rellenar la ficha de empresa al 100%.** Todo lo demás depende de esto. El
   nombre, el teléfono y la dirección que pongas aquí se copiarán a 40 sitios.
3. Ejecutar la auditoría del sitio y arreglar los problemas *critical* y *error*.
   Conseguir enlaces hacia un sitio roto es tirar el trabajo.
4. Investigar keywords desde 2-5 semillas; reconstruir clústeres; asignar una URL
   objetivo a cada clúster.
5. Generar oportunidades filtrando por esfuerzo ≤ 2, y trabajar la lista:
   - todos los perfiles de mapa y negocio,
   - todos los perfiles de marca,
   - los perfiles de desarrollador que apliquen.
6. Generar el `llms.txt` y el JSON-LD, y publicarlos.

### Semanas 3-4 — Citaciones y nicho (objetivo: 25 → 45 dominios)

1. Citaciones locales del país objetivo (Draken las filtra por país).
2. Directorios de nicho y de IA: son mayoritariamente dofollow y aprueban rápido.
3. Reclamar perfiles en plataformas de reseñas y **pedir reseñas reales a
   clientes reales**. Esto vale doble: enlace y peso en respuestas de IA.
4. Marcar 20 keywords como seguidas y ejecutar el primer seguimiento de
   posiciones para tener línea base.
5. Generar el conjunto de preguntas de IA y ejecutar la primera medición.

### Semanas 5-8 — Prueba y recuperación (objetivo: 45 → 65 dominios)

1. Ejecutar *Menciones sin enlace* y trabajar la lista entera. Es lo que mejor
   convierte.
2. Ejecutar *Link intersect* contra los competidores. Empezar por los dominios
   que enlazan a **dos o más** competidores.
3. Contactar a proveedores, clientes y socios para listados e integraciones.
4. Publicar la primera pieza que merezca enlaces: una herramienta gratuita, una
   plantilla o una guía que no exista ya mejor hecha.
5. Registrarse en plataformas de peticiones de periodistas y responder 2-3 por
   semana.

### Semanas 9-12 — Editorial (objetivo: 65 → 85 dominios y subiendo)

1. **Lanzar un estudio de datos original.** Es la acción de mayor retorno de todo
   el trimestre. Un dataset propio, publicado en tu dominio, con metodología
   reproducible.
2. Difundirlo: peticiones de periodistas, contacto con medios del sector,
   publicación en repositorios de datos (Zenodo, Kaggle, Hugging Face).
3. Buscar apariciones en podcasts del sector.
4. Trabajar páginas de recursos y enlaces rotos con el asset nuevo como gancho.
5. Re-medir todo: posiciones, perfil de enlaces, visibilidad en IA. Comparar con
   la línea base de la semana 4.

### A partir del día 90

Cadencia mensual estable:
- Re-verificar enlaces y recuperar los perdidos (más barato que ganar nuevos).
- Un contenido enlazable al mes.
- Un estudio de datos al trimestre.
- Revisar el reparto de anchors antes de cada campaña.
- Re-medir la visibilidad en IA semanalmente (cambia mucho más rápido que las
  posiciones).

---

## 10. Medición: qué mirar y qué ignorar

### Mirar

| Métrica | Dónde en Draken | Por qué |
|---|---|---|
| Dominios de referencia vivos | Perfil de enlaces | Es *la* métrica de link building |
| Reparto de anchors vs. rangos sanos | Perfil → Anchors | Único riesgo autoinfligido |
| Enlaces perdidos | Perfil → velocidad | Recuperar es más barato que ganar |
| Keywords en posiciones 11-20 | Posiciones | Donde un cambio pequeño rinde más |
| Tasa de mención y de cita en IA | Visibilidad en IA | El canal que más rápido crece |
| Tasa de conversión del pipeline | Oportunidades | Te dice qué táctica funciona *para ti* |

### Ignorar

- **El número total de enlaces.** Mide dominios, no enlaces.
- **Las métricas de autoridad de terceros como objetivo.** Son estimaciones de
  terceros, no señales de Google. Útiles para comparar, inútiles como KPI.
- **Los movimientos diarios de posición.** Ruido. Mira tendencias de 4 semanas.
- **El volumen de búsqueda como número exacto.** Sirve para ordenar la lista, no
  para prever tráfico. Draken muestra la confianza de cada estimación por eso.

---

## 11. Especificidades del mercado español y LatAm

El catálogo de Draken incluye 111 citaciones locales, de las cuales una parte
sustancial cubre España y Latinoamérica.

- **España:** Páginas Amarillas, QDQ, 11870, Axesor, Infoempresa, Empresite,
  eInforma, SoloStocks, Habitissimo, Cylex ES, Guíalocal, Europages.
- **México:** Sección Amarilla, Amarillas Internet, Locanto.
- **Colombia, Argentina, Chile, Perú:** Páginas Amarillas CO/PE, Dateas,
  Guíalocal AR, Yapo CL.
- **Verticales en español:** Doctoralia y Top Doctors (salud), Idealista y
  Fotocasa (inmobiliaria), Habitissimo (reformas).

Tres observaciones prácticas:

1. **El NAP en español se estropea con facilidad.** Acentos, "C/" frente a
   "Calle", el prefijo +34 escrito de cinco maneras. Draken normaliza los
   teléfonos comparando los últimos nueve dígitos, pero tú tienes que escribirlo
   igual en todas partes.
2. **Los directorios locales españoles aprueban más despacio** que los
   internacionales: dos o tres semanas es normal. No los des por perdidos.
3. **Para proyectos en español, genera el conjunto de preguntas de IA en
   español.** Los asistentes dan respuestas distintas según el idioma de la
   pregunta, y la competencia suele ser mucho menor en español.

---

## 12. Resumen ejecutable

Si solo te llevas cinco ideas:

1. **Con cero enlaces, el nivel 1 (fichas y perfiles) es todo tu trabajo el
   primer mes.** Es gratis, es seguro y construye la entidad.
2. **La ficha de empresa se rellena una vez y bien.** Se copia a 40 sitios; los
   errores se multiplican por 40.
3. **Las menciones sin enlace son la táctica con mejor conversión.** Ejecútalas
   antes que cualquier outreach en frío.
4. **Los anchors de las fichas son siempre de marca.** Es la única regla del
   documento que no tiene excepciones.
5. **A partir del mes tres, un estudio de datos original vale más que todo lo
   demás junto** — y es también lo único que hace que los asistentes de IA te
   citen como fuente en lugar de mencionarte de pasada.
