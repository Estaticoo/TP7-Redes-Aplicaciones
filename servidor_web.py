import os
import sys
import json
import html
import time
import base64
import hashlib
import hmac
import secrets
import logging
import threading
from urllib.parse import parse_qs, unquote, urlsplit
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_CONFIG = os.path.join(BASE_DIR, "config_servidor.json")
ARCHIVO_LOG = os.path.join(BASE_DIR, "webserver.log")

# Bloqueo por fuerza bruta: más de MAX_INTENTOS fallos en VENTANA_BLOQUEO segundos
MAX_INTENTOS = 5
VENTANA_BLOQUEO = 300
MAX_BODY_POST = 10_000


def hashear_clave(clave, salt=None):
    """Hash PBKDF2-SHA256 con salt: la contraseña nunca se guarda en texto plano."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), bytes.fromhex(salt), 100_000)
    return salt, digest.hex()


def config_por_defecto():
    salt, pass_hash = hashear_clave("1234")
    return {
        "port": 8080,
        "document_root": os.path.join(BASE_DIR, "www"),
        "protected_dir": "/privado",
        "realm": "Panel Restringido TP7 - UTN FRM",
        "user": "admin",
        "pass_salt": salt,
        "pass_hash": pass_hash,
        "listar_directorios": True,
    }


def cargar_config():
    config = config_por_defecto()
    if os.path.exists(ARCHIVO_CONFIG):
        with open(ARCHIVO_CONFIG, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    else:
        guardar_config(config)
    config["document_root"] = os.path.realpath(config["document_root"])
    return config


def guardar_config(config):
    with open(ARCHIVO_CONFIG, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


CONFIG = cargar_config()
PUERTO_ACTIVO = CONFIG["port"]
CSRF_TOKEN = secrets.token_urlsafe(24)
intentos_fallidos = {}
lock_intentos = threading.Lock()

# Estilos CSS globales (Diseño Dashboard Moderno Dark Mode)
BASE_CSS = """
<style>
    :root {
        --bg: #0f172a;
        --card: #1e293b;
        --border: #334155;
        --text: #f8fafc;
        --muted: #94a3b8;
        --accent: #38bdf8;
        --accent-hover: #0284c7;
        --success: #22c55e;
        --danger: #ef4444;
        --warning: #f59e0b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
        font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        background-color: var(--bg);
        color: var(--text);
        line-height: 1.6;
    }
    nav {
        background-color: var(--card);
        border-bottom: 1px solid var(--border);
        padding: 1rem 2rem;
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        justify-content: space-between;
        align-items: center;
    }
    .brand {
        font-size: 1.25rem;
        font-weight: 700;
        color: var(--accent);
        text-decoration: none;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .badge {
        background: rgba(34, 197, 94, 0.15);
        color: var(--success);
        border: 1px solid var(--success);
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .nav-links a {
        color: var(--text);
        text-decoration: none;
        margin-left: 1.5rem;
        font-size: 0.95rem;
        transition: color 0.2s;
    }
    .nav-links a:hover { color: var(--accent); }
    .container {
        max-width: 1050px;
        margin: 2rem auto;
        padding: 0 1.5rem;
    }
    .grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        gap: 1.5rem;
        margin-top: 1.5rem;
    }
    .card {
        background-color: var(--card);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.25);
    }
    .card h3 {
        color: var(--accent);
        margin-bottom: 0.75rem;
        font-size: 1.15rem;
    }
    .card p { color: var(--muted); font-size: 0.92rem; margin-bottom: 1.2rem; }
    .card ul { color: var(--muted); font-size: 0.92rem; margin: 0 0 1.2rem 1.2rem; }
    .btn {
        display: inline-block;
        background-color: var(--accent);
        color: #0f172a;
        font-weight: 600;
        padding: 0.6rem 1.2rem;
        border-radius: 8px;
        text-decoration: none;
        border: none;
        cursor: pointer;
        font-size: 0.9rem;
        transition: all 0.2s;
    }
    .btn:hover { background-color: var(--accent-hover); color: white; }
    .btn-danger { background-color: var(--danger); color: white; }
    .btn-outline {
        background: transparent;
        border: 1px solid var(--border);
        color: var(--text);
    }
    .btn-outline:hover { border-color: var(--accent); color: var(--accent); }
    .stat-box {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 0.85rem 1rem;
        margin-bottom: 0.75rem;
        font-family: Consolas, monospace;
        font-size: 0.88rem;
        overflow-wrap: anywhere;
    }
    input[type=text], input[type=password], input[type=number] {
        width: 100%;
        padding: 0.7rem;
        margin-top: 0.35rem;
        margin-bottom: 1rem;
        background: var(--bg);
        border: 1px solid var(--border);
        border-radius: 6px;
        color: var(--text);
        font-family: inherit;
    }
    input:focus { outline: 1px solid var(--accent); }
    label { font-size: 0.9rem; font-weight: 600; color: var(--muted); }
    .check { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 1.2rem; }
    pre {
        background: #090d16;
        border: 1px solid var(--border);
        padding: 1rem;
        border-radius: 8px;
        overflow-x: auto;
        font-family: Consolas, monospace;
        font-size: 0.85rem;
        color: #a7f3d0;
        max-height: 450px;
    }
    .alert {
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 1.5rem;
        background: rgba(34, 197, 94, 0.15);
        border: 1px solid var(--success);
        color: #86efac;
    }
    .alert-error {
        background: rgba(239, 68, 68, 0.15);
        border-color: var(--danger);
        color: #fca5a5;
    }
