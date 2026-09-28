# Visibilidad en IA (GEO): cómo conseguir que los asistentes te recomienden

> *Generative Engine Optimization*. El canal que más rápido está creciendo y
> donde menos competencia hay todavía, sobre todo en español.

---

## 1. Por qué esto es un problema distinto al SEO

En un buscador, el usuario ve diez resultados y elige. En un asistente, el
usuario ve **una respuesta** que nombra dos o tres opciones. La diferencia
práctica:

| SEO clásico | Visibilidad en IA |
|---|---|
| Compites por una posición | Compites por ser **nombrado** |
| 10 huecos por consulta | 2-4 huecos por respuesta |
| La página posiciona | La **entidad** se nombra |
| El contenido es el activo | La **reputación en terceros** es el activo |
| Cambia en semanas | Cambia en días |
| Se mide con rank tracking | Se mide preguntando |

La consecuencia más importante: **no puedes optimizar tu página para aparecer en
una respuesta de IA**. Lo que optimizas es lo que se dice de ti en las fuentes
que el modelo lee.

---

## 2. De dónde sale lo que dice un asistente sobre ti

Tres mecanismos distintos, con implicaciones distintas:

### 2.1 Conocimiento paramétrico (lo que el modelo "sabe")
Aprendido durante el entrenamiento, a partir de un corpus de web. Es lento de
cambiar —requiere un reentrenamiento— pero es lo que produce las respuestas
cuando el asistente no busca.

**Qué lo mueve:** presencia consistente y repetida en los corpus que dominan el
entrenamiento. En la práctica: Wikipedia, Wikidata, Reddit, Stack Overflow,
GitHub, plataformas de reseñas, prensa, y repositorios de datos y papers.

**Qué NO lo mueve:** publicar más contenido en tu propio blog.

### 2.2 Recuperación en tiempo real (RAG)
El asistente busca, lee unas páginas y responde citándolas. Es lo que hace
Perplexity siempre, y lo que hacen ChatGPT y Gemini cuando la consulta lo pide.

**Qué lo mueve:** que tu página sea encontrable (SEO clásico), rápida, y
estructurada de forma que un fragmento concreto responda a la pregunta.

### 2.3 Grafo de conocimiento
Datos estructurados sobre entidades. Alimenta tanto paneles de búsqueda como la
desambiguación del modelo.

**Qué lo mueve:** Wikidata, schema.org en tu sitio, y consistencia de NAP entre
todas tus fichas.

**La consecuencia estratégica:** los tres mecanismos se alimentan de sitios de
terceros, no de tu web. Tu web solo controla el tercero, y parcialmente.

---

## 3. Las siete palancas, por orden de impacto

### 1. Presencia en plataformas de reseñas (impacto muy alto, esfuerzo medio)
Cuando alguien pregunta "el mejor software de X", el modelo ha leído G2,
Capterra, Trustpilot y TrustRadius. Estar ahí con reseñas reales es la palanca
más directa que existe para consultas comerciales.

**Acción:** reclama el perfil en las cuatro, y pide reseñas a clientes reales.
No compres reseñas: además de ser fraude, los agregadores las detectan y
despublican el perfil entero.

### 2. Ítem en Wikidata (impacto muy alto, esfuerzo alto, requisitos estrictos)
Es la fuente estructurada más citada del mundo y alimenta directamente el grafo
de conocimiento.

**Requisito previo innegociable:** necesitas referencias independientes
verificables. Crear un ítem sin ellas termina en borrado y deja constancia.
Construye primero cobertura en prensa o publicaciones del sector; luego crea el
ítem.

**Sobre Wikipedia:** no te autocrees un artículo. La política de conflicto de
interés es explícita, la edición pagada no declarada está prohibida, y el efecto
de que te pillen es peor que no tener artículo. Draken lo lista con esfuerzo 5 y
la etiqueta `high-risk` precisamente para que quede registrado como objetivo a
largo plazo, no como tarea.

### 3. Participación real en Reddit y Stack Exchange (impacto alto, esfuerzo alto)
Son, medido por frecuencia de cita, dos de los corpus más presentes en las
respuestas. Una respuesta genuinamente buena que mencione tu producto donde
encaja sigue rindiendo años después.

