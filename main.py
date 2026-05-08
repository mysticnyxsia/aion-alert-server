import os
import json
import html
import urllib.parse
import urllib.request
from typing import Set, Optional, Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()

clients: Set[WebSocket] = set()
ADMIN_KEY = os.getenv("ADMIN_KEY", "TRIUMPH_ADMIN")

# Google Cloud Translation API key stays ONLY on Render.
GOOGLE_TRANSLATE_API_KEY = os.getenv("GOOGLE_TRANSLATE_API_KEY", "").strip()
TRANSLATE_TARGET = os.getenv("TRANSLATE_TARGET", "zh-CN").strip() or "zh-CN"
TRANSLATE_SOURCE = os.getenv("TRANSLATE_SOURCE", "en").strip() or "en"

last_argo_update: Optional[Dict[str, Any]] = None
translation_cache: Dict[str, str] = {}


@app.get("/")
async def health():
    return {
        "status": "ok",
        "service": "Aion Alert Server",
        "clients": len(clients),
        "has_argo": last_argo_update is not None,
        "google_translate": bool(GOOGLE_TRANSLATE_API_KEY),
        "translate_target": TRANSLATE_TARGET,
    }


def translate_text_google(text: str) -> str:
    """Translate with Google Cloud Translation Basic v2.

    Fallback behavior: if the API key is missing or Google errors, return "".
    The overlay will then show the original English message.
    """
    clean = str(text or "").strip()
    if not clean or not GOOGLE_TRANSLATE_API_KEY:
        return ""

    cache_key = f"{TRANSLATE_SOURCE}->{TRANSLATE_TARGET}:{clean}"
    if cache_key in translation_cache:
        return translation_cache[cache_key]

    try:
        data = urllib.parse.urlencode({
            "q": clean,
            "source": TRANSLATE_SOURCE,
            "target": TRANSLATE_TARGET,
            "format": "text",
            "key": GOOGLE_TRANSLATE_API_KEY,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://translation.googleapis.com/language/translate/v2",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=4) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))

        translated = (
            payload.get("data", {})
            .get("translations", [{}])[0]
            .get("translatedText", "")
        )

        translated = html.unescape(str(translated)).strip()
        if translated:
            # Tiny cache; enough for repeated PvP calls, avoids unnecessary API calls.
            if len(translation_cache) > 500:
                translation_cache.clear()
            translation_cache[cache_key] = translated
        return translated

    except Exception as e:
        print("[translate error]", repr(e), flush=True)
        return ""


async def safe_send(ws: WebSocket, message: dict) -> bool:
    try:
        await ws.send_text(json.dumps(message, ensure_ascii=False))
        return True
    except Exception:
        return False


async def broadcast(message: dict):
    dead = []

    for ws in list(clients):
        ok = await safe_send(ws, message)
        if not ok:
            dead.append(ws)

    for ws in dead:
        clients.discard(ws)


async def websocket_handler(websocket: WebSocket):
    global last_argo_update

    await websocket.accept()
    clients.add(websocket)

    # Send last known Argo to every newly connected overlay.
    if last_argo_update is not None:
        await safe_send(websocket, last_argo_update)

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except Exception:
                continue

            msg_type = data.get("type")

            # Only RL/admin may push alerts or Argo sync.
            if msg_type in ("alert", "argo_update"):
                if data.get("admin_key") != ADMIN_KEY:
                    continue

            if msg_type == "alert":
                original = str(data.get("text", "ALERT")).strip() or "ALERT"
                translated_zh = translate_text_google(original)

                await broadcast({
                    "type": "alert",
                    "text": original,
                    "text_zh": translated_zh,
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
    except Exception as e:
        print("[websocket error]", repr(e), flush=True)
    finally:
        clients.discard(websocket)


@app.websocket("/ws")
async def websocket_ws(websocket: WebSocket):
    await websocket_handler(websocket)


@app.websocket("/")
async def websocket_root(websocket: WebSocket):
    await websocket_handler(websocket)
