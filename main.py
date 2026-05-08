import os
import json
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()

clients: Set[WebSocket] = set()
ADMIN_KEY = os.getenv("ADMIN_KEY", "TRIUMPH_ADMIN")

last_argo_update = None


@app.get("/")
async def health():
    return {"status": "ok", "service": "Aion Alert Server"}


async def broadcast(message: dict):
    text = json.dumps(message)
    dead = []

    for ws in list(clients):
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)

    for ws in dead:
        clients.discard(ws)


async def websocket_handler(websocket: WebSocket):
    global last_argo_update

    await websocket.accept()
    clients.add(websocket)

    # Envoie automatiquement le dernier Argo au user qui vient de se connecter
    if last_argo_update is not None:
        try:
            await websocket.send_text(json.dumps(last_argo_update))
        except Exception:
            pass

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except Exception:
                continue

            msg_type = data.get("type")

            if msg_type in ("alert", "argo_update"):
                if data.get("admin_key") != ADMIN_KEY:
                    continue

            if msg_type == "alert":
                await broadcast({
                    "type": "alert",
                    "text": data.get("text", "ALERT"),
                    "sender": data.get("sender", "Unknown"),
                })

            elif msg_type == "argo_update":
                last_argo_update = {
                    "type": "argo_update",
                    "death_time": data.get("death_time"),
                    "sender": data.get("sender", "Unknown"),
                }

                await broadcast(last_argo_update)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        clients.discard(websocket)


@app.websocket("/")
async def websocket_root(websocket: WebSocket):
    await websocket_handler(websocket)


@app.websocket("/ws")
async def websocket_ws(websocket: WebSocket):
    await websocket_handler(websocket)
