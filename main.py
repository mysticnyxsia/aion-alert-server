import os
import json
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()

clients: Set[WebSocket] = set()

ADMIN_KEY = os.getenv("ADMIN_KEY", "TRIUMPH_ADMIN")


@app.get("/")
async def health():
    return {"status": "ok", "service": "Aion Alert Server"}


async def broadcast(message: dict):
    dead = []

    text = json.dumps(message)

    for ws in list(clients):
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)

    for ws in dead:
        clients.discard(ws)


async def websocket_handler(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except Exception:
                continue

            msg_type = data.get("type")

            # Seuls les RL/admin peuvent envoyer
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
                await broadcast({
                    "type": "argo_update",
                    "death_time": data.get("death_time"),
                    "sender": data.get("sender", "Unknown"),
                })

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