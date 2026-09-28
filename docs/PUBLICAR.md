# Cómo conseguir tu URL

Draken es autoalojado: **no hay una URL que yo pueda darte**, la generas tú al
arrancarlo. Aquí están las cuatro formas reales, de más rápida a más control.

---

## Antes de nada: ¿tu hosting puede con esto?

Draken necesita **un proceso Python corriendo todo el tiempo y escuchando en un
puerto**. Eso descarta la mayoría de los planes de *hosting compartido*
(Hostinger, Banahosting, cPanel y similares): puedes subir los ficheros, pero el
servidor mata los procesos en segundo plano y no te deja abrir un puerto.

Compruébalo en 10 segundos. Entra por SSH y pega esto:

```bash
curl -fsSL https://raw.githubusercontent.com/Teoremadepierre/Draken/claude/backlinks-seo-tool-study-2tlk0x/scripts/check-hosting.sh | bash
```

Solo lee: no instala nada, no cambia nada y no imprime ninguna contraseña. Te
dice el tipo de hosting, la versión de Python, si puedes abrir un puerto y qué
hosts alcanza tu servidor.

Las dos líneas que deciden:

```
bind a port: CAN BIND (port 8000)     ← si dice CANNOT BIND, no se puede
systemd:     yes                      ← si dice no, no hay servicio permanente
```

| Señal en la salida | Qué significa |
|---|---|
| `detected: vps-root` o `vps-sudo` + `CAN BIND` | Perfecto → **Opción A** |
| `detected: shared-*` o `CANNOT BIND` | No sirve → **Opción B o C**, o sube a un VPS |
| Python por debajo de 3.11 | Instálalo, o usa la opción B (el contenedor ya lo trae) |
| `github.com: BLOCKED` | El servidor no tiene salida; ni siquiera podrás clonar |

> **Nunca pegues tu contraseña de SSH en un chat** (ni en este). Queda guardada
> en el historial. Los comandos de esta guía los ejecutas tú en tu terminal, así
> que nadie necesita tus credenciales.

---

## Decisión rápida

```
 ¿Tienes ya un VPS o servidor con SSH?
   │
   ├── SÍ ──▶ Opción A · install.sh          → 10 min · https://tudominio.com
   │
   └── NO ──┬── ¿Quieres algo gratis y sin servidor?
            │     │
            │     ├── SÍ ──▶ Opción B · Render     → 5 min · https://draken-xxx.onrender.com
            │     │
            │     └── NO ───▶ Opción C · Fly.io    → 8 min · https://draken.fly.dev
            │
            └── ¿Solo tú, desde tu portátil, sin publicar nada?
                  └──────────▶ Opción D · Cloudflare Tunnel → 3 min
```

| | Opción A · VPS | Opción B · Render | Opción C · Fly.io | Opción D · Túnel |
|---|---|---|---|---|
| Tiempo | 10 min | 5 min | 8 min | 3 min |
| Coste | Tu VPS (3-6 €/mes) | Gratis | Gratis con límites | Gratis |
| Necesita servidor | Sí | No | No | No |
| Necesita dominio | Sí | No | No | No |
| HTTPS | Automático | Incluido | Incluido | Incluido |
| Datos persistentes | Sí | Sí (Postgres) | Sí (volumen) | Sí (tu disco) |
| Se duerme si no se usa | No | Sí (plan free) | Sí (configurable) | Depende de tu equipo |
| Bueno para | Uso real del equipo | Probarlo en serio | Uso real barato | Probarlo tú solo |

---

## Opción A · Tu propio servidor, con un comando

La mejor si vas a usarlo de verdad con el equipo. Un VPS de 3-6 €/mes sobra
(Hetzner CX22, DigitalOcean básico, Contabo, o el hosting que ya tengas si
permite SSH y Docker o Python).

**Antes:** apunta un registro `A` de tu dominio (por ejemplo `seo.tudominio.com`)
a la IP del servidor. Sin eso Caddy no puede emitir el certificado.

```bash
ssh root@LA-IP-DE-TU-SERVIDOR

curl -fsSL https://raw.githubusercontent.com/Teoremadepierre/Draken/claude/backlinks-seo-tool-study-2tlk0x/install.sh \
  | bash -s -- seo.tudominio.com
```

Eso instala Python y Caddy, crea el usuario de servicio, genera una clave
secreta y una contraseña de administrador, monta el servicio systemd, configura
HTTPS automático y programa el barrido semanal.

Al terminar imprime:

```
   URL:       https://seo.tudominio.com
   User:      admin
   Password:  aB3kL9mQ2xR7tY4w
```

**Sin dominio todavía:** `bash -s -- --no-tls` y te deja en
`http://LA-IP:8000`. Sirve para probar, pero no lo compartas así: va sin cifrar.

**Volver a ejecutarlo** actualiza el código y reinicia. No pierde datos ni
cambia la contraseña.

---

## Opción B · Render (gratis, sin servidor)

