"""Punto 1: Cliente de correo electrónico con SMTP, IMAP y POP3."""
import re
import ssl
import html
import email
import email.policy
import imaplib
import poplib
import smtplib
import mimetypes
from email.message import EmailMessage
from email.utils import formatdate, getaddresses, make_msgid
import streamlit as st

TAB_REDACTAR = "✉️ Redactar (SMTP)"
TAB_IMAP = "📥 Bandeja IMAP"
TAB_POP3 = "📦 Bandeja POP3"
MESES_IMAP = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SEGURIDAD_SMTP = ["SSL/TLS", "STARTTLS", "Ninguna"]

PERFILES = {
    "Servidor local de prueba": {
        "correo_usuario": "alumno@tp7.local", "correo_clave": "1234",
        "smtp_host": "127.0.0.1", "smtp_port": 1025, "smtp_seg": "Ninguna",
        "imap_host": "127.0.0.1", "imap_port": 1143, "imap_ssl": False,
        "pop_host": "127.0.0.1", "pop_port": 1110, "pop_ssl": False,
    },
    "Gmail": {
        "correo_usuario": "tu_correo@gmail.com", "correo_clave": "",
        "smtp_host": "smtp.gmail.com", "smtp_port": 465, "smtp_seg": "SSL/TLS",
        "imap_host": "imap.gmail.com", "imap_port": 993, "imap_ssl": True,
        "pop_host": "pop.gmail.com", "pop_port": 995, "pop_ssl": True,
    },
    "Outlook / Hotmail": {
        "correo_usuario": "tu_correo@outlook.com", "correo_clave": "",
        "smtp_host": "smtp-mail.outlook.com", "smtp_port": 587, "smtp_seg": "STARTTLS",
        "imap_host": "outlook.office365.com", "imap_port": 993, "imap_ssl": True,
        "pop_host": "outlook.office365.com", "pop_port": 995, "pop_ssl": True,
    },
}

CAMPOS_REDACCION = ["redactar_para", "redactar_cc", "redactar_cco", "redactar_asunto", "redactar_cuerpo"]
# Claves de widgets que deben sobrevivir al cambiar de módulo en la barra lateral
CLAVES_PERSISTENTES = ["correo_perfil", *PERFILES["Gmail"], *CAMPOS_REDACCION, "imap_carpeta"]


# ============================================================================
# Estado y conexiones
# ============================================================================
def aplicar_perfil():
    st.session_state.update(PERFILES[st.session_state.correo_perfil])


def inicializar_estado():
    ss = st.session_state
    if "correo_perfil" not in ss:
        ss.correo_perfil = "Servidor local de prueba"
        aplicar_perfil()
    for campo in CAMPOS_REDACCION:
        ss.setdefault(campo, "")
    ss.setdefault("imap_carpeta", "INBOX")
    ss.setdefault("redactar_nonce", 0)
    ss.setdefault("redactar_adjuntos_reenvio", [])
    ss.setdefault("imap_resultados", [])
    ss.setdefault("pop_resultados", [])


def avisar(tipo, texto):
    st.session_state.correo_aviso = (tipo, texto)


def contexto_tls():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def conectar_smtp():
    ss = st.session_state
    host, puerto = ss.smtp_host, int(ss.smtp_port)
    if ss.smtp_seg == "SSL/TLS":
        servidor = smtplib.SMTP_SSL(host, puerto, context=contexto_tls(), timeout=20)
    else:
        servidor = smtplib.SMTP(host, puerto, timeout=20)
        if ss.smtp_seg == "STARTTLS":
            servidor.starttls(context=contexto_tls())
    servidor.ehlo_or_helo_if_needed()
    # El servidor local no pide autenticación; Gmail/Outlook sí (anuncian AUTH en EHLO)
    if ss.correo_clave and servidor.has_extn("auth"):
        servidor.login(ss.correo_usuario, ss.correo_clave)
    return servidor


