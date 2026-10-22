"""Punto 4: Cliente FTP (RFC 959) con canal de control y canal de datos."""
import io
import contextlib
import ftplib
import posixpath
import streamlit as st

CLAVES_PERSISTENTES = ["ftp_host", "ftp_port", "ftp_user", "ftp_pass", "ftp_pasivo", "ftp_dir"]
COMANDOS_CON_DATOS = {"LIST", "NLST", "MLSD", "RETR", "STOR", "STOU", "APPE"}


def inicializar_estado():
    ss = st.session_state
    ss.setdefault("ftp_host", "127.0.0.1")
    ss.setdefault("ftp_port", 2121)
    ss.setdefault("ftp_user", "anonymous")
    ss.setdefault("ftp_pass", "")
    ss.setdefault("ftp_pasivo", True)
    ss.setdefault("ftp_dir", "/")
    ss.setdefault("ftp_nonce", 0)


def avisar(tipo, texto):
    st.session_state.ftp_aviso = (tipo, texto)


def ejecutar(operacion, directorio=None, dialogo="ftp_dialogo"):
    """Abre la sesión FTP, hace CWD, ejecuta la operación y cierra con QUIT.

    Guarda en session_state[dialogo] el diálogo del canal de control (comandos del cliente
    y respuestas del servidor) para mostrarlo en pantalla. ftplib oculta la contraseña del PASS.
    """
    ss = st.session_state
    salida = io.StringIO()
    try:
        with contextlib.redirect_stdout(salida):
            ftp = ftplib.FTP(timeout=10)
            ftp.set_debuglevel(1)
            try:
                ftp.connect(ss.ftp_host, int(ss.ftp_port))
                ftp.login(ss.ftp_user, ss.ftp_pass)
                ftp.set_pasv(ss.ftp_pasivo)
                ftp.cwd(directorio or ss.ftp_dir)
                return operacion(ftp)
            finally:
                try:
                    ftp.quit()
                except (*ftplib.all_errors, AttributeError):
                    ftp.close()
    finally:
        ss[dialogo] = salida.getvalue().replace("*cmd* ", "C: ").replace("*resp* ", "S: ").replace("*welcome* ", "S: ")


def accion(descripcion, operacion):
    """Ejecuta una operación desde un botón y deja un aviso con la respuesta del servidor ({r})."""
    try:
        resultado = ejecutar(operacion)
        avisar("success", descripcion.replace("{r}", str(resultado)))
    except ftplib.all_errors as e:
        avisar("error", f"Error FTP: {e}")


# ============================================================================
# Callbacks de los botones
# ============================================================================
def cambiar_directorio(destino):
    # Primero se valida el CWD en el servidor; solo si funciona se cambia el directorio guardado
    try:
        ruta = ejecutar(lambda ftp: ftp.pwd(), directorio=destino)
        st.session_state.ftp_dir = ruta
        avisar("success", f"CWD correcto. Directorio actual: {ruta}")
    except ftplib.all_errors as e:
        avisar("error", f"No se pudo cambiar a '{destino}': {e}")


def ir_a_ruta():
    destino = st.session_state.ftp_ruta_manual.strip()
    if destino:
        cambiar_directorio(destino if destino.startswith("/") else posixpath.join(st.session_state.ftp_dir, destino))


def subir():
    ss = st.session_state
    archivo = ss.get(f"ftp_subida_{ss.ftp_nonce}")
    if not archivo:
        avisar("warning", "Elegí un archivo para subir.")
        return
    accion(f"⬆️ STOR {archivo.name}: {{r}}", lambda ftp: ftp.storbinary(f"STOR {archivo.name}", io.BytesIO(archivo.getvalue())))
    ss.ftp_nonce += 1


def preparar_descarga():
    ss = st.session_state
    nombre = ss.ftp_archivo_sel
    buffer = io.BytesIO()
    try:
        respuesta = ejecutar(lambda ftp: ftp.retrbinary(f"RETR {nombre}", buffer.write))
        ss.ftp_descarga = (nombre, buffer.getvalue())
        avisar("success", f"⬇️ RETR {nombre}: {respuesta} ({len(buffer.getvalue())} bytes). Presioná 'Guardar en mi PC'.")
    except ftplib.all_errors as e:
        avisar("error", f"Error FTP: {e}")


def crear_carpeta():
    nombre = st.session_state.ftp_mkd.strip()
    if nombre:
        accion(f"📁 MKD {nombre}: carpeta creada ({{r}})", lambda ftp: ftp.mkd(nombre))
        st.session_state.ftp_mkd = ""


def borrar_carpeta():
    nombre = st.session_state.ftp_rmd
    accion(f"🗑️ RMD {nombre}: {{r}}", lambda ftp: ftp.rmd(nombre))


