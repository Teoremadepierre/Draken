# Render paso a paso (gratis)

Esto te deja una URL pública tipo `https://draken-xxxx.onrender.com`, con
usuario y contraseña, sin servidor propio y sin tarjeta de crédito.

Tiempo: **10 minutos**, de los cuales 6 son esperar al primer build.

Si lo que quieres es solo probarlo en tu ordenador, no necesitas nada de esto:
[EMPEZAR.md](EMPEZAR.md).

---

## Antes de empezar

Necesitas dos cuentas gratuitas: **GitHub** y **Render**. Nada más.

Y decide ya la contraseña de administrador, porque te la va a pedir a mitad del
proceso. Que sea larga (12 caracteres o más): esa URL va a estar abierta a
internet, y lo único que separa tu panel del mundo es esa contraseña.

---

## 1. El repositorio

Si el repo ya es tuyo, sáltate este paso.

1. Entra en `https://github.com/Teoremadepierre/Draken`
2. Botón **Fork** (arriba a la derecha) → **Create fork**.

Ahora el código está en tu cuenta y Render podrá leerlo.

---

## 2. Conectar Render con GitHub

1. Entra en [render.com](https://render.com) → **Get Started** → **GitHub**.
2. Autoriza a Render.
3. Te preguntará a qué repositorios puede acceder: elige **Only select
   repositories** y marca tu fork de Draken. No hace falta darle acceso a todo.

---

## 3. Crear el servicio

1. En el panel de Render: botón **New +** (arriba a la derecha) → **Blueprint**.
2. En la lista, busca tu repo `Draken` → **Connect**.
3. En **Branch**, elige `claude/backlinks-seo-tool-study-2tlk0x`
   (o `main` si ya lo has fusionado).
4. Render lee el fichero `render.yaml` del repo y te enseña lo que va a crear:
   - un servicio web llamado **draken**
   - una base de datos Postgres llamada **draken-db**

   Si en vez de eso te dice *"no render.yaml found"*, la rama elegida es la
   equivocada: vuelve al paso 3.

5. Debajo aparece **una sola casilla que rellenar**:

   | Campo | Qué pones |
   |---|---|
   | `DRAKEN_ADMIN_PASSWORD` | La contraseña que decidiste. Esta es tu clave de entrada. |

   Las demás variables marcadas como opcionales (`DRAKEN_ANTHROPIC_API_KEY`,
   `DRAKEN_BING_WEBMASTER_API_KEY`, `DRAKEN_GSC_SITE_URL`...) puedes dejarlas
   vacías y añadirlas después. Draken funciona sin ninguna.

6. **Apply** / **Create resources**.

---

## 4. Esperar el build

Render construye la imagen Docker. Tarda entre 5 y 8 minutos la primera vez.

Verás la pestaña **Logs** llenarse. Lo que tiene que aparecer al final:

```
[draken] preparing the database and source catalog...
[draken] listening on 0.0.0.0:10000
INFO:     Application startup complete.
```

Cuando el estado del servicio pase a **Live** (verde), ya está.

**Si ves `[draken] NOTICE: authentication is OFF`**, es que la contraseña no
llegó. Ve al paso 6 y ponla a mano.

---

## 5. Entrar

Tu URL está arriba del todo en la página del servicio, con forma
`https://draken-xxxx.onrender.com`. Ábrela.

- Usuario: `admin`
- Contraseña: la que pusiste en el paso 3

Dentro: menú → **Escáner** → pega la URL de tu web → **Escanear ahora**.

---

## 6. Cambiar o añadir variables después

Página del servicio → pestaña **Environment** → **Add Environment Variable** o
edita una existente → **Save, rebuild, and deploy**.

Las que más cambian la calidad de los datos, por orden de impacto:

| Variable | Qué te da | Coste |
|---|---|---|
| `DRAKEN_GSC_SERVICE_ACCOUNT_JSON` + `DRAKEN_GSC_SITE_URL` | Impresiones, clics y posiciones que Google midió de verdad en tu sitio | gratis |
| `DRAKEN_BING_WEBMASTER_API_KEY` | Tus backlinks reales | gratis |
| `DRAKEN_ANTHROPIC_API_KEY` | El asistente de arreglos y la medición de visibilidad en IA | de pago, por uso |
| `DRAKEN_SERPAPI_KEY` | Posiciones exactas en Google | de pago |

`DRAKEN_GSC_SERVICE_ACCOUNT_JSON` es especial: en un servidor normal apuntarías
a un fichero de claves, pero en Render no hay disco donde dejarlo. Abre el JSON
que te descargó Google Cloud, **copia todo el contenido** y pégalo entero en el
valor de esa variable. Los pasos para conseguir ese fichero están en
[PUBLICAR.md](PUBLICAR.md).

---

## Lo que tienes que saber del plan gratuito

**Se duerme.** Tras unos 15 minutos sin visitas, Render apaga el servicio. La
siguiente visita tarda unos 30 segundos en cargar mientras despierta. No es un
error, no pierdes datos. Si te molesta, el plan más barato de Render lo quita.

**Un escaneo largo puede morir.** El contenedor gratuito tiene poca memoria, y
por eso el `render.yaml` limita la auditoría a 150 páginas. Si tu web es más
grande, audita por secciones o pásate a un plan con más RAM.

**La base de datos caduca.** El Postgres gratuito de Render tiene fecha de
caducidad (Render la indica en la página de la base de datos; suele rondar los
90 días). Cuando llega, deja de funcionar y hay que crear otra. **Esto es lo
único que puede costarte trabajo perdido, y tiene solución en una línea.**

---

## Copia de seguridad (hazla)

Desde el propio panel: **Ajustes → Exportar** descarga un JSON con todo:
proyectos, keywords, clústeres, backlinks, oportunidades con su estado,
campañas, envíos y prompts de IA.

O desde la URL directamente, estando dentro de la sesión:

```
https://draken-xxxx.onrender.com/api/export
```

Guárdalo en tu ordenador. Para restaurarlo en otra instalación (otra cuenta de
Render, un VPS, tu portátil):

```bash
draken import draken-all-2026-09-28.json
```

Los identificadores se reasignan solos y el catálogo de 355 fuentes se carga si
hace falta, así que no importa que la instalación de destino esté recién hecha.

**Ponte un recordatorio para exportar una vez al mes.** Es un fichero, y es la
diferencia entre cambiar de hosting en cinco minutos o volver a empezar.

---

## Si algo falla

| Lo que ves | Qué pasa |
|---|---|
| `no render.yaml found in repository` | Rama equivocada en el paso 3. |
| Build en rojo, `failed to solve` | Suele ser un build sin memoria. Reintenta con **Manual Deploy → Clear build cache & deploy**. |
| La URL da 502 | Todavía arrancando, o se está despertando. Espera 60 s y recarga. |
| Entra pero dice que la contraseña es incorrecta | Comprueba `DRAKEN_ADMIN_PASSWORD` en **Environment**. Si la cambias, hay que redesplegar. |
| `authentication is OFF` en los logs | Falta `DRAKEN_ADMIN_PASSWORD`. Añádela **antes** de compartir la URL con nadie. |
| Los datos desaparecieron | Se te ha caducado el Postgres gratuito. Por eso la copia de seguridad. |

---

## Cuando se te quede pequeño

El camino de salida está pensado y es corto:

1. `draken export -o todo.json` (o **Ajustes → Exportar**)
2. Monta un VPS con `install.sh` — un comando, HTTPS incluido
   ([PUBLICAR.md](PUBLICAR.md), opción A)
3. `draken import todo.json`

No pierdes nada y no repites trabajo.