**Acción:** gánate posición primero. Responde veinte preguntas sin mencionarte
antes de mencionarte una vez. El *self-promotion* descarado se elimina y quema
la cuenta.

### 4. Datos originales en tu dominio (impacto alto, esfuerzo alto)
Es la única forma fiable de que te **citen como fuente** en lugar de nombrarte de
pasada. Un modelo cita a quien tiene el dato, y el dato tiene que estar en algún
sitio.

**Acción:** publica un estudio, un benchmark o un dataset con metodología
reproducible. Súbelo también a Zenodo (con DOI), Hugging Face o Kaggle: esos
repositorios están fuertemente representados en los corpus.

### 5. Datos estructurados y `llms.txt` (impacto medio, esfuerzo bajo)
No te hace aparecer, pero hace que cuando aparezcas te describan correctamente.
Sin JSON-LD, el modelo infiere tu entidad de la prosa, y se equivoca.

**Acción:** Draken genera ambos en *Activos GEO*. El `llms.txt` va en la raíz del
sitio como `text/plain`; el JSON-LD en el `<head>` de todas las páginas.

### 6. Páginas de comparación explícitas (impacto medio, esfuerzo medio)
Los modelos citan con mucha más facilidad afirmaciones explícitas y
estructuradas que prosa de marketing. Una página que diga literalmente "Acme es
para equipos de menos de diez personas; si necesitas SSO y facturación por
departamento, X es mejor opción" es citable. "La solución líder del mercado" no
lo es.

**Acción:** publica comparativas honestas, incluyendo dónde **no** eres la mejor
opción. Es lo que hace que un modelo te recomiende con confianza para tu caso.

### 7. Consistencia de entidad (impacto medio, esfuerzo bajo)
El mismo nombre, teléfono, dirección y descripción en todas partes. Sin esto, el
sistema no consolida "Acme", "Acme SEO" y `acme.com` en una entidad.

**Acción:** *Activos GEO → Consistencia de entidad* compara tu ficha canónica
contra lo que dicen tus listados.

---

## 4. Cómo se mide en Draken

### El conjunto de preguntas
Draken genera las preguntas que **escribiría un comprador real**, no consultas de
marca. Cinco categorías:

| Categoría | Ejemplo | Para qué sirve |
|---|---|---|
| `discovery` | "¿Cuáles son las mejores herramientas de X en 2026?" | Donde se decide la compra |
| `comparison` | "Acme vs Competidor: ¿cuál es mejor para Y?" | Donde se pierde o se gana |
| `brand` | "¿Qué es Acme? ¿Es de fiar?" | Control de narrativa |
| `problem` | "¿Cómo hago X?" | Entrada al embudo |
| `local` | "¿Mejor X en Madrid?" | Solo si eres local |

Si solo mides preguntas de marca siempre parecerás visible, y no habrás medido
nada. Las de `discovery` son las que importan.

### Lo que se extrae de cada respuesta

- **¿Te menciona?** Con coincidencia por límite de palabra, y probando variantes
  del nombre (`competidor-dos.com` se escribe "Competidor Dos" en prosa).
- **¿En qué orden?** La posición entre las entidades nombradas es un buen proxy
  de la fuerza de la recomendación.
- **¿Cita tu dominio?** Perplexity devuelve sus fuentes explícitamente; en los
  demás se extraen las URLs del texto.
- **¿A qué competidores nombra?**
- **¿Con qué tono?** Positivo, neutro o negativo, en la ventana de texto
  alrededor de tu mención.

### La puntuación (0-100)

```
mencionado                    +34
  posición 1                  +26
  posición 2                  +18
  posición 3                  +12
  posición 4+                 +2 a +10
dominio citado como fuente    +30
tono positivo                 +10
tono negativo                 −14
nombrado entre 5+ rivales      −6
```

Ser **citado** pesa casi tanto como ser mencionado el primero, a propósito: la
cita es lo que trae tráfico y lo que se sostiene entre versiones del modelo.

### Motores soportados

| Motor | Variable | Nota |
|---|---|---|
| Anthropic | `DRAKEN_ANTHROPIC_API_KEY` | |
| OpenAI | `DRAKEN_OPENAI_API_KEY` | |
| Perplexity | `DRAKEN_PERPLEXITY_API_KEY` | **El más informativo**: devuelve sus fuentes |
| Google Gemini | `DRAKEN_GEMINI_API_KEY` | |

