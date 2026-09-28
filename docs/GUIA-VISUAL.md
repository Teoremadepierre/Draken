# Guía visual: Draken en 20 minutos

> Para alguien que nunca ha hecho SEO. No hay teoría: qué pulsar, qué vas a ver
> y qué significa. Los diagramas se ven en cualquier visor de Markdown.

---

## El recorrido completo, de un vistazo

```
                    ┌──────────────────────────────────┐
   TÚ ──── pegas ──▶│  ESCÁNER                         │
        una URL     │  "https://tudominio.com"         │
                    └────────────────┬─────────────────┘
                                     │  (1-2 min)
                 ┌───────────────────┼───────────────────┐
                 ▼                   ▼                   ▼
        ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
        │ AUDITORÍA      │  │ ENLACES        │  │ VISIBILIDAD IA │
        │ ¿qué está mal? │  │ ¿quién me      │  │ ¿me nombran    │
        │                │  │  enlaza?       │  │  los chats?    │
        └───────┬────────┘  └───────┬────────┘  └───────┬────────┘
                │                   │                   │
                └───────────────────┼───────────────────┘
                                    ▼
                    ┌──────────────────────────────────┐
                    │  UN SOLO INFORME                 │
                    │                                  │
                    │  • Qué arreglar (por prioridad)  │
                    │  • Qué backlinks puedes conseguir│
                    │    HOY y con qué autoridad       │
                    │  • Cómo te ven las IA            │
                    └────────────────┬─────────────────┘
                                     │
                    ┌────────────────┴─────────────────┐
                    ▼                                  ▼
          ┌──────────────────┐             ┌──────────────────┐
          │ "Arreglar"       │             │ "Compartir"      │
          │ → la IA te dice  │             │ → enlace para un │
          │   el cambio      │             │   compañero, con │
          │   exacto         │             │   su propia IA   │
          └──────────────────┘             └──────────────────┘
```

---

## Paso 1 · Escanea

**Dónde:** menú izquierdo → **Escáner**

```
┌─────────────────────────────────────────────────────────┐
│  Pega la URL y listo.                                   │
│                                                         │
│  ┌───────────────────────────────────┐ ┌────────┐ ┌───┐ │
│  │ https://tudominio.com             │ │ Normal │ │ ▶ │ │
│  └───────────────────────────────────┘ └────────┘ └───┘ │
│                                         150 págs  Escanear│
└─────────────────────────────────────────────────────────┘
```

**Qué hace por dentro, en orden:**

1. Lee tu portada y deduce nombre, idioma, país y sector. No tienes que
   rellenar nada.
2. Rastrea el sitio respetando `robots.txt`.
3. Busca quién te enlaza ya.
4. Puntúa las 355 fuentes del catálogo **para tu caso concreto**.
5. Crea las preguntas con las que medir tu visibilidad en asistentes de IA.

**Tarda 1-2 minutos.** Puedes seguir usando el resto de la app mientras.

---

## Paso 2 · Lee las seis cifras

```
┌───────────┬───────────┬───────────┬───────────┬──────────┬────────────┐
│ GLOBAL    │ TÉCNICA   │ ENLACES   │ IA        │ PROBLEMAS│ BACKLINKS  │
│   17.3    │   43.3    │    0.0    │   0.0     │    31    │    114     │
│  🔴       │   🔴      │   🔴      │   🔴      │          │   🟢       │
└───────────┴───────────┴───────────┴───────────┴──────────┴────────────┘
   ▲            ▲           ▲          ▲           ▲          ▲
   │            │           │          │           │          └ los que puedes
   │            │           │          │           │            conseguir HOY
   │            │           │          │           └ cosas mal en el sitio
   │            │           │          └ % de respuestas de IA que te nombran
   │            │           └ fuerza de tu perfil de enlaces (0 = no tienes)
   │            └ salud técnica del sitio
   └ 40% técnica + 40% enlaces + 20% IA
```

**Cómo leerlo sin saber SEO:**

| Color | Significa |
|:---:|---|
| 🔴 rojo | Por debajo de 45. Hay trabajo real que hacer. |
| 🟡 ámbar | Entre 45 y 75. Funciona, pero se queda corto. |
| 🟢 verde | Por encima de 75. Mantenlo. |

**Al empezar de cero, "Enlaces 0.0" y "IA 0.0" son lo normal.** No es un fallo:
es el punto de partida.

---

## Paso 3 · La barra de calidad de datos

