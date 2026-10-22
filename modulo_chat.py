"""Punto 3: Cliente web de chat. Se conecta por TCP a servidor_chat.py (mismo protocolo que cliente_chat.py)."""
import os
import streamlit as st
from chat_protocolo import ClienteChat, ErrorChat, PUERTO_CHAT, formatear

ARCHIVO_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_server.log")
INACTIVIDAD_MAX = 180  # segundos sin que la página consulte al cliente → se cierra la conexión TCP
CLAVES_PERSISTENTES = ["chat_host", "chat_puerto", "chat_usuario", "chat_canal", "chat_con"]


def cliente():
    return st.session_state.get("chat_cliente")


def avisar(tipo, texto):
    st.session_state.chat_aviso = (tipo, texto)


def privados_nuevos(c):
    vistos = st.session_state.setdefault("chat_vistos", {})
    return {u: n for u, msgs in list(c.privados.items())
            if (n := sum(1 for m in list(msgs) if m["de"] != c.usuario and m["id"] > vistos.get(u, 0)))}


# ============================================================================
# Callbacks
# ============================================================================
def conectar():
    ss = st.session_state
    try:
        ss.chat_cliente = ClienteChat(ss.chat_host, ss.chat_puerto, ss.chat_usuario.strip(), ss.chat_clave,
                                      inactividad_max=INACTIVIDAD_MAX)
        ss.chat_historial_cargado = set()
        ss.chat_vistos = {}
        avisar("success", f"Conectado al servidor de chat {ss.chat_host}:{ss.chat_puerto} como {ss.chat_cliente.usuario}.")
    except (ErrorChat, OSError) as e:
        avisar("error", f"No se pudo conectar: {e}")


def desconectar():
    c = cliente()
    if c:
        c.cerrar()
    st.session_state.chat_cliente = None


def crear_canal():
    ss = st.session_state
    try:
        ss.chat_canal = cliente().crear_canal(ss.chat_nuevo_canal)
        ss.chat_nuevo_canal = ""
        avisar("success", f"Canal #{ss.chat_canal} creado.")
    except ErrorChat as e:
        avisar("error", str(e))


def guardar_perfil():
    ss = st.session_state
    foto = ss.get("chat_foto")
    try:
        cliente().actualizar_perfil(ss.chat_estado, foto.getvalue() if foto else None)
        avisar("success", "Perfil actualizado en el servidor.")
    except ErrorChat as e:
        avisar("error", str(e))


# ============================================================================
# Vistas que se refrescan solas (st.fragment con run_every)
# ============================================================================
def avatar(c, usuario):
    try:
        return c.foto_de(usuario) or "👤"
    except ErrorChat:
        return "👤"


def dibujar_mensajes(c, mensajes, contenedor, prefijo):
    for m in mensajes:
        if m["tipo"] == "sistema":
            contenedor.caption(formatear(m))
            continue
        with contenedor.chat_message(m["de"], avatar=avatar(c, m["de"])):
            hora = m["hora"][-8:]
            if m["tipo"] == "archivo":
                st.markdown(f"**{m['de']}** · {hora} · 📎 envió **{m['nombre']}** ({m['tamano']:,} bytes)")
                st.download_button("Descargar archivo", data=lambda i=m["id"]: c.descargar(i)[1], file_name=m["nombre"],
                                   key=f"{prefijo}_dl_{m['id']}", on_click="ignore")
            else:
                st.markdown(f"**{m['de']}** · {hora}")
                st.text(m["texto"])


@st.fragment(run_every=1.5)
def mensajes_canal(canal):
    c = cliente()
    if not c:
        return
    c.tocar()
    mensajes = list(c.canales.get(canal, []))[-150:]
    caja = st.container(height=380, border=True)
    if not mensajes:
        caja.caption("Todavía no hay mensajes en este canal.")
    dibujar_mensajes(c, mensajes, caja, f"canal_{canal}")
    st.download_button("💾 Guardar conversación (.txt)", file_name=f"chat_{canal}.txt", on_click="ignore",
                       data=lambda: "\n".join(formatear(m) for m in list(c.canales.get(canal, []))))


