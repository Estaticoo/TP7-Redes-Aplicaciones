import streamlit as st
import smtplib
import imaplib
import poplib
import email
from email.message import EmailMessage
from ftplib import FTP
from datetime import datetime
import logging
import io
import os

st.set_page_config(page_title="TP7 - Redes de Información", layout="wide")

# Logging para el Chat (Punto 3)
logging.basicConfig(filename="chat_server.log", level=logging.INFO, format="%(asctime)s - %(message)s")

st.sidebar.title("TP N°7 - Aplicaciones")
modulo = st.sidebar.radio("Seleccionar Aplicación:", [
    "1. Cliente de Correo (SMTP/IMAP/POP3)",
    "3. Chat Mensajería Instantánea",
    "4. Cliente FTP"
])

# ==============================================================================
# PUNTO 1: CLIENTE DE CORREO (SMTP, IMAP, POP3)
# ==============================================================================
if modulo == "1. Cliente de Correo (SMTP/IMAP/POP3)":
    st.header("1. Cliente de Correo Electrónico")
    
    with st.expander("⚙️ Configuración de Servidores de Correo", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            email_user = st.text_input("Usuario / Email", "tu_correo@gmail.com")
            email_pass = st.text_input("Contraseña de Aplicación", type="password", help="En Gmail usar Contraseña de Aplicación de 16 letras")
        with col2:
            smtp_host = st.text_input("Servidor SMTP", "smtp.gmail.com")
            smtp_port = st.number_input("Puerto SMTP", value=465)
            modo_local = st.checkbox("Usar SMTP Local de Prueba (Sin SSL - Puerto 1025)")
        with col3:
            imap_host = st.text_input("Servidor IMAP", "imap.gmail.com")
            pop_host = st.text_input("Servidor POP3", "pop.gmail.com")

    # Estado para autocompletar Responder / Reenviar
    if "dest_auto" not in st.session_state: st.session_state.dest_auto = ""
    if "asunto_auto" not in st.session_state: st.session_state.asunto_auto = ""
    if "cuerpo_auto" not in st.session_state: st.session_state.cuerpo_auto = ""

    tab_smtp, tab_imap, tab_pop = st.tabs([
        "✉️ Redactar / Responder / Reenviar (SMTP)",
        "📥 Bandeja IMAP (Búsqueda y Acciones)",
        "📦 Bandeja POP3"
    ])

    with tab_smtp:
        st.subheader("Enviar Correo (SMTP)")
        dest = st.text_input("Para:", value=st.session_state.dest_auto)
        asunto = st.text_input("Asunto:", value=st.session_state.asunto_auto)
        cuerpo = st.text_area("Mensaje:", value=st.session_state.cuerpo_auto, height=150)
        
        if st.button("Enviar Correo"):
            try:
                msg = EmailMessage()
                msg.set_content(cuerpo)
                msg["Subject"] = asunto
                msg["From"] = email_user
                msg["To"] = dest
                
                if modo_local:
                    with smtplib.SMTP("127.0.0.1", 1025) as server:
                        server.send_message(msg)
                else:
                    with smtplib.SMTP_SSL(smtp_host, int(smtp_port)) as server:
                        server.login(email_user, email_pass)
                        server.send_message(msg)
                st.success("✅ Correo enviado exitosamente por protocolo SMTP.")
            except Exception as e:
                st.error(f"Error SMTP: {e}")

    with tab_imap:
        st.subheader("Búsqueda y Gestión de Correos (IMAP)")
        c1, c2 = st.columns([1, 2])
        with c1:
            criterio = st.selectbox("Buscar por criterio:", [
                "ALL (Todos)",
                "FROM (Remitente)",
                "TO (Destinatario)",
                "SUBJECT (Asunto)",
                "TEXT (Cuerpo del mail)"
            ])
        with c2:
            texto_buscar = st.text_input("Término de búsqueda:")

        if st.button("🔍 Buscar en Servidor IMAP"):
            try:
                mail = imaplib.IMAP4_SSL(imap_host)
                mail.login(email_user, email_pass)
                mail.select("inbox")
                
                clave = criterio.split(" ")[0]
                query = "ALL" if clave == "ALL" else f'({clave} "{texto_buscar}")'
                _, data = mail.search(None, query)
                mail_ids = data[0].split()
                
                st.info(f"Se encontraron {len(mail_ids)} correos. Mostrando los últimos 5:")
                st.session_state.lista_correos = []
                
                for m_id in reversed(mail_ids[-5:]):
                    _, msg_data = mail.fetch(m_id, "(RFC822)")
                    raw = email.message_from_bytes(msg_data[0][1])
                    body_txt = ""
                    if raw.is_multipart():
                        for part in raw.walk():
                            if part.get_content_type() == "text/plain":
                                body_txt = part.get_payload(decode=True).decode(errors="ignore")
                                break
                    else:
                        body_txt = raw.get_payload(decode=True).decode(errors="ignore")
                        
                    st.session_state.lista_correos.append({
                        "id": m_id.decode(),
                        "from": raw.get("From", ""),
                        "to": raw.get("To", ""),
                        "subject": raw.get("Subject", "(Sin asunto)"),
                        "body": body_txt[:500]
                    })
                mail.logout()
            except Exception as e:
                st.error(f"Error IMAP: {e}")

        # Mostrar resultados con botones de Responder, Reenviar y Eliminar
        if "lista_correos" in st.session_state:
            for c in st.session_state.lista_correos:
                with st.expander(f"ID #{c['id']} | De: {c['from']} | Asunto: {c['subject']}"):
                    st.write(f"**Para:** {c['to']}")
                    st.text(c["body"])
                    b1, b2, b3 = st.columns(3)
                    if b1.button("↩️ Responder", key=f"rep_{c['id']}"):
                        st.session_state.dest_auto = c["from"]
                        st.session_state.asunto_auto = f"Re: {c['subject']}"
                        st.session_state.cuerpo_auto = f"\n\n--- En respuesta a {c['from']} ---\n{c['body']}"
                        st.toast("Datos cargados en la pestaña Redactar (SMTP)")
                    if b2.button("➡️ Reenviar", key=f"fwd_{c['id']}"):
                        st.session_state.dest_auto = ""
                        st.session_state.asunto_auto = f"Fwd: {c['subject']}"
                        st.session_state.cuerpo_auto = f"--- Mensaje Reenviado ---\nDe: {c['from']}\n\n{c['body']}"
                        st.toast("Datos cargados en la pestaña Redactar (SMTP)")
                    if b3.button("🗑️ Eliminar", key=f"del_{c['id']}"):
                        try:
                            mail = imaplib.IMAP4_SSL(imap_host)
                            mail.login(email_user, email_pass)
                            mail.select("inbox")
                            mail.store(c["id"], '+FLAGS', '\\Deleted')
                            mail.expunge()
                            mail.logout()
                            st.success(f"Correo #{c['id']} eliminado del servidor.")
                        except Exception as e:
                            st.error(f"Error al eliminar: {e}")

    with tab_pop:
        st.subheader("Descarga de Mensajes con POP3")
        if st.button("📥 Conectar y Descargar por POP3"):
            try:
                pop = poplib.POP3_SSL(pop_host)
                pop.user(email_user)
                pop.pass_(email_pass)
                num, total_bytes = pop.stat()
                st.success(f"Conectado por POP3: {num} mensajes en buzón ({total_bytes} bytes).")
                for i in range(max(1, num - 3), num + 1):
                    resp, lines, octets = pop.retr(i)
                    msg = email.message_from_bytes(b"\n".join(lines))
                    st.write(f"**Mensaje #{i}** | De: `{msg['From']}` | Asunto: `{msg['Subject']}`")
                pop.quit()
            except Exception as e:
                st.error(f"Error POP3: {e}")

# ==============================================================================
# PUNTO 3: CHAT / MENSAJERÍA INSTANTÁNEA
# ==============================================================================
elif modulo == "3. Chat Mensajería Instantánea":
    st.header("3. Aplicación Cliente/Servidor de Chat")

    @st.cache_resource
    def iniciar_servidor_chat():
        return {
            "canales": {"General": [], "Redes_UTN": [], "TP7_Grupo": []},
            "privados": [],
            "usuarios": {}
        }

    chat_srv = iniciar_servidor_chat()

    # Perfil lateral
    with st.sidebar:
        st.subheader("👤 Mi Perfil de Chat")
        mi_usuario = st.text_input("Nick de Usuario", "Hernan")
        mi_estado = st.text_input("Estado / Info", "Conectado desde UTN FRM")
        mi_foto = st.file_uploader("Foto de Perfil", type=["png", "jpg", "jpeg"])
        if st.button("Guardar Perfil"):
            chat_srv["usuarios"][mi_usuario] = {
                "estado": mi_estado,
                "foto": mi_foto.getvalue() if mi_foto else None
            }
            logging.info(f"PERFIL ACTUALIZADO: {mi_usuario} ({mi_estado})")
            st.success("Perfil registrado en el servidor.")

    t_canales, t_privados, t_perfiles, t_logs = st.tabs([
        "💬 Múltiples Canales",
        "🔒 Mensajes Privados y Archivos",
        "👥 Perfiles de Usuarios",
        "📋 Registro del Servidor (Logs)"
    ])

    with t_canales:
        c_sel, c_new = st.columns([2, 1])
        canal = c_sel.selectbox("Canal Activo:", list(chat_srv["canales"].keys()))
        nuevo_canal = c_new.text_input("Crear nuevo canal:")
        if c_new.button("Crear Canal") and nuevo_canal:
            chat_srv["canales"][nuevo_canal] = []
            logging.info(f"CANAL CREADO: {nuevo_canal} por {mi_usuario}")
            st.rerun()

        st.markdown(f"### Sala: #{canal}")
        caja = st.container(height=280, border=True)
        for m in chat_srv["canales"][canal]:
            caja.markdown(f"**[{m['hora']}] {m['user']}:** {m['msg']}")

        msg_txt = st.text_input("Escribir mensaje al canal:")
        b_env, b_ref, b_save = st.columns(3)
        if b_env.button("Enviar al Canal") and msg_txt:
            hora = datetime.now().strftime("%H:%M:%S")
            chat_srv["canales"][canal].append({"hora": hora, "user": mi_usuario, "msg": msg_txt})
            logging.info(f"MSG CANAL #{canal} | {mi_usuario}: {msg_txt}")
            st.rerun()
        if b_ref.button("🔄 Actualizar Chat"):
            st.rerun()
        
        historial = "\n".join([f"[{m['hora']}] {m['user']}: {m['msg']}" for m in chat_srv["canales"][canal]])
        b_save.download_button("💾 Guardar Conversación", historial, file_name=f"chat_{canal}.txt")

    with t_privados:
        col_form, col_bandeja = st.columns(2)
        with col_form:
            st.subheader("Enviar Privado / Archivo")
            para_user = st.text_input("Destinatario (Nick exacto):", "Compañero")
            priv_txt = st.text_area("Mensaje privado:")
            archivo_adj = st.file_uploader("Enviar archivo a este usuario:")
            if st.button("Enviar Privado"):
                hora = datetime.now().strftime("%H:%M:%S")
                chat_srv["privados"].append({
                    "hora": hora, "de": mi_usuario, "para": para_user,
                    "msg": priv_txt,
                    "archivo_bytes": archivo_adj.getvalue() if archivo_adj else None,
                    "archivo_nombre": archivo_adj.name if archivo_adj else None
                })
                logging.info(f"PRIVADO | De: {mi_usuario} -> Para: {para_user} | Archivo: {archivo_adj.name if archivo_adj else 'No'}")
                st.success("Mensaje/Archivo enviado.")

        with col_bandeja:
            st.subheader(f"Mensajes Privados de {mi_usuario}")
            for i, p in enumerate(chat_srv["privados"]):
                if p["para"] == mi_usuario or p["de"] == mi_usuario:
                    with st.container(border=True):
                        st.markdown(f"**[{p['hora']}] {p['de']} ➡️ {p['para']}:** {p['msg']}")
                        if p["archivo_bytes"]:
                            st.download_button(
                                f"📎 Descargar {p['archivo_nombre']}",
                                p["archivo_bytes"],
                                file_name=p["archivo_nombre"],
                                key=f"priv_file_{i}"
                            )

    with t_perfiles:
        st.subheader("Usuarios Registrados")
        if not chat_srv["usuarios"]:
            st.info("Guardá tu perfil en la barra lateral izquierda para aparecer acá.")
        for u, info in chat_srv["usuarios"].items():
            c_img, c_dat = st.columns([1, 5])
            if info["foto"]:
                c_img.image(info["foto"], width=70)
            else:
                c_img.markdown("## 👤")
            c_dat.markdown(f"**Usuario:** `{u}`  \n**Estado:** {info['estado']}")
            st.divider()

    with t_logs:
        st.subheader("Archivo chat_server.log")
        if os.path.exists("chat_server.log"):
            with open("chat_server.log", "r") as f:
                st.code(f.read())

# ==============================================================================
# PUNTO 4: CLIENTE FTP
# ==============================================================================
elif modulo == "4. Cliente FTP":
    st.header("4. Aplicación Cliente de FTP")
    
    c1, c2, c3, c4 = st.columns(4)
    ftp_host = c1.text_input("Servidor FTP", "127.0.0.1")
    ftp_port = c2.number_input("Puerto FTP", value=2121)
    ftp_user = c3.text_input("Usuario FTP", "anonymous")
    ftp_pass = c4.text_input("Contraseña FTP", type="password")

    if "ftp_dir" not in st.session_state:
        st.session_state.ftp_dir = "/"

    try:
        ftp = FTP()
        ftp.connect(ftp_host, int(ftp_port), timeout=5)
        ftp.login(ftp_user, ftp_pass)
        ftp.cwd(st.session_state.ftp_dir)
        
        st.success(f"✅ Conectado al servidor FTP | Directorio actual (`PWD`): `{ftp.pwd()}`")

        # Listado detallado (LIST y NLST)
        lineas_list = []
        ftp.retrlines("LIST", lineas_list.append)
        nombres_nlst = ftp.nlst()

        st.subheader("📂 Contenido del Directorio (Comando `LIST`)")
        st.code("\n".join(lineas_list) if lineas_list else "(Directorio vacío)")

        col_up, col_down, col_cmd = st.columns(3)

        with col_up:
            st.markdown("#### ⬆️ Subir Archivo (`STOR`)")
            up_file = st.file_uploader("Seleccionar archivo local:")
            if up_file and st.button("Subir al FTP (STOR)"):
                ftp.storbinary(f"STOR {up_file.name}", io.BytesIO(up_file.getvalue()))
                st.success(f"Subido: {up_file.name}")
                st.rerun()

        with col_down:
            st.markdown("#### ⬇️ Bajar Archivo (`RETR`)")
            if nombres_nlst:
                arch_sel = st.selectbox("Archivo en el servidor:", nombres_nlst)
                if st.button("Leer desde FTP (RETR)"):
                    buf = io.BytesIO()
                    ftp.retrbinary(f"RETR {arch_sel}", buf.write)
                    st.download_button(f"💾 Guardar {arch_sel} en mi PC", buf.getvalue(), file_name=arch_sel)

        with col_cmd:
            st.markdown("#### 🛠️ Comandos FTP (`CWD`, `MKD`, `DELE`)")
            sub_dir = st.text_input("Cambiar directorio (`CWD`):", value=st.session_state.ftp_dir)
            if st.button("Ejecutar CWD"):
                st.session_state.ftp_dir = sub_dir
                st.rerun()
                
            nueva_carp = st.text_input("Crear carpeta (`MKD`):")
            if st.button("Ejecutar MKD") and nueva_carp:
                ftp.mkd(nueva_carp)
                st.rerun()

            borrar_arch = st.text_input("Eliminar archivo (`DELE`):")
            if st.button("Ejecutar DELE") and borrar_arch:
                ftp.delete(borrar_arch)
                st.rerun()

        ftp.quit()
    except Exception as e:
        st.error(f"Error de conexión o comando FTP: {e}")
        st.info("💡 Asegurate de tener corriendo en otra terminal: python -m pyftpdlib -p 2121 -w")