```
┌────────────────────────────────────────────────────────────────┐
│  Calidad de los datos: 1/4    [Datos estimados]                │
│  ████████░░░░░░░░░░░░░░░░░░░░░░░░                              │
│                                                                │
│  Para que dejen de ser estimaciones y pasen a ser mediciones:  │
│   • Search Console  → impresiones, clics y posiciones reales   │
│   • Bing Webmaster  → tus backlinks reales, gratis             │
│   • Proveedor SERP  → posiciones exactas de Google             │
└────────────────────────────────────────────────────────────────┘
```

Esto es lo más honesto de toda la herramienta: **te dice cuándo un número es una
estimación y cuándo es una medición.**

| Nivel | Qué tienes |
|:---:|---|
| 1 | Todo estimado. Sirve para ordenar prioridades, no para presupuestar. |
| 2 | Posiciones reales, volumen estimado. |
| 3 | Datos reales de tu sitio (Search Console conectado). |
| 4 | Completo: datos reales tuyos + posiciones exactas de cualquier keyword. |

**Conectar Search Console cuesta 15 minutos y es gratis.** Es lo que más sube el
nivel. Instrucciones paso a paso en **Fuentes de datos**.

---

## Paso 4 · "Qué arreglar"

```
 #  GRAVEDAD   PROBLEMA                            AFECTA A          
 ─────────────────────────────────────────────────────────────────── 
 1  crítico    No tienes ningún backlink              —     [Arreglar]
 2  error      Página interna rota (404)              1     [Arreglar]
 3  error      Título duplicado                       2     [Arreglar]
 4  error      Falta el H1                            1     [Arreglar]
 5  aviso      Contenido escaso                       6     [Arreglar]
             ▲                                             ▲
             │                                             │
      ordenado por impacto,                    pulsa y la IA te dice
      no por orden alfabético                  el cambio EXACTO para
                                               tu caso, no genérico
```

**El botón "Arreglar"** manda a la IA el problema con sus datos reales (qué URLs,
qué gravedad, qué tecnología detectada) y te devuelve el cambio concreto.

**Si no tienes clave de IA configurada**, en vez del error te da un informe
listo para copiar y pegar en Claude o ChatGPT, con todo el contexto dentro. Así
nunca te quedas sin respuesta.

---

## Paso 5 · "Backlinks ya"

Esta es la pestaña que responde a *"¿qué backlinks puedo conseguir ahora mismo?"*

```
┌──────────────┬──────────┬───────────────┬──────────────┬─────────┐
│ DISPONIBLES  │ DOFOLLOW │ AUTORIDAD ø   │ AUTORIDAD    │ HORAS   │
│     114      │    30    │     77.1      │   máx 100    │  74.9   │
└──────────────┴──────────┴───────────────┴──────────────┴─────────┘

  DÓNDE                  AUTORIDAD   TIPO       ESFUERZO   PESO IA
 ────────────────────────────────────────────────────────────────────
  PyPI                       94      dofollow     ••        50    [Abrir]
  DEV Community              90      dofollow     ••        40    [Abrir]
  Stack Overflow             96      nofollow     •         85    [Abrir]
  GitHub                     96      nofollow     •         80    [Abrir]
```

**Tres grupos, por cuándo puedes tenerlos:**

```
   HOY                    PRONTO                  CAMPAÑA
   ───                    ──────                  ───────
   Rellenas un            Necesita cuenta         Necesita contenido
   formulario y ya        o que te aprueben       o una relación
   esfuerzo 1-2           esfuerzo 3              esfuerzo 4-5

   Empieza AQUÍ           Segunda semana          Mes 2-3
```

**Cómo leer las columnas:**

- **Autoridad** — la fuerza del sitio, de 0 a 100. Más alto es mejor, pero la
  relevancia importa más.
- **Tipo** — `dofollow` transmite autoridad; `nofollow` no, pero **sí cuenta como
  señal de marca y lo leen las IA**, así que no lo descartes.
- **Esfuerzo** — puntos: `•` trivial, `•••••` necesita escribir un artículo.
- **Peso IA** — cuánto aparece ese sitio como fuente en respuestas de asistentes.
  Un peso alto vale aunque el enlace sea nofollow.

---

## Paso 6 · Comparte con quien haga falta

```
   TÚ                                          TU COMPAÑERO
   ──                                          ────────────

   Escáner → Compartir → Crear enlace
        │
        ├──▶ https://tuseo.com/shared/aBc123…  ──────┐
        │                                            │
        │    sin cuenta · solo lectura · caduca      ▼
        │                                    ┌────────────────┐
        │                                    │ Ve el informe  │
        │                                    │ completo       │
        │                                    │                │
        │                                    │ [Copiar para   │
        │                                    │  su IA]        │
        │                                    │       │        │
        │                                    └───────┼────────┘
        │                                            ▼
        │                                     Su propio Claude
        │                                     (no consume el tuyo)
        │
        └──▶ ¿Y si además debe trabajar?
             Equipo → Invitar → le llega un enlace de un solo uso
             y elige contraseña. Puede poner SU clave de IA.
```

