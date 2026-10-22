"""Punto 3: Servidor de Chat / Mensajería Instantánea sobre TCP.

Uso:  python servidor_chat.py [--host 0.0.0.0] [--puerto 5050]

Atiende a cada cliente en un hilo propio (socketserver.ThreadingTCPServer) y habla el
protocolo descrito en chat_protocolo.py. Guarda usuarios, canales, historial, archivos y
fotos en la carpeta chat_data/ y registra la actividad en chat_server.log.
"""
import os
import re
import sys
import json
import time
import hmac
import hashlib
import secrets
import logging
import argparse
import threading
import socketserver
from datetime import datetime
from chat_protocolo import PUERTO_CHAT, MAX_LINEA, MAX_ARCHIVO, MAX_FOTO, codificar, decodificar, a_base64, de_base64

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIR_DATOS = os.path.join(BASE_DIR, "chat_data")
DIR_HISTORIAL = os.path.join(DIR_DATOS, "historial")
DIR_ARCHIVOS = os.path.join(DIR_DATOS, "archivos")
DIR_FOTOS = os.path.join(DIR_DATOS, "fotos")
ARCHIVO_USUARIOS = os.path.join(DIR_DATOS, "usuarios.json")
ARCHIVO_CANALES = os.path.join(DIR_DATOS, "canales.json")
ARCHIVO_LOG = os.path.join(BASE_DIR, "chat_server.log")

CANALES_INICIALES = ["General", "Redes_UTN", "TP7_Grupo"]
PATRON_NOMBRE = re.compile(r"[A-Za-z0-9_.-]{2,20}")
PATRON_CANAL = re.compile(r"[A-Za-z0-9_-]{2,30}")
MAX_TEXTO = 4000
MAX_HISTORIAL = 200
FIRMAS_IMAGEN = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF8", b"RIFF")  # PNG, JPG, GIF, WEBP


def configurar_logging():
    formato = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    logger = logging.getLogger("servidor_chat")
    logger.setLevel(logging.INFO)
    for handler in (logging.FileHandler(ARCHIVO_LOG, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        handler.setFormatter(formato)
        logger.addHandler(handler)
    return logger


log = configurar_logging()


class ErrorPedido(Exception):
    pass


def hashear(clave, salt):
    return hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), bytes.fromhex(salt), 100_000).hex()


def leer_json(ruta, defecto):
    if os.path.exists(ruta):
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    return defecto


def escribir_json(ruta, datos):
    temporal = ruta + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
    os.replace(temporal, ruta)