def conectar_imap():
    ss = st.session_state
    if ss.imap_ssl:
        imap = imaplib.IMAP4_SSL(ss.imap_host, int(ss.imap_port), ssl_context=contexto_tls(), timeout=20)
    else:
        imap = imaplib.IMAP4(ss.imap_host, int(ss.imap_port), timeout=20)
    imap.login(ss.correo_usuario, ss.correo_clave)
    return imap


def seleccionar_carpeta(imap):
    carpeta = st.session_state.get("imap_carpeta") or "INBOX"
    tipo, datos = imap.select(citar(carpeta))
    if tipo != "OK":
        raise imaplib.IMAP4.error(f"No se pudo abrir la carpeta {carpeta}: {datos}")


def conectar_pop3():
    ss = st.session_state
    if ss.pop_ssl:
        pop = poplib.POP3_SSL(ss.pop_host, int(ss.pop_port), context=contexto_tls(), timeout=20)
    else:
        pop = poplib.POP3(ss.pop_host, int(ss.pop_port), timeout=20)
    pop.user(ss.correo_usuario)
    pop.pass_(ss.correo_clave)
    return pop


def citar(nombre):
    return '"' + nombre.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ============================================================================
# Análisis de mensajes (RFC 5322 / MIME)
# ============================================================================
def parsear(datos):
    msg = email.message_from_bytes(datos, policy=email.policy.default)
    cuerpo = ""
    parte = msg.get_body(preferencelist=("plain", "html"))
    if parte is not None:
        try:
            cuerpo = parte.get_content()
        except (LookupError, ValueError):
            cuerpo = (parte.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
        if parte.get_content_subtype() == "html":
            cuerpo = html.unescape(re.sub(r"<[^>]+>", " ", cuerpo))
    adjuntos = [(p.get_filename() or "adjunto", p.get_payload(decode=True) or b"") for p in msg.iter_attachments()]
    return {
        "de": str(msg.get("From", "")),
        "para": str(msg.get("To", "")),
        "cc": str(msg.get("Cc", "")),
        "responder_a": str(msg.get("Reply-To", "")),
        "asunto": str(msg.get("Subject", "")) or "(Sin asunto)",
        "fecha": str(msg.get("Date", "")),
        "message_id": str(msg.get("Message-ID", "")),
        "referencias": str(msg.get("References", "")),
        "cuerpo": re.sub(r"\n{3,}", "\n\n", cuerpo).strip(),
        "adjuntos": adjuntos,
    }


def direcciones(*campos):
    return [direccion for _, direccion in getaddresses([c for c in campos if c]) if direccion]


# ============================================================================
# Acciones (callbacks: se ejecutan antes de redibujar la página)
# ============================================================================
def limpiar_redaccion():
    ss = st.session_state
    for campo in CAMPOS_REDACCION:
        ss[campo] = ""
    ss.redactar_adjuntos_reenvio = []
    ss.pop("redactar_en_respuesta_a", None)
    ss.pop("redactar_referencias", None)
    ss.redactar_nonce += 1  # reinicia el selector de adjuntos


def enviar_correo():
    ss = st.session_state
    destinatarios = direcciones(ss.redactar_para, ss.redactar_cc, ss.redactar_cco)
    if not destinatarios:
        avisar("error", "Indicá al menos un destinatario.")
        return
    try:
        msg = EmailMessage()
        msg["From"] = ss.correo_usuario
        if ss.redactar_para:
            msg["To"] = ss.redactar_para
        if ss.redactar_cc:
            msg["Cc"] = ss.redactar_cc
        if ss.redactar_cco:
            msg["Bcc"] = ss.redactar_cco  # send_message lo usa como destinatario y no lo transmite
        msg["Subject"] = ss.redactar_asunto
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=ss.correo_usuario.partition("@")[2] or "tp7.local")
        if ss.get("redactar_en_respuesta_a"):
            msg["In-Reply-To"] = ss.redactar_en_respuesta_a
            msg["References"] = ss.redactar_referencias
        msg.set_content(ss.redactar_cuerpo)
        adjuntos = [(f.name, f.getvalue()) for f in ss.get(f"redactar_adjuntos_{ss.redactar_nonce}") or []]
        adjuntos += list(ss.redactar_adjuntos_reenvio)
        for nombre, datos in adjuntos:
            tipo = mimetypes.guess_type(nombre)[0] or "application/octet-stream"
            principal, _, secundario = tipo.partition("/")
            msg.add_attachment(datos, maintype=principal, subtype=secundario, filename=nombre)
        with conectar_smtp() as servidor:
            rechazados = servidor.send_message(msg)
        enviados = len(destinatarios) - len(rechazados)
        avisar("success", f"✅ Correo enviado por SMTP a {enviados} destinatario(s) con {len(adjuntos)} adjunto(s).")
        limpiar_redaccion()
    except Exception as e:
        avisar("error", f"Error SMTP: {e}")


