# Despliegue

Tres opciones, de menos a más trabajo. Todas sirven API y panel en el mismo
puerto y no requieren compilar nada.

---

## Opción 1 — Local (desarrollo o uso personal)

```bash
git clone <tu-repo> draken && cd draken
python3 -m venv .venv && source .venv/bin/activate
pip install -e "backend[dev]"

cp .env.example .env          # edítalo si quieres; funciona sin tocarlo
draken init-db                # crea las tablas y carga las 355 fuentes
draken serve                  # http://127.0.0.1:8000
```

Sin autenticación por defecto en local. Para activarla:

```bash
draken hash-password 'tu-contraseña'   # copia el hash resultante
# en .env:
#   DRAKEN_AUTH_ENABLED=true
#   DRAKEN_ADMIN_USER=admin
#   DRAKEN_ADMIN_PASSWORD_HASH=pbkdf2_sha256$240000$...
```

---

## Opción 2 — Docker

```bash
docker compose up -d
# http://localhost:8000
```

`docker-compose.yml` monta `./data` como volumen, así que la base de datos y los
datasets sobreviven a `docker compose down`.

> **Permisos del volumen.** La imagen corre como usuario sin privilegios, así que
> `./data` tiene que ser escribible por él. Si ves un error de permisos al
> arrancar, ejecuta `sudo chown -R 1000:1000 ./data` una vez, o descomenta la
> línea `user:` del compose para correr con tu propio UID.

Para Postgres en vez de SQLite, descomenta el servicio `db` del compose y pon:

```
DRAKEN_DATABASE_URL=postgresql+psycopg://draken:draken@db:5432/draken
```

(requiere `pip install "draken[postgres]"`, ya incluido en la imagen).

---

## Opción 3 — VPS propio con nginx y systemd (recomendado para el equipo)

Esta es la opción para "que corra en nuestro hosting privado". Probado sobre
Debian/Ubuntu.

