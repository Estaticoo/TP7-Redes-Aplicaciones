# 🌐 Trabajo Práctico N° 7: Implementación de Aplicaciones de Red

**Universidad Tecnológica Nacional - Facultad Regional Mendoza (UTN FRM)**
**Carrera:** Ingeniería en Sistemas de Información
**Asignatura:** Redes de Información
**Docente a cargo:** Esp. Prof. Raúl Tonelli

**Grupo J — Integrantes:**

- Castro
- Donoso
- Lagos
- Lumonte
- Quiroga

---

## 📋 Descripción

Implementación y caracterización de cuatro aplicaciones de la capa de aplicación sobre TCP/IP, escritas en Python 3:

| # | Aplicación | Protocolos | Archivos |
|---|---|---|---|
| 1 | **Cliente de correo** (web) | SMTP, IMAP4rev1, POP3 | `modulo_correo.py` (+ `servidor_correo_mock.py` para pruebas) |
| 2 | **Servidor web** propio | HTTP/1.0 | `servidor_web.py` |
| 3 | **Chat cliente/servidor** | Protocolo propio sobre TCP (JSON Lines) | `servidor_chat.py`, `chat_protocolo.py`, `modulo_chat.py`, `cliente_chat.py` |
| 4 | **Cliente FTP** (web) | FTP (control + datos, pasivo y activo) | `modulo_ftp.py` |

Los clientes 1, 3 y 4 se usan desde una única aplicación web (`app.py`, hecha con Streamlit). El servidor web (punto 2) y los servidores de chat, correo y FTP de prueba se ejecutan como procesos aparte.

### Servicios y puertos

| Servicio | Comando | Puerto(s) |
|---|---|---|
| App web con los clientes de correo, chat y FTP | `python -m streamlit run app.py` | 8501 |
| Servidor web HTTP (punto 2) | `python servidor_web.py` | 8080 |
| Servidor de chat (punto 3) | `python servidor_chat.py` | 5050 |
| Servidor de correo de prueba | `python servidor_correo_mock.py` | 1025 SMTP · 1143 IMAP · 1110 POP3 |
| Servidor FTP de prueba (pyftpdlib) | `python -m pyftpdlib -p 2121 -w -d ftp_files` | 2121 |

---

## 🛠️ Instalación

Requiere **Python 3.11 o superior**.

**Windows (PowerShell):**

```powershell
git clone https://github.com/Estaticoo/TP7-Redes-Aplicaciones
cd TP7-Redes-Aplicaciones
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**macOS / Linux:**

```bash
git clone https://github.com/Estaticoo/TP7-Redes-Aplicaciones
cd TP7-Redes-Aplicaciones
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 🚀 Ejecución

Para levantar todo de una vez:

- **Windows:** doble clic en `iniciar_tp7.bat` (abre una ventana por servicio).
- **macOS / Linux:** `./iniciar_tp7.sh` (Ctrl+C detiene todo).

Después abrir **http://localhost:8501** (clientes) y **http://localhost:8080** (servidor web).

También se puede iniciar cada servicio por separado con los comandos de la tabla anterior, usando `.venv\Scripts\python.exe` (Windows) o `.venv/bin/python` (macOS/Linux).

---

## ✅ Requisitos de la consigna y cómo verificarlos

### 1. Cliente de correo — `modulo_correo.py`

| Requisito | Implementación | Cómo probarlo |
|---|---|---|
| SMTP | `smtplib` con SSL/TLS, STARTTLS o sin cifrado; CC, CCO y adjuntos | Pestaña **Redactar** → Enviar |
| IMAP | `imaplib`: búsqueda en el servidor (`UID SEARCH`), descarga (`UID FETCH BODY.PEEK[]`) | Pestaña **Bandeja IMAP** → Buscar |
| POP3 | `poplib`: `STAT`, `UIDL`, `RETR`, `DELE`, `QUIT` | Pestaña **Bandeja POP3** → Descargar |
| Responder / Responder a todos | Completa destinatario, `Re:`, texto citado y cabeceras `In-Reply-To` / `References` | Botón **Responder** en un mensaje |
| Reenviar | `Fwd:` con el mensaje original y sus adjuntos | Botón **Reenviar** |
| Eliminar | IMAP: `UID STORE +FLAGS (\Deleted)` + `EXPUNGE` (en Gmail mueve a la Papelera). POP3: `DELE` + `QUIT` | Botón **Eliminar** |
| Buscar por distintos criterios | Remitente, destinatario, CC, asunto, **cuerpo**, texto completo y fecha, combinables. Soporta acentos (`CHARSET UTF-8`) | Formulario de búsqueda IMAP |

