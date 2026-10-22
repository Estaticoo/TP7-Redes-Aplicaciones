"""Protocolo de chat del TP7 y cliente reutilizable (lo usan la app web y el cliente de terminal).

Protocolo de capa de aplicación sobre TCP (puerto 5050 por defecto):
  - Cada mensaje es un objeto JSON en UTF-8 terminado en salto de línea ("JSON Lines").
  - El cliente envía pedidos con un campo "req" (número de pedido); el servidor contesta
    {"tipo": "ok", "req": n, ...} o {"tipo": "error", "req": n, "mensaje": "..."}.
  - El servidor además empuja eventos sin "req" (mensajes nuevos, usuarios conectados, canales).
  - Los archivos y fotos viajan codificados en Base64 dentro del JSON.
"""
import json
import time
import queue
import base64
import socket
import itertools
import threading

PUERTO_CHAT = 5050
MAX_LINEA = 16 * 1024 * 1024
MAX_ARCHIVO = 8 * 1024 * 1024
MAX_FOTO = 1024 * 1024


def codificar(obj):
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


def decodificar(linea):
    return json.loads(linea.decode("utf-8"))


def a_base64(datos):
    return base64.b64encode(datos).decode("ascii")


def de_base64(texto):
    return base64.b64decode(texto) if texto else b""


def formatear(m):
    """Representación de texto de un mensaje, para pantalla y para guardar conversaciones."""
    hora = m.get("hora", "")[-8:]
    if m["tipo"] == "sistema":
        return f"[{hora}] * {m['texto']}"
    if m["tipo"] == "archivo":
        return f"[{hora}] {m['de']} envió el archivo '{m['nombre']}' ({m['tamano']} bytes) [id {m['id']}]"
    return f"[{hora}] {m['de']}: {m['texto']}"


class ErrorChat(Exception):
    pass