### 1. Sistema

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip nginx git
sudo useradd --system --create-home --shell /bin/bash draken
```

### 2. Código

```bash
sudo -u draken -i
git clone <tu-repo> /home/draken/draken
cd /home/draken/draken
python3 -m venv .venv
.venv/bin/pip install -e backend
cp .env.example .env
```

### 3. Configuración

Edita `/home/draken/draken/.env`. Como mínimo:

```ini
DRAKEN_ENV=production
DRAKEN_SECRET_KEY=<cadena aleatoria larga>     # openssl rand -hex 32
DRAKEN_HOST=127.0.0.1
DRAKEN_PORT=8000
DRAKEN_AUTH_ENABLED=true
DRAKEN_ADMIN_USER=tu-usuario
DRAKEN_ADMIN_PASSWORD_HASH=<salida de draken hash-password>
DRAKEN_USER_AGENT=DrakenSEO/0.1 (+https://tu-dominio.com/bot)
DRAKEN_CORS_ORIGINS=https://seo.tu-dominio.com
```

> `DRAKEN_SECRET_KEY` firma las cookies de sesión. Si la dejas por defecto en
> producción, cualquiera puede falsificar una sesión.

```bash
.venv/bin/python -m draken.cli.main init-db
exit
```

### 4. Servicio

```bash
sudo cp /home/draken/draken/deploy/systemd/draken.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now draken
sudo systemctl status draken
```

### 5. nginx y TLS

```bash
sudo cp /home/draken/draken/deploy/nginx/draken.conf /etc/nginx/sites-available/draken
sudo ln -s /etc/nginx/sites-available/draken /etc/nginx/sites-enabled/
# edita server_name en ese fichero
sudo nginx -t && sudo systemctl reload nginx

sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d seo.tu-dominio.com
```

### 6. Tareas programadas

```bash
sudo -u draken crontab -e
```

```cron
# Barrido completo de cada proyecto, lunes a las 03:00
0 3 * * 1 cd /home/draken/draken && .venv/bin/python -m draken.cli.main sweep 1 >> /home/draken/logs/sweep.log 2>&1

# Posiciones a diario a las 06:00
0 6 * * * cd /home/draken/draken && .venv/bin/python -m draken.cli.main keywords track 1 >> /home/draken/logs/ranks.log 2>&1

# Visibilidad en IA, dos veces por semana
0 7 * * 1,4 cd /home/draken/draken && .venv/bin/python -m draken.cli.main ai run 1 >> /home/draken/logs/ai.log 2>&1
```

`mkdir -p /home/draken/logs` antes.

---

## Configuración por variables de entorno

Todas llevan prefijo `DRAKEN_`. La lista completa y comentada está en
`.env.example`. Las que más importan:

### Seguridad
| Variable | Por defecto | Nota |
|---|---|---|
| `DRAKEN_SECRET_KEY` | inseguro | **Cámbiala en producción** |
| `DRAKEN_AUTH_ENABLED` | `false` | Actívala si es accesible desde fuera |
| `DRAKEN_ADMIN_PASSWORD_HASH` | vacío | `draken hash-password '…'` |
| `DRAKEN_CORS_ORIGINS` | `*` | Restríngelo a tu dominio |

### Límites de los envíos automáticos
| Variable | Por defecto | Efecto |
|---|---|---|
| `DRAKEN_SUBMISSIONS_DRY_RUN` | `true` | No envía nada; solo prepara y registra |
| `DRAKEN_SUBMISSIONS_REQUIRE_APPROVAL` | `true` | Cada envío necesita aprobación humana |
| `DRAKEN_SUBMISSIONS_PER_DOMAIN_DAILY_CAP` | `1` | Máximo por dominio y día |
| `DRAKEN_SUBMISSIONS_GLOBAL_DAILY_CAP` | `25` | Máximo total diario |

Se comprueban en el servidor. Desactivar la simulación es una decisión
deliberada: a partir de ahí Draken hace peticiones POST a formularios de
terceros en tu nombre.

### Etiqueta de rastreo
| Variable | Por defecto |
|---|---|
| `DRAKEN_RESPECT_ROBOTS` | `true` |
| `DRAKEN_CRAWL_CONCURRENCY` | `5` |
| `DRAKEN_CRAWL_DELAY_SECONDS` | `0.5` |
| `DRAKEN_MAX_PAGES_PER_AUDIT` | `500` |

### Proveedores opcionales
`DRAKEN_SERPAPI_KEY`, `DRAKEN_DATAFORSEO_LOGIN` / `_PASSWORD`,
`DRAKEN_OPENPAGERANK_KEY`, `DRAKEN_ANTHROPIC_API_KEY`, `DRAKEN_OPENAI_API_KEY`,
`DRAKEN_PERPLEXITY_API_KEY`, `DRAKEN_GEMINI_API_KEY`, y la sección SMTP.

---

## Salida a internet

Draken necesita alcanzar, según lo que uses:

| Destino | Para qué |
|---|---|
| El sitio que auditas | Rastreo y análisis on-page |
| `suggestqueries.google.com`, `api.bing.com`, `duckduckgo.com` | Sugerencias de keywords |
| `html.duckduckgo.com` | Posiciones sin proveedor de pago |
| Dominios arbitrarios | Verificación de enlaces y búsqueda de contactos |
| `index.commoncrawl.org` | Reconocimiento opcional |
| `api.anthropic.com`, `api.openai.com`, `api.perplexity.ai`, `generativelanguage.googleapis.com` | Visibilidad en IA |

Si tu red bloquea los endpoints de autocompletado, la investigación de keywords
sigue funcionando: desmarca "consultar autocompletado en vivo" y Draken generará
y puntuará las variantes igualmente.

---

## Copias de seguridad

Con SQLite todo el estado está en dos sitios:

```bash
# base de datos (usa .backup, no cp, para no copiar a mitad de escritura)
sqlite3 /home/draken/draken/data/draken.db ".backup '/backup/draken-$(date +%F).db'"

# datasets editables
tar czf /backup/seeds-$(date +%F).tar.gz /home/draken/draken/data/seeds/
```

Con Postgres, `pg_dump` de siempre.

---

## Actualizar

```bash
sudo -u draken -i
cd /home/draken/draken
git pull
.venv/bin/pip install -e backend
.venv/bin/python -m draken.cli.main init-db      # idempotente
exit
sudo systemctl restart draken
```

`init-db` crea las tablas que falten y recarga el catálogo de fuentes; no borra
datos.

---

## Diagnóstico

```bash
sudo journalctl -u draken -f                        # logs en vivo
curl -s localhost:8000/api/health | python3 -m json.tool
```

`/api/health` responde qué proveedor de SERP está activo, si es aproximado, qué
motores de IA hay configurados y en qué estado están los límites de envío. Es lo
primero que hay que mirar cuando algo "no da los datos esperados".

| Síntoma | Causa habitual |
|---|---|
| Posiciones raras o vacías | Sin proveedor de pago; el motor gratuito es aproximado |
| La investigación de keywords devuelve pocas | La red bloquea el autocompletado; usa el modo sin autocompletado |
| La auditoría rastrea 1 página | `robots.txt` bloquea, o el sitio no es alcanzable desde el servidor |
| "No AI engine configured" | Falta la clave de API correspondiente |
| Los envíos no envían | `DRAKEN_SUBMISSIONS_DRY_RUN` sigue en `true` (es lo correcto hasta que lo revises) |