**Perfiles de servidor:** el perfil *Servidor local de prueba* (por defecto) usa `servidor_correo_mock.py` con el usuario `alumno@tp7.local` y la clave `1234` (sirve cualquier dirección con esa clave). El buzón arranca con 3 mensajes de ejemplo. El perfil *Gmail* necesita una [Contraseña de Aplicación](https://myaccount.google.com/apppasswords) y tener IMAP habilitado.

### 2. Servidor web — `servidor_web.py`

| Requisito | Implementación | Cómo probarlo |
|---|---|---|
| Protocolo HTTP | `http.server` multihilo (`ThreadingHTTPServer`), métodos GET, HEAD y POST | http://localhost:8080/publico/ |
| Logging | `webserver.log`: cada petición (IP, línea de pedido, código, tamaño), cambios de configuración y alertas 401/403/429 | http://localhost:8080/logs (requiere login) |
| Bloquear acceso fuera del DocumentRoot | La ruta se decodifica y se resuelve con `realpath`; si sale de la raíz responde **403** | `curl --path-as-is http://localhost:8080/../../etc/passwd` |
| Interfaz de configuración vía web | Puerto, DocumentRoot, directorio protegido, realm, usuario, contraseña y listado de directorios; se guarda en `config_servidor.json` | http://localhost:8080/config |
| Protección de directorios con usuario y contraseña | HTTP Basic (RFC 7617) sobre el directorio físico, sin distinguir mayúsculas ni codificación URL | http://localhost:8080/privado/secreto.html → `admin` / `1234` |

**Medidas de seguridad adicionales:** contraseña guardada como hash PBKDF2-SHA256 con salt y comparada en tiempo constante; bloqueo de la IP por 5 minutos tras 5 intentos fallidos (HTTP 429); token CSRF en el formulario de configuración; límite de tamaño del cuerpo POST; cabeceras `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` y `Content-Security-Policy`; escape HTML de todo lo que se muestra (logs, rutas); la cabecera `Server` no revela la versión de Python; la contraseña nunca se escribe en el log.

Pruebas de seguridad rápidas (todas deben dar 401 o 403):

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/PRIVADO/secreto.html
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/%70rivado/secreto.html
curl -s -o /dev/null -w "%{http_code}\n" --path-as-is http://localhost:8080/%2e%2e/%2e%2e/etc/passwd
```

En Windows usar `curl.exe` y, para el traversal, `http://localhost:8080/../../Windows/win.ini`.

### 3. Chat cliente/servidor — `servidor_chat.py`, `chat_protocolo.py`, `modulo_chat.py`, `cliente_chat.py`

| Requisito | Implementación |
|---|---|
| Múltiples canales y mensajes privados | Canales `General`, `Redes_UTN`, `TP7_Grupo` y los que creen los usuarios. Cada mensaje de canal se envía solo a los miembros del canal; los privados, solo a emisor y receptor |
| Protocolo | Protocolo propio de capa de aplicación sobre TCP (ver abajo), en lugar de XMPP/AMQP |
| Enviar archivos a un usuario | El archivo viaja en Base64, el servidor lo guarda y notifica al destinatario; solo emisor y receptor pueden descargarlo (máx. 8 MB) |
| Información de usuarios, perfil, foto | Registro con contraseña (hash PBKDF2), estado, foto (PNG/JPG/GIF/WEBP, máx. 1 MB), fecha de registro y presencia en línea |
| Guardar conversaciones | El servidor guarda todo el historial en `chat_data/historial/*.jsonl`; cada cliente puede exportar la conversación a `.txt` |
| Logging | `chat_server.log`: conexiones TCP, logins (y fallidos), canales, mensajes, archivos y perfiles. De los privados se registra solo el metadato, no el contenido |

Hay **dos clientes** que hablan el mismo protocolo: la app web (pestaña Chat) y un cliente de terminal:

```bash
python cliente_chat.py --usuario Ana --host 127.0.0.1
```

Para probar entre varias PCs de la misma red, ejecutar `servidor_chat.py` en una (escucha en todas las interfaces) y conectarse desde las demás con su IP.

**Especificación del protocolo:** cada mensaje es un objeto JSON en UTF-8 terminado en `\n`. El cliente envía pedidos con un número `req` y el servidor responde `{"tipo": "ok", "req": n, ...}` o `{"tipo": "error", "req": n, "mensaje": "..."}`. Además, el servidor empuja eventos sin `req` a los clientes conectados.

| Pedido (cliente → servidor) | Campos | Respuesta |
|---|---|---|
| `login` | `usuario`, `clave` | Registra al usuario la primera vez; devuelve canales y usuarios |
| `unirse` / `salir_canal` | `canal` | Historial del canal |
| `crear_canal` | `canal` | — |
| `mensaje_canal` | `canal`, `texto` | — |
| `mensaje_privado` | `para`, `texto` | — |
| `historial` | `canal` o `con` | Últimos 200 mensajes |
| `enviar_archivo` | `para`, `nombre`, `datos` (Base64) | `id` del archivo |
| `descargar` | `id` | `nombre`, `datos` (Base64) |
| `perfil` | `estado`, `foto` (Base64, opcional) | — |
| `ver_perfil` / `usuarios` | `usuario` / — | Perfil con foto / lista de usuarios |

| Evento (servidor → clientes) | Cuándo |
|---|---|
| `mensaje_canal`, `mensaje_privado`, `archivo` | Llega un mensaje o archivo |
| `usuarios` | Alguien se conecta, se desconecta o cambia su perfil |
| `canales` | Se crea un canal |

### 4. Cliente FTP — `modulo_ftp.py`

| Requisito | Implementación |
|---|---|
| Comandos más comunes | `USER`, `PASS`, `PWD`, `CWD`, `CDUP`, `LIST`, `MLSD`, `MKD`, `RMD`, `DELE`, `RNFR`/`RNTO`, `SIZE`, `TYPE`, `PASV`/`PORT`, `QUIT`, más una consola para enviar comandos al canal de control (`SYST`, `STAT`, `FEAT`, `HELP`, `NOOP`…) |
| Subir y bajar archivos | `STOR` y `RETR` en modo binario |

Permite elegir modo **pasivo** o **activo** y muestra el **diálogo del canal de control** (comandos del cliente y respuestas del servidor, con la contraseña oculta).

---

## 🦈 Capturas con Wireshark (para la caracterización)

Todo corre en local, así que se captura en la interfaz de **loopback** (en Windows hace falta Npcap con soporte loopback). Los servidores de prueba no cifran, así que se ven los comandos de cada protocolo. Como usan puertos no estándar, hay que indicarle a Wireshark el protocolo con *Analizar → Decodificar como…*:

| Protocolo | Filtro | Decodificar como |
|---|---|---|
| SMTP / IMAP / POP3 | `tcp.port in {1025 1143 1110}` | 1025 → SMTP, 1143 → IMAP, 1110 → POP |
| HTTP | `tcp.port == 8080` | HTTP (se ve la cabecera `Authorization: Basic`) |
| FTP | `tcp.port == 2121 \|\| ftp-data` | 2121 → FTP |
| Chat | `tcp.port == 5050` | *Seguir → Flujo TCP* muestra los JSON |

---

## 📂 Estructura del repositorio

```text
├── app.py                   # App web: menú y navegación entre los clientes
├── modulo_correo.py         # Punto 1: cliente de correo SMTP / IMAP / POP3
├── servidor_correo_mock.py  # Servidor de correo de prueba (SMTP 1025, IMAP 1143, POP3 1110)
├── servidor_web.py          # Punto 2: servidor HTTP con DocumentRoot, Basic Auth, configuración y logs
├── servidor_chat.py         # Punto 3: servidor de chat TCP multihilo
├── chat_protocolo.py        # Punto 3: protocolo y cliente reutilizable
├── modulo_chat.py           # Punto 3: cliente de chat web
├── cliente_chat.py          # Punto 3: cliente de chat de terminal
├── modulo_ftp.py            # Punto 4: cliente FTP
├── iniciar_tp7.bat          # Inicia todo en Windows
├── iniciar_tp7.sh           # Inicia todo en macOS / Linux
└── requirements.txt         # Dependencias (streamlit, pyftpdlib, aiosmtpd y sus dependencias)
```

Al ejecutarse se crean `www/` (DocumentRoot), `buzones/`, `chat_data/`, `ftp_files/`, `config_servidor.json` y los `*.log` (todos excluidos del repositorio).

## ⚠️ Limitaciones conocidas

- El servidor web, el chat y los servidores de prueba de correo y FTP no usan TLS: las credenciales viajan sin cifrar (HTTP Basic solo las codifica en Base64). En producción se usaría HTTPS, FTPS y TLS en el chat.
- El servidor de correo de prueba acepta cualquier dirección con la clave `1234` y solo tiene la carpeta INBOX.
- El servidor web tiene un único usuario administrador.
