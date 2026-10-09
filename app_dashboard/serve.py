import logging
import secrets
import subprocess
import sys
import threading
import shutil
from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import uvicorn
import json


from modelo import get_meta, get_dashboard_state, get_last_update_date, reset_cache
from configuraciones.configuraciones import (
    STATIC_DIR, SERVER_HOST, SERVER_PORT, SERVER_RELOAD, MODELO_DEFAULTS, DATA_PATH,
    AUTH_USER_PRESENTACION, AUTH_PASS_PRESENTACION,
    AUTH_USER_DASHBOARD, AUTH_PASS_DASHBOARD,
)
from asistente_prompt import leer_prompt_config, guardar_nuevo_prompt, UpdatePromptRequest
from asistente import procesar_chat, MensajeChat
app = FastAPI(title="Dashboard Dinámico Urgencias")

from fastapi.requests import Request

logger = logging.getLogger(__name__)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Error no manejado")
    return Response(
        # No exponer el traceback al cliente: va al log del servidor.
        content="Error interno del servidor.",
        status_code=500,
        media_type="text/html"
    )

# --- Autenticación HTTP Basic (independiente por realm) ---
# Realms distintos => las credenciales de la presentación NO sirven para el
# dashboard y viceversa (funcionan de forma totalmente independiente).
_basic_presentacion = HTTPBasic(realm="Presentacion")
_basic_dashboard = HTTPBasic(realm="Dashboard")


def _verificar(credentials: HTTPBasicCredentials, usuario_ok: str, clave_ok: str, realm: str):
    # secrets.compare_digest evita ataques de temporización (timing attacks)
    usuario_valido = secrets.compare_digest(credentials.username, usuario_ok)
    clave_valida = secrets.compare_digest(credentials.password, clave_ok)
    if not (usuario_valido and clave_valida):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autorizado",
            headers={"WWW-Authenticate": f'Basic realm="{realm}"'},
        )


def auth_presentacion(credentials: HTTPBasicCredentials = Depends(_basic_presentacion)):
    _verificar(credentials, AUTH_USER_PRESENTACION, AUTH_PASS_PRESENTACION, "Presentacion")


def auth_dashboard(credentials: HTTPBasicCredentials = Depends(_basic_dashboard)):
    _verificar(credentials, AUTH_USER_DASHBOARD, AUTH_PASS_DASHBOARD, "Dashboard")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Servir estáticos (solo assets: JS/CSS). El HTML del dashboard NO vive aquí,
# se sirve desde la ruta protegida /dashboard para no exponerlo sin login.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
entregas_dir = os.path.join(PROJECT_ROOT, "entregas")
if os.path.exists(entregas_dir):
    app.mount("/entregas", StaticFiles(directory=entregas_dir), name="entregas")
# NOTA: se eliminó el montaje "/app_dashboard" que servía toda la carpeta del
# backend (exponía serve.py, configuraciones.py, etc. como código fuente).

# Carpeta privada (no montada) con las páginas HTML servidas tras autenticar.
PAGINAS_DIR = os.path.join(os.path.dirname(__file__), "paginas")

class TargetConfig(BaseModel):
    tipo: str = MODELO_DEFAULTS["tipo"]
    k: float = MODELO_DEFAULTS["k"]
    ventana: int = MODELO_DEFAULTS["ventana"]
    severidad: float = MODELO_DEFAULTS["severidad"]

class FeaturesConfig(BaseModel):
    clima: bool = MODELO_DEFAULTS["features"]["clima"]
    red: bool = MODELO_DEFAULTS["features"]["red"]
    viral: bool = MODELO_DEFAULTS["features"]["viral"]
    z_rob8: bool = MODELO_DEFAULTS["features"]["z_rob8"]

class FiltroConfig(BaseModel):
    comuna: str | None = None
    tipo: str | None = None
    centro: str | None = None

class SemanaRef(BaseModel):
    anio: int
    semana: int

class EvalRequest(BaseModel):
    target: TargetConfig
    features: FeaturesConfig
    filtro: FiltroConfig
    recall_objetivo: float = 83.0
    train_years: list[int] = [2023, 2024, 2025]
    test_years: list[int] = [2026]
    semanas_estimar: list[SemanaRef] = []

import datetime

def format_week_date(year, week, archivo_actualizado=None):
    try:
        d = datetime.date.fromisocalendar(int(year), int(week), 1)
        end = d + datetime.timedelta(days=6)
        base = f"Semana {week} ({d.strftime('%d/%m')} al {end.strftime('%d/%m')}) del {year}"
    except Exception:
        base = f"Semana {week} del {year}"
    if archivo_actualizado:
        try:
            dt = datetime.datetime.fromisoformat(archivo_actualizado)
            base += f" el {dt.strftime('%d-%m')} a las {dt.strftime('%H:%M')}hrs"
        except Exception:
            pass
    return base

