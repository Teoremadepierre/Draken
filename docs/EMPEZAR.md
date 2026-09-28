# Probar Draken en tu ordenador

Draken **no tiene icono ni se instala como un programa normal**. Es un servidor
web: lo arrancas con un comando, se queda funcionando en tu propio ordenador y
tú entras **por el navegador**, en una dirección local:

```
http://127.0.0.1:8000
```

Esa dirección solo funciona en tu ordenador. Nadie de fuera la ve. Si luego
quieres entrar desde el móvil o desde otro sitio, eso es publicar, y va en
[PUBLICAR.md](PUBLICAR.md).

---

## Mac y Linux · un comando

Abre la Terminal y pega esto:

```bash
git clone -b claude/backlinks-seo-tool-study-2tlk0x https://github.com/Teoremadepierre/Draken.git
cd Draken
bash scripts/empezar.sh
```

El script hace todo lo demás: instala lo que falta, genera la clave secreta,
prepara la base de datos con las 355 fuentes de enlaces y abre el navegador.

La primera vez tarda 2-4 minutos (está descargando las dependencias). Las
siguientes, unos segundos.

Cuando veas esto, ya está:

```
  Draken is starting
  Open this in your browser:  http://127.0.0.1:8000
  Stop it with Ctrl+C
```

**Para pararlo:** vuelve a la Terminal y pulsa `Ctrl+C`.
**Para volver a arrancarlo otro día:** `cd Draken && bash scripts/empezar.sh`.

> Si el puerto 8000 lo está usando otro programa: `PORT=8123 bash scripts/empezar.sh`.

---

## Windows

Tres caminos, de más fácil a más manual.

**1. Docker Desktop** (lo más simple si no quieres tocar Python)

Instala [Docker Desktop](https://www.docker.com/products/docker-desktop/), y en
PowerShell, dentro de la carpeta del proyecto:

```powershell
copy .env.example .env
docker compose up -d
```

Entra en `http://127.0.0.1:8000`. Para pararlo: `docker compose down`.

> El `.env.example` trae `DRAKEN_AUTH_ENABLED=true` con la contraseña vacía, y
> así **el panel no te dejará entrar**. Para uso local, edita el `.env` y pon
> `DRAKEN_AUTH_ENABLED=false`. Si prefieres dejar el login puesto, pon también
> `DRAKEN_ADMIN_PASSWORD=la-que-quieras` y entra con el usuario `admin`.

**2. WSL** (Windows Subsystem for Linux)

Abre Ubuntu desde el menú de inicio y sigue exactamente las instrucciones de
Mac/Linux de arriba. Es el mismo comando.

**3. Python nativo en PowerShell**

Instala Python 3.11 o superior desde [python.org](https://www.python.org/downloads/)
marcando *"Add Python to PATH"*, y después:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e backend
copy .env.example .env
draken init-db
draken serve
```

---

## Docker en Mac y Linux

Si ya tienes Docker y prefieres no instalar Python:

```bash
cp .env.example .env
# para uso local, quita el login:
sed -i.bak 's/^DRAKEN_AUTH_ENABLED=.*/DRAKEN_AUTH_ENABLED=false/' .env
docker compose up -d
```

`http://127.0.0.1:8000`. Los logs: `docker compose logs -f`. Parar: `docker compose down`.

---

## Qué haces una vez dentro

1. Menú lateral → **Escáner**.
2. Pega la URL de tu web y pulsa **Escanear ahora**.
3. En uno o dos minutos tienes el informe: qué está mal en el sitio ordenado por
   impacto, qué backlinks puedes conseguir hoy y con qué autoridad, y cómo te
   describen los asistentes de IA.

Si es tu primera vez con SEO, empieza por **Empieza aquí** en el menú: lleva los
pasos en orden y trae glosario. También está la [guía visual](GUIA-VISUAL.md).

---

## Dónde quedan tus datos

Todo vive en la carpeta `data/` del proyecto, en un fichero `draken.db`. No sale
nada a ningún servidor nuestro: no hay servidor nuestro.

Para llevártelo a otro ordenador o a un servidor:

```bash
.venv/bin/draken export -o mi-copia.json     # copia de seguridad completa
.venv/bin/draken import mi-copia.json        # restaurar en la otra instalación
```

---

## Si algo falla

| Lo que ves | Qué pasa |
|---|---|
| `python3: command not found` | No tienes Python. Mac: `brew install python@3.12`. Ubuntu: `sudo apt install python3.12 python3.12-venv`. |
| `could not create .venv` | Falta el módulo venv: `sudo apt install python3-venv`. |
| `Address already in use` | El puerto 8000 está ocupado: `PORT=8123 bash scripts/empezar.sh`. |
| La página carga pero pide usuario y contraseña | Tienes `DRAKEN_AUTH_ENABLED=true` en el `.env` sin contraseña. Ponlo en `false` para uso local. |
| El escáner no encuentra nada de la competencia | Tu red o tu proveedor bloquea los buscadores. Menú → **Fuentes de datos** → *Diagnóstico de conectividad*: dice exactamente qué host falla y qué deja de funcionar por ello. |

---

## ¿Y para entrar desde cualquier ordenador?

Eso ya no es local: hay que publicarlo en algún sitio con una URL propia y
contraseña. Está todo en [PUBLICAR.md](PUBLICAR.md), y el camino gratuito
paso a paso en [RENDER.md](RENDER.md).
