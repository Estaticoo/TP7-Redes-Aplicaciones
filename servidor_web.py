import os
import base64
import logging
from datetime import datetime
from urllib.parse import parse_qs
from http.server import HTTPServer, SimpleHTTPRequestHandler

CONFIG = {
    "document_root": os.path.abspath("./www"),
    "protected_dir": "/privado",
    "user": "admin",
    "pass": "1234",
    "port": 8080
}

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
    }
    input {
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
</style>
"""

NAVBAR = """
<nav>
    <a href="/" class="brand">
        🌐 Servidor HTTP TP7 <span class="badge">ONLINE - TCP :8080</span>
    </a>
    <div class="nav-links">
        <a href="/">🏠 Inicio</a>
        <a href="/privado/secreto.html">🔒 Zona Protegida</a>
        <a href="/config">⚙️ Configuración</a>
        <a href="/logs">📋 Logs del Servidor</a>
    </div>
</nav>
"""

def inicializar_archivos():
    os.makedirs(os.path.join(CONFIG["document_root"], "privado"), exist_ok=True)
    with open(os.path.join(CONFIG["document_root"], "privado", "secreto.html"), "w", encoding="utf-8") as f:
        f.write(f"""<!DOCTYPE html>
        <html><head><meta charset="utf-8"><title>Zona Protegida - HTTP Basic Auth</title>{BASE_CSS}</head>
        <body>{NAVBAR}
        <div class="container">
            <div class="card" style="border-color: var(--success);">
                <h3>🔓 Acceso Autorizado (HTTP 200 OK)</h3>
                <p>Has superado exitosamente el desafío de autenticación <b>HTTP Basic (RFC 7617)</b> para este directorio restringido.</p>
                <div class="stat-box">
                    <b>Directorio protegido:</b> /privado<br>
                    <b>Método de validación:</b> Cabecera Authorization: Basic (Base64)<br>
                    <b>Estado de sesión:</b> Credenciales verificadas por el servidor
                </div>
                <a href="/" class="btn">⬅️ Volver al Panel Principal</a>
            </div>
        </div></body></html>""")

inicializar_archivos()
logging.basicConfig(filename="webserver.log", level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

class ServidorHTTPMejorado(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        entrada = f"Cliente: {self.client_address[0]} | {format % args}"
        logging.info(entrada)
        print(entrada)

    def enviar_html(self, codigo, contenido):
        self.send_response(codigo)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(contenido.encode("utf-8"))

    def verificar_autenticacion(self):
        auth = self.headers.get("Authorization")
        esperado = base64.b64encode(f"{CONFIG['user']}:{CONFIG['pass']}".encode()).decode()
        if auth == f"Basic {esperado}":
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Panel Restringido TP7 - UTN FRM"')
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        html_401 = f"""<!DOCTYPE html>
        <html><head><meta charset="utf-8"><title>401 No Autorizado</title>{BASE_CSS}</head>
        <body>{NAVBAR}
        <div class="container">
            <div class="card" style="border-color: var(--danger);">
                <h3 style="color: var(--danger);">⛔ Error 401 - No Autorizado (Unauthorized)</h3>
                <p>El acceso al recurso <code>{self.path}</code> requiere autenticación mediante usuario y contraseña.</p>
                <div class="stat-box">Cabecera enviada por el servidor: WWW-Authenticate: Basic realm="Panel Restringido TP7"</div>
                <a href="{self.path}" class="btn">🔑 Reintentar Login</a>
                <a href="/" class="btn btn-outline">Volver al Inicio</a>
            </div>
        </div></body></html>"""
        self.wfile.write(html_401.encode("utf-8"))
        logging.warning(f"401 AUTH RECHAZADA | IP: {self.client_address[0]} | Ruta: {self.path}")
        return False

    def render_dashboard(self):
        html = f"""<!DOCTYPE html>
        <html><head><meta charset="utf-8"><title>Servidor Web HTTP - TP7 Redes</title>{BASE_CSS}</head>
        <body>{NAVBAR}
        <div class="container">
            <h2>Panel de Control del Servidor Web HTTP</h2>
            <p style="color: var(--muted);">Universidad Tecnológica Nacional - Facultad Regional Mendoza | Redes de Información - TP N°7</p>

            <div class="grid">
                <div class="card">
                    <h3>🔒 Protección de Directorios</h3>
                    <p>Prueba el control de acceso mediante autenticación HTTP Basic en rutas restringidas del servidor.</p>
                    <div class="stat-box">Ruta protegida: <b>{CONFIG['protected_dir']}</b><br>Usuario activo: <b>{CONFIG['user']}</b></div>
                    <a href="{CONFIG['protected_dir']}/secreto.html" class="btn">Entrar a Zona Protegida</a>
                </div>

                <div class="card">
                    <h3>⚙️ Configuración vía Web</h3>
                    <p>Modifica en caliente el DocumentRoot, la ruta protegida y las credenciales de acceso del servidor.</p>
                    <div class="stat-box">DocumentRoot:<br><b>{CONFIG['document_root']}</b></div>
                    <a href="/config" class="btn">Abrir Configuración</a>
                </div>

                <div class="card">
                    <h3>📋 Registro de Eventos (Logging)</h3>
                    <p>Inspecciona en tiempo real las peticiones HTTP, códigos de respuesta y bloqueos de seguridad.</p>
                    <div class="stat-box">Archivo de registro:<br><b>webserver.log</b></div>
                    <a href="/logs" class="btn">Ver Logs en Vivo</a>
                </div>
            </div>

            <div class="card" style="margin-top: 1.5rem;">
                <h3>🛡️ Medidas de Seguridad Activas (DocumentRoot Isolation)</h3>
                <p>El servidor valida todas las rutas solicitadas con <code>os.path.abspath</code> para bloquear ataques de <i>Directory Traversal</i> fuera del DocumentRoot.</p>
                <div class="stat-box">
                    Comando de prueba en terminal para demostrar bloqueo 403:<br>
                    <span style="color: var(--accent);">curl --path-as-is http://localhost:8080/../../Windows/win.ini</span>
                </div>
            </div>
        </div></body></html>"""
        self.enviar_html(200, html)

    def do_GET(self):
        # 1. Dashboard Principal
        if self.path in ["/", "/index.html"]:
            self.render_dashboard()
            return

        # 2. Visor de Logs estilizado
        if self.path == "/logs":
            contenido_log = "Sin registros aún."
            if os.path.exists("webserver.log"):
                with open("webserver.log", "r", encoding="utf-8", errors="ignore") as f:
                    lineas = f.readlines()
                    contenido_log = "".join(reversed(lineas[-80:])) # Últimas 80 líneas arriba
            html = f"""<!DOCTYPE html>
            <html><head><meta charset="utf-8"><title>Logs del Servidor HTTP</title>{BASE_CSS}</head>
            <body>{NAVBAR}
            <div class="container">
                <div class="card">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 1rem;">
                        <h3>📋 Registro de Información del Servidor (webserver.log)</h3>
                        <div>
                            <a href="/logs" class="btn">🔄 Actualizar</a>
                            <a href="/" class="btn btn-outline">Inicio</a>
                        </div>
                    </div>
                    <p>Mostrando los eventos más recientes primero (Peticiones HTTP, cambios de configuración y alertas 401/403):</p>
                    <pre>{contenido_log}</pre>
                </div>
            </div></body></html>"""
            self.enviar_html(200, html)
            return

        # 3. Interfaz de Configuración vía Web
        if self.path.startswith("/config"):
            if not self.verificar_autenticacion(): return
            alerta = '<div class="alert">✅ Parámetros del servidor actualizados correctamente en tiempo real.</div>' if "ok=1" in self.path else ""
            html = f"""<!DOCTYPE html>
            <html><head><meta charset="utf-8"><title>Configuración del Servidor</title>{BASE_CSS}</head>
            <body>{NAVBAR}
            <div class="container">
                <div class="card">
                    <h3>⚙️ Configurar Parámetros del Servidor Web</h3>
                    <p>Los cambios aplicados aquí modifican el comportamiento del servidor HTTP de forma inmediata sin reiniciar el proceso.</p>
                    {alerta}
                    <form method="POST" action="/config">
                        <label>Directorio Raíz (DocumentRoot):</label>
                        <input name="docroot" value="{CONFIG['document_root']}" required>
                        
                        <label>Prefijo de Directorio Protegido:</label>
                        <input name="protdir" value="{CONFIG['protected_dir']}" required>
                        
                        <label>Usuario de Autenticación HTTP:</label>
                        <input name="user" value="{CONFIG['user']}" required>
                        
                        <label>Contraseña de Autenticación HTTP:</label>
                        <input name="pass" type="text" value="{CONFIG['pass']}" required>
                        
                        <button type="submit" class="btn">💾 Guardar Configuración</button>
                        <a href="/" class="btn btn-outline" style="margin-left:10px;">Cancelar</a>
                    </form>
                </div>
            </div></body></html>"""
            self.enviar_html(200, html)
            return

        # 4. Medida de Seguridad: Bloquear cualquier acceso fuera del DocumentRoot
        ruta_fisica = os.path.abspath(os.path.join(CONFIG["document_root"], self.path.lstrip("/")))
        if not ruta_fisica.startswith(CONFIG["document_root"]):
            logging.error(f"403 BLOQUEO DOCUMENT_ROOT | IP: {self.client_address[0]} | Intento: {self.path}")
            html_403 = f"""<!DOCTYPE html>
            <html><head><meta charset="utf-8"><title>403 Prohibido</title>{BASE_CSS}</head>
            <body>{NAVBAR}
            <div class="container">
                <div class="card" style="border-color: var(--danger);">
                    <h3 style="color: var(--danger);">🛡️ Error 403 - Prohibido (Directory Traversal Bloqueado)</h3>
                    <p>El servidor bloqueó el acceso porque la ruta solicitada intenta salir del <b>DocumentRoot</b> autorizado.</p>
                    <div class="stat-box">Ruta solicitada: {self.path}<br>DocumentRoot seguro: {CONFIG['document_root']}</div>
                    <a href="/" class="btn">Volver al Inicio</a>
                </div>
            </div></body></html>"""
            self.enviar_html(403, html_403)
            return

        # 5. Protección por usuario y contraseña para el directorio configurado
        if self.path.startswith(CONFIG["protected_dir"]):
            if not self.verificar_autenticacion(): return

        self.directory = CONFIG["document_root"]
        super().do_GET()

    def do_POST(self):
        if self.path.startswith("/config"):
            if not self.verificar_autenticacion(): return
            length = int(self.headers.get("Content-Length", 0))
            params = parse_qs(self.rfile.read(length).decode("utf-8"))
            CONFIG["document_root"] = os.path.abspath(params.get("docroot", [CONFIG["document_root"]])[0])
            CONFIG["protected_dir"] = params.get("protdir", [CONFIG["protected_dir"]])[0]
            CONFIG["user"] = params.get("user", [CONFIG["user"]])[0]
            CONFIG["pass"] = params.get("pass", [CONFIG["pass"]])[0]
            inicializar_archivos()
            logging.info(f"CONFIGURACION ACTUALIZADA VIA WEB | Nuevo estado: {CONFIG}")
            self.send_response(303)
            self.send_header("Location", "/config?ok=1")
            self.end_headers()

if __name__ == "__main__":
    puerto = CONFIG["port"]
    print(f"Servidor Web HTTP activo en http://localhost:{puerto}")
    HTTPServer(("0.0.0.0", puerto), ServidorHTTPMejorado).serve_forever()