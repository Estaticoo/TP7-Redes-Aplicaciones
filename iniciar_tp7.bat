@echo off
mkdir ftp_files 2>nul
start "Servidor Web HTTP (Puerto 8080)" .\.venv\Scripts\python.exe servidor_web.py
start "Servidor FTP Local (Puerto 2121)" .\.venv\Scripts\python.exe -m pyftpdlib -p 2121 -w -d ./ftp_files
start "Servidor SMTP Mock (Puerto 1025)" .\.venv\Scripts\python.exe servidor_correo_mock.py
start "App Principal TP7 (Puerto 8501)" .\.venv\Scripts\python.exe -m streamlit run app.py