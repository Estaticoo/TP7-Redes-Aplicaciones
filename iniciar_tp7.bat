@echo off
rem Inicia todos los servicios del TP7 en Windows (cada uno en su propia ventana)
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Primero crea el entorno: python -m venv .venv  y luego  .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)
mkdir ftp_files 2>nul
start "Servidor Web HTTP (8080)" .\.venv\Scripts\python.exe servidor_web.py
start "Servidor de Correo SMTP 1025 / IMAP 1143 / POP3 1110" .\.venv\Scripts\python.exe servidor_correo_mock.py
start "Servidor de Chat TCP (5050)" .\.venv\Scripts\python.exe servidor_chat.py
start "Servidor FTP Local (2121)" .\.venv\Scripts\python.exe -m pyftpdlib -p 2121 -w -d ./ftp_files
start "App Principal TP7 (8501)" .\.venv\Scripts\python.exe -m streamlit run app.py
timeout /t 4 >nul
start "" http://localhost:8501
start "" http://localhost:8080
