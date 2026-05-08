import os
import json
import html
import urllib.parse
import urllib.request
from typing import Set, Optional, Dict, Any, Tuple

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query

app = FastAPI()

clients: Set[WebSocket] = set()
ADMIN_KEY = os.getenv("ADMIN_KEY", "TRIUMPH_ADMIN")

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


@app.get("/translate-test")
async def translate_test(q: str = Query("enemy north push mid")):
    translated, error = translate_text_google(q)
    return {
        "input": q,
        "translated": translated,
        "error": error,
        "google_translate": bool(GOOGLE_TRANSLATE_API_KEY),
        "target": TRANSLATE_TARGET,
    }


def translate_text_google(text: str) -> Tuple[str, str]:
    clean = str(text or "").strip()

    if not clean:
        return "", "empty text"

    if not GOOGLE_TRANSLATE_API_KEY:
        return "", "missing GOOGLE_TRANSLATE_API_KEY"

    cache_key = f"{TRANSLATE_SOURCE}->{TRANSLATE_TARGET}:{clean}"
    if cache_key in translation_cache:
        return translation_cache[cache_key], ""

    try:
        url = (
            "https://translation.googleapis.com/language/translate/v2"
            + "?key="
            + urllib.parse.quote(GOOGLE_TRANSLATE_API_KEY)
        )

        data = urllib.parse.urlencode({
            "q": clean,
            "source": TRANSLATE_SOURCE,
            "target": TRANSLATE_TARGET,
            "format": "text",
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))

        translated = (
            payload.get("data", {})
            .get("translations", [{}])[0]
            .get("translatedText", "")
        )

        translated = html.unescape(str(translated)).strip()

        if not translated:
            return "", "Google response missing translatedText"

        if len(translation_cache) > 500:
            translation_cache.clear()

        translation_cache[cache_key] = translated
        return translated, ""

    except Exception as e:
        err = repr(e)
        print("[translate error]", err, flush=True)
        return "", err


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

            if msg_type in ("alert", "argo_update"):
                if data.get("admin_key") != ADMIN_KEY:
                    continue

            if msg_type == "alert":
                original = str(data.get("text", "ALERT")).strip() or "ALERT"
                translated_zh, translate_error = translate_text_google(original)

                # Old users keep reading "text" in English.
                # Chinese users read "text_zh".
                await broadcast({
                    "type": "alert",
                    "text": original,
                    "text_zh": translated_zh,
                    "translated_text": translated_zh,
                    "translate_error": translate_error,
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