1. Haz un fork de este repo a tu GitHub (o úsalo directamente si es tuyo).
2. Entra en [render.com](https://render.com) y conecta tu GitHub.
3. **New → Blueprint**, elige el repo. Render lee `render.yaml` y crea el
   servicio web más una base de datos Postgres.
4. Te pedirá **`DRAKEN_ADMIN_PASSWORD`**: pon la que quieras. Es la única
   variable obligatoria.
5. Espera al primer build (5-8 minutos).

**Tu URL:** `https://draken-xxxx.onrender.com` (Render te la enseña).
**Entra con:** `admin` y la contraseña que pusiste.

> **Lo que hay que saber del plan gratuito:** el servicio se duerme tras 15
> minutos sin uso y tarda unos 30 segundos en despertar. La base de datos
> Postgres gratuita caduca a los 90 días y hay que recrearla. Para uso real
> pásate al plan de pago más barato o a la opción A.

Se usa Postgres y no SQLite a propósito: en el plan gratuito el disco es
efímero y un reinicio se llevaría por delante un fichero SQLite.

---

## Opción C · Fly.io

Más barato que Render para uso continuo, y elige región (`mad` es Madrid).

```bash
curl -L https://fly.io/install.sh | sh          # instala flyctl
fly auth signup                                 # o `fly auth login`

git clone -b claude/backlinks-seo-tool-study-2tlk0x https://github.com/Teoremadepierre/Draken
cd Draken

fly launch --no-deploy --copy-config            # lee fly.toml
fly volumes create draken_data --size 1         # para que la base de datos persista
fly secrets set \
    DRAKEN_SECRET_KEY="$(openssl rand -hex 32)" \
    DRAKEN_ADMIN_PASSWORD='la-que-tu-quieras'
fly deploy
```

**Tu URL:** `https://draken.fly.dev` (o el nombre que elijas en `fly launch`).

Con `auto_stop_machines = "suspend"` la máquina se suspende cuando nadie la usa
y despierta en 1-2 segundos, así que casi no gasta.

---

## Opción D · Cloudflare Tunnel (sin servidor, sin abrir puertos)

Para cuando quieres probarlo desde otro ordenador sin montar nada. Corre en tu
portátil y Cloudflare le pone una URL pública.

```bash
# 1. Arranca Draken en local
cd Draken && source .venv/bin/activate
draken serve                    # http://127.0.0.1:8000

# 2. En otra terminal
brew install cloudflared        # macOS
# o: https://github.com/cloudflare/cloudflared/releases

cloudflared tunnel --url http://localhost:8000
```

`cloudflared` imprime algo como:

```
https://random-words-here.trycloudflare.com
```

**Esa es tu URL**, accesible desde cualquier sitio mientras tengas el comando
abierto.

> **Importante:** esa URL es pública y no requiere contraseña si tienes
> `DRAKEN_AUTH_ENABLED=false`. Antes de pasársela a nadie:
> ```
> DRAKEN_AUTH_ENABLED=true
> DRAKEN_ADMIN_PASSWORD=la-que-tu-quieras
> ```
> y reinicia. Es un túnel temporal: al cerrar la terminal, la URL muere.

---

## Antes de compartir la URL con alguien

Tres cosas, en este orden:

1. **Activa la autenticación.** Sin ella, quien llegue a la URL entra.
   ```
   DRAKEN_AUTH_ENABLED=true
   DRAKEN_ADMIN_PASSWORD=algo-largo-y-aleatorio
   ```
   Mejor todavía: usa `DRAKEN_ADMIN_PASSWORD_HASH`, así la contraseña en claro
   no queda en las variables de entorno.
   ```bash
   draken hash-password 'tu-contraseña'
   ```

2. **Cambia `DRAKEN_SECRET_KEY`.** Firma las cookies de sesión. Si queda la de
   por defecto, cualquiera puede falsificar una sesión.
   ```bash
   openssl rand -hex 32
   ```

3. **Restringe CORS** a tu dominio:
   ```
   DRAKEN_CORS_ORIGINS=https://seo.tudominio.com
   ```

Las tres opciones A, B y C ya lo dejan así. La D no: tienes que hacerlo tú.

---

## Después de entrar

1. **Escáner** → pega la URL de tu web → espera 1-2 minutos.
2. **Fuentes de datos** → conecta Search Console y Bing Webmaster. Son gratis y
   son los que convierten las estimaciones en mediciones reales.
3. **Ficha de empresa** → rellénala al 100% antes de enviar nada a ningún
   directorio.
4. **Equipo** → invita a quien tenga que trabajar, o crea un enlace compartido
   desde el Escáner para quien solo tenga que leer.

---

## Si algo falla

```bash
# Opción A (VPS)
systemctl status draken
journalctl -u draken -f
curl -s localhost:8000/api/health | python3 -m json.tool

# Opción B (Render): pestaña Logs del servicio
# Opción C (Fly)
fly logs
fly status
```

| Síntoma | Causa habitual |
|---|---|
| `502` de Caddy o nginx | El servicio no arrancó. Mira `journalctl -u draken -n 50`. |
| Certificado no emitido | El DNS todavía no apunta al servidor, o el puerto 80 está cerrado. |
| "Invalid username or password" | Falta `DRAKEN_ADMIN_PASSWORD` o `_HASH`. `/api/auth/status` te lo dice. |
| Tarda 30 s en cargar | Plan gratuito de Render: el servicio estaba dormido. |
| Los datos desaparecen al reiniciar | SQLite en disco efímero. Usa Postgres (Render) o un volumen (Fly). |
| Las búsquedas no devuelven nada | **Fuentes de datos → Comprobar conexión**. Casi siempre es la red. |