def citar_cuerpo(c):
    citado = "\n".join("> " + linea for linea in c["cuerpo"].splitlines())
    return f"\n\nEl {c['fecha']}, {c['de']} escribió:\n{citado}"


def preparar_respuesta(c, a_todos=False):
    ss = st.session_state
    limpiar_redaccion()
    ss.redactar_para = c["responder_a"] or c["de"]
    if a_todos:
        propio = ss.correo_usuario.lower()
        ss.redactar_cc = ", ".join(d for d in direcciones(c["para"], c["cc"]) if d.lower() != propio)
    asunto = c["asunto"]
    ss.redactar_asunto = asunto if asunto.lower().startswith("re:") else f"Re: {asunto}"
    ss.redactar_cuerpo = citar_cuerpo(c)
    ss.redactar_en_respuesta_a = c["message_id"]
    ss.redactar_referencias = f"{c['referencias']} {c['message_id']}".strip()
    ss.correo_tab = TAB_REDACTAR
    avisar("info", "Respuesta preparada: revisá el texto y presioná Enviar.")


def preparar_reenvio(c):
    ss = st.session_state
    limpiar_redaccion()
    asunto = c["asunto"]
    ss.redactar_asunto = asunto if asunto.lower().startswith("fwd:") else f"Fwd: {asunto}"
    ss.redactar_cuerpo = (
        "\n\n---------- Mensaje reenviado ----------\n"
        f"De: {c['de']}\nFecha: {c['fecha']}\nAsunto: {c['asunto']}\nPara: {c['para']}\n\n{c['cuerpo']}"
    )
    ss.redactar_adjuntos_reenvio = list(c["adjuntos"])
    ss.correo_tab = TAB_REDACTAR
    avisar("info", "Reenvío preparado: completá el destinatario y presioná Enviar.")


def buscar_papelera(imap):
    """Busca la carpeta marcada como \\Trash (RFC 6154). En Gmail borrar = mover a la Papelera."""
    _, carpetas = imap.list()
    for linea in carpetas or []:
        texto = linea.decode("utf-8", errors="replace") if isinstance(linea, bytes) else str(linea)
        if "\\Trash" in texto:
            nombre = re.search(r'"([^"]+)"\s*$', texto) or re.search(r"(\S+)\s*$", texto)
            return nombre.group(1)
    return None


def eliminar_imap(uid):
    ss = st.session_state
    try:
        imap = conectar_imap()
        seleccionar_carpeta(imap)
        papelera = buscar_papelera(imap)
        if papelera and papelera != ss.get("imap_carpeta"):
            imap.uid("COPY", uid, citar(papelera))
        # Se identifica el mensaje por UID (estable), no por número de secuencia
        imap.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
        imap.expunge()
        imap.logout()
        ss.imap_resultados = [c for c in ss.imap_resultados if c["id"] != uid]
        destino = f" (movido a {papelera})" if papelera else ""
        avisar("success", f"🗑️ Correo UID {uid} eliminado por IMAP{destino}.")
    except Exception as e:
        avisar("error", f"Error IMAP al eliminar: {e}")