class ClienteChat:
    def __init__(self, host, puerto, usuario, clave, inactividad_max=None):
        self.sock = socket.create_connection((host, int(puerto)), timeout=10)
        self.sock.settimeout(None)
        self.lector = self.sock.makefile("rb")
        self.lock_envio = threading.Lock()
        self.contador = itertools.count(1)
        self.pendientes = {}
        self.conectado = True
        self.motivo_desconexion = ""
        self.usuario = None
        self.canales = {}      # canal -> lista de mensajes
        self.unidos = set()    # canales a los que estoy suscripto
        self.privados = {}     # otro usuario -> lista de mensajes
        self.usuarios = {}     # usuario -> {estado, conectado, foto}
        self.fotos = {}        # usuario -> (version, bytes)
        self.oyentes = []      # funciones llamadas con cada evento (cliente de terminal)
        self.ultimo_uso = time.time()
        self.inactividad_max = inactividad_max
        threading.Thread(target=self._leer, daemon=True).start()
        if inactividad_max:
            threading.Thread(target=self._vigilar_inactividad, daemon=True).start()
        try:
            r = self.pedir({"tipo": "login", "usuario": usuario, "clave": clave})
        except Exception:
            self.cerrar()
            raise
        self.usuario = r["usuario"]
        self.canales = {c: [] for c in r["canales"]}
        self._actualizar_usuarios(r["usuarios"])

    # ------------------------------------------------------------------ transporte
    def _enviar(self, obj):
        with self.lock_envio:
            self.sock.sendall(codificar(obj))

    def pedir(self, obj, timeout=20):
        if not self.conectado:
            raise ErrorChat(f"Sin conexión con el servidor. {self.motivo_desconexion}")
        req = next(self.contador)
        cola = queue.Queue(maxsize=1)
        self.pendientes[req] = cola
        try:
            self._enviar({**obj, "req": req})
            respuesta = cola.get(timeout=timeout)
        except queue.Empty:
            raise ErrorChat("El servidor no respondió a tiempo")
        finally:
            self.pendientes.pop(req, None)
        if respuesta.get("tipo") == "error":
            raise ErrorChat(respuesta.get("mensaje", "Error desconocido"))
        return respuesta

    def _leer(self):
        try:
            while True:
                linea = self.lector.readline(MAX_LINEA)
                if not linea:
                    self.motivo_desconexion = self.motivo_desconexion or "El servidor cerró la conexión."
                    break
                obj = decodificar(linea)
                cola = self.pendientes.get(obj.get("req"))
                if cola is not None:
                    cola.put(obj)
                else:
                    self._procesar_evento(obj)
        except (OSError, ValueError) as e:
            self.motivo_desconexion = self.motivo_desconexion or f"Conexión perdida: {e}"
        finally:
            self.conectado = False
            for cola in list(self.pendientes.values()):
                cola.put({"tipo": "error", "mensaje": self.motivo_desconexion})
            for oyente in self.oyentes:
                oyente({"tipo": "desconectado", "texto": self.motivo_desconexion})

    def _vigilar_inactividad(self):
        while self.conectado:
            time.sleep(5)
            if time.time() - self.ultimo_uso > self.inactividad_max:
                self.motivo_desconexion = "Desconectado por inactividad."
                self.cerrar()

    def tocar(self):
        self.ultimo_uso = time.time()

    def cerrar(self):
        self.conectado = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()

    # ------------------------------------------------------------------ eventos
    @staticmethod
    def _agregar(lista, mensaje):
        if not any(m.get("id") == mensaje.get("id") for m in lista[-50:]):
            lista.append(mensaje)

    @staticmethod
    def _fusionar(historial, actuales):
        ids = {m["id"] for m in historial}
        return sorted(historial + [m for m in actuales if m["id"] not in ids], key=lambda m: m["id"])

    def _actualizar_usuarios(self, lista):
        self.usuarios = {u["usuario"]: u for u in lista}

    def _procesar_evento(self, ev):
        tipo = ev.get("tipo")
        if tipo in ("mensaje_canal", "sistema") and ev.get("canal"):
            self._agregar(self.canales.setdefault(ev["canal"], []), ev)
        elif tipo in ("mensaje_privado", "archivo"):
            otro = ev["para"] if ev["de"] == self.usuario else ev["de"]
            self._agregar(self.privados.setdefault(otro, []), ev)
        elif tipo == "usuarios":
            self._actualizar_usuarios(ev["usuarios"])
        elif tipo == "canales":
            for canal in ev["canales"]:
                self.canales.setdefault(canal, [])
        for oyente in self.oyentes:
            oyente(ev)

    # ------------------------------------------------------------------ operaciones
    def unirse(self, canal):
        r = self.pedir({"tipo": "unirse", "canal": canal})
        self.unidos.add(canal)
        self.canales[canal] = self._fusionar(r["historial"], self.canales.get(canal, []))
        return self.canales[canal]

    def salir_canal(self, canal):
        self.pedir({"tipo": "salir_canal", "canal": canal})
        self.unidos.discard(canal)

    def crear_canal(self, canal):
        r = self.pedir({"tipo": "crear_canal", "canal": canal})
        self.canales.setdefault(r["canal"], [])
        return r["canal"]

    def enviar_canal(self, canal, texto):
        if canal not in self.unidos:
            self.unirse(canal)
        self.pedir({"tipo": "mensaje_canal", "canal": canal, "texto": texto})

    def historial_privado(self, usuario):
        r = self.pedir({"tipo": "historial", "con": usuario})
        self.privados[usuario] = self._fusionar(r["historial"], self.privados.get(usuario, []))
        return self.privados[usuario]

    def enviar_privado(self, para, texto):
        self.pedir({"tipo": "mensaje_privado", "para": para, "texto": texto})

    def enviar_archivo(self, para, nombre, datos):
        if len(datos) > MAX_ARCHIVO:
            raise ErrorChat(f"El archivo supera el máximo de {MAX_ARCHIVO // (1024 * 1024)} MB")
        self.pedir({"tipo": "enviar_archivo", "para": para, "nombre": nombre, "datos": a_base64(datos)}, timeout=60)

    def descargar(self, id_archivo):
        r = self.pedir({"tipo": "descargar", "id": id_archivo}, timeout=60)
        return r["nombre"], de_base64(r["datos"])

    def actualizar_perfil(self, estado, foto=None):
        pedido = {"tipo": "perfil", "estado": estado}
        if foto is not None:
            pedido["foto"] = a_base64(foto)
        self.pedir(pedido)

    def ver_perfil(self, usuario):
        r = self.pedir({"tipo": "ver_perfil", "usuario": usuario})
        r["foto"] = de_base64(r.get("foto"))
        return r

    def foto_de(self, usuario):
        """Foto de perfil con caché local: solo se pide de nuevo si cambió la versión."""
        info = self.usuarios.get(usuario, {})
        version = info.get("foto_version")
        if not version:
            return None
        if self.fotos.get(usuario, (None,))[0] != version:
            self.fotos[usuario] = (version, self.ver_perfil(usuario)["foto"])
        return self.fotos[usuario][1]
