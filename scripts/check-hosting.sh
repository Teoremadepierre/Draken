#!/usr/bin/env bash
#
# Draken hosting check.
#
# Paste this whole block into your SSH session. It only reads: it installs
# nothing, changes nothing and prints no passwords. Copy the output back and it
# says exactly which deployment path your server supports.
#
#   curl -fsSL https://raw.githubusercontent.com/Teoremadepierre/Draken/claude/backlinks-seo-tool-study-2tlk0x/scripts/check-hosting.sh | bash
#
# Or, if curl is unavailable, paste the file contents directly.

echo "================= DRAKEN HOSTING CHECK ================="
echo

# --- identity ------------------------------------------------------------
echo "--- Server ---"
echo "user:        $(id -un 2>/dev/null) (uid $(id -u 2>/dev/null))"
echo "hostname:    $(hostname 2>/dev/null)"
echo "home:        ${HOME}"
echo "os:          $( (. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME") || uname -sr )"
echo "kernel:      $(uname -r 2>/dev/null)"
echo "arch:        $(uname -m 2>/dev/null)"
echo

# --- shared hosting or a real machine? -----------------------------------
echo "--- Hosting type ---"
HOSTING="unknown"
if [ "$(id -u)" -eq 0 ]; then
    HOSTING="vps-root"
elif [ -d /usr/local/cpanel ] || [ -d /opt/cpanel ] || [ -f /usr/local/cpanel/version ]; then
    HOSTING="shared-cpanel"
elif [ -d /usr/local/hestia ] || [ -d /usr/local/vesta ]; then
    HOSTING="shared-panel"
elif echo "$(id -un)" | grep -qE '^u[0-9]{6,}$'; then
    HOSTING="shared-likely"
elif sudo -n true 2>/dev/null; then
    HOSTING="vps-sudo"
fi
echo "detected:    ${HOSTING}"
echo "sudo:        $(sudo -n true 2>/dev/null && echo 'yes (passwordless)' || (command -v sudo >/dev/null && echo 'present, needs a password' || echo 'not available'))"
echo "systemd:     $( [ -d /run/systemd/system ] && echo yes || echo 'no (cannot install a service)')"
echo "docker:      $(command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1 && echo yes || echo no)"
echo

# --- python --------------------------------------------------------------
echo "--- Python ---"
for candidate in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        echo "$candidate:  $("$candidate" --version 2>&1)"
    fi
done
PYBIN="$(command -v python3.12 || command -v python3.11 || command -v python3 || echo '')"
if [ -n "$PYBIN" ]; then
    echo "chosen:      ${PYBIN}"
    "$PYBIN" -c "import sys; v=sys.version_info; print('version ok:  %s' % ('yes' if v>=(3,11) else 'NO - Draken needs 3.11+'))" 2>/dev/null
    "$PYBIN" -c "import venv" 2>/dev/null && echo "venv:        yes" || echo "venv:        NO (python3-venv missing)"
    "$PYBIN" -m pip --version >/dev/null 2>&1 && echo "pip:         yes" || echo "pip:         no"
else
    echo "chosen:      NONE FOUND"
fi
echo

# --- can we run a long-lived server? -------------------------------------
echo "--- Long-running process ---"
echo "screen:      $(command -v screen >/dev/null && echo yes || echo no)"
echo "tmux:        $(command -v tmux >/dev/null && echo yes || echo no)"
echo "nohup:       $(command -v nohup >/dev/null && echo yes || echo no)"
echo "cron:        $(command -v crontab >/dev/null && echo yes || echo no)"
if command -v crontab >/dev/null 2>&1; then
    crontab -l >/dev/null 2>&1 && echo "crontab:     readable" || echo "crontab:     empty or denied"
fi

# Binding a port is the single hard requirement.
if [ -n "$PYBIN" ]; then
    BIND_TEST=$("$PYBIN" - <<'PYEOF' 2>&1
import socket
for port in (8000, 8080, 3000, 0):
    try:
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))
        actual = s.getsockname()[1]
        s.close()
        print(f"CAN BIND (port {actual})")
        break
    except Exception as exc:
        last = exc
else:
    print(f"CANNOT BIND: {last}")
PYEOF
)
    echo "bind a port: ${BIND_TEST}"
fi
echo

# --- resources -----------------------------------------------------------
echo "--- Resources ---"
echo "disk free:   $(df -h "$HOME" 2>/dev/null | awk 'NR==2 {print $4" of "$2}')"
if [ -r /proc/meminfo ]; then
    echo "memory:      $(awk '/MemTotal/ {printf "%.1f GB", $2/1048576}' /proc/meminfo)"
fi
echo "cpus:        $(nproc 2>/dev/null || echo '?')"
echo

# --- outbound network (Draken crawls and queries APIs) -------------------
echo "--- Outbound network ---"
for host in github.com pypi.org html.duckduckgo.com api.anthropic.com searchconsole.googleapis.com; do
    if command -v curl >/dev/null 2>&1; then
        code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 "https://${host}" 2>/dev/null)
        [ "$code" = "000" ] && echo "${host}: BLOCKED" || echo "${host}: ok (${code})"
    else
        echo "${host}: (curl not available)"
    fi
done
echo

# --- verdict -------------------------------------------------------------
echo "--- Verdict ---"
case "$HOSTING" in
    vps-root|vps-sudo)
        echo "This looks like a VPS you control."
        echo "Use install.sh: it sets up systemd, Caddy and HTTPS in one command."
        ;;
    shared-cpanel|shared-panel|shared-likely)
        echo "This looks like SHARED hosting."
        echo "Draken needs a Python process running continuously and listening on a port."
        echo "Shared plans normally kill background processes and do not let you bind one,"
        echo "so Draken cannot run here even though the files would upload fine."
        echo
        echo "Check the 'bind a port' and 'systemd' lines above to confirm."
        echo "If they say CANNOT BIND / no, you need a VPS or a free platform instead."
        ;;
    *)
        echo "Could not classify this host. Read the lines above:"
        echo "  - 'bind a port' must say CAN BIND"
        echo "  - Python must be 3.11 or newer"
        echo "  - github.com and pypi.org must be reachable"
        ;;
esac
echo
echo "=============== END OF CHECK (no secrets above) ==============="