def eliminar_pop3(uid_pop):
    ss = st.session_state
    try:
        pop = conectar_pop3()
        _, lineas, _ = pop.uidl()
        numeros = {u: int(n) for n, u in (l.decode().split(" ", 1) for l in lineas)}
        if uid_pop not in numeros:
            pop.quit()
            avisar("error", "El mensaje ya no está en el servidor.")
            return
        pop.dele(numeros[uid_pop])
        pop.quit()  # POP3 borra recién al cerrar la sesión con QUIT
        ss.pop_resultados = [c for c in ss.pop_resultados if c["id"] != uid_pop]
        avisar("success", f"🗑️ Mensaje {numeros[uid_pop]} eliminado por POP3 (DELE + QUIT).")
    except Exception as e:
        avisar("error", f"Error POP3 al eliminar: {e}")


# ============================================================================
# Búsqueda IMAP y descarga POP3
# ============================================================================
def buscar_imap(criterios, desde, cantidad):
    imap = conectar_imap()
    try:
        seleccionar_carpeta(imap)
        conjuntos = []
        for clave, valor in criterios:
            # Cada criterio va como literal UTF-8 para soportar acentos y ñ
            imap.literal = valor.encode("utf-8")
            tipo, datos = imap.uid("SEARCH", "CHARSET", "UTF-8", clave)
            if tipo != "OK":
                raise imaplib.IMAP4.error(f"SEARCH {clave} falló: {datos}")
            conjuntos.append(set(datos[0].split()))
        if desde:
            fecha = f"{desde.day:02d}-{MESES_IMAP[desde.month - 1]}-{desde.year}"
            conjuntos.append(set(imap.uid("SEARCH", None, f"SINCE {fecha}")[1][0].split()))
        if not conjuntos:
            conjuntos.append(set(imap.uid("SEARCH", None, "ALL")[1][0].split()))
        uids = sorted(set.intersection(*conjuntos), key=int, reverse=True)
        resultados = []
        if uids:
            elegidos = b",".join(uids[:cantidad]).decode()
            # BODY.PEEK[] descarga el mensaje sin marcarlo como leído
            _, datos = imap.uid("FETCH", elegidos, "(BODY.PEEK[])")
            for item in datos:
                if isinstance(item, tuple):
                    uid = re.search(rb"UID (\d+)", item[0])
                    c = parsear(item[1])
                    c["id"] = uid.group(1).decode() if uid else "?"
                    resultados.append(c)
            resultados.sort(key=lambda c: int(c["id"]) if c["id"].isdigit() else 0, reverse=True)
        return len(uids), resultados
    finally:
        imap.logout()


def descargar_pop3(cantidad):
    pop = conectar_pop3()
    try:
        bienvenida = pop.getwelcome().decode("utf-8", errors="replace")
        total, octetos = pop.stat()
        _, lineas, _ = pop.uidl()
        uidl = {int(n): u for n, u in (l.decode().split(" ", 1) for l in lineas)}
        resultados = []
        for numero in range(total, max(0, total - cantidad), -1):
            _, lineas_msg, _ = pop.retr(numero)
            c = parsear(b"\r\n".join(lineas_msg))
            c.update(id=uidl.get(numero, str(numero)), numero=numero)
            resultados.append(c)
        return bienvenida, total, octetos, resultados
    finally:
        pop.quit()