def borrar_archivo():
    nombre = st.session_state.ftp_dele
    accion(f"🗑️ DELE {nombre}: {{r}}", lambda ftp: ftp.delete(nombre))


def renombrar():
    ss = st.session_state
    origen, destino = ss.ftp_rnfr, ss.ftp_rnto.strip()
    if destino:
        accion(f"✏️ RNFR {origen} / RNTO {destino}: {{r}}", lambda ftp: ftp.rename(origen, destino))
        ss.ftp_rnto = ""


def tamano():
    nombre = st.session_state.ftp_archivo_sel

    def consultar(ftp):
        ftp.voidcmd("TYPE I")  # SIZE se responde en modo binario (RFC 3659)
        return ftp.size(nombre)
    accion(f"📏 SIZE {nombre}: {{r}} bytes", consultar)


def comando_manual():
    ss = st.session_state
    comando = ss.ftp_comando.strip()
    if not comando:
        return
    if comando.split()[0].upper() in COMANDOS_CON_DATOS:
        avisar("warning", "Ese comando necesita un canal de datos: usá los botones de listar, subir o bajar.")
        return
    accion(f"Respuesta del servidor a '{comando}': {{r}}", lambda ftp: ftp.sendcmd(comando))


# ============================================================================
# Listado del directorio
# ============================================================================
def listar(ftp):
    pwd = ftp.pwd()
    crudo = []
    ftp.retrlines("LIST", crudo.append)
    entradas = []
    try:
        for nombre, datos in ftp.mlsd(facts=["type", "size", "modify"]):
            if datos.get("type") in ("file", "dir"):
                fecha = datos.get("modify", "")
                entradas.append({
                    "Nombre": nombre,
                    "Tipo": "📁 carpeta" if datos["type"] == "dir" else "📄 archivo",
                    "Tamaño (bytes)": int(datos["size"]) if datos.get("size", "").isdigit() else None,
                    "Modificado (UTC)": f"{fecha[:4]}-{fecha[4:6]}-{fecha[6:8]} {fecha[8:10]}:{fecha[10:12]}" if len(fecha) >= 12 else "",
                })
    except ftplib.error_perm:
        # Servidor sin MLSD (RFC 3659): se interpreta la salida estilo Unix de LIST
        for linea in crudo:
            partes = linea.split(None, 8)
            if len(partes) == 9 and partes[8] not in (".", ".."):
                entradas.append({"Nombre": partes[8], "Tipo": "📁 carpeta" if linea.startswith("d") else "📄 archivo",
                                 "Tamaño (bytes)": int(partes[4]) if partes[4].isdigit() else None,
                                 "Modificado (UTC)": " ".join(partes[5:8])})
    entradas.sort(key=lambda e: (e["Tipo"] != "📁 carpeta", e["Nombre"].lower()))
    return {"pwd": pwd, "bienvenida": ftp.welcome, "crudo": crudo, "entradas": entradas}


