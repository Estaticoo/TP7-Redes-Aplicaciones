"""Punto 3: Cliente de chat de terminal (habla el mismo protocolo TCP que la app web).

Uso:  python cliente_chat.py --usuario Ana [--host 127.0.0.1] [--puerto 5050]
La primera vez que se usa un nombre de usuario queda registrado con la contraseña ingresada.
"""
import os
import argparse
import getpass
from chat_protocolo import ClienteChat, ErrorChat, PUERTO_CHAT, formatear

AYUDA = """Comandos:
  <texto>                       Envía el texto al canal actual
  /canales                      Lista los canales
  /unirse <canal>               Cambia al canal (y muestra su historial)
  /crear <canal>                Crea un canal nuevo
  /privado <usuario> <texto>    Envía un mensaje privado
  /conversacion <usuario>       Muestra el historial privado con ese usuario
  /archivo <usuario> <ruta>     Envía un archivo a un usuario
  /descargar <id> [carpeta]     Descarga un archivo recibido
  /usuarios                     Lista usuarios y quién está conectado
  /perfil <estado>              Cambia tu estado
  /foto <ruta>                  Cambia tu foto de perfil (PNG/JPG/GIF)
  /ver <usuario>                Muestra el perfil de un usuario
  /guardar [archivo]            Guarda la conversación del canal actual en un .txt
  /ayuda                        Muestra esta ayuda
  /salir                        Cierra la conexión"""


def main():
    parser = argparse.ArgumentParser(description="Cliente de chat TP7 (terminal)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--puerto", type=int, default=PUERTO_CHAT)
    parser.add_argument("--usuario", required=True)
    args = parser.parse_args()

    cliente = ClienteChat(args.host, args.puerto, args.usuario, getpass.getpass("Contraseña: "))
    canal_actual = "General"

    def mostrar_evento(ev):
        tipo = ev.get("tipo")
        if tipo == "mensaje_canal" and ev["de"] != cliente.usuario:
            print(f"\n#{ev['canal']} {formatear(ev)}")
        elif tipo in ("mensaje_privado", "archivo") and ev["de"] != cliente.usuario:
            print(f"\n[privado] {formatear(ev)}")
        elif tipo == "canales":
            print(f"\n* Canales disponibles: {', '.join(ev['canales'])}")
        elif tipo == "desconectado":
            print(f"\n* {ev['texto']}")

    cliente.oyentes.append(mostrar_evento)
    for m in cliente.unirse(canal_actual)[-15:]:
        print(formatear(m))
    print(f"Conectado como {cliente.usuario} a {args.host}:{args.puerto}. Canal actual: #{canal_actual}. Escribí /ayuda para ver los comandos.")

    while cliente.conectado:
        try:
            linea = input(f"#{canal_actual}> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not linea:
            continue
        comando, _, resto = linea.partition(" ")
        try:
            if not linea.startswith("/"):
                cliente.enviar_canal(canal_actual, linea)
            elif comando == "/salir":
                break
            elif comando == "/ayuda":
                print(AYUDA)
            elif comando == "/canales":
                print("Canales: " + ", ".join(f"#{c}" + (" (actual)" if c == canal_actual else "") for c in cliente.canales))
            elif comando == "/unirse":
                canal_actual = resto.strip().lstrip("#")
                for m in cliente.unirse(canal_actual)[-15:]:
                    print(formatear(m))
            elif comando == "/crear":
                print(f"Canal #{cliente.crear_canal(resto.strip())} creado.")
            elif comando == "/privado":
                para, _, texto = resto.partition(" ")
                cliente.enviar_privado(para, texto)
            elif comando == "/conversacion":
                for m in cliente.historial_privado(resto.strip())[-30:]:
                    print(formatear(m))
            elif comando == "/archivo":
                para, _, ruta = resto.partition(" ")
                with open(os.path.expanduser(ruta.strip()), "rb") as f:
                    cliente.enviar_archivo(para, os.path.basename(ruta.strip()), f.read())
                print("Archivo enviado.")
            elif comando == "/descargar":
                id_archivo, _, carpeta = resto.partition(" ")
                nombre, datos = cliente.descargar(int(id_archivo))
                destino = os.path.join(carpeta.strip() or ".", nombre)
                with open(destino, "wb") as f:
                    f.write(datos)
                print(f"Guardado en {destino} ({len(datos)} bytes).")
            elif comando == "/usuarios":
                for u in cliente.pedir({"tipo": "usuarios"})["usuarios"]:
                    print(f"  {'🟢' if u['conectado'] else '⚪'} {u['usuario']:<20} {u['estado']}")
            elif comando == "/perfil":
                cliente.actualizar_perfil(resto.strip())
                print("Estado actualizado.")
            elif comando == "/foto":
                with open(os.path.expanduser(resto.strip()), "rb") as f:
                    cliente.actualizar_perfil(cliente.usuarios.get(cliente.usuario, {}).get("estado", ""), f.read())
                print("Foto actualizada.")
            elif comando == "/ver":
                p = cliente.ver_perfil(resto.strip())
                print(f"  {p['usuario']} | {'conectado' if p['conectado'] else 'desconectado'} | estado: {p['estado'] or '-'} | "
                      f"registrado: {p['registrado']} | foto: {'sí' if p['foto'] else 'no'}")
            elif comando == "/guardar":
                destino = resto.strip() or f"chat_{canal_actual}.txt"
                with open(destino, "w", encoding="utf-8") as f:
                    f.write("\n".join(formatear(m) for m in cliente.canales.get(canal_actual, [])))
                print(f"Conversación guardada en {destino}.")
            else:
                print("Comando desconocido. Escribí /ayuda.")
        except (ErrorChat, OSError, ValueError) as e:
            print(f"Error: {e}")
    cliente.cerrar()
    print("Desconectado.")


if __name__ == "__main__":
    main()