# ============================================================================
# Interfaz
# ============================================================================
def mostrar_mensaje(c, protocolo):
    etiqueta = f"#{c.get('numero', c['id'])} | De: {c['de']} | Asunto: {c['asunto']}"
    with st.expander(etiqueta):
        st.markdown(f"**Para:** {c['para'] or '-'}  \n**CC:** {c['cc'] or '-'}  \n**Fecha:** {c['fecha'] or '-'}")
        st.text(c["cuerpo"] or "(Sin contenido de texto)")
        for i, (nombre, datos) in enumerate(c["adjuntos"]):
            st.download_button(f"📎 {nombre} ({len(datos)} bytes)", datos, file_name=nombre,
                               key=f"{protocolo}_adj_{c['id']}_{i}", on_click="ignore")
        b1, b2, b3, b4 = st.columns(4)
        b1.button("↩️ Responder", key=f"{protocolo}_rep_{c['id']}", on_click=preparar_respuesta, args=(c,))
        b2.button("↩️ Responder a todos", key=f"{protocolo}_repall_{c['id']}", on_click=preparar_respuesta, args=(c, True))
        b3.button("➡️ Reenviar", key=f"{protocolo}_fwd_{c['id']}", on_click=preparar_reenvio, args=(c,))
        accion = eliminar_imap if protocolo == "imap" else eliminar_pop3
        b4.button("🗑️ Eliminar", key=f"{protocolo}_del_{c['id']}", on_click=accion, args=(c["id"],))


def mostrar_configuracion():
    with st.expander("⚙️ Configuración de Servidores de Correo", expanded=False):
        st.selectbox("Perfil", list(PERFILES), key="correo_perfil", on_change=aplicar_perfil,
                     help="Completa los servidores y puertos habituales. Después se pueden editar.")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.text_input("Usuario / Email", key="correo_usuario")
            st.text_input("Contraseña", type="password", key="correo_clave",
                          help="En Gmail usar una Contraseña de Aplicación de 16 letras. En el servidor local: 1234")
        with col2:
            st.text_input("Servidor SMTP", key="smtp_host")
            st.number_input("Puerto SMTP", min_value=1, max_value=65535, key="smtp_port")
            st.selectbox("Seguridad SMTP", SEGURIDAD_SMTP, key="smtp_seg")
        with col3:
            st.text_input("Servidor IMAP", key="imap_host")
            st.number_input("Puerto IMAP", min_value=1, max_value=65535, key="imap_port")
            st.checkbox("IMAP con SSL/TLS", key="imap_ssl")
        with col4:
            st.text_input("Servidor POP3", key="pop_host")
            st.number_input("Puerto POP3", min_value=1, max_value=65535, key="pop_port")
            st.checkbox("POP3 con SSL/TLS", key="pop_ssl")
    ss = st.session_state
    st.caption(f"Conectado como **{ss.correo_usuario}** · SMTP {ss.smtp_host}:{ss.smtp_port} ({ss.smtp_seg}) · "
               f"IMAP {ss.imap_host}:{ss.imap_port}{' SSL' if ss.imap_ssl else ''} · "
               f"POP3 {ss.pop_host}:{ss.pop_port}{' SSL' if ss.pop_ssl else ''}")


def mostrar_redactar():
    ss = st.session_state
    st.subheader("Enviar Correo (SMTP)")
    st.caption("SMTP (RFC 5321) entrega el mensaje al servidor de salida: EHLO → [STARTTLS] → AUTH → MAIL FROM → RCPT TO → DATA → QUIT. "
               "Puertos: 25 (entre servidores), 587 (STARTTLS), 465 (SSL/TLS implícito).")
    st.text_input("Para:", key="redactar_para", placeholder="destino@ejemplo.com, otro@ejemplo.com")
    c1, c2 = st.columns(2)
    c1.text_input("CC:", key="redactar_cc")
    c2.text_input("CCO (copia oculta):", key="redactar_cco")
    st.text_input("Asunto:", key="redactar_asunto")
    st.text_area("Mensaje:", key="redactar_cuerpo", height=200)
    st.file_uploader("Adjuntar archivos:", accept_multiple_files=True, key=f"redactar_adjuntos_{ss.redactar_nonce}")
    if ss.redactar_adjuntos_reenvio:
        st.caption("Se reenviarán los adjuntos originales: " + ", ".join(n for n, _ in ss.redactar_adjuntos_reenvio))
    if ss.get("redactar_en_respuesta_a"):
        st.caption(f"Respuesta a {ss.redactar_en_respuesta_a} (cabeceras In-Reply-To y References)")
    b1, b2, _ = st.columns([1, 1, 3])
    b1.button("📤 Enviar Correo", type="primary", on_click=enviar_correo)
    b2.button("🧹 Limpiar", on_click=limpiar_redaccion)