# ============================================================================
# Estado compartido del servidor (protegido por un lock)
# ============================================================================
class Estado:
    def __init__(self):
        for carpeta in (DIR_DATOS, DIR_HISTORIAL, DIR_ARCHIVOS, DIR_FOTOS):
            os.makedirs(carpeta, exist_ok=True)
        self.lock = threading.RLock()
        self.usuarios = leer_json(ARCHIVO_USUARIOS, {})
        self.canales = leer_json(ARCHIVO_CANALES, list(CANALES_INICIALES))
        self.sesiones = {}  # usuario -> conjunto de sesiones TCP abiertas
        self.ultimo_id = 0

    def nuevo_id(self):
        with self.lock:
            self.ultimo_id = max(self.ultimo_id + 1, time.time_ns() // 1000)
            return self.ultimo_id

    def guardar_usuarios(self):
        escribir_json(ARCHIVO_USUARIOS, self.usuarios)

    def lista_usuarios(self):
        with self.lock:
            lista = [{
                "usuario": nombre,
                "estado": datos.get("estado", ""),
                "conectado": bool(self.sesiones.get(nombre)),
                "foto_version": datos.get("foto_version"),
                "registrado": datos.get("registrado", ""),
            } for nombre, datos in self.usuarios.items()]
        return sorted(lista, key=lambda u: (not u["conectado"], u["usuario"].lower()))

    def sesiones_de(self, usuarios):
        with self.lock:
            return [s for u in usuarios for s in self.sesiones.get(u, ())]

    def todas_las_sesiones(self):
        with self.lock:
            return [s for conjunto in self.sesiones.values() for s in conjunto]

    def miembros(self, canal):
        with self.lock:
            return [s for s in self.todas_las_sesiones() if canal in s.canales]


estado = Estado()


def archivo_historial(canal=None, usuarios=None):
    if canal:
        return os.path.join(DIR_HISTORIAL, f"canal__{canal}.jsonl")
    a, b = sorted(usuarios)
    return os.path.join(DIR_HISTORIAL, f"privado__{a}__{b}.jsonl")


def guardar_en_historial(ruta, mensaje):
    with estado.lock, open(ruta, "a", encoding="utf-8") as f:
        f.write(json.dumps(mensaje, ensure_ascii=False) + "\n")


def leer_historial(ruta):
    if not os.path.exists(ruta):
        return []
    with estado.lock, open(ruta, "r", encoding="utf-8") as f:
        return [json.loads(linea) for linea in f.readlines()[-MAX_HISTORIAL:] if linea.strip()]


def difundir(sesiones, evento):
    for sesion in sesiones:
        sesion.enviar(evento)


def difundir_usuarios():
    difundir(estado.todas_las_sesiones(), {"tipo": "usuarios", "usuarios": estado.lista_usuarios()})


def ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ============================================================================
# Sesión de un cliente (un hilo por conexión TCP)
# ============================================================================
class SesionChat(socketserver.StreamRequestHandler):
    def setup(self):
        super().setup()
        self.usuario = None
        self.canales = set()
        self.lock_envio = threading.Lock()
        self.origen = f"{self.client_address[0]}:{self.client_address[1]}"

    def enviar(self, obj):
        try:
            with self.lock_envio:
                self.wfile.write(codificar(obj))
        except OSError:
            pass  # el cliente se desconectó; se limpia en finish()

    def handle(self):
        log.info(f"CONEXION TCP abierta desde {self.origen}")
        while True:
            try:
                linea = self.rfile.readline(MAX_LINEA)
            except OSError:
                break
            if not linea:
                break
            if not linea.endswith(b"\n"):
                log.warning(f"MENSAJE DEMASIADO GRANDE desde {self.origen}: se cierra la conexión")
                self.enviar({"tipo": "error", "mensaje": "Mensaje demasiado grande"})
                break
            try:
                pedido = decodificar(linea)
                if not isinstance(pedido, dict):
                    raise ValueError("se esperaba un objeto JSON")
            except ValueError as e:
                self.enviar({"tipo": "error", "mensaje": f"JSON inválido: {e}"})
                continue
            req = pedido.get("req")
            try:
                respuesta = self.despachar(pedido)
                self.enviar({"tipo": "ok", "req": req, **(respuesta or {})})
            except ErrorPedido as e:
                self.enviar({"tipo": "error", "req": req, "mensaje": str(e)})
            except Exception as e:
                log.error(f"ERROR procesando {pedido.get('tipo')} de {self.usuario or self.origen}: {e!r}")
                self.enviar({"tipo": "error", "req": req, "mensaje": "Error interno del servidor"})

    def finish(self):
        if self.usuario:
            with estado.lock:
                estado.sesiones.get(self.usuario, set()).discard(self)
                sigue_conectado = bool(estado.sesiones.get(self.usuario))
            if not sigue_conectado:
                difundir_usuarios()
            log.info(f"LOGOUT {self.usuario} ({self.origen})")
        log.info(f"CONEXION TCP cerrada {self.origen}")
        super().finish()

    # ------------------------------------------------------------------ pedidos
    def despachar(self, pedido):
        tipo = pedido.get("tipo")
        if tipo == "ping":
            return {}
        if tipo == "login":
            return self.login(pedido)
        if not self.usuario:
            raise ErrorPedido("Primero hay que iniciar sesión")
        acciones = {
            "usuarios": lambda p: {"usuarios": estado.lista_usuarios()},
            "crear_canal": self.crear_canal,
            "unirse": self.unirse,
            "salir_canal": self.salir_canal,
            "mensaje_canal": self.mensaje_canal,
            "mensaje_privado": self.mensaje_privado,
            "historial": self.historial,
            "enviar_archivo": self.enviar_archivo,
            "descargar": self.descargar,
            "perfil": self.perfil,
            "ver_perfil": self.ver_perfil,
        }
        if tipo not in acciones:
            raise ErrorPedido(f"Tipo de pedido desconocido: {tipo}")
        return acciones[tipo](pedido)

    def login(self, p):
        if self.usuario:
            raise ErrorPedido("La sesión ya está iniciada")
        usuario, clave = str(p.get("usuario", "")).strip(), str(p.get("clave", ""))
        if not PATRON_NOMBRE.fullmatch(usuario):
            raise ErrorPedido("Usuario inválido: 2 a 20 caracteres (letras sin acentos, números, _ . -)")
        if not clave:
            raise ErrorPedido("La contraseña no puede estar vacía")
        with estado.lock:
            datos = estado.usuarios.get(usuario)
            if datos is None:
                if any(u.lower() == usuario.lower() for u in estado.usuarios):
                    raise ErrorPedido("Ya existe un usuario con ese nombre (con otras mayúsculas)")
                salt = secrets.token_hex(16)
                estado.usuarios[usuario] = {"salt": salt, "hash": hashear(clave, salt), "estado": "", "registrado": ahora()}
                estado.guardar_usuarios()
                log.info(f"REGISTRO de usuario nuevo: {usuario} ({self.origen})")
            elif not hmac.compare_digest(hashear(clave, datos["salt"]), datos["hash"]):
                log.warning(f"LOGIN FALLIDO para {usuario} desde {self.origen}")
                raise ErrorPedido("Contraseña incorrecta")
            self.usuario = usuario
            estado.sesiones.setdefault(usuario, set()).add(self)
            canales = list(estado.canales)
        log.info(f"LOGIN {usuario} desde {self.origen}")
        difundir_usuarios()
        return {"usuario": usuario, "canales": canales, "usuarios": estado.lista_usuarios()}

    def canal_existente(self, p):
        canal = str(p.get("canal", ""))
        if canal not in estado.canales:
            raise ErrorPedido(f"No existe el canal #{canal}")
        return canal

    def crear_canal(self, p):
        canal = str(p.get("canal", "")).strip().lstrip("#")
        if not PATRON_CANAL.fullmatch(canal):
            raise ErrorPedido("Nombre de canal inválido: 2 a 30 caracteres (letras sin acentos, números, _ -)")
        with estado.lock:
            if any(c.lower() == canal.lower() for c in estado.canales):
                raise ErrorPedido(f"El canal #{canal} ya existe")
            estado.canales.append(canal)
            escribir_json(ARCHIVO_CANALES, estado.canales)
        log.info(f"CANAL CREADO #{canal} por {self.usuario}")
        difundir(estado.todas_las_sesiones(), {"tipo": "canales", "canales": list(estado.canales)})
        return {"canal": canal}

    def unirse(self, p):
        canal = self.canal_existente(p)
        nuevo = canal not in self.canales
        self.canales.add(canal)
        if nuevo:
            log.info(f"UNION {self.usuario} -> #{canal}")
        return {"canal": canal, "historial": leer_historial(archivo_historial(canal=canal))}

    def salir_canal(self, p):
        canal = self.canal_existente(p)
        self.canales.discard(canal)
        log.info(f"SALIDA {self.usuario} <- #{canal}")
        return {}

    def texto_valido(self, p):
        texto = str(p.get("texto", "")).strip()
        if not texto:
            raise ErrorPedido("El mensaje está vacío")
        if len(texto) > MAX_TEXTO:
            raise ErrorPedido(f"El mensaje supera los {MAX_TEXTO} caracteres")
        return texto

    def destinatario_valido(self, p):
        para = str(p.get("para", ""))
        if para not in estado.usuarios:
            raise ErrorPedido(f"No existe el usuario {para}")
        return para

    def mensaje_canal(self, p):
        canal = self.canal_existente(p)
        texto = self.texto_valido(p)
        self.canales.add(canal)
        mensaje = {"tipo": "mensaje_canal", "id": estado.nuevo_id(), "canal": canal, "de": self.usuario, "texto": texto, "hora": ahora()}
        guardar_en_historial(archivo_historial(canal=canal), mensaje)
        difundir(estado.miembros(canal), mensaje)
        log.info(f"MSG CANAL #{canal} | {self.usuario}: {texto}")
        return {"id": mensaje["id"]}

    def mensaje_privado(self, p):
        para = self.destinatario_valido(p)
        texto = self.texto_valido(p)
        mensaje = {"tipo": "mensaje_privado", "id": estado.nuevo_id(), "de": self.usuario, "para": para, "texto": texto, "hora": ahora()}
        guardar_en_historial(archivo_historial(usuarios=(self.usuario, para)), mensaje)
        difundir(estado.sesiones_de({self.usuario, para}), mensaje)
        # Por privacidad, en el log de los privados queda solo el metadato, no el contenido
        log.info(f"PRIVADO {self.usuario} -> {para} ({len(texto)} caracteres)")
        return {"id": mensaje["id"]}

    def historial(self, p):
        if p.get("canal"):
            return {"historial": leer_historial(archivo_historial(canal=self.canal_existente(p)))}
        con = str(p.get("con", ""))
        if con not in estado.usuarios:
            raise ErrorPedido(f"No existe el usuario {con}")
        return {"historial": leer_historial(archivo_historial(usuarios=(self.usuario, con)))}

    def enviar_archivo(self, p):
        para = self.destinatario_valido(p)
        nombre = os.path.basename(str(p.get("nombre", "archivo")).replace("\\", "/")) or "archivo"
        try:
            datos = de_base64(p.get("datos"))
        except ValueError:
            raise ErrorPedido("Datos del archivo inválidos (se esperaba Base64)")
        if len(datos) > MAX_ARCHIVO:
            raise ErrorPedido(f"El archivo supera el máximo de {MAX_ARCHIVO // (1024 * 1024)} MB")
        id_archivo = estado.nuevo_id()
        with open(os.path.join(DIR_ARCHIVOS, f"{id_archivo}.bin"), "wb") as f:
            f.write(datos)
        mensaje = {"tipo": "archivo", "id": id_archivo, "de": self.usuario, "para": para, "nombre": nombre, "tamano": len(datos), "hora": ahora()}
        escribir_json(os.path.join(DIR_ARCHIVOS, f"{id_archivo}.json"), mensaje)
        guardar_en_historial(archivo_historial(usuarios=(self.usuario, para)), mensaje)
        difundir(estado.sesiones_de({self.usuario, para}), mensaje)
        log.info(f"ARCHIVO {self.usuario} -> {para} | {nombre} ({len(datos)} bytes)")
        return {"id": id_archivo}

    def descargar(self, p):
        try:
            id_archivo = int(p.get("id"))
        except (TypeError, ValueError):
            raise ErrorPedido("Identificador de archivo inválido")
        ruta_meta = os.path.join(DIR_ARCHIVOS, f"{id_archivo}.json")
        meta = leer_json(ruta_meta, None)
        if meta is None:
            raise ErrorPedido("El archivo no existe")
        if self.usuario not in (meta["de"], meta["para"]):
            log.warning(f"DESCARGA DENEGADA {self.usuario} intentó bajar el archivo {id_archivo}")
            raise ErrorPedido("No tenés permiso para descargar este archivo")
        with open(os.path.join(DIR_ARCHIVOS, f"{id_archivo}.bin"), "rb") as f:
            datos = f.read()
        log.info(f"DESCARGA {self.usuario} <- {meta['nombre']} ({len(datos)} bytes)")
        return {"nombre": meta["nombre"], "datos": a_base64(datos)}

    def perfil(self, p):
        texto_estado = str(p.get("estado", "")).strip()[:140]
        foto = None
        if p.get("foto"):
            # Se valida todo antes de modificar el perfil, para no dejar cambios a medias
            try:
                foto = de_base64(p["foto"])
            except ValueError:
                raise ErrorPedido("Foto inválida (se esperaba Base64)")
            if not foto.startswith(FIRMAS_IMAGEN):
                raise ErrorPedido("La foto debe ser PNG, JPG, GIF o WEBP")
            if len(foto) > MAX_FOTO:
                raise ErrorPedido("La foto supera 1 MB")
        with estado.lock:
            datos = estado.usuarios[self.usuario]
            datos["estado"] = texto_estado
            if foto is not None:
                with open(os.path.join(DIR_FOTOS, f"{self.usuario}.img"), "wb") as f:
                    f.write(foto)
                datos["foto_version"] = estado.nuevo_id()
            estado.guardar_usuarios()
        log.info(f"PERFIL ACTUALIZADO {self.usuario} | estado: {texto_estado}{' | foto nueva' if p.get('foto') else ''}")
        difundir_usuarios()
        return {}

    def ver_perfil(self, p):
        usuario = str(p.get("usuario", ""))
        if usuario not in estado.usuarios:
            raise ErrorPedido(f"No existe el usuario {usuario}")
        datos = estado.usuarios[usuario]
        ruta_foto = os.path.join(DIR_FOTOS, f"{usuario}.img")
        foto = ""
        if datos.get("foto_version") and os.path.exists(ruta_foto):
            with open(ruta_foto, "rb") as f:
                foto = a_base64(f.read())
        return {"usuario": usuario, "estado": datos.get("estado", ""), "registrado": datos.get("registrado", ""),
                "conectado": bool(estado.sesiones.get(usuario)), "foto": foto}


class ServidorChat(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor de chat TP7 (TCP + JSON Lines)")
    parser.add_argument("--host", default="0.0.0.0", help="Interfaz donde escuchar (0.0.0.0 = todas)")
    parser.add_argument("--puerto", type=int, default=PUERTO_CHAT)
    args = parser.parse_args()
    servidor = ServidorChat((args.host, args.puerto), SesionChat)
    log.info(f"Servidor de chat escuchando en {args.host}:{args.puerto} | Canales: {', '.join(estado.canales)}")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        log.info("Servidor de chat detenido")
        servidor.server_close()
