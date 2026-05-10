import asyncio
import json
import os
import time

import websockets

CLIENTS = set()

async def broadcast(message: str):
    dead = []
    for client in list(CLIENTS):
        try:
            await client.send(message)
        except Exception:
            dead.append(client)
    for client in dead:
        CLIENTS.discard(client)

async def handler(websocket):
    CLIENTS.add(websocket)
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
            except Exception:
                continue

            msg_type = data.get("type")

            # Render server clock sync for AionWatcher clients.
            # The client uses this to correct bad Windows clocks.
            if msg_type == "time_sync_request":
                await websocket.send(json.dumps({
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

    finally:
        CLIENTS.discard(websocket)

async def main():
    port = int(os.environ.get("PORT", "10000"))
    async with websockets.serve(handler, "0.0.0.0", port, ping_interval=25, ping_timeout=10):
        print(f"Aion alert server running on port {port}", flush=True)
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
