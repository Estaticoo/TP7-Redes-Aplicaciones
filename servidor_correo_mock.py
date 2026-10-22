"""Servidor de correo local de prueba: SMTP (1025), IMAP (1143) y POP3 (1110).

Sirve para probar el cliente de correo sin internet y para capturar con Wireshark
los tres protocolos en texto plano. Los mensajes se guardan como archivos .eml en
buzones/<direccion>/ y cualquier dirección de correo inicia sesión con la clave 1234.
"""
import os
import re
import sys
import time
import email
import email.policy
import logging
import threading
import socketserver
from datetime import datetime
from email.message import EmailMessage
from email.utils import format_datetime, parsedate_to_datetime
from aiosmtpd.controller import Controller

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIR_BUZONES = os.path.join(BASE_DIR, "buzones")
ARCHIVO_LOG = os.path.join(BASE_DIR, "servidor_correo.log")

HOST = "127.0.0.1"
PUERTO_SMTP = 1025
PUERTO_IMAP = 1143
PUERTO_POP3 = 1110
CLAVE_PRUEBA = "1234"
USUARIO_DEMO = "alumno@tp7.local"
LIMITE_LINEA = 64 * 1024
CAPACIDADES_IMAP = "IMAP4rev1 LITERAL+ UIDPLUS ID ENABLE"

lock_buzones = threading.Lock()


