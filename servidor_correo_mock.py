import time
from aiosmtpd.controller import Controller
from datetime import datetime

class ManejadorCorreoLocal:
    async def handle_DATA(self, server, session, envelope):
        remitente = envelope.mail_from
        destinatarios = envelope.rcpt_tos
        contenido = envelope.content.decode('utf-8', errors='replace')
        hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        salida = (
            f"\n{'='*60}\n"
            f"[{hora}] NUEVO CORREO RECIBIDO POR SMTP\n"
            f"De: {remitente}\n"
            f"Para: {', '.join(destinatarios)}\n"
            f"--- Contenido del Mensaje ---\n"
            f"{contenido}\n"
            f"{'='*60}\n"
        )
        print(salida)
        
        with open("correos_recibidos.log", "a", encoding="utf-8") as f:
            f.write(salida)
            
        return '250 Mensaje aceptado para entrega'

if __name__ == '__main__':
    HOST = "127.0.0.1"
    PORT = 1025
    controlador = Controller(ManejadorCorreoLocal(), hostname=HOST, port=PORT)
    controlador.start()
    print(f"Servidor SMTP Mock escuchando en {HOST}:{PORT}...")
    print("Presiona Ctrl+C para detener el servidor.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDeteniendo servidor SMTP...")
        controlador.stop()