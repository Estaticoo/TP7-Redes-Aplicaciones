#!/usr/bin/env bash
# Inicia todos los servicios del TP7 en macOS / Linux. Ctrl+C detiene todo.
cd "$(dirname "$0")" || exit 1
PY=.venv/bin/python
if [ ! -x "$PY" ]; then
    echo "Primero creá el entorno: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi
mkdir -p ftp_files
pids=()
"$PY" servidor_web.py & pids+=($!)
"$PY" servidor_correo_mock.py & pids+=($!)
"$PY" servidor_chat.py & pids+=($!)
"$PY" -m pyftpdlib -p 2121 -w -d ./ftp_files & pids+=($!)
trap 'kill "${pids[@]}" 2>/dev/null' EXIT INT TERM
(sleep 4; for url in http://localhost:8501 http://localhost:8080; do open "$url" 2>/dev/null || xdg-open "$url" 2>/dev/null; done) &
"$PY" -m streamlit run app.py