def configurar_logging():
    formato = logging.Formatter("%(asctime)s | %(message)s")
    logger = logging.getLogger("servidor_correo")
    logger.setLevel(logging.INFO)
    for handler in (logging.FileHandler(ARCHIVO_LOG, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        handler.setFormatter(formato)
        logger.addHandler(handler)
    return logger


log = configurar_logging()


# ============================================================================
# ALMACENAMIENTO: un directorio por buzón, un archivo .eml por mensaje (UID)
# ============================================================================
class Buzon:
    def __init__(self, direccion):
        self.direccion = direccion.strip().lower()
        nombre = re.sub(r"[^a-z0-9@._-]", "_", self.direccion)
        self.ruta = os.path.join(DIR_BUZONES, nombre)

    def uids(self):
        if not os.path.isdir(self.ruta):
            return []
        return sorted(int(n[:-4]) for n in os.listdir(self.ruta) if n.endswith(".eml") and n[:-4].isdigit())

    def leer(self, uid):
        with open(os.path.join(self.ruta, f"{uid}.eml"), "rb") as f:
            return f.read()

    def agregar(self, datos):
        with lock_buzones:
            os.makedirs(self.ruta, exist_ok=True)
            archivo_siguiente = os.path.join(self.ruta, ".uidnext")
            siguiente = 1
            if os.path.exists(archivo_siguiente):
                with open(archivo_siguiente, "r") as f:
                    siguiente = int(f.read().strip() or 1)
            with open(os.path.join(self.ruta, f"{siguiente}.eml"), "wb") as f:
                f.write(normalizar_crlf(datos))
            with open(archivo_siguiente, "w") as f:
                f.write(str(siguiente + 1))
            return siguiente

    def eliminar(self, uid):
        with lock_buzones:
            ruta = os.path.join(self.ruta, f"{uid}.eml")
            if os.path.exists(ruta):
                os.remove(ruta)

    def uid_siguiente(self):
        archivo = os.path.join(self.ruta, ".uidnext")
        if os.path.exists(archivo):
            with open(archivo, "r") as f:
                return int(f.read().strip() or 1)
        return 1


def normalizar_crlf(datos):
    return re.sub(rb"\r?\n", b"\r\n", datos)


def credenciales_validas(usuario, clave):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+", usuario or "")) and clave == CLAVE_PRUEBA


# ============================================================================
# SMTP (aiosmtpd) - recibe correos y los entrega en el buzón de cada destinatario
# ============================================================================
class ManejadorSMTP:
    async def handle_EHLO(self, server, session, envelope, hostname, responses):
        session.host_name = hostname
        log.info(f"SMTP | C: EHLO {hostname} | Cliente {session.peer[0]}")
        return responses

    async def handle_MAIL(self, server, session, envelope, address, mail_options):
        envelope.mail_from = address
        envelope.mail_options.extend(mail_options)
        log.info(f"SMTP | C: MAIL FROM:<{address}> | S: 250 OK")
        return "250 OK"

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        if not re.fullmatch(r"[^@\s]+@[^@\s]+", address):
            log.info(f"SMTP | C: RCPT TO:<{address}> | S: 550 Dirección inválida")
            return "550 Direccion de destino invalida"
        envelope.rcpt_tos.append(address)
        log.info(f"SMTP | C: RCPT TO:<{address}> | S: 250 OK")
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        ahora = format_datetime(datetime.now().astimezone())
        traza = (
            f"Return-Path: <{envelope.mail_from}>\r\n"
            f"Received: from {session.host_name or 'desconocido'} ([{session.peer[0]}])\r\n"
            f"\tby tp7.local (Servidor SMTP TP7) with SMTP; {ahora}\r\n"
        ).encode("utf-8")
        for destinatario in envelope.rcpt_tos:
            uid = Buzon(destinatario).agregar(traza + envelope.original_content)
            log.info(f"SMTP | DATA {len(envelope.original_content)} bytes entregados a {destinatario} (UID {uid})")
        return "250 Mensaje aceptado para entrega"


# ============================================================================
# Utilidades comunes a IMAP y POP3
# ============================================================================
def analizar(datos):
    return email.message_from_bytes(datos, policy=email.policy.default)


def texto_cuerpo(msg):
    partes = []
    for parte in msg.walk():
        if parte.get_content_maintype() == "text" and not parte.is_attachment():
            try:
                partes.append(parte.get_content())
            except (LookupError, ValueError):
                pass
    return "\n".join(partes)


def coincide(msg, criterio, valor):
    valor = valor.casefold()
    if criterio in ("FROM", "TO", "CC", "BCC", "SUBJECT"):
        return valor in str(msg.get(criterio, "")).casefold()
    if criterio == "BODY":
        return valor in texto_cuerpo(msg).casefold()
    if criterio == "TEXT":
        cabeceras = " ".join(f"{k}: {v}" for k, v in msg.items())
        return valor in (cabeceras + "\n" + texto_cuerpo(msg)).casefold()
    return False


def fecha_mensaje(msg):
    try:
        return parsedate_to_datetime(msg["Date"]).date()
    except (TypeError, ValueError):
        return None


# ============================================================================
# IMAP4rev1 (subconjunto) - RFC 3501
# ============================================================================
def tokenizar(texto):
    tokens, i = [], 0
    while i < len(texto):
        c = texto[i]
        if c == " ":
            i += 1
        elif c == '"':
            j, buf = i + 1, []
            while j < len(texto) and texto[j] != '"':
                if texto[j] == "\\" and j + 1 < len(texto):
                    j += 1
                buf.append(texto[j])
                j += 1
            tokens.append("".join(buf))
            i = j + 1
        else:
            j, profundidad = i, 0
            while j < len(texto) and (texto[j] != " " or profundidad > 0):
                if texto[j] in "([":
                    profundidad += 1
                elif texto[j] in ")]":
                    profundidad -= 1
                j += 1
            tokens.append(texto[i:j])
            i = j
    return tokens


class SesionIMAP(socketserver.StreamRequestHandler):
    def setup(self):
        super().setup()
        self.usuario = None
        self.buzon = None
        self.uids = []
        self.flags = {}

    def enviar(self, linea):
        self.wfile.write(linea.encode("utf-8") + b"\r\n")

    def responder(self, tag, estado, texto):
        self.enviar(f"{tag} {estado} {texto}")
        log.info(f"IMAP | S: {tag} {estado} {texto}")

    def leer_comando(self):
        tokens = []
        linea = self.rfile.readline(LIMITE_LINEA)
        if not linea:
            return None
        while True:
            texto = linea.decode("utf-8", "replace").rstrip("\r\n")
            literal = re.search(r"\{(\d+)(\+?)\}$", texto)
            if not literal:
                return tokens + tokenizar(texto)
            tokens += tokenizar(texto[:literal.start()])
            if not literal.group(2):
                self.enviar("+ Listo para recibir el literal")
            tokens.append(self.rfile.read(int(literal.group(1))).decode("utf-8", "replace"))
            linea = self.rfile.readline(LIMITE_LINEA)

    def handle(self):
        log.info(f"IMAP | Conexión desde {self.client_address[0]}:{self.client_address[1]}")
        self.enviar(f"* OK [CAPABILITY {CAPACIDADES_IMAP}] Servidor IMAP TP7 listo")
        while True:
            try:
                tokens = self.leer_comando()
            except (ConnectionError, OSError):
                break
            if tokens is None:
                break
            if len(tokens) < 2:
                self.enviar("* BAD Comando incompleto")
                continue
            tag, comando, args = tokens[0], tokens[1].upper(), tokens[2:]
            visibles = args[:1] + ["****"] if comando == "LOGIN" else args
            log.info(f"IMAP | C: {tag} {comando} {' '.join(a if len(a) < 60 else a[:57] + '...' for a in visibles)}")
            modo_uid = False
            if comando == "UID" and args:
                modo_uid, comando, args = True, args[0].upper(), args[1:]
            try:
                if self.despachar(tag, comando, args, modo_uid) == "LOGOUT":
                    break
            except Exception as e:
                self.responder(tag, "BAD", f"Error procesando {comando}: {e}")
        log.info(f"IMAP | Conexión cerrada {self.client_address[0]}:{self.client_address[1]}")

    def despachar(self, tag, comando, args, modo_uid):
        if comando == "CAPABILITY":
            self.enviar(f"* CAPABILITY {CAPACIDADES_IMAP}")
            self.responder(tag, "OK", "CAPABILITY completado")
        elif comando == "NOOP":
            self.responder(tag, "OK", "NOOP completado")
        elif comando == "ID":
            self.enviar('* ID ("name" "Servidor IMAP TP7")')
            self.responder(tag, "OK", "ID completado")
        elif comando == "ENABLE":
            self.responder(tag, "OK", "ENABLE completado")
        elif comando == "LOGOUT":
            self.enviar("* BYE Cerrando conexión")
            self.responder(tag, "OK", "LOGOUT completado")
            return "LOGOUT"
        elif comando == "LOGIN":
            if len(args) == 2 and credenciales_validas(args[0], args[1]):
                self.usuario = args[0].lower()
                self.responder(tag, "OK", f"[CAPABILITY {CAPACIDADES_IMAP}] LOGIN completado")
            else:
                self.responder(tag, "NO", "[AUTHENTICATIONFAILED] Usuario o contraseña inválidos")
        elif self.usuario is None:
            self.responder(tag, "NO", "Primero hay que iniciar sesión (LOGIN)")
        elif comando == "LIST":
            self.enviar('* LIST (\\HasNoChildren) "/" INBOX')
            self.responder(tag, "OK", "LIST completado")
        elif comando in ("SELECT", "EXAMINE"):
            self.seleccionar(tag, comando, args)
        elif self.buzon is None:
            self.responder(tag, "NO", "Primero hay que seleccionar un buzón (SELECT)")
        elif comando == "SEARCH":
            self.buscar(tag, args, modo_uid)
        elif comando == "FETCH":
            self.obtener(tag, args, modo_uid)
        elif comando == "STORE":
            self.almacenar_flags(tag, args, modo_uid)
        elif comando == "EXPUNGE":
            self.expurgar(notificar=True)
            self.responder(tag, "OK", "EXPUNGE completado")
        elif comando == "CLOSE":
            self.expurgar(notificar=False)
            self.buzon = None
            self.responder(tag, "OK", "CLOSE completado")
        elif comando in ("COPY", "MOVE"):
            self.responder(tag, "NO", "[TRYCREATE] Solo existe el buzón INBOX")
        else:
            self.responder(tag, "BAD", f"Comando no soportado: {comando}")

    def seleccionar(self, tag, comando, args):
        if not args or args[0].upper() != "INBOX":
            self.responder(tag, "NO", "Solo existe el buzón INBOX")
            return
        self.buzon = Buzon(self.usuario)
        self.uids = self.buzon.uids()
        self.flags = {uid: set() for uid in self.uids}
        self.enviar("* FLAGS (\\Seen \\Deleted)")
        self.enviar("* OK [PERMANENTFLAGS (\\Seen \\Deleted)] Flags permitidos")
        self.enviar(f"* {len(self.uids)} EXISTS")
        self.enviar("* 0 RECENT")
        self.enviar("* OK [UIDVALIDITY 1] UIDs válidos")
        self.enviar(f"* OK [UIDNEXT {self.buzon.uid_siguiente()}] Próximo UID")
        modo = "READ-ONLY" if comando == "EXAMINE" else "READ-WRITE"
        self.responder(tag, "OK", f"[{modo}] {comando} completado")

    def resolver_conjunto(self, conjunto, modo_uid):
        maximo = (self.uids[-1] if self.uids else 0) if modo_uid else len(self.uids)
        rangos = []
        for parte in conjunto.split(","):
            a, _, b = parte.partition(":")
            a = maximo if a == "*" else int(a)
            b = a if not b else (maximo if b == "*" else int(b))
            rangos.append((min(a, b), max(a, b)))
        return [(seq, uid) for seq, uid in enumerate(self.uids, 1)
                if any(lo <= (uid if modo_uid else seq) <= hi for lo, hi in rangos)]

    def buscar(self, tag, args, modo_uid):
        args = list(args)
        if args and args[0].upper() == "CHARSET":
            args = args[2:]
        criterios = []
        while args:
            clave = args.pop(0).upper()
            if clave in ("ALL", "UNDELETED", "DELETED", "SEEN", "UNSEEN"):
                criterios.append((clave, None))
            elif clave in ("FROM", "TO", "CC", "BCC", "SUBJECT", "BODY", "TEXT", "SINCE", "BEFORE", "ON") and args:
                criterios.append((clave, args.pop(0)))
            else:
                self.responder(tag, "BAD", f"Criterio de búsqueda no soportado: {clave}")
                return
        resultado = []
        for seq, uid in enumerate(self.uids, 1):
            try:
                msg = analizar(self.buzon.leer(uid))
            except FileNotFoundError:
                continue
            if all(self.cumple(msg, uid, c, v) for c, v in criterios):
                resultado.append(str(uid if modo_uid else seq))
        self.enviar("* SEARCH" + ("" if not resultado else " " + " ".join(resultado)))
        self.responder(tag, "OK", f"SEARCH completado ({len(resultado)} resultados)")

    def cumple(self, msg, uid, criterio, valor):
        if criterio in ("ALL", "SEEN", "UNSEEN"):
            return True
        if criterio == "DELETED":
            return "\\Deleted" in self.flags.get(uid, set())
        if criterio == "UNDELETED":
            return "\\Deleted" not in self.flags.get(uid, set())
        if criterio in ("SINCE", "BEFORE", "ON"):
            fecha_msg = fecha_mensaje(msg)
            if fecha_msg is None:
                return False
            fecha = datetime.strptime(valor, "%d-%b-%Y").date()
            return {"SINCE": fecha_msg >= fecha, "BEFORE": fecha_msg < fecha, "ON": fecha_msg == fecha}[criterio]
        return coincide(msg, criterio, valor)

    def obtener(self, tag, args, modo_uid):
        if len(args) < 2:
            self.responder(tag, "BAD", "FETCH requiere conjunto e ítems")
            return
        items = args[1].strip("()").upper().split()
        if modo_uid and "UID" not in items:
            items.insert(0, "UID")
        for seq, uid in self.resolver_conjunto(args[0], modo_uid):
            try:
                datos = self.buzon.leer(uid)
            except FileNotFoundError:
                continue
            partes, literales = [], []
            for item in items:
                if item == "UID":
                    partes.append(f"UID {uid}")
                elif item == "FLAGS":
                    partes.append(f"FLAGS ({' '.join(sorted(self.flags.get(uid, set())))})")
                elif item == "RFC822.SIZE":
                    partes.append(f"RFC822.SIZE {len(datos)}")
                elif item == "INTERNALDATE":
                    fecha = datetime.fromtimestamp(os.path.getmtime(os.path.join(self.buzon.ruta, f"{uid}.eml")))
                    partes.append(f'INTERNALDATE "{fecha.strftime("%d-%b-%Y %H:%M:%S")} -0300"')
                elif item in ("RFC822", "BODY[]", "BODY.PEEK[]"):
                    etiqueta = "RFC822" if item == "RFC822" else "BODY[]"
                    literales.append((etiqueta, datos))
                    if item != "BODY.PEEK[]":
                        self.flags.setdefault(uid, set()).add("\\Seen")
                elif item in ("RFC822.HEADER", "BODY[HEADER]", "BODY.PEEK[HEADER]"):
                    etiqueta = "RFC822.HEADER" if item == "RFC822.HEADER" else "BODY[HEADER]"
                    literales.append((etiqueta, datos.split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n"))
            linea = f"* {seq} FETCH (" + " ".join(partes)
            if not literales:
                self.enviar(linea + ")")
                continue
            salida = linea.encode("utf-8")
            for i, (etiqueta, contenido) in enumerate(literales):
                separador = b" " if (partes or i) else b""
                salida += separador + f"{etiqueta} {{{len(contenido)}}}\r\n".encode("utf-8") + contenido
            self.wfile.write(salida + b")\r\n")
        self.responder(tag, "OK", "FETCH completado")

    def almacenar_flags(self, tag, args, modo_uid):
        if len(args) < 3:
            self.responder(tag, "BAD", "STORE requiere conjunto, operación y flags")
            return
        operacion = args[1].upper()
        flags = set(args[2].strip("()").split())
        for seq, uid in self.resolver_conjunto(args[0], modo_uid):
            actuales = self.flags.setdefault(uid, set())
            if operacion.startswith("+FLAGS"):
                actuales |= flags
            elif operacion.startswith("-FLAGS"):
                actuales -= flags
            else:
                actuales.clear()
                actuales |= flags
            if not operacion.endswith(".SILENT"):
                extra = f"UID {uid} " if modo_uid else ""
                self.enviar(f"* {seq} FETCH ({extra}FLAGS ({' '.join(sorted(actuales))}))")
        self.responder(tag, "OK", "STORE completado")

    def expurgar(self, notificar):
        # Se recorre de atrás hacia adelante para que los números de secuencia no se corran
        for seq in range(len(self.uids), 0, -1):
            uid = self.uids[seq - 1]
            if "\\Deleted" in self.flags.get(uid, set()):
                self.buzon.eliminar(uid)
                del self.uids[seq - 1]
                self.flags.pop(uid, None)
                log.info(f"IMAP | Mensaje UID {uid} eliminado del buzón {self.usuario}")
                if notificar:
                    self.enviar(f"* {seq} EXPUNGE")


# ============================================================================
# POP3 - RFC 1939
# ============================================================================
class SesionPOP3(socketserver.StreamRequestHandler):
    def setup(self):
        super().setup()
        self.usuario_propuesto = None
        self.buzon = None
        self.uids = []
        self.borrados = set()

    def enviar(self, linea):
        self.wfile.write(linea.encode("utf-8") + b"\r\n")
        log.info(f"POP3 | S: {linea}")

    def enviar_multilinea(self, encabezado, lineas_bytes):
        self.enviar(encabezado)
        cuerpo = b"".join((b"." + l if l.startswith(b".") else l) + b"\r\n" for l in lineas_bytes)
        self.wfile.write(cuerpo + b".\r\n")

    def mensaje(self, argumento):
        """Devuelve (numero, uid) para un número de mensaje válido y no borrado."""
        try:
            numero = int(argumento)
        except (TypeError, ValueError):
            return None
        if 1 <= numero <= len(self.uids) and numero not in self.borrados:
            return numero, self.uids[numero - 1]
        return None

    def handle(self):
        log.info(f"POP3 | Conexión desde {self.client_address[0]}:{self.client_address[1]}")
        self.enviar("+OK Servidor POP3 TP7 listo")
        while True:
            try:
                linea = self.rfile.readline(LIMITE_LINEA)
            except (ConnectionError, OSError):
                break
            if not linea:
                break
            partes = linea.decode("utf-8", "replace").strip().split(" ")
            comando, args = partes[0].upper(), partes[1:]
            log.info(f"POP3 | C: {' '.join([comando] + (['****'] if comando == 'PASS' else args))}")
            try:
                if self.despachar(comando, args) == "QUIT":
                    break
            except Exception as e:
                self.enviar(f"-ERR Error procesando {comando}: {e}")
        log.info(f"POP3 | Conexión cerrada {self.client_address[0]}:{self.client_address[1]}")

    def despachar(self, comando, args):
        if comando == "CAPA":
            self.enviar_multilinea("+OK Lista de capacidades", [b"USER", b"UIDL", b"TOP"])
        elif comando == "QUIT":
            for numero in sorted(self.borrados):
                self.buzon.eliminar(self.uids[numero - 1])
            if self.borrados:
                log.info(f"POP3 | {len(self.borrados)} mensajes eliminados del buzón {self.buzon.direccion}")
            self.enviar("+OK Hasta luego")
            return "QUIT"
        elif self.buzon is None:
            self.despachar_autorizacion(comando, args)
        else:
            self.despachar_transaccion(comando, args)

    def despachar_autorizacion(self, comando, args):
        if comando == "USER" and args:
            self.usuario_propuesto = args[0]
            self.enviar("+OK Usuario recibido, enviar PASS")
        elif comando == "PASS" and self.usuario_propuesto:
            if credenciales_validas(self.usuario_propuesto, " ".join(args)):
                self.buzon = Buzon(self.usuario_propuesto)
                self.uids = self.buzon.uids()
                self.enviar(f"+OK Buzón abierto con {len(self.uids)} mensajes")
            else:
                self.usuario_propuesto = None
                self.enviar("-ERR Usuario o contraseña inválidos")
        else:
            self.enviar("-ERR Primero USER y PASS")

    def despachar_transaccion(self, comando, args):
        vigentes = [(n, u) for n, u in enumerate(self.uids, 1) if n not in self.borrados]
        if comando == "STAT":
            total = sum(len(self.buzon.leer(u)) for _, u in vigentes)
            self.enviar(f"+OK {len(vigentes)} {total}")
        elif comando in ("LIST", "UIDL"):
            def detalle(n, u):
                return f"{n} {len(self.buzon.leer(u)) if comando == 'LIST' else u}"
            if args:
                elegido = self.mensaje(args[0])
                self.enviar(f"+OK {detalle(*elegido)}" if elegido else "-ERR No existe ese mensaje")
            else:
                self.enviar_multilinea(f"+OK {len(vigentes)} mensajes", [detalle(n, u).encode() for n, u in vigentes])
        elif comando in ("RETR", "TOP"):
            elegido = self.mensaje(args[0] if args else None)
            if not elegido:
                self.enviar("-ERR No existe ese mensaje")
                return
            datos = self.buzon.leer(elegido[1])
            lineas = datos.split(b"\r\n")
            if lineas and lineas[-1] == b"":
                lineas.pop()
            if comando == "TOP":
                corte = lineas.index(b"") if b"" in lineas else len(lineas)
                lineas = lineas[:corte + 1 + int(args[1] if len(args) > 1 else 0)]
            self.enviar_multilinea(f"+OK {len(datos)} octetos", lineas)
        elif comando == "DELE":
            elegido = self.mensaje(args[0] if args else None)
            if elegido:
                self.borrados.add(elegido[0])
                self.enviar(f"+OK Mensaje {elegido[0]} marcado para borrar")
            else:
                self.enviar("-ERR No existe ese mensaje")
        elif comando == "RSET":
            self.borrados.clear()
            self.enviar("+OK Marcas de borrado descartadas")
        elif comando == "NOOP":
            self.enviar("+OK")
        else:
            self.enviar(f"-ERR Comando no soportado: {comando}")


class ServidorTCP(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


# ============================================================================
# Datos de ejemplo para que el buzón de prueba no arranque vacío
# ============================================================================
def crear_mensajes_de_ejemplo():
    buzon = Buzon(USUARIO_DEMO)
    if buzon.uids() or buzon.uid_siguiente() > 1:
        return
    ejemplos = [
        ("profesor@frm.utn.test", "Bienvenida al TP N°7 de Redes de Información",
         "Hola,\n\nEn este trabajo práctico van a implementar aplicaciones de correo, web, chat y FTP.\n"
         "Adjunto la consigna resumida.\n\nSaludos.", ("consigna.txt", "Cliente de correo, servidor web, chat y cliente FTP.")),
        ("hernan@tp7.local", "Reunión del grupo",
         "Nos juntamos el jueves para revisar el informe y las capturas de Wireshark.", None),
        ("bedelia@frm.utn.test", "Cronograma de entregas",
         "Recordatorio: la entrega del TP7 es por el campus virtual. Incluir el enlace al repositorio y el cliente FTP.", None),
    ]
    for i, (remitente, asunto, cuerpo, adjunto) in enumerate(ejemplos):
        msg = EmailMessage()
        msg["From"] = remitente
        msg["To"] = USUARIO_DEMO
        if i == 2:
            msg["Cc"] = "hernan@tp7.local"
        msg["Subject"] = asunto
        msg["Date"] = format_datetime(datetime.now().astimezone())
        msg["Message-ID"] = f"<ejemplo-{i + 1}-{int(time.time())}@tp7.local>"
        msg.set_content(cuerpo)
        if adjunto:
            msg.add_attachment(adjunto[1].encode("utf-8"), maintype="text", subtype="plain", filename=adjunto[0])
        buzon.agregar(msg.as_bytes())
    log.info(f"Se crearon {len(ejemplos)} mensajes de ejemplo en el buzón {USUARIO_DEMO}")


if __name__ == "__main__":
    os.makedirs(DIR_BUZONES, exist_ok=True)
    crear_mensajes_de_ejemplo()

    controlador = Controller(ManejadorSMTP(), hostname=HOST, port=PUERTO_SMTP)
    controlador.start()
    servidores = [ServidorTCP((HOST, PUERTO_IMAP), SesionIMAP), ServidorTCP((HOST, PUERTO_POP3), SesionPOP3)]
    for servidor in servidores:
        threading.Thread(target=servidor.serve_forever, daemon=True).start()

    log.info(f"Servidor SMTP escuchando en {HOST}:{PUERTO_SMTP}")
    log.info(f"Servidor IMAP escuchando en {HOST}:{PUERTO_IMAP}")
    log.info(f"Servidor POP3 escuchando en {HOST}:{PUERTO_POP3}")
    log.info(f"Usuario de prueba: {USUARIO_DEMO} / Contraseña: {CLAVE_PRUEBA} (sirve cualquier dirección con esa clave)")
    print("Presiona Ctrl+C para detener los servidores.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDeteniendo servidores de correo...")
        controlador.stop()
        for servidor in servidores:
            servidor.shutdown()
