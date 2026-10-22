import streamlit as st
import modulo_correo
import modulo_chat
import modulo_ftp

st.set_page_config(page_title="TP7 - Redes de Información", page_icon="🌐", layout="wide")

# Streamlit borra el estado de los widgets que no se dibujan en una ejecución. Re-asignarlos
# conserva la configuración (servidores, usuario, borradores) al cambiar de módulo.
for clave in modulo_correo.CLAVES_PERSISTENTES + modulo_chat.CLAVES_PERSISTENTES + modulo_ftp.CLAVES_PERSISTENTES:
    if clave in st.session_state:
        st.session_state[clave] = st.session_state[clave]

MODULOS = {
    "1. Cliente de Correo (SMTP/IMAP/POP3)": modulo_correo,
    "3. Chat Mensajería Instantánea": modulo_chat,
    "4. Cliente FTP": modulo_ftp,
}

st.sidebar.title("TP N°7 - Aplicaciones")
st.sidebar.caption("Redes de Información · UTN FRM")
seleccion = st.sidebar.radio("Seleccionar Aplicación:", list(MODULOS), key="modulo")
st.sidebar.caption("El punto 2 (Servidor Web HTTP) corre aparte: `python servidor_web.py` → http://localhost:8080")
with st.sidebar:
    modulo_chat.indicador_sidebar()

MODULOS[seleccion].mostrar()