@st.fragment(run_every=1.5)
def mensajes_privados(con):
    c = cliente()
    if not c:
        return
    c.tocar()
    mensajes = list(c.privados.get(con, []))[-150:]
    if mensajes:
        st.session_state.setdefault("chat_vistos", {})[con] = mensajes[-1]["id"]
    caja = st.container(height=380, border=True)
    if not mensajes:
        caja.caption(f"Todavía no hay mensajes con {con}.")
    dibujar_mensajes(c, mensajes, caja, f"priv_{con}")
    st.download_button("💾 Guardar conversación (.txt)", file_name=f"privado_{c.usuario}_{con}.txt", on_click="ignore",
                       data=lambda: "\n".join(formatear(m) for m in list(c.privados.get(con, []))))


@st.fragment(run_every=3)
def lista_usuarios():
    c = cliente()
    if not c:
        return
    for usuario, info in list(c.usuarios.items()):
        col_img, col_datos = st.columns([1, 7])
        foto = avatar(c, usuario)
        if isinstance(foto, bytes):
            col_img.image(foto, width=64)
        else:
            col_img.markdown("## 👤")
        presencia = "🟢 Conectado" if info["conectado"] else "⚪ Desconectado"
        propio = " (vos)" if usuario == c.usuario else ""
        col_datos.markdown(f"**{usuario}**{propio} · {presencia}  \nEstado: {info['estado'] or '-'}  \n"
                           f"Registrado: {info.get('registrado') or '-'}")
        st.divider()


@st.fragment(run_every=5)
def indicador_sidebar():
    """Estado del chat en la barra lateral (en todos los módulos) y aviso de privados nuevos."""
    c = cliente()
    if not c:
        return
    if not c.conectado:
        st.caption(f"💬 Chat desconectado. {c.motivo_desconexion}")
        return
    c.tocar()
    nuevos = privados_nuevos(c)
    texto = f"💬 Chat: conectado como **{c.usuario}**"
    if nuevos:
        texto += "  \n📩 Privados nuevos de: " + ", ".join(f"{u} ({n})" for u, n in nuevos.items())
    st.caption(texto)


# ============================================================================
# Pantallas
# ============================================================================
def mostrar_login():
    ss = st.session_state
    ss.setdefault("chat_host", "127.0.0.1")
    ss.setdefault("chat_puerto", PUERTO_CHAT)
    ss.setdefault("chat_usuario", "")
    st.info("Iniciá primero el servidor en una terminal: `python servidor_chat.py`. "
            "La primera vez que usás un nombre de usuario queda registrado con la contraseña que elijas. "
            "Para probar desde otra PC de la red, usá la IP de la máquina donde corre el servidor.")
    with st.form("form_login_chat"):
        c1, c2 = st.columns([3, 1])
        c1.text_input("Servidor de chat (host / IP)", key="chat_host")
        c2.number_input("Puerto TCP", min_value=1, max_value=65535, key="chat_puerto")
        c3, c4 = st.columns(2)
        c3.text_input("Usuario", key="chat_usuario", placeholder="Ej: Hernan")
        c4.text_input("Contraseña", type="password", key="chat_clave")
        st.form_submit_button("🔌 Conectar", type="primary", on_click=conectar)


def mostrar_perfil(c):
    with st.sidebar:
        st.subheader("👤 Mi Perfil de Chat")
        st.caption(f"Usuario: **{c.usuario}**")
        actual = c.usuarios.get(c.usuario, {})
        foto = avatar(c, c.usuario)
        if isinstance(foto, bytes):
            st.image(foto, width=90)
        if "chat_estado" not in st.session_state:
            st.session_state.chat_estado = actual.get("estado", "")
        st.text_input("Estado / Info", key="chat_estado", max_chars=140)
        st.file_uploader("Foto de perfil (máx. 1 MB)", type=["png", "jpg", "jpeg", "gif", "webp"], key="chat_foto")
        st.button("Guardar Perfil", on_click=guardar_perfil)
        st.button("🔌 Desconectar", on_click=desconectar)


