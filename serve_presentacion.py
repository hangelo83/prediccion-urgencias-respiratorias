import json
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Servir archivos estáticos (imágenes de la carpeta entregas)
app.mount("/entregas", StaticFiles(directory="entregas"), name="entregas")

# Estado global de la presentación
current_state = {
    "current_slide": 0,
    "active_modal": None
}

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        # Al conectar, enviar estado inicial
        await websocket.send_json(current_state)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict, sender: WebSocket):
        for connection in self.active_connections:
            if connection != sender:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

manager = ConnectionManager()

@app.get("/")
async def get_presentation():
    return FileResponse("presentacion_resultados.html")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Actualizar memoria del servidor
            if message.get("type") == "slide_changed":
                current_state["current_slide"] = message.get("slide", 0)
            elif message.get("type") == "modal_opened":
                current_state["active_modal"] = message.get("id")
            elif message.get("type") == "modal_closed":
                # Validar que si cerramos el modal activo, se limpia el estado
                if current_state["active_modal"] == message.get("id"):
                    current_state["active_modal"] = None

            # Retransmitir al resto de los clientes
            await manager.broadcast(message, sender=websocket)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    # Ejecutar en puerto 8081 para no chocar con el dashboard (8080)
    uvicorn.run(app, host="0.0.0.0", port=8081)