@app.get("/", response_class=HTMLResponse, dependencies=[Depends(auth_presentacion)])
def index():
    path = os.path.join(PROJECT_ROOT, "presentacion_resultados_v2.html")
    try:
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
            
            try:
                upd = get_last_update_date()
                update_str = format_week_date(upd['anio'], upd['semana'], upd.get('archivo_actualizado'))
            except Exception:
                update_str = "No disponible"

            html = html.replace("{{ULTIMA_ACTUALIZACION}}", update_str)
            return Response(content=html, media_type="text/html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    except Exception as e:
        try:
            files = os.listdir(PROJECT_ROOT)
        except Exception:
            files = []
        return Response(
            content=f"Error 500 Interno.<br>Path intentado: {path}<br>PROJECT_ROOT: {PROJECT_ROOT}<br>__file__: {__file__}<br>Error real: {str(e)}<br>Archivos en raiz: {files}",
            status_code=500,
            media_type="text/html"
        )

@app.get("/dashboard", response_class=HTMLResponse, dependencies=[Depends(auth_dashboard)])
def dashboard():
    with open(os.path.join(PAGINAS_DIR, "index.html"), "r", encoding="utf-8") as f:
        html = f.read()
        try:
            upd = get_last_update_date()
            update_str = format_week_date(upd['anio'], upd['semana'], upd.get('archivo_actualizado'))
        except Exception:
            update_str = "No disponible"
        return html.replace("{{ULTIMA_ACTUALIZACION}}", update_str)

@app.get("/api/meta", dependencies=[Depends(auth_dashboard)])
def meta():
    return JSONResponse(content=get_meta())

@app.post("/api/evaluar", dependencies=[Depends(auth_dashboard)])
def evaluar(req: EvalRequest):
    estado = get_dashboard_state(
        req.target.dict(),
        req.features.dict(),
        req.filtro.dict(),
        req.recall_objetivo,
        req.train_years,
        req.test_years,
        [s.dict() for s in req.semanas_estimar]
    )
    return JSONResponse(content=estado)

@app.get("/api/chat/prompt", dependencies=[Depends(auth_dashboard)])
def get_prompt():
    estado = leer_prompt_config()
    return JSONResponse(content=estado.model_dump())

@app.post("/api/chat/prompt", dependencies=[Depends(auth_dashboard)])
def update_prompt(req: UpdatePromptRequest):
    estado = guardar_nuevo_prompt(req.nuevo_prompt)
    return JSONResponse(content=estado.model_dump())

class InferenciaRequest(BaseModel):
    historial: list[MensajeChat]

@app.post("/api/chat/inference", dependencies=[Depends(auth_dashboard)])
def chat_inference(req: InferenciaRequest):
    try:
        config = leer_prompt_config()
        prompt = config.prompt_actual
        respuesta = procesar_chat(req.historial, prompt)
        return JSONResponse(content={"respuesta": respuesta})
    except Exception as e:
        print(f"Error en inferencia: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Botón "Actualizar datos": corre la cadena ETL completa (descarga DEIS/FluNet →
# arma el panel → genera artifacts) y refresca el dashboard sin reiniciar el proceso. ---
_etl_lock = threading.Lock()

def _run_etl_step(cmd, cwd, nombre):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        detalle = (proc.stderr or proc.stdout or "(sin salida)")[-2000:]
        raise HTTPException(status_code=500, detail=f"Falló {nombre}: {detalle}")

@app.post("/api/actualizar_datos", dependencies=[Depends(auth_dashboard)])
def actualizar_datos():
    if not _etl_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Ya hay una actualización de datos en curso. Espera a que termine.")
    try:
        # Respaldo del panel servido, antes de sobrescribirlo (misma convención que
        # dataset_salud/historico/ ya usa el resto del proyecto).
        if os.path.exists(DATA_PATH):
            historico_dir = os.path.join(PROJECT_ROOT, "dataset_salud", "historico")
            os.makedirs(historico_dir, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(DATA_PATH, os.path.join(historico_dir, f"panel_dashboard_pre_refresh_{ts}.parquet"))

        _run_etl_step([sys.executable, os.path.join("src", "download_data.py")], PROJECT_ROOT, "download_data.py")
        _run_etl_step([sys.executable, os.path.join("src", "build_dataset.py")], PROJECT_ROOT, "build_dataset.py")
        _run_etl_step([sys.executable, "build_artifacts.py"], os.path.dirname(os.path.abspath(__file__)), "build_artifacts.py")

        # Los 3 pasos terminaron OK: recién ahora se invalida el caché en memoria del modelo.
        reset_cache()
        upd = get_last_update_date()
        texto = format_week_date(upd['anio'], upd['semana'], upd.get('archivo_actualizado'))
        return JSONResponse(content={"ok": True, "anio": upd['anio'], "semana": upd['semana'], "texto": texto})
    finally:
        _etl_lock.release()

# --- Sincronización de Presentación (WebSockets) ---
import json


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        # Estado compartido de la presentación. Se guarda en el servidor para
        # que quien se une reciba de inmediato la lámina y el over (modal) que
        # el presentador tiene en pantalla en ese momento.
        self.state = {"current_slide": 0, "active_modal": None}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        # Envía el estado actual SOLO al recién llegado (sincronización inicial).
        try:
            await websocket.send_text(json.dumps({
                "current_slide": self.state["current_slide"],
                "active_modal": self.state["active_modal"],
            }))
        except Exception:
            pass

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    def actualizar_estado(self, message: str):
        # Interpreta el mensaje del presentador y actualiza el estado guardado.
        try:
            data = json.loads(message)
        except Exception:
            return
        tipo = data.get("type")
        if tipo == "slide_changed" and "slide" in data:
            self.state["current_slide"] = data["slide"]
        elif tipo == "modal_opened" and data.get("id"):
            self.state["active_modal"] = data["id"]
        elif tipo == "modal_closed":
            # Se cierra el over solo si es el que estaba activo (o sin id).
            if not data.get("id") or data.get("id") == self.state["active_modal"]:
                self.state["active_modal"] = None

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            manager.actualizar_estado(data)
            await manager.broadcast(data)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

print(f"\n[INFO] Credenciales activas para la Presentación -> Usuario: '{AUTH_USER_PRESENTACION}' | Clave: '{AUTH_PASS_PRESENTACION}'")

if __name__ == "__main__":
    uvicorn.run("serve:app", host=SERVER_HOST, port=SERVER_PORT, reload=SERVER_RELOAD)
