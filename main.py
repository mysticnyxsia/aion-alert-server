import json
import time
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()
CLIENTS: Set[WebSocket] = set()


async def broadcast(message: str):
    dead = []
    for client in list(CLIENTS):
        try:
            await client.send_text(message)
        except Exception:
            dead.append(client)

    for client in dead:
        CLIENTS.discard(client)


@app.get("/")
async def health_check():
    return {"status": "ok", "service": "AionWatcher websocket server"}


@app.websocket("/")
async def websocket_root(websocket: WebSocket):
    await websocket.accept()
    CLIENTS.add(websocket)

    try:
        while True:
            message = await websocket.receive_text()

            try:
                data = json.loads(message)
            except Exception:
                continue

            msg_type = data.get("type")

            # Render server clock sync for AionWatcher clients.
            # Client uses this to correct bad Windows clocks.
            if msg_type == "time_sync_request":
                await websocket.send_text(json.dumps({
                    "type": "time_sync_response",
                    "client_ms": data.get("client_ms"),
                    "server_ms": int(time.time() * 1000)
                }))
                continue

            # Existing shared alerts.
            if msg_type == "alert":
                await broadcast(message)
                continue

            # Existing Argo timer sync.
            if msg_type == "argo_update":
                await broadcast(message)
                continue

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        CLIENTS.discard(websocket)