</style>
"""


def navbar():
    return f"""
<nav>
    <a href="/" class="brand">
        🌐 Servidor HTTP TP7 <span class="badge">ONLINE - TCP :{PUERTO_ACTIVO}</span>
    </a>
    <div class="nav-links">
        <a href="/">🏠 Inicio</a>
        <a href="/publico/">📄 Sitio Público</a>
        <a href="{html.escape(CONFIG['protected_dir'])}/secreto.html">🔒 Zona Protegida</a>
        <a href="/config">⚙️ Configuración</a>
        <a href="/logs">📋 Logs del Servidor</a>
    </div>
</nav>
"""


def pagina(titulo, cuerpo):
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo)}</title>{BASE_CSS}</head>
<body>{navbar()}
<div class="container">{cuerpo}</div></body></html>"""


def escribir_si_no_existe(ruta, contenido):
    if not os.path.exists(ruta):
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)


def inicializar_archivos():
    """Crea contenido de ejemplo en el DocumentRoot (sin pisar archivos existentes)."""
    raiz = CONFIG["document_root"]
    escribir_si_no_existe(os.path.join(raiz, "publico", "index.html"), pagina("Sitio Público - TP7", """
        <div class="card">
            <h3>📄 Archivo estático servido desde el DocumentRoot</h3>
            <p>Esta página es un archivo <code>publico/index.html</code> dentro del DocumentRoot. Se sirve con
            <b>HTTP 200 OK</b>, cabecera <code>Content-Type: text/html</code> y sin autenticación.</p>
            <a href="/" class="btn">⬅️ Volver al Panel Principal</a>
        </div>"""))
    carpeta_protegida = CONFIG["protected_dir"].strip("/")
    escribir_si_no_existe(os.path.join(raiz, carpeta_protegida, "secreto.html"), pagina("Zona Protegida - HTTP Basic Auth", f"""
        <div class="card" style="border-color: var(--success);">
            <h3>🔓 Acceso Autorizado (HTTP 200 OK)</h3>
            <p>Has superado exitosamente el desafío de autenticación <b>HTTP Basic (RFC 7617)</b> para este directorio restringido.</p>
            <div class="stat-box">
                <b>Directorio protegido:</b> /{html.escape(carpeta_protegida)}<br>
                <b>Método de validación:</b> Cabecera Authorization: Basic (Base64)<br>
                <b>Estado de sesión:</b> Credenciales verificadas por el servidor
            </div>
            <a href="/" class="btn">⬅️ Volver al Panel Principal</a>
        </div>"""))


def configurar_logging():
    formato = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    archivo = logging.FileHandler(ARCHIVO_LOG, encoding="utf-8")
    archivo.setFormatter(formato)
    consola = logging.StreamHandler(sys.stdout)
    consola.setFormatter(formato)
    logger = logging.getLogger("servidor_web")
    logger.setLevel(logging.INFO)
    logger.addHandler(archivo)
    logger.addHandler(consola)
    return logger


log = configurar_logging()
inicializar_archivos()