# ============================================================================
# Interfaz
# ============================================================================
def mostrar():
    inicializar_estado()
    ss = st.session_state
    st.header("4. Aplicación Cliente de FTP")
    st.caption("FTP (RFC 959) usa dos conexiones TCP: el canal de control (puerto 21, comandos USER, PASS, CWD, LIST, RETR, STOR…) "
               "y un canal de datos por cada transferencia. En modo pasivo (PASV) el cliente abre la conexión de datos; "
               "en modo activo (PORT) la abre el servidor.")

    c1, c2, c3, c4, c5 = st.columns([3, 1, 2, 2, 1.4], vertical_alignment="bottom")
    c1.text_input("Servidor FTP", key="ftp_host")
    c2.number_input("Puerto", min_value=1, max_value=65535, key="ftp_port")
    c3.text_input("Usuario FTP", key="ftp_user")
    c4.text_input("Contraseña FTP", type="password", key="ftp_pass")
    c5.checkbox("Modo pasivo", key="ftp_pasivo")

    if aviso := ss.pop("ftp_aviso", None):
        getattr(st, aviso[0])(aviso[1])

    try:
        datos = ejecutar(listar, dialogo="ftp_dialogo_listado")
    except ftplib.error_perm as e:
        if ss.ftp_dir != "/":
            st.warning(f"No se pudo abrir {ss.ftp_dir} ({e}). Se vuelve a la raíz.")
            ss.ftp_dir = "/"
            st.rerun()
        st.error(f"El servidor rechazó la conexión o el login: {e}")
        mostrar_dialogo()
        return
    except ftplib.all_errors as e:
        st.error(f"No se pudo conectar a {ss.ftp_host}:{ss.ftp_port}: {e}")
        st.info("💡 Para probar en local, iniciá un servidor FTP en otra terminal: `python -m pyftpdlib -p 2121 -w -d ftp_files`")
        mostrar_dialogo()
        return

    st.success(f"✅ Conectado | Directorio actual (`PWD`): `{datos['pwd']}` | Bienvenida: `{datos['bienvenida']}`")
    carpetas = [e["Nombre"] for e in datos["entradas"] if e["Tipo"] == "📁 carpeta"]
    archivos = [e["Nombre"] for e in datos["entradas"] if e["Tipo"] == "📄 archivo"]

    st.subheader("📂 Contenido del directorio (MLSD / LIST)")
    if datos["entradas"]:
        st.dataframe(datos["entradas"], hide_index=True, width="stretch")
    else:
        st.caption("(Directorio vacío)")
    with st.expander("Respuesta cruda del comando LIST"):
        st.code("\n".join(datos["crudo"]) or "(vacío)", language=None)

    st.markdown("#### 🧭 Navegación (`CWD`, `CDUP`)")
    n1, n2, n3 = st.columns(3, vertical_alignment="bottom")
    if carpetas:
        n1.selectbox("Carpeta", carpetas, key="ftp_carpeta_sel")
        n1.button("📂 Entrar (CWD)", on_click=lambda: cambiar_directorio(posixpath.join(datos["pwd"], ss.ftp_carpeta_sel)))
    else:
        n1.caption("No hay subcarpetas.")
    n2.button("⬆️ Subir un nivel (CDUP)", on_click=cambiar_directorio, args=(posixpath.dirname(datos["pwd"].rstrip("/")) or "/",),
              disabled=datos["pwd"] == "/")
    n3.text_input("Ir a una ruta", key="ftp_ruta_manual", placeholder="/docs o subcarpeta")
    n3.button("Ejecutar CWD", on_click=ir_a_ruta)

    col_up, col_down = st.columns(2)
    with col_up:
        st.markdown("#### ⬆️ Subir archivo (`STOR`)")
        st.file_uploader("Seleccionar archivo local:", key=f"ftp_subida_{ss.ftp_nonce}")
        st.button("Subir al servidor (STOR)", on_click=subir, type="primary")
    with col_down:
        st.markdown("#### ⬇️ Bajar archivo (`RETR`)")
        if archivos:
            st.selectbox("Archivo en el servidor:", archivos, key="ftp_archivo_sel")
            b1, b2 = st.columns(2)
            b1.button("Descargar (RETR)", on_click=preparar_descarga, type="primary")
            b2.button("Ver tamaño (SIZE)", on_click=tamano)
            descarga = ss.get("ftp_descarga")
            if descarga and descarga[0] in archivos:
                st.download_button(f"💾 Guardar {descarga[0]} en mi PC", descarga[1], file_name=descarga[0], on_click="ignore")
        else:
            st.caption("No hay archivos en este directorio.")

    st.markdown("#### 🛠️ Otros comandos (`MKD`, `RMD`, `DELE`, `RNFR`/`RNTO`)")
    o1, o2, o3, o4 = st.columns(4)
    with o1:
        st.text_input("Crear carpeta (MKD):", key="ftp_mkd")
        st.button("Ejecutar MKD", on_click=crear_carpeta)
    with o2:
        if carpetas:
            st.selectbox("Borrar carpeta vacía (RMD):", carpetas, key="ftp_rmd")
            st.button("Ejecutar RMD", on_click=borrar_carpeta)
        else:
            st.caption("RMD: no hay carpetas.")
    with o3:
        if archivos:
            st.selectbox("Borrar archivo (DELE):", archivos, key="ftp_dele")
            st.button("Ejecutar DELE", on_click=borrar_archivo)
        else:
            st.caption("DELE: no hay archivos.")
    with o4:
        if datos["entradas"]:
            st.selectbox("Renombrar (RNFR):", [e["Nombre"] for e in datos["entradas"]], key="ftp_rnfr")
            st.text_input("Nuevo nombre (RNTO):", key="ftp_rnto")
            st.button("Renombrar", on_click=renombrar)

    with st.expander("⌨️ Consola: enviar un comando FTP al canal de control"):
        st.caption("Ejemplos: SYST, STAT, FEAT, HELP, NOOP, PWD, MDTM archivo.txt, SIZE archivo.txt")
        st.text_input("Comando", key="ftp_comando")
        st.button("Enviar comando", on_click=comando_manual)

    mostrar_dialogo()


def mostrar_dialogo():
    with st.expander("📡 Canal de control: diálogo de la última operación (C: cliente, S: servidor)"):
        st.code(st.session_state.get("ftp_dialogo") or "(todavía no se ejecutó ninguna operación)", language=None)
    with st.expander("📡 Canal de control: diálogo del listado (USER, PASS, CWD, PASV/PORT, LIST, MLSD)"):
        st.code(st.session_state.get("ftp_dialogo_listado") or "(sin datos)", language=None)