def mostrar_imap():
    ss = st.session_state
    st.subheader("Búsqueda y Gestión de Correos (IMAP)")
    st.caption("IMAP (RFC 3501) deja los mensajes en el servidor y permite carpetas, búsquedas del lado del servidor (SEARCH) "
               "y marcas (STORE \\Deleted + EXPUNGE). Puertos: 143 (texto plano / STARTTLS) y 993 (SSL/TLS).")
    with st.form("form_busqueda_imap"):
        c1, c2, c3 = st.columns(3)
        de = c1.text_input("Remitente (FROM)")
        para = c2.text_input("Destinatario (TO)")
        cc = c3.text_input("Con copia (CC)")
        c4, c5, c6 = st.columns(3)
        asunto = c4.text_input("Asunto (SUBJECT)")
        cuerpo = c5.text_input("Cuerpo del mail (BODY)")
        texto = c6.text_input("Texto completo (TEXT)")
        c7, c8, c9 = st.columns(3)
        desde = c7.date_input("Desde la fecha (SINCE)", value=None, format="DD/MM/YYYY")
        c8.text_input("Carpeta", key="imap_carpeta", help="En Gmail también: [Gmail]/Enviados, [Gmail]/Papelera, etc.")
        cantidad = c9.number_input("Máximo a mostrar", min_value=1, max_value=100, value=20)
        buscar = st.form_submit_button("🔍 Buscar en Servidor IMAP", type="primary")
    if buscar:
        criterios = [(k, v.strip()) for k, v in [("FROM", de), ("TO", para), ("CC", cc), ("SUBJECT", asunto),
                                                 ("BODY", cuerpo), ("TEXT", texto)] if v.strip()]
        try:
            total, ss.imap_resultados = buscar_imap(criterios, desde, int(cantidad))
            filtro = " AND ".join(f'{k} "{v}"' for k, v in criterios) or "ALL"
            st.info(f"Búsqueda `{filtro}`: {total} correo(s) encontrados. Mostrando {len(ss.imap_resultados)}.")
        except Exception as e:
            ss.imap_resultados = []
            st.error(f"Error IMAP: {e}")
    for c in ss.imap_resultados:
        mostrar_mensaje(c, "imap")


def mostrar_pop3():
    ss = st.session_state
    st.subheader("Descarga de Mensajes con POP3")
    st.caption("POP3 (RFC 1939) descarga los mensajes al cliente: USER/PASS → STAT → LIST/UIDL → RETR → DELE → QUIT. "
               "No tiene carpetas ni búsqueda en el servidor. Puertos: 110 (texto plano) y 995 (SSL/TLS).")
    c1, c2 = st.columns([1, 3])
    cantidad = c1.number_input("Últimos mensajes a descargar", min_value=1, max_value=50, value=10)
    if c2.button("📥 Conectar y Descargar por POP3", type="primary"):
        try:
            bienvenida, total, octetos, ss.pop_resultados = descargar_pop3(int(cantidad))
            st.success(f"Servidor: `{bienvenida}` · STAT: {total} mensajes en el buzón ({octetos} bytes).")
        except Exception as e:
            ss.pop_resultados = []
            st.error(f"Error POP3: {e}")
    for c in ss.pop_resultados:
        mostrar_mensaje(c, "pop")


def mostrar():
    inicializar_estado()
    st.header("1. Cliente de Correo Electrónico")
    mostrar_configuracion()
    if aviso := st.session_state.pop("correo_aviso", None):
        getattr(st, aviso[0])(aviso[1])
    tab_smtp, tab_imap, tab_pop = st.tabs([TAB_REDACTAR, TAB_IMAP, TAB_POP3], key="correo_tab", on_change="rerun")
    with tab_smtp:
        mostrar_redactar()
    with tab_imap:
        mostrar_imap()
    with tab_pop:
        mostrar_pop3()