def mostrar_canales(c):
    ss = st.session_state
    canales = sorted(c.canales, key=str.lower)
    if ss.get("chat_canal") not in canales:
        ss.chat_canal = "General" if "General" in canales else canales[0]
    col_sel, col_nuevo = st.columns([2, 1])
    canal = col_sel.selectbox("Canal activo:", canales, key="chat_canal", format_func=lambda x: f"#{x}")
    col_nuevo.text_input("Crear nuevo canal:", key="chat_nuevo_canal", placeholder="Nombre_del_canal")
    col_nuevo.button("Crear Canal", on_click=crear_canal)
    if canal not in c.unidos:
        try:
            c.unirse(canal)
        except ErrorChat as e:
            st.error(str(e))
    st.markdown(f"### Sala: #{canal}")
    mensajes_canal(canal)
    with st.form("form_mensaje_canal", clear_on_submit=True):
        col_txt, col_btn = st.columns([5, 1], vertical_alignment="bottom")
        texto = col_txt.text_input("Escribir mensaje al canal:", max_chars=4000)
        enviar = col_btn.form_submit_button("Enviar", type="primary")
    if enviar and texto.strip():
        try:
            c.enviar_canal(canal, texto)
            st.rerun()
        except ErrorChat as e:
            st.error(str(e))


def mostrar_privados(c):
    ss = st.session_state
    otros = [u for u in c.usuarios if u != c.usuario]
    if not otros:
        st.info("Todavía no hay otros usuarios registrados. Abrí otra pestaña o el cliente de terminal con otro usuario.")
        return
    nuevos = privados_nuevos(c)

    def etiqueta(u):
        info = c.usuarios.get(u, {})
        marca = f"  📩 {nuevos[u]}" if u in nuevos else ""
        return f"{'🟢' if info.get('conectado') else '⚪'} {u}{marca}"

    con = st.selectbox("Conversación privada con:", otros, key="chat_con", format_func=etiqueta)
    cargados = ss.setdefault("chat_historial_cargado", set())
    if con not in cargados:
        try:
            c.historial_privado(con)
            cargados.add(con)
        except ErrorChat as e:
            st.error(str(e))
    mensajes_privados(con)
    with st.form("form_privado", clear_on_submit=True):
        texto = st.text_area("Mensaje privado:", height=80, max_chars=4000)
        archivo = st.file_uploader("Enviar archivo a este usuario (máx. 8 MB):")
        enviar = st.form_submit_button("Enviar Privado", type="primary")
    if enviar:
        try:
            if archivo:
                c.enviar_archivo(con, archivo.name, archivo.getvalue())
            if texto.strip():
                c.enviar_privado(con, texto)
            if archivo or texto.strip():
                st.rerun()
        except ErrorChat as e:
            st.error(str(e))


def mostrar_logs():
    st.subheader("Registro del servidor (chat_server.log)")
    st.caption("Solo disponible cuando el servidor corre en esta misma máquina. Los mensajes privados se registran sin su contenido.")
    if st.button("🔄 Actualizar log"):
        st.rerun()
    if os.path.exists(ARCHIVO_LOG):
        with open(ARCHIVO_LOG, "r", encoding="utf-8", errors="replace") as f:
            st.code("".join(reversed(f.readlines()[-150:])) or "(vacío)", language=None)
    else:
        st.info("No se encontró chat_server.log en esta carpeta.")


def mostrar():
    st.header("3. Aplicación Cliente/Servidor de Chat")
    st.caption(f"Protocolo propio sobre TCP (puerto {PUERTO_CHAT}): mensajes JSON de una línea. "
               "El servidor empuja los mensajes nuevos a cada cliente conectado; esta página los muestra al instante.")
    if aviso := st.session_state.pop("chat_aviso", None):
        getattr(st, aviso[0])(aviso[1])
    c = cliente()
    if c is None:
        mostrar_login()
        return
    if not c.conectado:
        st.error(f"Se perdió la conexión con el servidor de chat. {c.motivo_desconexion}")
        st.button("🔌 Volver a conectar", on_click=desconectar, type="primary")
        return
    st.success(f"Conectado como **{c.usuario}** a {st.session_state.chat_host}:{st.session_state.chat_puerto} (TCP)")
    mostrar_perfil(c)
    # Solo se dibuja la pestaña abierta: así un privado no se marca como leído si no se está viendo
    t_canales, t_privados, t_usuarios, t_logs = st.tabs([
        "💬 Canales", "🔒 Mensajes Privados y Archivos", "👥 Usuarios y Perfiles", "📋 Registro del Servidor (Logs)"
    ], key="chat_tab", on_change="rerun")
    with t_canales:
        if t_canales.open:
            mostrar_canales(c)
    with t_privados:
        if t_privados.open:
            mostrar_privados(c)
    with t_usuarios:
        if t_usuarios.open:
            lista_usuarios()
    with t_logs:
        if t_logs.open:
            mostrar_logs()