Cada motor es independiente: con uno configurado ya se mide, y los no
configurados se omiten sin romper la ejecución.

**Sobre AI Overviews de Google y la interfaz web de ChatGPT:** ninguno expone una
API soportada para su superficie de consumo. Draken mide las respuestas de los
modelos vía API oficial más Perplexity, que sí expone sus citas. Eso responde a
la pregunta que importa —"¿los asistentes me conocen y me recomiendan?"— sin
hacer scraping de productos cuyos términos lo prohíben.

---

## 5. El dato más accionable de todo el módulo

La vista *Visibilidad en IA → Resumen* incluye **"Dominios que citan los
motores"**: los dominios que aparecen como fuente en las respuestas a **tus**
preguntas.

Esa lista es, literalmente, tu lista de objetivos de enlaces para IA. No es una
heurística: es la medición de qué fuentes usa el modelo para responder a las
preguntas de tus clientes. Consigue presencia en esas fuentes y apareces en esas
respuestas.

Crúzala con el *Link intersect* del módulo de backlinks: la intersección entre
"quién cita el modelo" y "quién enlaza a mis competidores" es la lista de
prioridades más corta y más rentable que vas a tener.

---

## 6. Plan de 30 días para visibilidad en IA

**Semana 1 — Línea base**
1. Configurar al menos una API. Perplexity si solo vas a poner una.
2. Generar el conjunto de preguntas (en el idioma de tu mercado).
3. Ejecutar la medición. Anotar la tasa de mención y de cita.
4. Generar y publicar `llms.txt` y el JSON-LD.

**Semana 2 — Entidad**
1. Rellenar la ficha de empresa al 100%.
2. Comprobar consistencia de entidad y corregir los listados que difieran.
3. Reclamar perfiles en G2, Capterra, Trustpilot y las verticales que apliquen.
4. Pedir reseñas reales a cinco clientes.

**Semana 3 — Contenido citable**
1. Publicar una página de comparación honesta contra tus dos competidores
   principales, diciendo explícitamente para quién **no** eres la mejor opción.
2. Publicar una página de precios clara y sin registro obligatorio. Los modelos
   no pueden citar lo que está detrás de un formulario.
3. Añadir `FAQPage` a las páginas que ya tengan preguntas como encabezados.

**Semana 4 — Fuentes de terceros**
1. Responder cinco preguntas reales en Reddit o Stack Exchange, sin promocionarte.
2. Registrarse en plataformas de peticiones de periodistas y responder tres.
3. Re-ejecutar la medición y comparar con la semana 1.
4. Revisar "Dominios que citan los motores" y añadir los que falten al pipeline
   de enlaces.

---

## 7. Errores frecuentes

| Error | Por qué falla |
|---|---|
| Medir solo preguntas de marca | Siempre sales. No has medido nada. |
| Publicar "contenido para IA" en tu blog | El conocimiento paramétrico no viene de tu blog. |
| Rellenar páginas de palabras clave | Los modelos extraen afirmaciones, no densidad. |
| Comprar reseñas | Fraude, se detecta, y tumba el perfil entero. |
| Autocrearse un artículo de Wikipedia | Violación de política; peor que no tenerlo. |
| Medir una vez y sacar conclusiones | Las respuestas varían entre ejecuciones. Mide semanalmente. |
| Ignorar el tono | Aparecer descrito negativamente es peor que no aparecer. |
| Medir solo en inglés | En español hay mucha menos competencia y respuestas distintas. |

---

## 8. Relación con el SEO clásico

No son canales separados:

- Las fuentes que citan los modelos son, en gran medida, las mismas que enlazan
  a tus competidores.
- El SEO clásico hace que tu página sea recuperable, que es el requisito del
  mecanismo RAG.
- Los datos estructurados sirven a ambos.
- Las reseñas y las fichas sirven a ambos.

La diferencia está en el **orden de prioridad**: para SEO clásico el contenido
propio va primero; para visibilidad en IA la reputación en terceros va primero.
Draken puntúa las oportunidades teniendo en cuenta ambas cosas, por eso cada
fuente del catálogo lleva su `llm_citation_weight`.
