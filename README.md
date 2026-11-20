#### Workspace initialization
```
python -m venv .venv
.\.venv\Scripts\activate
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```
#### Launching (dev mode)
`.\.venv\Scripts\python.exe -m uvicorn guitarcv_restapi.main:app --reload --host 127.0.0.1 --port 8000`