class ServidorHTTPMejorado(SimpleHTTPRequestHandler):
    server_version = "TP7-HTTP/2.0"
    sys_version = ""  # No revelar la versión de Python en la cabecera Server

    def log_message(self, format, *args):
        log.info(f"Cliente: {self.client_address[0]} | {format % args}")

    def end_headers(self):
        # Cabeceras de seguridad en todas las respuestas
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    # ------------------------------------------------------------------ utilidades
    def enviar_html(self, codigo, contenido, cabeceras=None):
        cuerpo = contenido.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'")
        self.send_header("Cache-Control", "no-store")
        for nombre, valor in (cabeceras or {}).items():
            self.send_header(nombre, valor)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(cuerpo)

    def ruta_url(self):
        """Ruta pedida ya decodificada (%xx) y sin query string."""
        return unquote(urlsplit(self.path).path)

    def resolver_ruta_fisica(self):
        """Devuelve la ruta real en disco o None si queda fuera del DocumentRoot.

        Se resuelve con realpath (normaliza '..', '%2e%2e', barras invertidas y enlaces
        simbólicos) y se compara con commonpath, no con un simple prefijo de texto.
        """
        raiz = os.path.realpath(CONFIG["document_root"])
        try:
            ruta = os.path.realpath(os.path.join(raiz, self.ruta_url().lstrip("/\\")))
            return ruta if os.path.commonpath([raiz, ruta]) == raiz else None
        except ValueError:  # p. ej. otra unidad en Windows o caracteres nulos
            return None

    def es_ruta_protegida(self, ruta_fisica):
        """Compara rutas físicas sin distinguir mayúsculas (Windows y macOS no las distinguen)."""
        raiz = os.path.realpath(CONFIG["document_root"])
        protegida = os.path.realpath(os.path.join(raiz, CONFIG["protected_dir"].strip("/")))
        protegida = os.path.normcase(protegida).casefold()
        ruta = os.path.normcase(ruta_fisica).casefold()
        return ruta == protegida or ruta.startswith(protegida.rstrip(os.sep) + os.sep)

    # ------------------------------------------------------------- autenticación
    def ip_bloqueada(self):
        ip = self.client_address[0]
        ahora = time.time()
        with lock_intentos:
            recientes = [t for t in intentos_fallidos.get(ip, []) if ahora - t < VENTANA_BLOQUEO]
            intentos_fallidos[ip] = recientes
            return len(recientes) >= MAX_INTENTOS

    def registrar_fallo(self):
        with lock_intentos:
            intentos_fallidos.setdefault(self.client_address[0], []).append(time.time())

    def credenciales_validas(self):
        tipo, _, valor = self.headers.get("Authorization", "").partition(" ")
        if tipo.lower() != "basic":
            return False
        try:
            usuario, _, clave = base64.b64decode(valor.strip(), validate=True).decode("utf-8").partition(":")
        except ValueError:
            return False
        _, hash_recibido = hashear_clave(clave, CONFIG["pass_salt"])
        usuario_ok = hmac.compare_digest(usuario.encode("utf-8"), CONFIG["user"].encode("utf-8"))
        clave_ok = hmac.compare_digest(hash_recibido, CONFIG["pass_hash"])
        return usuario_ok and clave_ok

    def verificar_autenticacion(self):
        ip = self.client_address[0]
        ruta = html.escape(self.ruta_url())
        if self.ip_bloqueada():
            log.warning(f"429 IP BLOQUEADA POR INTENTOS FALLIDOS | IP: {ip} | Ruta: {self.path}")
            self.enviar_html(429, pagina("429 Demasiados intentos", f"""
                <div class="card" style="border-color: var(--warning);">
                    <h3 style="color: var(--warning);">⏳ Error 429 - Demasiados intentos fallidos</h3>
                    <p>Tu IP quedó bloqueada temporalmente tras {MAX_INTENTOS} contraseñas incorrectas.
                    Volvé a intentar en unos minutos.</p>
                    <a href="/" class="btn btn-outline">Volver al Inicio</a>
                </div>"""), {"Retry-After": str(VENTANA_BLOQUEO)})
            return False
        if self.credenciales_validas():
            return True
        if "Authorization" in self.headers:
            self.registrar_fallo()
            log.warning(f"401 AUTH RECHAZADA | IP: {ip} | Ruta: {self.path}")
        realm = CONFIG["realm"].replace('"', "'")
        self.enviar_html(401, pagina("401 No Autorizado", f"""
            <div class="card" style="border-color: var(--danger);">
                <h3 style="color: var(--danger);">⛔ Error 401 - No Autorizado (Unauthorized)</h3>
                <p>El acceso al recurso <code>{ruta}</code> requiere autenticación mediante usuario y contraseña.</p>
                <div class="stat-box">Cabecera enviada por el servidor: WWW-Authenticate: Basic realm="{html.escape(realm)}"</div>
                <a href="{ruta}" class="btn">🔑 Reintentar Login</a>
                <a href="/" class="btn btn-outline">Volver al Inicio</a>
            </div>"""), {"WWW-Authenticate": f'Basic realm="{realm}", charset="UTF-8"'})
        return False

    # ------------------------------------------------------------------ páginas
    def render_dashboard(self):
        protegida = html.escape(CONFIG["protected_dir"])
        listado = "Activado" if CONFIG["listar_directorios"] else "Desactivado"
        self.enviar_html(200, pagina("Servidor Web HTTP - TP7 Redes", f"""
            <h2>Panel de Control del Servidor Web HTTP</h2>
            <p style="color: var(--muted);">Universidad Tecnológica Nacional - Facultad Regional Mendoza | Redes de Información - TP N°7</p>

            <div class="grid">
                <div class="card">
                    <h3>📄 Contenido Estático (HTTP)</h3>
                    <p>Archivos servidos directamente desde el DocumentRoot con GET y HEAD.</p>
                    <div class="stat-box">DocumentRoot:<br><b>{html.escape(CONFIG['document_root'])}</b><br>Listado de directorios: <b>{listado}</b></div>
                    <a href="/publico/" class="btn">Ver Sitio Público</a>
                </div>

                <div class="card">
                    <h3>🔒 Protección de Directorios</h3>
                    <p>Control de acceso mediante autenticación HTTP Basic en el directorio restringido.</p>
                    <div class="stat-box">Ruta protegida: <b>{protegida}</b><br>Usuario: <b>{html.escape(CONFIG['user'])}</b></div>
                    <a href="{protegida}/secreto.html" class="btn">Entrar a Zona Protegida</a>
                </div>

                <div class="card">
                    <h3>⚙️ Configuración vía Web</h3>
                    <p>Puerto, DocumentRoot, ruta protegida, realm, credenciales y listado de directorios. Requiere usuario y contraseña.</p>
                    <a href="/config" class="btn">Abrir Configuración</a>
                </div>

                <div class="card">
                    <h3>📋 Registro de Eventos (Logging)</h3>
                    <p>Peticiones HTTP, códigos de respuesta, cambios de configuración y bloqueos de seguridad. Requiere usuario y contraseña.</p>
                    <div class="stat-box">Archivo de registro:<br><b>webserver.log</b></div>
                    <a href="/logs" class="btn">Ver Logs</a>
                </div>
            </div>

            <div class="card" style="margin-top: 1.5rem;">
                <h3>🛡️ Medidas de Seguridad Activas</h3>
                <ul>
                    <li><b>Aislamiento del DocumentRoot:</b> cada ruta se decodifica y se resuelve con <code>realpath</code>; si queda fuera de la raíz (<code>..</code>, <code>%2e%2e</code>, enlaces simbólicos) responde 403.</li>
                    <li><b>Directorio protegido</b> verificado sobre la ruta física, sin distinguir mayúsculas ni codificación URL.</li>
                    <li><b>Contraseña guardada como hash</b> PBKDF2-SHA256 con salt, comparada en tiempo constante.</li>
                    <li><b>Bloqueo por fuerza bruta:</b> {MAX_INTENTOS} intentos fallidos bloquean la IP {VENTANA_BLOQUEO // 60} minutos (HTTP 429).</li>
                    <li><b>Token CSRF</b> en el formulario de configuración y límite de tamaño en el cuerpo POST.</li>
                    <li><b>Cabeceras de seguridad:</b> X-Content-Type-Options, X-Frame-Options, Referrer-Policy y Content-Security-Policy.</li>
                    <li>La cabecera <code>Server</code> no revela la versión de Python.</li>
                </ul>
                <div class="stat-box">
                    Prueba de Directory Traversal (debe responder 403):<br>
                    <span style="color: var(--accent);">curl --path-as-is http://localhost:{PUERTO_ACTIVO}/../../etc/passwd</span><br>
                    <span style="color: var(--accent);">curl.exe --path-as-is http://localhost:{PUERTO_ACTIVO}/../../Windows/win.ini</span>
                </div>
            </div>"""))

    def render_logs(self):
        solo_alertas = parse_qs(urlsplit(self.path).query).get("filtro") == ["alertas"]
        lineas = []
        if os.path.exists(ARCHIVO_LOG):
            with open(ARCHIVO_LOG, "r", encoding="utf-8", errors="replace") as f:
                lineas = f.readlines()
        if solo_alertas:
            lineas = [l for l in lineas if "| WARNING |" in l or "| ERROR |" in l]
        contenido = html.escape("".join(reversed(lineas[-200:]))) or "Sin registros aún."
        self.enviar_html(200, pagina("Logs del Servidor HTTP", f"""
            <div class="card">
                <div style="display:flex; flex-wrap:wrap; gap:0.5rem; justify-content:space-between; align-items:center; margin-bottom: 1rem;">
                    <h3>📋 Registro de Información del Servidor (webserver.log)</h3>
                    <div>
                        <a href="/logs" class="btn">Todos</a>
                        <a href="/logs?filtro=alertas" class="btn btn-outline">Solo alertas (401/403/429)</a>
                    </div>
                </div>
                <p>Mostrando los eventos más recientes primero (últimas 200 líneas).</p>
                <pre>{contenido}</pre>
            </div>"""))

    def render_config(self, mensaje="", error=False):
        c = {k: html.escape(str(v)) for k, v in CONFIG.items()}
        alerta = ""
        if mensaje:
            alerta = f'<div class="alert{" alert-error" if error else ""}">{html.escape(mensaje)}</div>'
        elif "ok=1" in self.path:
            alerta = '<div class="alert">✅ Parámetros del servidor actualizados correctamente.</div>'
        if CONFIG["port"] != PUERTO_ACTIVO:
            alerta += f'<div class="alert alert-error">El puerto {CONFIG["port"]} se aplicará al reiniciar el servidor (ahora escucha en {PUERTO_ACTIVO}).</div>'
        marcado = "checked" if CONFIG["listar_directorios"] else ""
        self.enviar_html(400 if error else 200, pagina("Configuración del Servidor", f"""
            <div class="card">
                <h3>⚙️ Configurar Parámetros del Servidor Web</h3>
                <p>Los cambios se guardan en <code>config_servidor.json</code> y se aplican de inmediato (el puerto, al reiniciar).</p>
                {alerta}
                <form method="POST" action="/config">
                    <input type="hidden" name="csrf" value="{CSRF_TOKEN}">
                    <label>Puerto TCP:</label>
                    <input name="port" type="number" min="1" max="65535" value="{c['port']}" required>

                    <label>Directorio Raíz (DocumentRoot):</label>
                    <input name="docroot" type="text" value="{c['document_root']}" required>

                    <label>Directorio Protegido (relativo al DocumentRoot):</label>
                    <input name="protdir" type="text" value="{c['protected_dir']}" required>

                    <label>Realm (texto del diálogo de login):</label>
                    <input name="realm" type="text" value="{c['realm']}" required>

                    <label>Usuario de Autenticación HTTP:</label>
                    <input name="user" type="text" value="{c['user']}" required>

                    <label>Nueva contraseña (dejar vacío para mantener la actual):</label>
                    <input name="pass" type="password" autocomplete="new-password">

                    <div class="check">
                        <input id="listar" name="listar" type="checkbox" value="1" {marcado}>
                        <label for="listar">Permitir listado de directorios sin index.html</label>
                    </div>

                    <button type="submit" class="btn">💾 Guardar Configuración</button>
                    <a href="/" class="btn btn-outline" style="margin-left:10px;">Cancelar</a>
                </form>
            </div>"""))

    def render_403(self):
        log.error(f"403 BLOQUEO DOCUMENT_ROOT | IP: {self.client_address[0]} | Intento: {self.path}")
        self.enviar_html(403, pagina("403 Prohibido", f"""
            <div class="card" style="border-color: var(--danger);">
                <h3 style="color: var(--danger);">🛡️ Error 403 - Prohibido (Directory Traversal Bloqueado)</h3>
                <p>El servidor bloqueó el acceso porque la ruta solicitada intenta salir del <b>DocumentRoot</b> autorizado.</p>
                <div class="stat-box">Ruta solicitada: {html.escape(self.path)}</div>
                <a href="/" class="btn">Volver al Inicio</a>
            </div>"""))

    def list_directory(self, path):
        if not CONFIG["listar_directorios"]:
            self.send_error(403, "Listado de directorios deshabilitado")
            return None
        return super().list_directory(path)

    # ------------------------------------------------------------------ métodos HTTP
    def atender(self):
        ruta = self.ruta_url()

        # 1. Páginas internas del servidor
        if ruta in ("/", "/index.html"):
            self.render_dashboard()
            return
        if ruta == "/logs":
            if self.verificar_autenticacion():
                self.render_logs()
            return
        if ruta == "/config":
            if self.verificar_autenticacion():
                self.render_config()
            return

        # 2. Medida de seguridad: bloquear cualquier acceso fuera del DocumentRoot
        ruta_fisica = self.resolver_ruta_fisica()
        if ruta_fisica is None:
            self.render_403()
            return

        # 3. Protección por usuario y contraseña del directorio configurado
        if self.es_ruta_protegida(ruta_fisica) and not self.verificar_autenticacion():
            return

        # 4. Archivo estático desde el DocumentRoot
        self.directory = CONFIG["document_root"]
        if self.command == "HEAD":
            super().do_HEAD()
        else:
            super().do_GET()

    def do_GET(self):
        self.atender()

    def do_HEAD(self):
        self.atender()

    def do_POST(self):
        if self.ruta_url() != "/config":
            self.send_error(405, "Método no permitido para este recurso")
            return
        if not self.verificar_autenticacion():
            return
        largo = int(self.headers.get("Content-Length", 0) or 0)
        if largo > MAX_BODY_POST:
            self.send_error(413, "Cuerpo de la petición demasiado grande")
            return
        params = {k: v[0] for k, v in parse_qs(self.rfile.read(largo).decode("utf-8")).items()}

        if not hmac.compare_digest(params.get("csrf", ""), CSRF_TOKEN):
            log.warning(f"POST /config RECHAZADO (token CSRF inválido) | IP: {self.client_address[0]}")
            self.render_config("Token CSRF inválido: recargá la página e intentá de nuevo.", error=True)
            return

        try:
            puerto = int(params.get("port", CONFIG["port"]))
            if not 1 <= puerto <= 65535:
                raise ValueError
        except ValueError:
            self.render_config("El puerto debe ser un número entre 1 y 65535.", error=True)
            return
        protegida = "/" + params.get("protdir", CONFIG["protected_dir"]).strip().strip("/")
        if ".." in protegida.split("/"):
            self.render_config("El directorio protegido no puede contener '..'.", error=True)
            return
        docroot = os.path.realpath(params.get("docroot", CONFIG["document_root"]).strip())
        try:
            os.makedirs(docroot, exist_ok=True)
        except OSError as e:
            self.render_config(f"No se pudo usar el DocumentRoot: {e}", error=True)
            return

        nuevos = {
            "port": puerto,
            "document_root": docroot,
            "protected_dir": protegida,
            "realm": params.get("realm", CONFIG["realm"]).strip() or CONFIG["realm"],
            "user": params.get("user", CONFIG["user"]).strip() or CONFIG["user"],
            "listar_directorios": params.get("listar") == "1",
        }
        if params.get("pass"):
            nuevos["pass_salt"], nuevos["pass_hash"] = hashear_clave(params["pass"])
        cambios = [k for k, v in nuevos.items() if CONFIG.get(k) != v and k not in ("pass_salt", "pass_hash")]
        if "pass_hash" in nuevos:
            cambios.append("contraseña")
        CONFIG.update(nuevos)
        guardar_config(CONFIG)
        inicializar_archivos()
        # Nunca se registra la contraseña, solo qué parámetros cambiaron
        log.info(f"CONFIGURACION ACTUALIZADA VIA WEB | IP: {self.client_address[0]} | Cambios: {', '.join(cambios) or 'ninguno'}")
        self.send_response(303)
        self.send_header("Location", "/config?ok=1")
        self.send_header("Content-Length", "0")
        self.end_headers()


if __name__ == "__main__":
    servidor = ThreadingHTTPServer(("0.0.0.0", PUERTO_ACTIVO), ServidorHTTPMejorado)
    log.info(f"Servidor Web HTTP activo en http://localhost:{PUERTO_ACTIVO} | DocumentRoot: {CONFIG['document_root']}")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        log.info("Servidor Web HTTP detenido")
