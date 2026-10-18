# 🌐 Trabajo Práctico N° 7: Implementación de Aplicaciones de Red

**Universidad Tecnológica Nacional - Facultad Regional Mendoza (UTN FRM)**  
**Carrera:** Ingeniería en Sistemas de Información  
**Asignatura:** Redes de Información  
**Docente a cargo:** Esp. Prof. Raúl Tonelli

---

## 📋 Descripción del Proyecto

Este repositorio contiene la implementación y caracterización de cuatro aplicaciones de capa de aplicación sobre la pila TCP/IP:

1. **Cliente de Correo Electrónico Web** con soporte nativo para **SMTP, IMAP y POP3**.
2. **Servidor Web HTTP** propio con aislamiento de `DocumentRoot`, autenticación **HTTP Basic**, configuración en caliente vía Web y registro de auditoría (_Logging_).
3. **Sistema Cliente/Servidor de Mensajería Instantánea (Chat)** con soporte multi-canal, mensajería privada, transferencia de archivos P2P/directa, gestión de perfiles con foto y exportación de historial.
4. **Cliente y Servidor FTP** con soporte para comandos de control y transferencia de datos (`LIST`, `PWD`, `CWD`, `MKD`, `RMD`, `STOR`, `RETR`, `DELE`).

---

## 🛠️ Requisitos Previos e Instalación

El proyecto está desarrollado en **Python 3** utilizando sus librerías estándar de protocolos de red (`smtplib`, `imaplib`, `poplib`, `http.server`, `ftplib`) junto con `streamlit`, `pyftpdlib` y `aiosmtpd`.

### 1. Clonar el repositorio y crear el entorno virtual

```powershell
git clone <URL_DEL_REPOSITORIO>
cd "TP7 REDES"
python -m venv .venv
```

### 2. Instalar las dependencias

```powershell
.\.venv\Scripts\python.exe -m pip install streamlit pyftpdlib aiosmtpd
```

---

## 🚀 Guía de Ejecución por Módulo

Para levantar todos los servicios simultáneamente en Windows, se puede ejecutar el script automático `iniciar_tp7.bat` o iniciar cada módulo en una terminal independiente:

### Módulo 1, 3 y 4: Panel Web Unificado (`app.py`)

Levanta la interfaz web para el **Cliente de Correo**, **Chat Cliente/Servidor** y **Cliente FTP** en el puerto `8501`:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

- **Acceso en navegador:** `http://localhost:8501`

#### Configuración adicional para el Punto 1 (Correo):

- **Modo Real (Gmail):** Generar una _Contraseña de Aplicación_ de 16 caracteres en Google Security y habilitar POP/IMAP en la cuenta de Gmail (`smtp.gmail.com:465`, `imap.gmail.com:993`, `pop.gmail.com:995`).
- **Modo Prueba Local (Servidor SMTP Mock en puerto 1025):**
  ```powershell
  .\.venv\Scripts\python.exe servidor_correo_mock.py
  ```

#### Configuración adicional para el Punto 4 (Servidor FTP Local de prueba en puerto 2121):

```powershell
mkdir ftp_files -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pyftpdlib -p 2121 -w -d ./ftp_files
```

---

### Módulo 2: Servidor Web HTTP (`servidor_web.py`)

Levanta el servidor HTTP propio en el puerto `8080`:

```powershell
.\.venv\Scripts\python.exe servidor_web.py
```

- **Panel Principal:** `http://localhost:8080`
- **Zona Protegida (HTTP Basic Auth):** `http://localhost:8080/privado/secreto.html` (Credenciales por defecto: `admin` / `1234`)
- **Configuración del Servidor vía Web:** `http://localhost:8080/config`
- **Visor de Logs en tiempo real:** `http://localhost:8080/logs`
- **Prueba de seguridad (Bloqueo fuera de `DocumentRoot`):**
  ```powershell
  curl --path-as-is http://localhost:8080/../../Windows/win.ini
  ```

---

## 📂 Estructura del Repositorio

```text
├── app.py                   # Aplicación Web Principal (Correo SMTP/IMAP/POP3, Chat y Cliente FTP)
├── servidor_web.py          # Servidor HTTP con seguridad DocumentRoot, Auth Basic y Logs
├── servidor_correo_mock.py  # Servidor SMTP local (Puerto 1025) para pruebas sin internet
├── iniciar_tp7.bat          # Script de inicio automático de todos los servicios en Windows
└── README.md                # Documentación del proyecto
```