**Dos formas, según lo que necesite:**

| | Enlace compartido | Invitación de usuario |
|---|---|---|
| Ver informes | ✓ | ✓ |
| Lanzar escaneos | ✗ | ✓ |
| Mover el pipeline | ✗ | ✓ |
| Necesita cuenta | No | Sí |
| Su propia IA | Copiando el informe | Configurada en su perfil |
| Caduca | Cuando tú digas | No |

---

## Lo que hay en cada sección del menú

```
RESUMEN
  Empieza aquí ......... la guía paso a paso, con glosario
  Escáner .............. pega URL → informe completo        ← EMPIEZA AQUÍ
  Dashboard ............ estado general y qué hacer ahora

INVESTIGACIÓN
  Palabras clave ....... qué busca la gente
  Clústeres y temas .... agrupa keywords → una página por grupo
  Posiciones ........... histórico de dónde apareces
  Gap de keywords ...... dónde sale la competencia y tú no

SITIO WEB
  Auditoría del sitio .. todos los problemas técnicos
  Análisis on-page ..... puntúa UNA página contra UNA keyword

BACKLINKS
  Perfil de enlaces .... quién te enlaza y con qué calidad
  Oportunidades ........ la cola de trabajo priorizada        ← EL MOTOR
  Catálogo de fuentes .. las 355 fuentes, explorables
  Envíos ............... preparar y verificar altas
  Outreach ............. plantillas de correo personalizadas
  Campañas ............. objetivos de enlaces por campaña

VISIBILIDAD IA
  Visibilidad en IA .... cómo te describen los asistentes
  Activos GEO .......... llms.txt y datos estructurados

SISTEMA
  Ficha de empresa ..... tus datos canónicos (rellénala pronto)
  Equipo ............... personas, roles e invitaciones
  Fuentes de datos ..... conectar datos reales + diagnóstico de red
  Tareas y actividad ... qué está corriendo y qué se hizo
  Configuración ........ ajustes del proyecto y del despliegue
```

---

## Los tres errores que comete todo el mundo al empezar

```
  ❌ ERROR                          ✅ EN SU LUGAR
  ─────────────────────────────────────────────────────────────────
  Empezar escribiendo correos       Empezar por las fichas y perfiles:
  pidiendo enlaces                  son gratis y no hay que convencer
                                    a nadie

  Rellenar la ficha de empresa      Rellenarla al 100% ANTES de
  "más o menos"                     enviar nada: se copia a 40 sitios
                                    y los errores se multiplican por 40

  Usar la keyword como texto        Usar SIEMPRE tu marca en las fichas.
  del enlace en los directorios     Es la señal de manipulación más
                                    fácil de detectar que existe
```

---

## Qué esperar, mes a mes

```
  MES 1          MES 2              MES 3           A PARTIR DE AHÍ
  ─────          ─────              ─────           ───────────────
  0 → 45         45 → 65            65 → 85+        Ritmo estable
  dominios       dominios           dominios

  Fichas,        Menciones sin      Estudio de      1 contenido
  perfiles,      enlace, link       datos propio,   enlazable al mes
  citaciones     intersect,         podcasts,       1 estudio al
                 socios             prensa          trimestre

  ~6 h/semana    ~6 h/semana        ~8 h/semana     ~2 h/mes
```

Las posiciones no se mueven el primer mes. Es normal: los enlaces tardan entre
cuatro y doce semanas en reflejarse. Lo que sí se mueve pronto es la visibilidad
en IA, porque los asistentes cambian mucho más rápido que las clasificaciones.

---

## Si algo no da datos

Ve a **Fuentes de datos → Comprobar conexión**. Te dice exactamente qué host no
alcanza el servidor y qué deja de funcionar por ello.

```
  ✓ OK    Tu propio sitio            tudominio.com           12 ms
  ✗ X     Google autocomplete        suggestqueries.google…  ProxyError: 403
  ✗ X     DuckDuckGo resultados      html.duckduckgo.com     ProxyError: 403

  QUÉ QUEDA DESHABILITADO
   • Investigación de keywords — por Google autocomplete
   • Seguimiento de posiciones — por DuckDuckGo resultados

  DIAGNÓSTICO
   6 hosts rechazados por un proxy de salida, no por los servicios.
   Es una política de red de la máquina donde corre Draken.
```

Si varios hosts sin relación fallan a la vez con "ProxyError", **no es Draken ni
son los servicios: es el cortafuegos o el proxy de tu red.** Hay que permitir
esos hosts o mover Draken a un sitio con salida HTTPS sin filtrar.
