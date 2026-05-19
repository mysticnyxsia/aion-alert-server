import sys
import os
import json
import threading
import ctypes
import time
from ctypes import wintypes
from datetime import datetime, timedelta, timezone

try:
    import websocket
except Exception:
    websocket = None

try:
    import win32gui
    import win32con
    import win32process
except Exception:
    win32gui = None
    win32con = None
    win32process = None

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QEvent
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QPixmap, QCursor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QHBoxLayout,
    QVBoxLayout, QFrame, QDialog, QTabWidget, QCheckBox, QSpinBox,
    QComboBox, QColorDialog, QFormLayout, QGridLayout,
    QDialogButtonBox, QLayout, QSizePolicy, QMenu, QToolTip
)


class HotkeyCaptureButton(QPushButton):
    """Bouton qui capture la prochaine touche appuyée et affiche son nom."""

    _QT_KEY_MAP = {
        Qt.Key.Key_F1: "f1",   Qt.Key.Key_F2: "f2",   Qt.Key.Key_F3: "f3",
        Qt.Key.Key_F4: "f4",   Qt.Key.Key_F5: "f5",   Qt.Key.Key_F6: "f6",
        Qt.Key.Key_F7: "f7",   Qt.Key.Key_F8: "f8",   Qt.Key.Key_F9: "f9",
        Qt.Key.Key_F10: "f10", Qt.Key.Key_F11: "f11", Qt.Key.Key_F12: "f12",
        Qt.Key.Key_Insert: "insert",   Qt.Key.Key_Delete: "delete",
        Qt.Key.Key_Home: "home",       Qt.Key.Key_End: "end",
        Qt.Key.Key_PageUp: "pageup",   Qt.Key.Key_PageDown: "pagedown",
        Qt.Key.Key_Return: "enter",    Qt.Key.Key_Enter: "enter",
        Qt.Key.Key_Tab: "tab",         Qt.Key.Key_Escape: "escape",
        Qt.Key.Key_Backslash: "\\",    Qt.Key.Key_Slash: "/",
        Qt.Key.Key_QuoteLeft: "`",
    }

    def __init__(self, initial="", parent=None):
        super().__init__(parent)
        self._key_name = initial
        self._capturing = False
        self._update_text()
        self.clicked.connect(self._start_capture)

    def _update_text(self):
        if self._capturing:
            self.setText("⌨  Appuyez sur une touche...")
        elif self._key_name:
            self.setText(f"  {self._key_name}  —  cliquer pour changer")
        else:
            self.setText("  Cliquer pour assigner une touche")

    def _start_capture(self):
        self._capturing = True
        self._update_text()
        self.setFocus()

    _NUM_MAP = {
        Qt.Key.Key_0: "num0", Qt.Key.Key_1: "num1", Qt.Key.Key_2: "num2",
        Qt.Key.Key_3: "num3", Qt.Key.Key_4: "num4", Qt.Key.Key_5: "num5",
        Qt.Key.Key_6: "num6", Qt.Key.Key_7: "num7", Qt.Key.Key_8: "num8",
        Qt.Key.Key_9: "num9", Qt.Key.Key_Plus: "num+", Qt.Key.Key_Minus: "num-",
        Qt.Key.Key_Asterisk: "num*", Qt.Key.Key_Slash: "num/", Qt.Key.Key_Period: "num.",
        Qt.Key.Key_Return: "numenter", Qt.Key.Key_Enter: "numenter",
    }

    def keyPressEvent(self, event):
        if not self._capturing:
            super().keyPressEvent(event)
            return
        key = event.key()
        try:
            if event.modifiers() & Qt.KeyboardModifier.KeypadModifier:
                if key in self._NUM_MAP:
                    self._key_name = self._NUM_MAP[key]
                    self._capturing = False
                    self._update_text()
                    event.accept()
                    return
        except Exception:
            pass

        # Ignorer les touches modificatrices seules
        if key in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt,
                   Qt.Key.Key_Meta, Qt.Key.Key_AltGr):
            return
        name = self._QT_KEY_MAP.get(key)
        if not name:
            text = event.text().strip().lower()
            if text and text.isprintable():
                name = text
        if name:
            self._key_name = name
        self._capturing = False
        self._update_text()
        event.accept()

    def get_key_name(self):
        return self._key_name


def _base_dir():
    """Returns the folder next to the exe (or script during dev)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR   = _base_dir()
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
COMPLETION_STATE_FILE = os.path.join(BASE_DIR, "completion_state.json")
REMOTE_CONFIG_FILE = os.path.join(BASE_DIR, "remote_config.json")
REMOTE_CONFIG_CACHE_FILE = os.path.join(BASE_DIR, "remote_config.cache.json")
ICONS_DIR  = os.path.join(BASE_DIR, "icons")
SOUNDS_DIR = os.path.join(BASE_DIR, "sounds")

# Empêche de lancer plusieurs AionWatcher en même temps.
# Très important avec pythonw : sinon plusieurs overlays invisibles peuvent rester ouverts.
_SINGLE_INSTANCE_MUTEX = None

def ensure_single_instance():
    global _SINGLE_INSTANCE_MUTEX
    try:
        kernel32 = ctypes.windll.kernel32
        mutex_name = "Global\\AionWatcher_Nyxsia_Single_Instance"
        _SINGLE_INSTANCE_MUTEX = kernel32.CreateMutexW(None, False, mutex_name)
        last_error = kernel32.GetLastError()
        # 183 = ERROR_ALREADY_EXISTS
        if last_error == 183:
            sys.exit(0)
    except Exception:
        pass


RIFT_HOURS_TW = [2, 5, 8, 11, 14, 17, 20, 23]  # Taiwan server time (UTC+8)
ELEMENTS = ["shugo", "rift", "battlefield", "boss", "siege", "post_siege", "nahma", "daily"]

NAMES = {
    "shugo": "Shugo",
    "rift": "Rift",
    "battlefield": "Battlefield",
    "boss": "Next Boss",
    "siege": "Siege",
    "post_siege": "Post-Siege Bosses",
    "nahma": "Nahma",
    "daily": "Daily"
}

FIXED_ICONS = {
    "shugo": "shugo.png",
    "rift": "rift.png",
    "battlefield": "battlefield.png",
    "boss": "boss.png",
    "siege": "siege.png",
    "post_siege": "post_siege.png",
    "nahma": "nahma.png",
    "daily": "daily.png",
    "unknown": "unknown.png"
}

DEFAULT_CONFIG = {
    "appearance": {
        "icon_color": "#e9b1ef",
        "title_color": "#ffffff",
        "timer_color": "#c8a2ff",
        "font_family": "Segoe UI",
        "font_size": 11,
        "bold": False,
        "icon_size": 18,
        "alpha": 1.0,
        "background_color": "#000000",
        "background_opacity": 0,
        "x": 30,
        "y": 30,
        "layout": "line",
        "show_controls": True,
        "scale": 100
    },
    "labels": {
        "shugo": "Shugo",
        "rift": "Rift",
        "battlefield": "Battlefield",
        "boss": "Boss",
        "siege": "Siege",
        "post_siege": "Post-Siege Bosses",
        "nahma": "Nahma",
        "daily": "Daily"
    },
    "display": {
        "shugo": True,
        "rift": True,
        "battlefield": True,
        "boss": True,
        "siege": True,
        "post_siege": True,
        "nahma": True,
        "daily": True
    },
    "alarms": {
        "enabled": True,
        "beep": "asterisk",
        "events": {
            "shugo": {"enabled": False, "minutes": "", "repeat_enabled": False, "repeat_count": 1, "repeat_every_sec": 5},
            "rift": {"enabled": False, "minutes": "", "repeat_enabled": False, "repeat_count": 1, "repeat_every_sec": 5},
            "battlefield": {"enabled": False, "minutes": "", "repeat_enabled": False, "repeat_count": 1, "repeat_every_sec": 5},
            "boss": {"enabled": False, "minutes": "", "repeat_enabled": False, "repeat_count": 1, "repeat_every_sec": 5},
            "siege": {"enabled": False, "minutes": "", "repeat_enabled": False, "repeat_count": 1, "repeat_every_sec": 5},
            "post_siege": {"enabled": False, "minutes": "", "repeat_enabled": False, "repeat_count": 1, "repeat_every_sec": 5},
            "nahma": {"enabled": False, "minutes": "", "repeat_enabled": False, "repeat_count": 1, "repeat_every_sec": 5},
            "daily": {"enabled": False, "minutes": "", "repeat_enabled": False, "repeat_count": 1, "repeat_every_sec": 5},
            "argo": {"enabled": False, "minutes": "", "repeat_enabled": False, "repeat_count": 1, "repeat_every_sec": 5}
        }
    },
    "order": ELEMENTS,
    "argo_config": {
        "death_time": None,
        "server_open": ""
    },
    "remote_config": {
        "enabled": True,
        "url": "",
        "refresh_minutes": 10,
        "use_local_file": True
    },
    "completion": {
        "enabled": True,
        "show_progress_in_overlay": True,
        "dailies": [
            "Daily quests",
            "Daily instances",
            "Daily shop / claims"
        ],
        "corridors": [
            "Corridor 1",
            "Corridor 2",
            "Corridor 3"
        ],
        "battlefields": [
            "Battlefield 11:00 TW",
            "Battlefield 20:00 TW"
        ]
    },
    "shared_alerts": {
        "enabled": True,
        "server_url": "wss://aion-alert-server.onrender.com",
        "name": "Nyxsia",
        "admin_key": "TRIUMPH_ADMIN",
        "popup_x": 450,
        "popup_y": 120,
        "box_x": 40,
        "box_y": 420,
        "alert_font_family": "Segoe UI Black",
        "alert_font_size": 36,
        "alert_bold": True,
        "alert_color": "#ff961e",
        "alert_outline_color": "#000000",
        "alert_duration_sec": 8,
        "box_bg": "rgba(20,20,20,185)",
        "box_text": "#ffffff",
        "box_border": "#ffffff",
        "hotkey": ""
    }
}


TW_TZ = timezone(timedelta(hours=8))


# Internet time correction: timers use a real online UTC clock when available,
# so a PC clock that is a few seconds late/early does not shift the overlay.
TIME_OFFSET = timedelta(seconds=0)
TIME_SYNC_OK = False
TIME_SYNC_LAST = None


def sync_internet_time():
    """Sync against HTTP Date headers and store the offset vs this PC clock.
    If it fails, the overlay falls back to the normal PC clock.
    """
    global TIME_OFFSET, TIME_SYNC_OK, TIME_SYNC_LAST
    try:
        import urllib.request
        from email.utils import parsedate_to_datetime

        urls = (
            "https://www.google.com/generate_204",
            "https://www.cloudflare.com/",
            "https://www.microsoft.com/",
        )
        for url in urls:
            try:
                before = datetime.now(timezone.utc)
                req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "AionWatcher"})
                with urllib.request.urlopen(req, timeout=4) as response:
                    date_header = response.headers.get("Date")
                after = datetime.now(timezone.utc)
                if not date_header:
                    continue
                internet_utc = parsedate_to_datetime(date_header)
                if internet_utc.tzinfo is None:
                    internet_utc = internet_utc.replace(tzinfo=timezone.utc)
                # Approximate local comparison time with the request midpoint.
                local_midpoint = before + (after - before) / 2
                TIME_OFFSET = internet_utc.astimezone(timezone.utc) - local_midpoint
                TIME_SYNC_OK = True
                TIME_SYNC_LAST = datetime.now(timezone.utc)
                return True
            except Exception:
                continue
    except Exception:
        pass

    # If we already had a successful sync earlier, keep the last known offset
    # instead of suddenly falling back to the wrong PC clock because of a
    # temporary network issue.
    if not TIME_SYNC_OK:
        TIME_OFFSET = timedelta(seconds=0)
        TIME_SYNC_LAST = None
    return False


def true_utc_now():
    return datetime.now(timezone.utc) + TIME_OFFSET


def true_local_now():
    return true_utc_now().astimezone().replace(tzinfo=None)


def true_tw_now():
    return true_utc_now().astimezone(TW_TZ)

# ── Event schedule expressed in Taiwan server time (UTC+8) ──────────────────
# France (UTC+2 summer) = TW − 6 h. These TW constants are the source of truth;
# conversion to local machine time is done automatically by the helpers below.

BATTLEFIELD_WINDOWS_TW = [(11, 0, 14, 0), (20, 0, 22, 0)]  # (open_h, open_m, close_h, close_m) TW
SIEGE_WEEKDAYS_TW  = [2, 5]   # Wednesday=2, Saturday=5 in TW calendar
SIEGE_TW_HOUR      = 22       # 16:00 France UTC+2 -> 22:00 TW UTC+8
SIEGE_TW_MINUTE    = 0
POST_SIEGE_TW_HOUR = 22
POST_SIEGE_TW_MIN  = 30       # 16:30 France -> 22:30 TW
NAHMA_WEEKDAYS_TW  = [4, 6]   # Friday=4, Sunday=6 in TW calendar (16:00 France -> 22:00 TW)
NAHMA_TW_HOUR      = 22       # 16:00 France -> 22:00 TW
NAHMA_TW_MINUTE    = 0
DAILY_RESET_TW_HOUR = 5       # 23:00 France currently (CEST UTC+2) -> 05:00 Taiwan server time
DAILY_RESET_TW_MINUTE = 0
# ────────────────────────────────────────────────────────────────────────────


def tw_next_daily(tw_hour, tw_minute):
    """Next occurrence of HH:MM Taiwan server time, returned as local naive datetime."""
    now_tw = true_tw_now()
    target_tw = now_tw.replace(hour=tw_hour, minute=tw_minute, second=0, microsecond=0)
    if target_tw <= now_tw:
        target_tw += timedelta(days=1)
    return target_tw.astimezone().replace(tzinfo=None)


def tw_next_hourly_minute(tw_minute):
    """Next occurrence of every-hour event at :MM Taiwan server time, returned as local naive datetime."""
    now_tw = true_tw_now()
    target_tw = now_tw.replace(minute=tw_minute, second=0, microsecond=0)
    if target_tw <= now_tw:
        target_tw += timedelta(hours=1)
    return target_tw.astimezone().replace(tzinfo=None)


def tw_next_weekday(weekdays_tw, tw_hour, tw_minute=0):
    """Next occurrence of weekday+time in TW timezone, returned as local naive datetime."""
    now_tw = true_tw_now()
    best = None
    for weekday in weekdays_tw:
        days_ahead = (weekday - now_tw.weekday()) % 7
        target_tw = now_tw.replace(
            hour=tw_hour, minute=tw_minute, second=0, microsecond=0
        ) + timedelta(days=days_ahead)
        if target_tw <= now_tw:
            target_tw += timedelta(days=7)
        if best is None or target_tw < best:
            best = target_tw
    return best.astimezone().replace(tzinfo=None)


def tw_current_weekday(weekdays_tw, tw_hour, tw_minute=0):
    """If current TW weekday is in weekdays_tw, return the event time as local naive. Else None."""
    now_tw = true_tw_now()
    if now_tw.weekday() not in weekdays_tw:
        return None
    target_tw = now_tw.replace(hour=tw_hour, minute=tw_minute, second=0, microsecond=0)
    return target_tw.astimezone().replace(tzinfo=None)


def fmt_tw(local_naive_dt):
    """Format a local naive datetime as Taiwan server time string (HH:MM TW).
    Uses astimezone() which correctly infers the local UTC offset for that
    specific date/time (handles DST transitions properly).
    """
    try:
        # Python 3.6+: calling astimezone() on a naive dt assumes local time
        # and applies the correct UTC offset for THAT moment (DST-aware).
        tw = local_naive_dt.astimezone(TW_TZ)
        return tw.strftime("%d/%m %H:%M TW")
    except Exception:
        return "?"


def parse_shared_dt(value):
    """Parse shared Argo datetime safely across time zones.

    If the string contains timezone info, convert it to this PC's local naive time.
    If it is an old local/naive value, keep backward compatibility.
    """
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is not None:
            return dt.astimezone().replace(tzinfo=None)
        return dt
    except Exception:
        return None


def deep_merge(default, loaded):
    result = dict(default)
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def migrate_config(config):
    config = deep_merge(DEFAULT_CONFIG, config)

    for key in ELEMENTS:
        config["labels"].setdefault(key, DEFAULT_CONFIG["labels"][key])
        config["display"].setdefault(key, True)

    if not isinstance(config.get("order"), list):
        config["order"] = ELEMENTS.copy()
    for key in ELEMENTS:
        if key not in config["order"]:
            config["order"].append(key)
    config["order"] = [x for x in config["order"] if x in ELEMENTS]

    config["alarms"].setdefault("events", {})
    for key in ELEMENTS:
        config["alarms"]["events"][key] = deep_merge(
            DEFAULT_CONFIG["alarms"]["events"].get(key, DEFAULT_CONFIG["alarms"]["events"]["nahma"]),
            config["alarms"]["events"].get(key, {})
        )

    # Argo is not an overlay element, but it can have alarms.
    config["alarms"]["events"]["argo"] = deep_merge(
        DEFAULT_CONFIG["alarms"]["events"]["argo"],
        config["alarms"]["events"].get("argo", {})
    )

    if "argo_config" not in config:
        config["argo_config"] = {"death_time": None, "server_open": ""}
    config["argo_config"].setdefault("death_time", None)
    config["argo_config"].setdefault("server_open", "")

    config["remote_config"] = deep_merge(
        DEFAULT_CONFIG.get("remote_config", {}),
        config.get("remote_config", {})
    )

    return config



def _read_json_file(path):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else None
    except Exception:
        return None
    return None


def _write_json_file(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def _as_int_list(value, fallback):
    if not isinstance(value, list):
        return fallback
    result = []
    for item in value:
        try:
            result.append(int(item))
        except Exception:
            pass
    return result or fallback


def _as_time_windows(value, fallback):
    """Accepts [[open_h, open_m, close_h, close_m], ...]."""
    if not isinstance(value, list):
        return fallback
    windows = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 4:
            continue
        try:
            sh, sm, eh, em = [int(x) for x in item]
            if 0 <= sh <= 23 and 0 <= eh <= 23 and 0 <= sm <= 59 and 0 <= em <= 59:
                windows.append((sh, sm, eh, em))
        except Exception:
            continue
    return windows or fallback


def _as_hour_minute(obj, fallback_hour, fallback_minute):
    if not isinstance(obj, dict):
        return fallback_hour, fallback_minute
    try:
        hour = int(obj.get("hour_tw", obj.get("hour", fallback_hour)))
        minute = int(obj.get("minute_tw", obj.get("minute", fallback_minute)))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except Exception:
        pass
    return fallback_hour, fallback_minute


def fetch_remote_config(config):
    """Load optional remote_config.json without overwriting local user settings.

    Priority:
    1. AION_WATCHER_REMOTE_CONFIG_URL environment variable
    2. config.json -> remote_config.url
    3. local remote_config.json next to the exe/script
    4. last downloaded remote_config.cache.json
    """
    rc_settings = config.get("remote_config", {})
    if not rc_settings.get("enabled", True):
        return None

    url = os.getenv("AION_WATCHER_REMOTE_CONFIG_URL", "").strip() or str(rc_settings.get("url", "")).strip()

    if url:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "AionWatcher"})
            with urllib.request.urlopen(req, timeout=6) as response:
                raw = response.read().decode("utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                _write_json_file(REMOTE_CONFIG_CACHE_FILE, data)
                return data
        except Exception:
            cached = _read_json_file(REMOTE_CONFIG_CACHE_FILE)
            if cached:
                return cached

    if rc_settings.get("use_local_file", True):
        local = _read_json_file(REMOTE_CONFIG_FILE)
        if local:
            return local

    cached = _read_json_file(REMOTE_CONFIG_CACHE_FILE)
    return cached


def apply_remote_config(config):
    """Apply online schedule/event overrides to this running app.

    Supported remote_config.json example:
    {
      "version": "1.0.1",
      "labels": {"siege": "Siege", "daily": "Daily"},
      "display": {"nahma": true},
      "schedule": {
        "rift_hours_tw": [2,5,8,11,14,17,20,23],
        "battlefield_windows_tw": [[11,0,14,0], [20,0,22,0]],
        "siege": {"weekdays_tw": [2,5], "hour_tw": 22, "minute_tw": 0},
        "post_siege": {"weekdays_tw": [2,5], "hour_tw": 22, "minute_tw": 30},
        "nahma": {"weekdays_tw": [4,6], "hour_tw": 22, "minute_tw": 0},
        "daily_reset": {"hour_tw": 5, "minute_tw": 0}
      }
    }
    """
    data = fetch_remote_config(config)
    if not isinstance(data, dict):
        return False

    global RIFT_HOURS_TW, BATTLEFIELD_WINDOWS_TW
    global SIEGE_WEEKDAYS_TW, SIEGE_TW_HOUR, SIEGE_TW_MINUTE
    global POST_SIEGE_TW_HOUR, POST_SIEGE_TW_MIN
    global NAHMA_WEEKDAYS_TW, NAHMA_TW_HOUR, NAHMA_TW_MINUTE
    global DAILY_RESET_TW_HOUR, DAILY_RESET_TW_MINUTE

    schedule = data.get("schedule", data)
    if not isinstance(schedule, dict):
        schedule = {}

    RIFT_HOURS_TW = _as_int_list(schedule.get("rift_hours_tw", schedule.get("rifts_tw")), RIFT_HOURS_TW)
    BATTLEFIELD_WINDOWS_TW = _as_time_windows(
        schedule.get("battlefield_windows_tw", schedule.get("battlefields_tw")),
        BATTLEFIELD_WINDOWS_TW
    )

    siege = schedule.get("siege", {})
    if isinstance(siege, dict):
        SIEGE_WEEKDAYS_TW = _as_int_list(siege.get("weekdays_tw", siege.get("weekdays")), SIEGE_WEEKDAYS_TW)
        SIEGE_TW_HOUR, SIEGE_TW_MINUTE = _as_hour_minute(siege, SIEGE_TW_HOUR, SIEGE_TW_MINUTE)

    post_siege = schedule.get("post_siege", {})
    if isinstance(post_siege, dict):
        POST_SIEGE_TW_HOUR, POST_SIEGE_TW_MIN = _as_hour_minute(post_siege, POST_SIEGE_TW_HOUR, POST_SIEGE_TW_MIN)

    nahma = schedule.get("nahma", {})
    if isinstance(nahma, dict):
        NAHMA_WEEKDAYS_TW = _as_int_list(nahma.get("weekdays_tw", nahma.get("weekdays")), NAHMA_WEEKDAYS_TW)
        NAHMA_TW_HOUR, NAHMA_TW_MINUTE = _as_hour_minute(nahma, NAHMA_TW_HOUR, NAHMA_TW_MINUTE)

    daily_reset = schedule.get("daily_reset", schedule.get("daily", {}))
    if isinstance(daily_reset, dict):
        DAILY_RESET_TW_HOUR, DAILY_RESET_TW_MINUTE = _as_hour_minute(daily_reset, DAILY_RESET_TW_HOUR, DAILY_RESET_TW_MINUTE)

    labels = data.get("labels")
    if isinstance(labels, dict):
        config.setdefault("labels", {})
        for key, value in labels.items():
            if key in ELEMENTS and isinstance(value, str) and value.strip():
                config["labels"][key] = value.strip()

    display = data.get("display")
    if isinstance(display, dict):
        config.setdefault("display", {})
        for key, value in display.items():
            if key in ELEMENTS:
                config["display"][key] = bool(value)

    alarm_defaults = data.get("alarm_defaults")
    if isinstance(alarm_defaults, dict):
        config.setdefault("alarms", {}).setdefault("events", {})
        for key, value in alarm_defaults.items():
            if key in ELEMENTS + ["argo"] and isinstance(value, dict):
                current = config["alarms"]["events"].setdefault(key, {})
                current.update(value)

    return True

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return migrate_config(json.load(f))
    except Exception:
        backup = CONFIG_FILE + ".broken"
        try:
            os.replace(CONFIG_FILE, backup)
        except Exception:
            pass
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def next_hour(now):
    return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def next_daily_time(now, hour, minute=0):
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def next_weekday_time(now, weekdays, hour, minute=0):
    best = None
    for weekday in weekdays:
        days_ahead = (weekday - now.weekday()) % 7
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
        if target <= now:
            target += timedelta(days=7)
        if best is None or target < best:
            best = target
    return best


def current_weekday_time(now, weekdays, hour, minute=0):
    if now.weekday() not in weekdays:
        return None
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def short_countdown(target, now):
    seconds = max(0, int((target - now).total_seconds()))
    days = seconds // 86400
    seconds %= 86400
    hours = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60

    if days:
        return f"{days}d{hours:02}h{minutes:02}m"
    if hours:
        return f"{hours}h{minutes:02}m{seconds:02}s"
    if minutes:
        return f"{minutes}m{seconds:02}s"
    return f"{seconds}s"


def short_countdown_approx(target, now):
    """Countdown rounded to nearest minute, no seconds, prefixed with ~."""
    total_sec = max(0, int((target - now).total_seconds()))
    minutes = (total_sec + 30) // 60
    days = minutes // 1440
    minutes %= 1440
    hours = minutes // 60
    minutes %= 60
    if days:
        return f"~{days}d{hours:02}h{minutes:02}m"
    if hours:
        return f"~{hours}h{minutes:02}m"
    return f"~{minutes}m"


def parse_alarm_minutes(text):
    result = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
            if value >= 0:
                result.append(value)
        except ValueError:
            pass
    return sorted(set(result), reverse=True)


def list_wav_sounds():
    """Return list of .wav filenames found in SOUNDS_DIR, sorted alphabetically."""
    if not os.path.isdir(SOUNDS_DIR):
        return []
    return sorted(
        f for f in os.listdir(SOUNDS_DIR)
        if f.lower().endswith(".wav")
    )



def load_completion_state():
    try:
        if os.path.exists(COMPLETION_STATE_FILE):
            with open(COMPLETION_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def save_completion_state(state):
    try:
        with open(COMPLETION_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def completion_day_key(now_tw=None):
    """Daily reset key based on Taiwan server reset, not PC date."""
    now_tw = now_tw or true_tw_now()
    reset_today = now_tw.replace(hour=DAILY_RESET_TW_HOUR, minute=DAILY_RESET_TW_MINUTE, second=0, microsecond=0)
    if now_tw < reset_today:
        now_tw = now_tw - timedelta(days=1)
    return now_tw.strftime("%Y-%m-%d")




def completion_week_key(now_tw=None):
    """Weekly reset key based on Taiwan server reset week, not PC date."""
    now_tw = now_tw or true_tw_now()
    reset_today = now_tw.replace(hour=DAILY_RESET_TW_HOUR, minute=DAILY_RESET_TW_MINUTE, second=0, microsecond=0)
    if now_tw < reset_today:
        now_tw = now_tw - timedelta(days=1)
    # ISO week, Monday-based, after the TW daily reset boundary.
    return now_tw.strftime("%G-W%V")

def completion_siege_key(now_tw=None):
    """Corridors reset every siege cycle. Key = latest siege start in TW time."""
    now_tw = now_tw or true_tw_now()
    candidates = []
    for back in range(0, 8):
        d = now_tw - timedelta(days=back)
        if d.weekday() in SIEGE_WEEKDAYS_TW:
            siege = d.replace(hour=SIEGE_TW_HOUR, minute=SIEGE_TW_MINUTE, second=0, microsecond=0)
            if siege <= now_tw:
                candidates.append(siege)
    if not candidates:
        # Fallback: should not happen, but keeps state stable.
        candidates.append(now_tw.replace(hour=SIEGE_TW_HOUR, minute=SIEGE_TW_MINUTE, second=0, microsecond=0))
    latest = max(candidates)
    return latest.strftime("%Y-%m-%d_%H-%M_TW")


def _completion_bucket(state, bucket, key, items):
    root = state.setdefault(bucket, {})
    if root.get("key") != key:
        root.clear()
        root["key"] = key
        root["done"] = {}
    done = root.setdefault("done", {})
    # Remove old/renamed entries to avoid phantom progress.
    for old in list(done.keys()):
        if old not in items:
            done.pop(old, None)
    for item in items:
        done.setdefault(item, False)
    return done

def play_beep_by_name(name):
    """Play a .wav file from SOUNDS_DIR. Falls back to system beep if missing."""
    try:
        import winsound
        if name and name.lower().endswith(".wav"):
            path = os.path.join(SOUNDS_DIR, name)
            if os.path.isfile(path):
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                return
        # Fallback if file not found
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass


class BossHoverFilter(QObject):
    """Event filter that shows a manual tooltip on transparent overlay windows."""
    def __init__(self, watcher):
        super().__init__(watcher)
        self.watcher = watcher

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Enter:
            text = self.watcher.boss_tooltip(true_local_now())
            if text:
                QToolTip.showText(QCursor.pos(), text)
        elif event.type() == QEvent.Type.Leave:
            QToolTip.hideText()
        return False


class Bridge(QObject):
    alert_received = pyqtSignal(str)
    argo_update_received = pyqtSignal(str)
    hotkey_pressed = pyqtSignal()


class TextAlert(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(None)
        self.config = config
        self.text = ""
        self.drag_pos = None
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(1000, 130)

    def show_text(self, text):
        self.text = text
        shared = self.config.get("shared_alerts", {})
        w = 1200
        h = max(110, int(shared.get("alert_font_size", 36)) * 3)
        self.resize(w, h)
        # Center horizontally on screen, use saved y position clamped to screen
        try:
            screen = QApplication.primaryScreen()
            saved_x = int(shared.get("popup_x", 450))
            saved_y = int(shared.get("popup_y", 120))
            for s in QApplication.screens():
                if s.geometry().contains(saved_x, saved_y):
                    screen = s
                    break
            geo = screen.availableGeometry()
            x = geo.left() + (geo.width() - w) // 2   # always centered horizontally
            y = max(geo.top(), min(saved_y, geo.bottom() - h))
        except Exception:
            x = 0
            y = 120
        self.move(x, y)
        self.show()
        self.raise_()
        self.update()
        duration = int(shared.get("alert_duration_sec", 8))
        self.hide_timer.start(max(1, duration) * 1000)

    def paintEvent(self, event):
        if not self.text:
            return

        shared = self.config.get("shared_alerts", {})
        family = shared.get("alert_font_family", "Segoe UI Black")
        size = int(shared.get("alert_font_size", 36))
        bold = bool(shared.get("alert_bold", True))
        color = QColor(shared.get("alert_color", "#ff961e"))
        outline = QColor(shared.get("alert_outline_color", "#000000"))

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        font = QFont(family, size)
        font.setBold(bold)
        painter.setFont(font)

        rect = self.rect()

        offsets = [(-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2), (-2, 2), (2, -2)]
        outline.setAlpha(230)
        painter.setPen(QPen(outline, 2))
        for dx, dy in offsets:
            painter.drawText(rect.adjusted(dx, dy, dx, dy), Qt.AlignmentFlag.AlignCenter, self.text)

        painter.setPen(QPen(color, 1))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            pos = event.globalPosition().toPoint() - self.drag_pos
            self.move(pos)
            self.config.setdefault("shared_alerts", {})
            self.config["shared_alerts"]["popup_x"] = pos.x()
            self.config["shared_alerts"]["popup_y"] = pos.y()
            save_config(self.config)
            event.accept()


class AlertInputBox(QWidget):
    def __init__(self, app_window):
        super().__init__(None)
        self.app_window = app_window
        self.config = app_window.config
        self.drag_pos = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.handle = QLabel("✥")
        self.handle.setFixedWidth(22)
        self.handle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Alert...")
        self.entry.returnPressed.connect(self.send)


        self.close_btn = QPushButton("×")
        self.close_btn.setFixedWidth(24)
        self.close_btn.clicked.connect(self.hide)

        layout = QHBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)
        layout.addWidget(self.handle)
        layout.addWidget(self.entry)
        layout.addWidget(self.close_btn)
        self.setLayout(layout)

        self.apply_style()
        shared = self.config.get("shared_alerts", {})
        x = int(shared.get("box_x", 40))
        y = int(shared.get("box_y", 420))
        self.resize(285, 38)
        # Clamp position to visible screen area
        try:
            screen = QApplication.primaryScreen()
            for s in QApplication.screens():
                if s.geometry().contains(x, y):
                    screen = s
                    break
            geo = screen.availableGeometry()
            x = max(geo.left(), min(x, geo.right()  - 285))
            y = max(geo.top(),  min(y, geo.bottom() - 38))
        except Exception:
            pass
        self.move(x, y)

    def apply_style(self):
        shared = self.config.get("shared_alerts", {})
        app = self.config.get("appearance", {})
        bg_color = QColor(app.get("background_color", "#000000"))
        bg_opacity = max(0, min(100, int(app.get("background_opacity", 0))))
        bg_alpha = int(bg_opacity * 2.55)
        bg = f"rgba({bg_color.red()},{bg_color.green()},{bg_color.blue()},{bg_alpha})"
        text = "#ffffff"
        border = "#ffffff"
        accent = app.get("icon_color", shared.get("alert_color", "#ff961e"))

        self.handle.setStyleSheet(f"color: {accent}; background: transparent; font-size: 17px;")
        common = f"""
            background: {bg};
            color: {text};
            border: 1px solid {border};
            border-radius: 7px;
            padding: 2px 4px;
            font-size: 13px;
        """
        self.entry.setStyleSheet("QLineEdit {" + common + "}")
        self.close_btn.setStyleSheet("QPushButton {" + common + "} QPushButton:hover { border: 1px solid " + accent + "; color: " + accent + "; }")

    def send(self):
        text = self.entry.text().strip()
        if text:
            self.app_window.send_shared_alert(text)
            self.entry.clear()

        # Important: the box stays visible, but it stops capturing keyboard input.
        self.entry.clearFocus()
        self.setFocus()

        # Let Qt finish processing Enter, then give focus back to Aion.
        QTimer.singleShot(0, self.app_window.restore_game_focus)
        QTimer.singleShot(80, self.app_window.restore_game_focus)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.handle.underMouse():
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            pos = event.globalPosition().toPoint() - self.drag_pos
            self.move(pos)
            self.config.setdefault("shared_alerts", {})
            self.config["shared_alerts"]["box_x"] = pos.x()
            self.config["shared_alerts"]["box_y"] = pos.y()
            save_config(self.config)
            event.accept()


class AionWatcherQt(QWidget):
    def __init__(self):
        super().__init__(None)
        self.config = load_config()
        apply_remote_config(self.config)
        self.ws = None
        self.ws_connected = False
        self.ws_lock = threading.Lock()
        self.last_game_hwnd = None
        self.played_alarms = set()
        self.icon_cache = {}
        self.completion_state = load_completion_state()

        self._hotkey_handle = None

        self._boss_hover_filter = BossHoverFilter(self)
        self.bridge = Bridge()
        self.bridge.alert_received.connect(self.show_shared_alert)
        self.bridge.argo_update_received.connect(self.apply_remote_argo_update)
        self.bridge.hotkey_pressed.connect(self._on_hotkey_pressed)

        self.alert_popup = TextAlert(self.config)
        self.alert_box = None

        # Anti-doublon alertes : évite d'afficher deux fois la même alerte
        # si Render la renvoie plusieurs fois, ou si deux connexions existent.
        self._last_shared_alert_text = ""
        self._last_shared_alert_time = None

        self.setWindowTitle("AionWatcher Qt")
        self.setObjectName("AionRoot")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.main_layout = QHBoxLayout()
        self.main_layout.setContentsMargins(5, 0, 5, 0)
        self.main_layout.setSpacing(2)
        self.main_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        self.setLayout(self.main_layout)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        # Left buttons frame (settings btn in line mode only)
        self.left_buttons = QFrame()
        self.left_buttons.setStyleSheet("background: transparent;")
        self.left_buttons_layout = QHBoxLayout()
        self.left_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.left_buttons_layout.setSpacing(2)
        self.left_buttons.setLayout(self.left_buttons_layout)
        self.main_layout.addWidget(self.left_buttons, 0, Qt.AlignmentFlag.AlignVCenter)

        self.drag = QLabel("✥")
        self.drag.setCursor(Qt.CursorShape.SizeAllCursor)
        self.drag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drag.setContentsMargins(0, 0, 0, 0)
        self.drag.setFixedWidth(14)
        self.main_layout.addWidget(self.drag, 0, Qt.AlignmentFlag.AlignCenter)

        self.content = QFrame()
        self.content.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout()
        self.content_layout_mode = "column"
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self.content.setLayout(self.content_layout)
        self.main_layout.addWidget(self.content, 0, Qt.AlignmentFlag.AlignVCenter)

        self.side_buttons = QFrame()
        self.side_buttons.setStyleSheet("background: transparent;")
        self.side_buttons_layout = QVBoxLayout()
        self.side_buttons_layout_mode = "column"
        self.side_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.side_buttons_layout.setSpacing(2)
        self.side_buttons.setLayout(self.side_buttons_layout)
        self.main_layout.addWidget(self.side_buttons, 0, Qt.AlignmentFlag.AlignVCenter)

        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.clicked.connect(self.close_all)

        self.mail_btn = QPushButton("✉")
        self.mail_btn.setFixedSize(22, 22)
        self.mail_btn.clicked.connect(self.show_alert_box)


        self.settings_btn = QPushButton("✦")
        self.settings_btn.setFixedSize(22, 22)
        self.settings_btn.clicked.connect(self.open_settings)

        self.arrange_side_buttons()

        self.rows = {}
        self.drag_pos = None

        sync_internet_time()

        self.apply_appearance()
        self.move(int(self.config["appearance"].get("x", 30)), int(self.config["appearance"].get("y", 30)))

        # Fallback HTTP time sync if Render is temporarily unavailable.
        self.time_sync_timer = QTimer(self)
        self.time_sync_timer.timeout.connect(sync_internet_time)
        self.time_sync_timer.start(15 * 60 * 1000)

        # Optional online config refresh: schedules/events can be changed without rebuilding the exe.
        self.remote_config_timer = QTimer(self)
        self.remote_config_timer.timeout.connect(self.refresh_remote_config)
        try:
            refresh_minutes = int(self.config.get("remote_config", {}).get("refresh_minutes", 10))
        except Exception:
            refresh_minutes = 10
        self.remote_config_timer.start(max(1, refresh_minutes) * 60 * 1000)

        # Main sync source: Render websocket server time.
        self.render_time_sync_timer = QTimer(self)
        self.render_time_sync_timer.timeout.connect(self.request_render_time_sync)
        self.render_time_sync_timer.start(5 * 60 * 1000)

        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self.update_timers)
        self.tick_timer.start(1000)

        self.focus_tracker_timer = QTimer(self)
        self.focus_tracker_timer.timeout.connect(self.track_game_focus)
        self.focus_tracker_timer.start(350)

        self.start_websocket_thread()
        QTimer.singleShot(500, self.register_hotkey)

        if self.config.get("shared_alerts", {}).get("admin_key"):
            self.show_alert_box()

    def refresh_remote_config(self):
        if apply_remote_config(self.config):
            self.rebuild_layout()
            self.update_timers()

    def showEvent(self, event):
        """After the first show, clamp position to fit within the current screen."""
        super().showEvent(event)
        if not getattr(self, "_initial_clamp_done", False):
            self._initial_clamp_done = True
            x = int(self.config["appearance"].get("x", 30))
            y = int(self.config["appearance"].get("y", 30))
            # 150ms delay ensures Qt has finished rendering and self.width()/height() are correct
            QTimer.singleShot(150, lambda: self._move_within_screen(x, y))

    def paintEvent(self, event):
        # Fond custom compact : on dessine uniquement autour du contenu visible.
        # Ça évite le gros bandeau vertical si Qt garde une ancienne hauteur de fenêtre.
        app = self.config.get("appearance", {})
        opacity = int(app.get("background_opacity", 0))
        if opacity <= 0:
            return

        color = QColor(app.get("background_color", "#000000"))
        color.setAlpha(max(0, min(255, int(opacity * 2.55))))

        mode = self.current_layout_mode() if hasattr(self, "current_layout_mode") else "line"
        if mode == "line":
            rects = []
            for w in (getattr(self, "left_buttons", None), getattr(self, "drag", None), getattr(self, "content", None), getattr(self, "side_buttons", None)):
                if w is not None and w.isVisible():
                    rects.append(w.geometry())
            if rects:
                bg_rect = rects[0]
                for r in rects[1:]:
                    bg_rect = bg_rect.united(r)
                # padding vertical minimal : c'est ici que le haut/bas est contrôlé.
                bg_rect = bg_rect.adjusted(-2, -2, 2, 2)
            else:
                bg_rect = self.rect().adjusted(0, 0, -1, -1)
            radius = 3
        else:
            bg_rect = self.rect().adjusted(0, 0, -1, -1)
            radius = 4

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(bg_rect, radius, radius)

    # Completion tracker
    def completion_items(self, bucket):
        comp = self.config.setdefault("completion", DEFAULT_CONFIG["completion"].copy())
        defaults = DEFAULT_CONFIG["completion"].get(bucket, [])
        items = comp.get(bucket, defaults)
        if not isinstance(items, list):
            items = defaults
        return [str(x).strip() for x in items if str(x).strip()]

    def completion_key_for_bucket(self, bucket):
        now_tw = true_tw_now()
        if bucket == "corridors":
            return completion_siege_key(now_tw)
        if bucket == "battlefields":
            return completion_week_key(now_tw)
        return completion_day_key(now_tw)

    def completion_done_map(self, bucket):
        items = self.completion_items(bucket)
        key = self.completion_key_for_bucket(bucket)
        done = _completion_bucket(self.completion_state, bucket, key, items)
        save_completion_state(self.completion_state)
        return done

    def completion_progress(self, bucket):
        items = self.completion_items(bucket)
        if not items:
            return ""
        done = self.completion_done_map(bucket)
        count = sum(1 for item in items if bool(done.get(item)))
        return f"{count}/{len(items)}"

    def completion_suffix(self, bucket):
        comp = self.config.get("completion", {})
        if not comp.get("enabled", True) or not comp.get("show_progress_in_overlay", True):
            return ""
        progress = self.completion_progress(bucket)
        return f" ✓{progress}" if progress else ""

    def set_completion_item(self, bucket, item, checked):
        done = self.completion_done_map(bucket)
        done[item] = bool(checked)
        save_completion_state(self.completion_state)
        try:
            self.update_timers()
        except Exception:
            pass

    def reset_completion_bucket(self, bucket):
        done = self.completion_done_map(bucket)
        for item in list(done.keys()):
            done[item] = False
        save_completion_state(self.completion_state)
        try:
            self.update_timers()
        except Exception:
            pass


    def simple_completion_done(self, name):
        simple = self.completion_state.setdefault("simple", {})
        now_tw = true_tw_now()
        if name == "corridors":
            key = completion_siege_key(now_tw)
        elif name == "battlefields":
            key = completion_week_key(now_tw)
        else:
            key = completion_day_key(now_tw)
        data = simple.get(name, {})
        return isinstance(data, dict) and data.get("key") == key and bool(data.get("done"))

    def open_completion_dialog(self):
        dlg = CompletionDialog(self)
        dlg.exec()

    # Time calculations
    def label_text(self, key):
        return self.config["labels"].get(key, DEFAULT_CONFIG["labels"][key])

    def next_rift_time(self, now):
        # now unused but kept for API compatibility
        return min(tw_next_daily(h, 0) for h in RIFT_HOURS_TW)

    def next_battlefield_time(self, now):
        return min(tw_next_daily(h, m) for (h, m, _, _) in BATTLEFIELD_WINDOWS_TW)

    def next_siege_time(self, now):
        return tw_next_weekday(SIEGE_WEEKDAYS_TW, SIEGE_TW_HOUR, SIEGE_TW_MINUTE)

    def next_post_siege_time(self, now):
        return tw_next_weekday(SIEGE_WEEKDAYS_TW, POST_SIEGE_TW_HOUR, POST_SIEGE_TW_MIN)

    def nahma_time(self, now):
        return tw_next_weekday(NAHMA_WEEKDAYS_TW, NAHMA_TW_HOUR, NAHMA_TW_MINUTE)

    def daily_time(self, now):
        return tw_next_daily(DAILY_RESET_TW_HOUR, DAILY_RESET_TW_MINUTE)

    def shugo_segment(self, now):
        # Shugo opens every hour at :00 — timezone-independent (hourly in any TZ)
        start = now.replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(minutes=3)
        if start <= now < end:
            return self.label_text("shugo"), f"OPEN {short_countdown(end, now)}", None
        return self.label_text("shugo"), short_countdown(next_hour(now), now), None

    def rift_segment(self, now):
        now_tw = true_tw_now()
        for h in RIFT_HOURS_TW:
            start_tw = now_tw.replace(hour=h, minute=0, second=0, microsecond=0)
            end_tw = start_tw + timedelta(minutes=10)
            if start_tw <= now_tw < end_tw:
                end_local = end_tw.astimezone().replace(tzinfo=None)
                return self.label_text("rift"), f"OPEN {short_countdown(end_local, now)}", None
        return self.label_text("rift"), short_countdown(self.next_rift_time(now), now), None

    def battlefield_segment(self, now):
        now_tw = true_tw_now()
        for (sh, sm, eh, em) in BATTLEFIELD_WINDOWS_TW:
            start_tw = now_tw.replace(hour=sh, minute=sm, second=0, microsecond=0)
            end_tw   = now_tw.replace(hour=eh, minute=em, second=0, microsecond=0)
            if start_tw <= now_tw < end_tw:
                end_local = end_tw.astimezone().replace(tzinfo=None)
                return self.label_text("battlefield"), f"OPEN {short_countdown(end_local, now)}", None
        return self.label_text("battlefield"), f"{short_countdown(self.next_battlefield_time(now), now)}", None

    def siege_segment(self, now):
        today = tw_current_weekday(SIEGE_WEEKDAYS_TW, SIEGE_TW_HOUR, SIEGE_TW_MINUTE)
        if today:
            prep = today - timedelta(minutes=10)
            end  = today + timedelta(minutes=30)
            if prep <= now < today:
                return self.label_text("siege"), f"PREP {short_countdown(today, now)}", None
            if today <= now < end:
                return self.label_text("siege"), f"NOW", None
        return self.label_text("siege"), f"{short_countdown(self.next_siege_time(now), now)}", None

    def post_siege_segment(self, now):
        today = tw_current_weekday(SIEGE_WEEKDAYS_TW, POST_SIEGE_TW_HOUR, POST_SIEGE_TW_MIN)
        if today:
            end = today + timedelta(minutes=30)
            if today <= now < end:
                return self.label_text("post_siege"), "NOW", None
        return self.label_text("post_siege"), short_countdown(self.next_post_siege_time(now), now), None

    def nahma_segment(self, now):
        return self.label_text("nahma"), short_countdown(self.nahma_time(now), now), None

    def daily_segment(self, now):
        return self.label_text("daily"), f"{short_countdown(self.daily_time(now), now)}", None

    def argo_next_spawn(self, now):
        """Returns the next Argo spawn as (source_str, local_datetime), or (None, None).
        death_time always has priority: server_open is only used when death_time is unknown."""
        argo = self.config.get("argo_config", {})

        # Priority 1: 12h after last known death
        death_str = argo.get("death_time")
        if death_str:
            try:
                death_time = parse_shared_dt(death_str)
                if death_time is None:
                    raise ValueError("Invalid Argo death_time")
                respawn = death_time + timedelta(hours=12)
                if respawn > now:
                    return "reset", respawn
            except Exception:
                pass
            # death_time is set but timer expired → Argo is UP, no future spawn known
            return None, None

        # Priority 2 (fallback): stored server open datetime (UTC ISO since last fix)
        server_open_str = (argo.get("server_open") or "").strip()
        if server_open_str:
            try:
                t = parse_shared_dt(server_open_str)  # handles both UTC-aware and old naive
                if t is not None and t > now:
                    return "server open", t
            except Exception:
                pass

        return None, None

    def _flush_argo_alarms(self):
        self.played_alarms = {k for k in self.played_alarms if not k.startswith("argo:")}

    def apply_remote_argo_update(self, death_time):
        """Apply an Argo timer received from the shared websocket server."""
        self.config.setdefault("argo_config", {})
        death_time = None if death_time in ("", "None", "null") else death_time

        if death_time:
            try:
                # Validate ISO date before saving it.
                if parse_shared_dt(str(death_time)) is None:
                    raise ValueError("Invalid Argo death_time")
                self.config["argo_config"]["death_time"] = str(death_time)
            except Exception:
                return
        else:
            self.config["argo_config"]["death_time"] = None

        save_config(self.config)
        self._flush_argo_alarms()
        try:
            self.update_timers()
        except Exception:
            pass

    def send_argo_update(self, death_time):
        """Send Argo timer update to everyone. Requires admin_key/RL config."""
        shared = self.config.get("shared_alerts", {})
        if not shared.get("admin_key"):
            return False

        payload = {
            "type": "argo_update",
            "death_time": death_time,
            "sender": shared.get("name", "Unknown"),
            "admin_key": shared.get("admin_key", "")
        }

        sent = False
        try:
            with self.ws_lock:
                if self.ws:
                    self.ws.send(json.dumps(payload))
                    sent = True
        except Exception:
            self.ws_connected = False

        return sent

    def mark_argo_dead(self):
        death_time = true_utc_now().isoformat()

        # Apply locally immediately, then share globally.
        self.apply_remote_argo_update(death_time)
        self.send_argo_update(death_time)

    def clear_argo_timer(self):
        # Apply locally immediately, then share globally.
        self.apply_remote_argo_update(None)
        self.send_argo_update(None)

    def _argo_context_menu(self, global_pos):
        menu = QMenu(self)

        is_rl = bool(self.config.get("shared_alerts", {}).get("admin_key"))
        kill_action = menu.addAction("💀  Argo killed  →  sync 12h respawn")
        reset_action = menu.addAction("✕  Clear Argo timer  →  sync")
        if not is_rl:
            kill_action.setEnabled(False)
            reset_action.setEnabled(False)
            menu.addSeparator()
            info_action = menu.addAction("Read only: only RL/admin can sync Argo")
            info_action.setEnabled(False)

        result = menu.exec(global_pos)
        if result == kill_action and is_rl:
            self.mark_argo_dead()
        elif result == reset_action and is_rl:
            self.clear_argo_timer()

    def boss_target(self, now):
        return self._boss_candidates(now)[0]

    def _boss_candidates(self, now):
        bosses = [("Kaïra", next_hour(now), "unknown")]
        argo_spawn = self.argo_next_spawn(now)
        if argo_spawn and argo_spawn[1]:
            bosses.append(("Argo", argo_spawn[1], None))
        bosses.sort(key=lambda b: b[1])
        return bosses

    def _fmt_boss(self, name, time, now):
        """Format a boss countdown: approx (no seconds) for Argo, precise for others."""
        if name == "Argo":
            return f"{name} {short_countdown_approx(time, now)}"
        return f"{name} {short_countdown(time, now)}"

    def boss_segment(self, now):
        # Argo is never shown in the main overlay — always in the hover tooltip.
        bosses = [b for b in self._boss_candidates(now) if b[0] != "Argo"]
        if not bosses:
            return self.label_text("boss"), "—", None
        earliest = bosses[0][1]
        shown = [b for b in bosses if abs((b[1] - earliest).total_seconds()) <= 120]

        parts = []
        extra_icon = None
        for name, time, status in shown:
            parts.append(self._fmt_boss(name, time, now))
            if status == "unknown":
                extra_icon = FIXED_ICONS["unknown"]

        return self.label_text("boss"), " / ".join(parts), extra_icon

    def boss_tooltip(self, now):
        """Hover tooltip: Argo timer (always) + any secondary Kaira bosses."""
        all_bosses = self._boss_candidates(now)

        # Kaira bosses not shown in main overlay
        kaira = [b for b in all_bosses if b[0] != "Argo"]
        earliest_kaira = kaira[0][1] if kaira else None
        secondary_kaira = [b for b in kaira if earliest_kaira and abs((b[1] - earliest_kaira).total_seconds()) > 120]

        # Argo always goes to tooltip if a timer is active
        argo = [b for b in all_bosses if b[0] == "Argo"]

        secondary = secondary_kaira + argo
        if not secondary:
            return ""
        lines = [self._fmt_boss(name, time, now) for name, time, _ in secondary]
        return "Next:  " + "   |   ".join(lines)

    def get_segment_data(self, now=None):
        if now is None:
            now = true_local_now()
        funcs = {
            "shugo": self.shugo_segment,
            "rift": self.rift_segment,
            "battlefield": self.battlefield_segment,
            "boss": self.boss_segment,
            "siege": self.siege_segment,
            "post_siege": self.post_siege_segment,
            "nahma": self.nahma_segment,
            
            "daily": self.daily_segment
        }
        data = {}
        for key in self.config.get("order", ELEMENTS):
            if self.config["display"].get(key, True):
                title, timer, extra_icon = funcs[key](now)
                data[key] = (FIXED_ICONS[key], title, timer, extra_icon)
        return data

    def alarm_targets(self, now):
        _, boss_time, _ = self.boss_target(now)
        argo_target = self.argo_next_spawn(now)[1]
        return {
            "shugo": next_hour(now),
            "rift": self.next_rift_time(now),
            "battlefield": self.next_battlefield_time(now),
            "boss": boss_time,
            "siege": self.next_siege_time(now),
            "post_siege": self.next_post_siege_time(now),
            "nahma": self.nahma_time(now),
            "daily": self.daily_time(now),
            "argo": argo_target
        }

    # UI
    def icon_pixmap(self, filename, size=None):
        app = self.config["appearance"]
        size = size or self._scaled_icon_size()
        color = QColor(app.get("icon_color", "#e9b1ef"))
        key = (filename, size, color.name())
        if key in self.icon_cache:
            return self.icon_cache[key]

        path = os.path.join(ICONS_DIR, filename)
        if not os.path.exists(path):
            return QPixmap()

        pix = QPixmap(path)
        if pix.isNull():
            return QPixmap()

        # Harmonise la taille visuelle des logos : certains fichiers ont beaucoup
        # de marge transparente, donc on croppe le contenu réel avant de scaler.
        try:
            img = pix.toImage()
            min_x, min_y = img.width(), img.height()
            max_x, max_y = -1, -1
            for y in range(img.height()):
                for x in range(img.width()):
                    if img.pixelColor(x, y).alpha() > 8:
                        if x < min_x: min_x = x
                        if y < min_y: min_y = y
                        if x > max_x: max_x = x
                        if y > max_y: max_y = y
            if max_x >= min_x and max_y >= min_y:
                pix = pix.copy(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)
        except Exception:
            pass

        pix = pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

        tinted = QPixmap(pix.size())
        tinted.fill(Qt.GlobalColor.transparent)
        painter = QPainter(tinted)
        painter.drawPixmap(0, 0, pix)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), color)
        painter.end()
        self.icon_cache[key] = tinted
        return tinted

    def qt_font(self):
        app = self.config["appearance"]
        font = QFont(app.get("font_family", "Segoe UI"), self._scaled_font_size())
        font.setBold(bool(app.get("bold", False)))
        return font

    def clear_content(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.rows = {}

    def current_layout_mode(self):
        mode = self.config.get("appearance", {}).get("layout", "line")
        if mode == "single_line":
            mode = "line"
        return mode if mode in ("column", "line") else "line"

    def arrange_side_buttons(self):
        mode = self.current_layout_mode()
        wanted = "line" if mode == "line" else "column"
        if getattr(self, "side_buttons_layout_mode", None) != wanted:
            old = self.side_buttons.layout()
            if old is not None:
                while old.count():
                    item = old.takeAt(0)
                    if item.widget():
                        item.widget().setParent(None)
                QWidget().setLayout(old)
            if wanted == "line":
                self.side_buttons_layout = QHBoxLayout()
                self.side_buttons_layout.setSpacing(2)
            else:
                self.side_buttons_layout = QVBoxLayout()
                self.side_buttons_layout.setSpacing(2)
            self.side_buttons_layout_mode = wanted
            self.side_buttons_layout.setContentsMargins(0, 0, 0, 0)
            self.side_buttons.setLayout(self.side_buttons_layout)

        while self.side_buttons_layout.count():
            item = self.side_buttons_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        while self.left_buttons_layout.count():
            item = self.left_buttons_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        if mode == "line":
            # Settings button goes to the LEFT of the overlay in line mode
            self.left_buttons_layout.addWidget(self.settings_btn, 0, Qt.AlignmentFlag.AlignCenter)
            self.left_buttons.show()
            for btn in (self.close_btn, self.mail_btn):
                self.side_buttons_layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignCenter)
        else:
            # Column mode: settings button stays in side_buttons on the right
            self.left_buttons.hide()
            for btn in (self.close_btn, self.mail_btn, self.settings_btn):
                self.side_buttons_layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignCenter)

    def ensure_content_layout(self):
        mode = self.current_layout_mode()
        if getattr(self, "content_layout_mode", None) == mode:
            return
        self.clear_content()
        old = self.content.layout()
        if old is not None:
            QWidget().setLayout(old)
        if mode == "line":
            self.content_layout = QHBoxLayout()
            self.content_layout.setSpacing(5)
        else:
            self.content_layout = QVBoxLayout()
            # En colonne : chaque event reste groupé titre+timer,
            # mais on laisse un petit espace entre deux events.
            self.content_layout.setSpacing(5)
        self.content_layout_mode = mode
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content.setLayout(self.content_layout)

    def rebuild_layout(self):
        self.ensure_content_layout()
        self.arrange_side_buttons()
        self.clear_content()
        visible = [k for k in self.config.get("order", ELEMENTS) if self.config["display"].get(k, True)]
        mode = self.current_layout_mode()

        for key in visible:
            row = QFrame()
            row.setStyleSheet("background: transparent; border: none;")
            layout = QHBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            # Ligne = ultra compact. Colonne = icône séparée un peu du bloc texte.
            layout.setSpacing(4 if mode == "line" else 4)
            row.setLayout(layout)

            icon = QLabel()
            icon_size = self._scaled_icon_size()
            if mode == "line":
                # Mode ligne : icône réglable, mais compacte par défaut.
                line_icon_size = max(12, icon_size)
                icon.setFixedSize(line_icon_size, line_icon_size)
            else:
                icon.setFixedWidth(icon_size + 1)
            icon.setContentsMargins(0, 0, 0, 0)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignCenter)

            extra_icon = QLabel()
            extra_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            extra_icon.setContentsMargins(0, 0, 0, 0)
            if mode == "line":
                combined = QLabel("")
                combined.setFont(self.qt_font())
                combined.setTextFormat(Qt.TextFormat.RichText)
                combined.setContentsMargins(0, 0, 0, 0)
                combined.setAlignment(Qt.AlignmentFlag.AlignVCenter)
                combined.setStyleSheet("background: transparent; border: none; padding: 0px; margin: 0px;")
                combined.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                line_text_h = max(14, self._scaled_font_size() + 6)
                combined.setMinimumHeight(line_text_h)
                combined.setMaximumHeight(line_text_h)
                row_h = max(line_icon_size, line_text_h, 18)
                row.setMinimumHeight(row_h)
                row.setMaximumHeight(row_h)
                layout.addWidget(combined, 0, Qt.AlignmentFlag.AlignVCenter)
                layout.addWidget(extra_icon, 0, Qt.AlignmentFlag.AlignCenter)
                self.content_layout.addWidget(row, 0, Qt.AlignmentFlag.AlignVCenter)
                self.rows[key] = {"icon": icon, "combined": combined, "extra_icon": extra_icon, "mode": "line", "frame": row}
                if key == "boss":
                    row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                    row.customContextMenuRequested.connect(
                        lambda pos, r=row: self._argo_context_menu(r.mapToGlobal(pos))
                    )
                    for _w in (row, icon, combined, extra_icon):
                        _w.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
                        _w.installEventFilter(self._boss_hover_filter)
            else:
                text_col = QVBoxLayout()
                text_col.setContentsMargins(0, 0, 0, 0)
                text_col.setSpacing(0)
                title = QLabel("")
                timer = QLabel("")
                title.setFont(self.qt_font())
                timer.setFont(self.qt_font())
                title.setStyleSheet(f"color: {self.config['appearance'].get('title_color', '#ffffff')}; background: transparent; border: none; padding: 0px; margin: 0px;")
                timer.setStyleSheet(f"color: {self.config['appearance'].get('timer_color', '#c8a2ff')}; background: transparent; border: none; padding: 0px; margin: 0px;")
                title.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                timer.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                timer_row = QHBoxLayout()
                timer_row.setContentsMargins(0, 0, 0, 0)
                timer_row.setSpacing(3)
                timer_row.addWidget(timer)
                timer_row.addWidget(extra_icon)
                text_col.addWidget(title)
                text_col.addLayout(timer_row)
                layout.addLayout(text_col)
                self.content_layout.addWidget(row)
                self.rows[key] = {"icon": icon, "title": title, "timer": timer, "extra_icon": extra_icon, "mode": "column", "frame": row}
                if key == "boss":
                    row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                    row.customContextMenuRequested.connect(
                        lambda pos, r=row: self._argo_context_menu(r.mapToGlobal(pos))
                    )
                    for _w in (row, icon, title, timer, extra_icon):
                        _w.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
                        _w.installEventFilter(self._boss_hover_filter)

        self.adjustSize()
        if mode == "line":
            self.force_compact_line_geometry()
        self.update_timers()


    def force_compact_line_geometry(self):
        if self.current_layout_mode() != "line":
            return
        self.setMinimumSize(0, 0)
        self.content.setMinimumSize(0, 0)
        self.side_buttons.setMinimumSize(0, 0)
        self.drag.setMinimumSize(0, 0)
        self.adjustSize()
        hint = self.sizeHint()
        new_w, new_h = hint.width(), hint.height()
        # Only call setFixedSize if size actually changed — avoids right-edge flicker
        # on every tick when countdown text width fluctuates by a few pixels.
        if new_w != self.width() or new_h != self.height():
            self.setFixedSize(new_w, new_h)

    def overlay_background_rgba(self):
        app = self.config.get("appearance", {})
        color = QColor(app.get("background_color", "#000000"))
        opacity = int(app.get("background_opacity", 0))
        opacity = max(0, min(100, opacity))
        alpha = int(opacity * 2.55)
        return f"rgba({color.red()},{color.green()},{color.blue()},{alpha})"

    def _move_within_screen(self, x, y):
        """Move the overlay to (x, y) but clamp it so it stays fully visible
        on the current screen geometry. Handles multi-monitor setups too."""
        try:
            screen = QApplication.primaryScreen()
            for s in QApplication.screens():
                if s.geometry().contains(x, y):
                    screen = s
                    break
            geo = screen.availableGeometry()
            # Use actual rendered size (reliable after 150ms delay in showEvent)
            w = max(self.width(), 10)
            h = max(self.height(), 10)
            # Clamp so the window stays inside the available screen area.
            # If the overlay is wider than the screen, anchor it to the left edge.
            clamped_x = max(geo.left(), min(x, geo.right() - w))
            clamped_y = max(geo.top(),  min(y, geo.bottom() - h))
            self.move(clamped_x, clamped_y)
            # Persist the corrected position so next launch starts correctly
            self.config["appearance"]["x"] = clamped_x
            self.config["appearance"]["y"] = clamped_y
            save_config(self.config)
        except Exception:
            self.move(x, y)

    def _scaled_font_size(self):
        base = int(self.config["appearance"].get("font_size", 11))
        scale = max(50, min(150, int(self.config["appearance"].get("scale", 100))))
        return max(6, round(base * scale / 100))

    def _scaled_icon_size(self):
        base = int(self.config["appearance"].get("icon_size", 35))
        scale = max(50, min(150, int(self.config["appearance"].get("scale", 100))))
        # Visuellement, les PNG recadrés paraissaient plus grands qu'avant.
        # On garde le réglage utilisateur, mais on applique un léger facteur
        # d'harmonisation pour retrouver une taille plus proche de l'ancienne.
        return max(8, round(base * scale / 100 * 0.88))

    def apply_appearance(self):
        app = self.config["appearance"]
        self.setWindowOpacity(float(app.get("alpha", 1.0)))
        font = self.qt_font()
        accent = app.get("icon_color", "#e9b1ef")
        mode = self.current_layout_mode()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.setStyleSheet("QWidget#AionRoot { background: transparent; border: none; }")
        if mode == "line":
            # Mode ligne : compact et centré verticalement.
            self.main_layout.setContentsMargins(5, 5, 5, 5)
            self.main_layout.setSpacing(2)
            self.left_buttons.setContentsMargins(0, 0, 0, 0)
            self.content.setContentsMargins(0, 0, 0, 0)
            self.side_buttons.setContentsMargins(0, 0, 0, 0)
            self.left_buttons_layout.setContentsMargins(0, 0, 0, 0)
            self.left_buttons_layout.setSpacing(2)
            self.content_layout.setContentsMargins(0, 0, 0, 0)
            self.content_layout.setSpacing(5)
            self.side_buttons_layout.setContentsMargins(0, 0, 0, 0)
            self.side_buttons_layout.setSpacing(2)
        else:
            # Mode colonne : un peu plus lisible, mais toujours sans gros contour.
            self.main_layout.setContentsMargins(2, 2, 2, 2)
            self.main_layout.setSpacing(2)
            self.content_layout.setContentsMargins(0, 0, 0, 0)
            self.content_layout.setSpacing(5)
            self.side_buttons_layout.setContentsMargins(0, 0, 0, 0)
            self.side_buttons_layout.setSpacing(1)

        # Boutons système harmonisés avec la poignée : même boîte, même centre visuel.
        btn_px = 18 if mode == "line" else 22
        btn_font_px = 14 if mode == "line" else 15
        base_btn = f"""
            QPushButton {{
                color: {accent};
                background: transparent;
                border: none;
                border-radius: 3px;
                padding: 0px;
                margin: 0px;
                font-size: {btn_font_px}px;
                font-family: "Segoe UI Symbol";
                min-width: {btn_px}px;
                min-height: {btn_px}px;
                max-width: {btn_px}px;
                max-height: {btn_px}px;
            }}
            QPushButton:hover {{
                background: rgba(40,40,40,90);
            }}
        """
        drag_font = QFont("Segoe UI Symbol", 10 if mode == "line" else btn_font_px)
        drag_font.setBold(False)
        self.drag.setFont(drag_font)
        if mode == "line":
            # Même boîte que les boutons pour l'alignement, mais symbole plus petit via la police.
            self.drag.setFixedSize(btn_px, btn_px)
        else:
            self.drag.setFixedSize(btn_px, 26)
        self.drag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drag.setStyleSheet(f"color: {accent}; background: transparent; padding: 0px; margin: 0px;")
        self.mail_btn.setStyleSheet(base_btn)
        self.settings_btn.setStyleSheet(base_btn)
        self.close_btn.setStyleSheet(base_btn)
        for _btn in (self.close_btn, self.mail_btn, self.settings_btn):
            _btn.setFixedSize(btn_px, btn_px)

        self.icon_cache.clear()
        self.update()
        self.rebuild_layout()
        if self.alert_box:
            self.alert_box.apply_style()

    def update_timers(self):
        now = true_local_now()
        data = self.get_segment_data(now)
        app = self.config["appearance"]
        title_color = app.get("title_color", "#ffffff")
        timer_color = app.get("timer_color", "#c8a2ff")
        icon_size   = max(12, self._scaled_icon_size())
        extra_size  = max(14, self._scaled_font_size() + 5)
        for key, row in self.rows.items():
            icon_file, title, timer, extra_icon_file = data.get(key, ("", "", "", None))
            mode = row.get("mode")

            # Certains PNG remplissent presque toute leur boîte après le crop
            # automatique et paraissent donc plus gros que les autres.
            # On corrige seulement leur taille visuelle, sans changer le layout.
            visual_icon_size = icon_size
            icon_box_size = icon_size
            if icon_file == FIXED_ICONS.get("shugo"):
                # Le cadeau remplit beaucoup sa boîte : il paraît trop gros sinon.
                visual_icon_size = max(10, round(icon_size * 0.82))
            elif icon_file == FIXED_ICONS.get("siege"):
                # La couronne paraît légèrement basse/petite à côté des autres.
                visual_icon_size = max(10, round(icon_size * 0.96))
            elif icon_file in (FIXED_ICONS.get("post_siege"), FIXED_ICONS.get("nahma"), "__none__"):
                # Icônes très fines : un peu plus grandes pour rester lisibles.
                visual_icon_size = max(10, round(icon_size * 1.10))
                icon_box_size = max(icon_size, visual_icon_size)
            elif icon_file == FIXED_ICONS.get("daily"):
                # Refresh daily : un peu réduit pour matcher les icônes fines du pack.
                visual_icon_size = max(10, round(icon_size * 0.82))

            if mode == "line":
                row["icon"].setFixedSize(icon_box_size, icon_size)
                row["icon"].setPixmap(self.icon_pixmap(icon_file, visual_icon_size))
                row["combined"].setText(
                    f'<span style="color:{title_color};">{title}</span> '
                    f'<span style="color:{timer_color};">{timer}</span>'
                )
            else:
                row["icon"].setPixmap(self.icon_pixmap(icon_file, visual_icon_size))
                row["title"].setText(title)
                row["timer"].setText(timer)

            if extra_icon_file:
                visual_extra_size = extra_size
                if extra_icon_file == FIXED_ICONS.get("unknown"):
                    # Le ? était visuellement trop dominant par rapport aux icônes.
                    visual_extra_size = max(11, round(extra_size * 0.66))
                row["extra_icon"].setFixedSize(extra_size, extra_size)
                row["extra_icon"].setAlignment(Qt.AlignmentFlag.AlignCenter)
                row["extra_icon"].setPixmap(self.icon_pixmap(extra_icon_file, visual_extra_size))
            else:
                row["extra_icon"].setFixedSize(0, 0)
                row["extra_icon"].clear()



        if self.current_layout_mode() == "line":
            self.force_compact_line_geometry()
        else:
            self.adjustSize()
        self.update()
        self.check_alarms(now)

    # Alarms
    def play_alarm_once(self):
        # Timer alarms only. Shared alerts never call this.
        name = self.config.get("alarms", {}).get("beep", "asterisk")
        play_beep_by_name(name)

    def play_alarm_sequence(self, repeat_count, repeat_every_sec, remaining=None):
        if remaining is None:
            remaining = repeat_count
        if remaining <= 0:
            return
        self.play_alarm_once()
        if remaining > 1:
            QTimer.singleShot(max(1, int(repeat_every_sec)) * 1000, lambda: self.play_alarm_sequence(repeat_count, repeat_every_sec, remaining - 1))

    def check_alarms(self, now=None):
        alarms = self.config.get("alarms", {})
        if not alarms.get("enabled", True):
            return

        if now is None:
            now = true_local_now()

        # Trim played_alarms safely.
        # Old version used ":" splitting, but ISO datetimes contain ":" too.
        cleaned = set()
        cutoff_dt = now - timedelta(hours=25)
        for alarm_key in self.played_alarms:
            try:
                parts = alarm_key.rsplit(":", 1)[0].split(":", 1)
                if len(parts) == 2:
                    alarm_dt = datetime.fromisoformat(parts[1])
                    if alarm_dt >= cutoff_dt:
                        cleaned.add(alarm_key)
            except Exception:
                # Keep unknown keys rather than crashing alarms.
                cleaned.add(alarm_key)
        self.played_alarms = cleaned

        targets = self.alarm_targets(now)
        event_settings = alarms.get("events", {})

        for key, target in targets.items():
            if not target:
                continue
            if key == "daily" and self.simple_completion_done("dailies"):
                continue
            if key != "argo" and not self.config["display"].get(key, True):
                continue
            settings = event_settings.get(key, {})
            if not settings.get("enabled", False):
                continue

            minutes_list = parse_alarm_minutes(settings.get("minutes", ""))
            repeat_enabled = bool(settings.get("repeat_enabled", False))
            repeat_count = int(settings.get("repeat_count", 1)) if repeat_enabled else 1
            repeat_every_sec = int(settings.get("repeat_every_sec", 5))

            for minutes_before in minutes_list:
                trigger_time = target - timedelta(minutes=minutes_before)
                diff = (now - trigger_time).total_seconds()

                # More tolerant trigger window:
                # old value was 1.5s, too easy to miss with lag, sleep, websocket time sync,
                # or a busy PC. This still plays only once thanks to alarm_key.
                if 0 <= diff < 75:
                    alarm_key = f"{key}:{target.isoformat()}:{minutes_before}"
                    if alarm_key not in self.played_alarms:
                        self.played_alarms.add(alarm_key)
                        self.play_alarm_sequence(repeat_count, repeat_every_sec)

    # Shared alerts
    def start_websocket_thread(self):
        if websocket is None:
            return
        shared = self.config.get("shared_alerts", {})
        if not shared.get("enabled", True) or not shared.get("server_url"):
            return
        threading.Thread(target=self.websocket_loop, daemon=True).start()


    def request_render_time_sync(self):
        """Ask the Render websocket server for its UTC time.
        The response updates TIME_OFFSET so all timers use Render time.
        """
        payload = {
            "type": "time_sync_request",
            "client_ms": int(time.time() * 1000)
        }
        try:
            with self.ws_lock:
                if self.ws:
                    self.ws.send(json.dumps(payload))
                    return True
        except Exception:
            self.ws_connected = False
        return False

    def apply_render_time_sync(self, client_ms, server_ms):
        """Apply Render server time correction with basic latency compensation."""
        global TIME_OFFSET, TIME_SYNC_OK, TIME_SYNC_LAST
        try:
            receive_ms = int(time.time() * 1000)
            client_ms = int(client_ms)
            server_ms = int(server_ms)

            rtt_ms = max(0, receive_ms - client_ms)
            estimated_server_now_ms = server_ms + (rtt_ms // 2)
            offset_ms = estimated_server_now_ms - receive_ms

            TIME_OFFSET = timedelta(milliseconds=offset_ms)
            TIME_SYNC_OK = True
            TIME_SYNC_LAST = datetime.now(timezone.utc)
            return True
        except Exception:
            return False

    def websocket_loop(self):
        import time
        url = self.config.get("shared_alerts", {}).get("server_url", "")
        while True:
            try:
                def on_open(ws):
                    self.ws_connected = True
                    try:
                        self.request_render_time_sync()
                    except Exception:
                        pass

                def on_close(ws, *args):
                    self.ws_connected = False

                def on_error(ws, error):
                    self.ws_connected = False

                def on_message(ws, message):
                    try:
                        data = json.loads(message)
                        if data.get("type") == "alert":
                            self.bridge.alert_received.emit(data.get("text", "ALERT"))
                        elif data.get("type") == "argo_update":
                            death_time = data.get("death_time")
                            self.bridge.argo_update_received.emit("" if death_time is None else str(death_time))
                        elif data.get("type") == "time_sync_response":
                            self.apply_render_time_sync(data.get("client_ms"), data.get("server_ms"))
                    except Exception:
                        pass

                ws = websocket.WebSocketApp(url, on_open=on_open, on_close=on_close, on_error=on_error, on_message=on_message)
                with self.ws_lock:
                    self.ws = ws
                ws.run_forever(ping_interval=25, ping_timeout=10)
            except Exception:
                self.ws_connected = False
            time.sleep(5)

    def send_shared_alert(self, text):
        shared = self.config.get("shared_alerts", {})
        payload = {
            "type": "alert",
            "text": text,
            "sender": shared.get("name", "Unknown"),
            "admin_key": shared.get("admin_key", "")
        }

        sent = False
        try:
            with self.ws_lock:
                if self.ws:
                    self.ws.send(json.dumps(payload))
                    sent = True
        except Exception:
            self.ws_connected = False

        # Ne pas afficher localement ici :
        # le websocket la renvoie déjà à tout le monde, y compris nous.
        pass

    def show_shared_alert(self, text):
        # Anti-doublon : si la même alerte arrive deux fois très vite,
        # on ignore la deuxième.
        now = datetime.now()
        clean_text = str(text or "").strip()

        if (
            clean_text == self._last_shared_alert_text
            and self._last_shared_alert_time is not None
            and (now - self._last_shared_alert_time).total_seconds() < 2
        ):
            return

        self._last_shared_alert_text = clean_text
        self._last_shared_alert_time = now

        self.alert_popup.show_text(clean_text)

    def show_alert_box(self):
        if not self.config.get("shared_alerts", {}).get("admin_key"):
            return
        if self.alert_box is None:
            self.alert_box = AlertInputBox(self)
        self.alert_box.show()
        self.alert_box.raise_()

    # Hotkey globale Windows — configurable dans les paramètres, sans AutoHotkey.
    # Elle fonctionne même quand Aion est au premier plan, tant que Windows accepte la touche.

    HOTKEY_ID = 9101
    WM_HOTKEY = 0x0312

    HOTKEY_VK = {
        "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
        "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
        "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
        "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
        "pageup": 0x21, "pagedown": 0x22,
        "tab": 0x09, "escape": 0x1B,
        "enter": 0x0D, "numenter": 0x0D,
        "num0": 0x60, "num1": 0x61, "num2": 0x62, "num3": 0x63, "num4": 0x64,
        "num5": 0x65, "num6": 0x66, "num7": 0x67, "num8": 0x68, "num9": 0x69,
        "num*": 0x6A, "num+": 0x6B, "num-": 0x6D, "num.": 0x6E, "num/": 0x6F,
        "`": 0xC0, "/": 0xBF, "\\": 0xDC,
    }

    def hotkey_to_vk(self, hotkey):
        hotkey = str(hotkey or "").strip().lower()
        if not hotkey:
            return None
        if hotkey in self.HOTKEY_VK:
            return self.HOTKEY_VK[hotkey]
        if len(hotkey) == 1 and "a" <= hotkey <= "z":
            return ord(hotkey.upper())
        if len(hotkey) == 1 and "0" <= hotkey <= "9":
            return ord(hotkey)
        return None

    def register_hotkey(self):
        self._unregister_hotkey()
        hotkey = self.config.get("shared_alerts", {}).get("hotkey", "").strip().lower()
        if not hotkey:
            print("[hotkey] aucune touche configurée", flush=True)
            return
        vk = self.hotkey_to_vk(hotkey)
        if vk is None:
            print(f"[hotkey] touche non supportée: {hotkey}", flush=True)
            return

        self._hotkey_stop = threading.Event()
        self._hotkey_thread_id = None
        self._hotkey_handle = True

        def loop():
            try:
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                self._hotkey_thread_id = kernel32.GetCurrentThreadId()
                ok = user32.RegisterHotKey(None, self.HOTKEY_ID, 0, vk)
                if not ok:
                    err = ctypes.GetLastError()
                    print(f"[hotkey] impossible d'enregistrer '{hotkey}' (erreur Windows {err}). Essaie une autre touche.", flush=True)
                    return
                print(f"[hotkey] enregistrée: {hotkey}", flush=True)

                msg = wintypes.MSG()
                while not self._hotkey_stop.is_set():
                    ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                    if ret == 0 or ret == -1:
                        break
                    if msg.message == self.WM_HOTKEY and msg.wParam == self.HOTKEY_ID:
                        self.bridge.hotkey_pressed.emit()
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
            except Exception as e:
                print(f"[hotkey] erreur thread: {e}", flush=True)
            finally:
                try:
                    ctypes.windll.user32.UnregisterHotKey(None, self.HOTKEY_ID)
                except Exception:
                    pass

        self._hotkey_thread = threading.Thread(target=loop, daemon=True)
        self._hotkey_thread.start()

    def _unregister_hotkey(self):
        try:
            if getattr(self, "_hotkey_stop", None):
                self._hotkey_stop.set()
            tid = getattr(self, "_hotkey_thread_id", None)
            if tid:
                ctypes.windll.user32.PostThreadMessageW(int(tid), 0x0012, 0, 0)  # WM_QUIT
        except Exception:
            pass
        self._hotkey_handle = None

    def _on_hotkey_pressed(self):
        self._focus_alert_box()

    def _focus_alert_box(self):
        if not self.config.get("shared_alerts", {}).get("admin_key"):
            return
        if self.alert_box is None:
            self.alert_box = AlertInputBox(self)
        self.alert_box.show()
        self.alert_box.raise_()
        self.alert_box.activateWindow()
        self.alert_box.entry.setFocus(Qt.FocusReason.OtherFocusReason)

    def hwnds_owned_by_overlay(self):
        hwnds = set()
        try:
            hwnds.add(int(self.winId()))
            if self.alert_box:
                hwnds.add(int(self.alert_box.winId()))
            if self.alert_popup:
                hwnds.add(int(self.alert_popup.winId()))
        except Exception:
            pass
        return hwnds

    def track_game_focus(self):
        # Keep remembering the last real foreground window that is not our overlay.
        if win32gui is None:
            return
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return
            if hwnd in self.hwnds_owned_by_overlay():
                return
            title = win32gui.GetWindowText(hwnd).lower()
            if "aionwatcher" in title:
                return
            self.last_game_hwnd = hwnd
        except Exception:
            pass

    def restore_game_focus(self):
        if win32gui is None or win32con is None:
            return

        hwnd = self.last_game_hwnd
        if not hwnd:
            return

        try:
            if not win32gui.IsWindow(hwnd):
                return

            # Avoid Windows' error sound: do not force anything if it refuses.
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            except Exception:
                pass

            # More reliable focus restore for games/borderless windows.
            if win32process is not None:
                try:
                    fg = win32gui.GetForegroundWindow()
                    current_thread = win32process.GetCurrentThreadId()
                    target_thread = win32process.GetWindowThreadProcessId(hwnd)[0]
                    fg_thread = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0

                    win32process.AttachThreadInput(current_thread, target_thread, True)
                    if fg_thread:
                        win32process.AttachThreadInput(current_thread, fg_thread, True)

                    win32gui.SetForegroundWindow(hwnd)
                    win32gui.SetActiveWindow(hwnd)
                    win32gui.SetFocus(hwnd)

                    if fg_thread:
                        win32process.AttachThreadInput(current_thread, fg_thread, False)
                    win32process.AttachThreadInput(current_thread, target_thread, False)
                    return
                except Exception:
                    try:
                        if fg_thread:
                            win32process.AttachThreadInput(current_thread, fg_thread, False)
                        win32process.AttachThreadInput(current_thread, target_thread, False)
                    except Exception:
                        pass

            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass

        except Exception:
            pass

    # Settings
    def open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            dlg.apply_to_config()
            save_config(self.config)
            self.apply_appearance()
            print(f"[settings] Appel register_hotkey avec hotkey='{self.config.get('shared_alerts',{}).get('hotkey','')}'", flush=True)
            self.register_hotkey()

    # Drag/close
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if child is self.drag:
                if win32gui:
                    try:
                        self.last_game_hwnd = win32gui.GetForegroundWindow()
                    except Exception:
                        pass
                self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            pos = event.globalPosition().toPoint() - self.drag_pos
            self.move(pos)
            self.config["appearance"]["x"] = pos.x()
            self.config["appearance"]["y"] = pos.y()
            save_config(self.config)
            event.accept()

    def close_all(self):
        save_config(self.config)

        try:
            self._unregister_hotkey()
        except Exception:
            pass

        try:
            if self.alert_box:
                self.alert_box.close()
        except Exception:
            pass

        try:
            self.alert_popup.close()
        except Exception:
            pass

        self.close()

        # Ferme complètement le process Python.
        app = QApplication.instance()
        if app:
            app.quit()

        sys.exit(0)



class CompletionDialog(QDialog):
    def __init__(self, watcher):
        super().__init__(watcher)
        self.watcher = watcher
        self.setWindowTitle("Daily / Corridors / Battlefields")
        self.resize(420, 360)
        self.setStyleSheet("""
            QDialog { background: #101014; color: white; }
            QLabel { color: white; }
            QCheckBox { color: white; padding: 2px; }
            QPushButton { background: #252535; color: white; border: 1px solid #555566; border-radius: 6px; padding: 5px 9px; }
            QPushButton:hover { border: 1px solid #e9b1ef; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        info = QLabel("Coche ce qui est terminé. Les dailies et battlefields reset au reset daily ; les corridors reset au prochain cycle de siège.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #bbbbbb;")
        root.addWidget(info)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self.checkboxes = {}
        self._build_bucket_tab("dailies", "Dailies")
        self._build_bucket_tab("corridors", "Corridors")
        self._build_bucket_tab("battlefields", "Battlefields")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_bucket_tab(self, bucket, title):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        items = self.watcher.completion_items(bucket)
        done = self.watcher.completion_done_map(bucket)
        self.checkboxes[bucket] = []

        if not items:
            empty = QLabel("Aucun item configuré.")
            empty.setStyleSheet("color: #888888;")
            layout.addWidget(empty)
        for item in items:
            cb = QCheckBox(item)
            cb.setChecked(bool(done.get(item)))
            cb.toggled.connect(lambda checked, b=bucket, it=item: self.watcher.set_completion_item(b, it, checked))
            layout.addWidget(cb)
            self.checkboxes[bucket].append(cb)

        layout.addStretch()
        reset_btn = QPushButton("Reset this list")
        reset_btn.setFixedWidth(120)
        def _reset():
            self.watcher.reset_completion_bucket(bucket)
            refreshed = self.watcher.completion_done_map(bucket)
            for cb in self.checkboxes.get(bucket, []):
                cb.blockSignals(True)
                cb.setChecked(bool(refreshed.get(cb.text())))
                cb.blockSignals(False)
        reset_btn.clicked.connect(_reset)
        layout.addWidget(reset_btn)
        self.tabs.addTab(tab, title)

class SettingsDialog(QDialog):
    def __init__(self, watcher):
        super().__init__(watcher)
        self.watcher = watcher
        self.config = watcher.config
        self.setWindowTitle("AionWatcher Settings")
        self.resize(620, 455)
        self.setStyleSheet("""
            QDialog { background: #101014; color: white; }
            QLabel { color: white; }
            QTabWidget::pane { border: 1px solid #333344; border-radius: 8px; }
            QTabBar::tab { background: #20202a; color: white; padding: 8px 14px; border-top-left-radius: 7px; border-top-right-radius: 7px; }
            QTabBar::tab:selected { background: #3a2a4f; }
            QLineEdit, QComboBox, QSpinBox {
                background: #20202a; color: white; border: 1px solid #444455; border-radius: 5px; padding: 4px;
            }
            QPushButton {
                background: #252535; color: white; border: 1px solid #555566; border-radius: 6px; padding: 6px 10px;
            }
            QPushButton:hover { border: 1px solid #e9b1ef; }
            QCheckBox { color: white; }
        """)

        root = QVBoxLayout()
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)
        self.setLayout(root)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        self.build_appearance_tab()
        self.build_elements_tab()
        self.build_alarms_tab()
        self.build_completion_tab()
        self.build_argo_tab()
        self.build_shared_style_tab()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def color_button(self, initial):
        # Bouton couleur simple et fiable : on utilise le sélecteur natif Windows
        # pour éviter les champs internes Qt avec flèches buggées.
        initial = initial if isinstance(initial, str) and QColor(initial).isValid() else "#000000"
        btn = QPushButton(initial)
        btn.setProperty("color", initial)
        btn.setFixedWidth(120)

        def apply_btn_style():
            c = btn.property("color") or initial
            if not QColor(c).isValid():
                c = "#000000"
                btn.setProperty("color", c)
            btn.setText(c)
            txt = "#ffffff" if QColor(c).lightness() < 145 else "#000000"
            btn.setStyleSheet(
                f"QPushButton {{ background: {c}; color: {txt}; border: 1px solid #777; "
                "border-radius: 5px; padding: 4px 8px; }}"
                "QPushButton:hover { border: 1px solid #e9b1ef; }"
            )

        def pick():
            current = QColor(btn.property("color") or initial)
            color = QColorDialog.getColor(current, self, "Choose color")
            if color.isValid():
                btn.setProperty("color", color.name())
                apply_btn_style()

        btn.clicked.connect(pick)
        apply_btn_style()
        return btn

    def spinbox_no_arrows(self, minimum, maximum, value, width=70):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setFixedWidth(width)
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        return spin

    def background_color_editor(self, initial):
        initial = initial if QColor(str(initial)).isValid() else "#000000"
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        edit = QLineEdit(initial)
        edit.setFixedWidth(86)
        preview = QPushButton("")
        preview.setFixedSize(32, 24)
        pick_btn = QPushButton("Pick")
        pick_btn.setFixedWidth(48)

        def normalize(text):
            text = str(text).strip()
            if text and not text.startswith("#"):
                text = "#" + text
            return text if QColor(text).isValid() else "#000000"

        def refresh():
            c = normalize(edit.text())
            preview.setStyleSheet(f"QPushButton {{ background: {c}; border: 1px solid #777; border-radius: 4px; }}")
            box.setProperty("color", c)

        def pick():
            current = QColor(normalize(edit.text()))
            color = QColorDialog.getColor(current, self, "Choose background color")
            if color.isValid():
                edit.setText(color.name())
                refresh()

        edit.textChanged.connect(refresh)
        preview.clicked.connect(pick)
        pick_btn.clicked.connect(pick)

        layout.addWidget(edit)
        layout.addWidget(preview)
        layout.addWidget(pick_btn)
        refresh()
        box.color_value = lambda: normalize(edit.text())
        return box

    def build_appearance_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        app = self.config["appearance"]
        self.icon_color = self.color_button(app.get("icon_color", "#e9b1ef"))
        self.title_color = self.color_button(app.get("title_color", "#ffffff"))
        self.timer_color = self.color_button(app.get("timer_color", "#c8a2ff"))
        self.background_color = self.color_button(app.get("background_color", "#000000"))

        self.background_opacity = self.spinbox_no_arrows(0, 100, int(app.get("background_opacity", 0)), 70)

        self.layout_mode = QComboBox()
        self.layout_mode.addItems(["line", "column"])
        current_layout = app.get("layout", "line")
        if current_layout == "single_line":
            current_layout = "line"
        self.layout_mode.setCurrentText(current_layout if current_layout in ("line", "column") else "line")

        self.font_family = QComboBox()
        self.font_family.addItems(["Segoe UI", "Segoe UI Semibold", "Arial", "Verdana", "Tahoma", "Calibri"])
        self.font_family.setCurrentText(app.get("font_family", "Segoe UI"))

        self.font_size = self.spinbox_no_arrows(8, 40, int(app.get("font_size", 12)), 70)

        self.icon_size = self.spinbox_no_arrows(16, 90, int(app.get("icon_size", 45)), 70)

        self.bold = QCheckBox()
        self.bold.setChecked(bool(app.get("bold", False)))

        self.alpha = self.spinbox_no_arrows(30, 100, int(float(app.get("alpha", 1.0)) * 100), 70)

        self.scale = self.spinbox_no_arrows(50, 150, int(app.get("scale", 100)), 70)
        self.scale.setSuffix(" %")

        form.addRow("Icon color", self.icon_color)
        form.addRow("Title color", self.title_color)
        form.addRow("Timer color", self.timer_color)
        form.addRow("Background color", self.background_color)
        form.addRow("Background opacity %", self.background_opacity)
        form.addRow("Overlay layout", self.layout_mode)
        form.addRow("Font", self.font_family)
        form.addRow("Font size", self.font_size)
        form.addRow("Icon size", self.icon_size)
        form.addRow("Bold", self.bold)
        form.addRow("Opacity %", self.alpha)
        form.addRow("Scale %", self.scale)

        self.tabs.addTab(tab, "Appearance")

    def build_elements_tab(self):
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(2)
        grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(QLabel("Show"), 0, 0)
        grid.addWidget(QLabel("Order"), 0, 1)
        grid.addWidget(QLabel("Label"), 0, 2)
        grid.addWidget(QLabel("Element"), 0, 3)

        self.display_vars = {}
        self.order_vars = {}
        self.label_vars = {}

        for i, key in enumerate(ELEMENTS, start=1):
            show = QCheckBox()
            show.setChecked(bool(self.config["display"].get(key, True)))
            order = QSpinBox()
            order.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            order.setFixedWidth(44)
            order.setRange(1, len(ELEMENTS))
            order.setValue(self.config["order"].index(key) + 1 if key in self.config["order"] else i)
            label = QLineEdit(self.config["labels"].get(key, DEFAULT_CONFIG["labels"][key]))
            label.setMaximumWidth(190)

            self.display_vars[key] = show
            self.order_vars[key] = order
            self.label_vars[key] = label

            grid.addWidget(show, i, 0)
            grid.addWidget(order, i, 1)
            grid.addWidget(label, i, 2)
            grid.addWidget(QLabel(NAMES[key]), i, 3)

        self.tabs.addTab(tab, "Elements")

    def build_alarms_tab(self):
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(2)
        grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.alarms_enabled = QCheckBox("Enable timer alarms")
        self.alarms_enabled.setChecked(bool(self.config["alarms"].get("enabled", True)))
        grid.addWidget(self.alarms_enabled, 0, 0, 1, 5)

        headers = ["Event", "Enabled", "Before", "Repeat", "Count", "Every sec"]
        for c, h in enumerate(headers):
            grid.addWidget(QLabel(h), 1, c)

        self.alarm_enabled = {}
        self.alarm_minutes = {}
        self.alarm_repeat = {}
        self.alarm_count = {}
        self.alarm_every = {}

        choices = ["", "0", "1", "5", "10", "30", "60", "30,10,1", "10,1", "5,1"]

        for r, key in enumerate(ELEMENTS + ["argo"], start=2):
            settings = self.config["alarms"]["events"].get(key, DEFAULT_CONFIG["alarms"]["events"].get(key, DEFAULT_CONFIG["alarms"]["events"]["boss"]))

            enabled = QCheckBox()
            enabled.setChecked(bool(settings.get("enabled", False)))

            minutes = QComboBox()
            minutes.setFixedWidth(82)
            minutes.setEditable(True)
            minutes.addItems(choices)
            minutes.setCurrentText(str(settings.get("minutes", "")))

            repeat = QCheckBox()
            repeat.setChecked(bool(settings.get("repeat_enabled", False)))

            count = QSpinBox()
            count.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            count.setFixedWidth(44)
            count.setRange(1, 10)
            count.setValue(int(settings.get("repeat_count", 1)))

            every = QSpinBox()
            every.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            every.setFixedWidth(44)
            every.setRange(1, 60)
            every.setValue(int(settings.get("repeat_every_sec", 5)))

            self.alarm_enabled[key] = enabled
            self.alarm_minutes[key] = minutes
            self.alarm_repeat[key] = repeat
            self.alarm_count[key] = count
            self.alarm_every[key] = every

            grid.addWidget(QLabel("Argo" if key == "argo" else NAMES[key]), r, 0)
            grid.addWidget(enabled, r, 1)
            grid.addWidget(minutes, r, 2)
            grid.addWidget(repeat, r, 3)
            grid.addWidget(count, r, 4)
            grid.addWidget(every, r, 5)

        self.tabs.addTab(tab, "Alarms")

        # ── Sound selector + Test button ─────────────────────────────────────
        current_beep = self.config["alarms"].get("beep", "")
        sound_row = len(ELEMENTS) + 3   # below headers + element rows + one blank

        grid.addWidget(QLabel("Alarm sound"), sound_row, 0)

        self.beep_choice = QComboBox()
        self.beep_choice.setFixedWidth(220)
        wav_files = list_wav_sounds()
        if wav_files:
            for wav in wav_files:
                self.beep_choice.addItem(wav, wav)
        else:
            self.beep_choice.addItem("— no file in sounds/ —", "")
        # Select the currently configured sound
        idx = self.beep_choice.findData(current_beep)
        if idx >= 0:
            self.beep_choice.setCurrentIndex(idx)
        grid.addWidget(self.beep_choice, sound_row, 1, 1, 3)

        test_btn = QPushButton("▶  Test")
        test_btn.setFixedWidth(80)
        def _test_sound():
            play_beep_by_name(self.beep_choice.currentData())
        test_btn.clicked.connect(_test_sound)
        grid.addWidget(test_btn, sound_row, 4)

        if not wav_files:
            hint = QLabel("→ Create a sounds/ folder and put your .wav files there")
            hint.setStyleSheet("color: #888; font-size: 10px;")
            grid.addWidget(hint, sound_row + 1, 0, 1, 5)

    def build_completion_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        state = self.watcher.completion_state
        simple = state.setdefault("simple", {})
        today_key = completion_day_key(true_tw_now())
        week_key = completion_week_key(true_tw_now())
        siege_key = completion_siege_key(true_tw_now())

        def _checked(name, key):
            data = simple.get(name, {})
            if not isinstance(data, dict) or data.get("key") != key:
                return False
            return bool(data.get("done"))

        self.completion_dailies = QCheckBox("Dailies done")
        self.completion_corridors = QCheckBox("Corridors done")
        self.completion_battlefields = QCheckBox("Battlefields done")

        self.completion_dailies.setChecked(_checked("dailies", today_key))
        self.completion_corridors.setChecked(_checked("corridors", siege_key))
        self.completion_battlefields.setChecked(_checked("battlefields", week_key))

        hint = QLabel("One checkbox per event. Dailies reset daily (TW reset). Battlefields reset weekly. Corridors reset at the next siege cycle. If Dailies is checked, the Daily alarm will not play.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #999999;")

        form.addRow("Dailies", self.completion_dailies)
        form.addRow("Corridors", self.completion_corridors)
        form.addRow("Battlefields", self.completion_battlefields)
        form.addRow("", hint)
        self.tabs.addTab(tab, "Completion")

    def build_argo_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        argo = self.config.get("argo_config", {})

        # Server open: "opens in X hours" → stores ISO local datetime
        server_row = QWidget()
        server_layout = QHBoxLayout(server_row)
        server_layout.setContentsMargins(0, 0, 0, 0)
        server_layout.setSpacing(4)

        self.argo_server_hours = QSpinBox()
        self.argo_server_hours.setRange(0, 72)
        self.argo_server_hours.setValue(0)
        self.argo_server_hours.setFixedWidth(55)
        self.argo_server_hours.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.argo_server_hours.setSuffix(" h")

        self.argo_server_minutes = QSpinBox()
        self.argo_server_minutes.setRange(0, 59)
        self.argo_server_minutes.setValue(0)
        self.argo_server_minutes.setFixedWidth(55)
        self.argo_server_minutes.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.argo_server_minutes.setSuffix(" min")

        set_server_btn = QPushButton("Set")
        set_server_btn.setFixedWidth(44)

        clear_server_btn = QPushButton("✕")
        clear_server_btn.setFixedWidth(28)

        server_layout.addWidget(self.argo_server_hours)
        server_layout.addWidget(self.argo_server_minutes)
        server_layout.addWidget(set_server_btn)
        server_layout.addWidget(clear_server_btn)
        server_layout.addStretch()
        form.addRow("Server opens in", server_row)

        # Display stored server open target
        def _server_display_text():
            so = self.config.get("argo_config", {}).get("server_open", "")
            if not so:
                return "—"
            try:
                t = parse_shared_dt(so)  # handles both UTC-aware and old naive strings
                if t is None or t <= datetime.now():
                    return "expired"
                tw = t.astimezone(TW_TZ)  # t is local naive; astimezone() infers correct DST offset
                return f"{short_countdown(t, datetime.now())}  ({tw.strftime('%d/%m %H:%M TW')})"
            except Exception:
                return "—"

        self.argo_server_label = QLabel(_server_display_text())
        self.argo_server_label.setStyleSheet("color: #aaaaaa;")
        form.addRow("Next server open", self.argo_server_label)

        def _set_server():
            hours = self.argo_server_hours.value()
            minutes = self.argo_server_minutes.value()
            target = datetime.now(timezone.utc) + timedelta(hours=hours, minutes=minutes)
            self.config.setdefault("argo_config", {})
            self.config["argo_config"]["server_open"] = target.isoformat()  # stored as UTC ISO
            save_config(self.config)
            self.argo_server_label.setText(_server_display_text())

        def _clear_server():
            self.config.setdefault("argo_config", {})
            self.config["argo_config"]["server_open"] = ""
            save_config(self.config)
            self.argo_server_label.setText("—")

        set_server_btn.clicked.connect(_set_server)
        clear_server_btn.clicked.connect(_clear_server)

        # Argo next spawn: direct countdown input → stores/syncs the equivalent death_time
        # so old clients still understand the shared update format.
        next_row = QWidget()
        next_layout = QHBoxLayout(next_row)
        next_layout.setContentsMargins(0, 0, 0, 0)
        next_layout.setSpacing(4)

        self.argo_next_hours = QSpinBox()
        self.argo_next_hours.setRange(0, 12)
        self.argo_next_hours.setValue(0)
        self.argo_next_hours.setFixedWidth(55)
        self.argo_next_hours.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.argo_next_hours.setSuffix(" h")

        self.argo_next_minutes = QSpinBox()
        self.argo_next_minutes.setRange(0, 59)
        self.argo_next_minutes.setValue(0)
        self.argo_next_minutes.setFixedWidth(55)
        self.argo_next_minutes.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.argo_next_minutes.setSuffix(" min")

        set_next_btn = QPushButton("⏱  Set")
        set_next_btn.setFixedWidth(64)

        next_layout.addWidget(self.argo_next_hours)
        next_layout.addWidget(self.argo_next_minutes)
        next_layout.addWidget(set_next_btn)
        next_layout.addStretch()
        form.addRow("Next spawn in", next_row)

        def _set_next_spawn():
            hours = self.argo_next_hours.value()
            minutes = self.argo_next_minutes.value()
            if hours == 0 and minutes == 0:
                return

            now_utc = datetime.now(timezone.utc)
            spawn_utc = now_utc + timedelta(hours=hours, minutes=minutes)
            death_time_utc = spawn_utc - timedelta(hours=12)
            death_iso = death_time_utc.isoformat()
            death_time = death_time_utc.astimezone().replace(tzinfo=None)
            respawn_local = spawn_utc.astimezone().replace(tzinfo=None)

            self.config.setdefault("argo_config", {})
            self.config["argo_config"]["death_time"] = death_iso
            self.config["argo_config"]["server_open"] = ""
            save_config(self.config)

            self.watcher._flush_argo_alarms()
            self.watcher.update_timers()
            self.watcher.send_argo_update(death_iso)

            self.argo_death_label.setText(
                f"Killed: {fmt_tw(death_time)}  →  UP: {fmt_tw(respawn_local)}"
            )
            self.argo_server_label.setText(_server_display_text())

        set_next_btn.clicked.connect(_set_next_spawn)

        # Current death time — displayed in TW server time
        def _death_display_text():
            d_str = self.config.get("argo_config", {}).get("death_time")
            if not d_str:
                return "—"
            try:
                dt_local = parse_shared_dt(d_str)  # UTC ISO → local naive
                if dt_local is None:
                    return d_str
                respawn_local = dt_local + timedelta(hours=12)
                return (f"Killed: {fmt_tw(dt_local)}  →  "
                        f"UP: {fmt_tw(respawn_local)}")
            except Exception:
                return d_str

        self.argo_death_label = QLabel(_death_display_text())
        self.argo_death_label.setStyleSheet("color: #aaaaaa;")
        form.addRow("Last death", self.argo_death_label)

        # "Died X h Y min ago" input row
        ago_row = QWidget()
        ago_layout = QHBoxLayout(ago_row)
        ago_layout.setContentsMargins(0, 0, 0, 0)
        ago_layout.setSpacing(4)

        self.argo_ago_hours = QSpinBox()
        self.argo_ago_hours.setRange(0, 11)
        self.argo_ago_hours.setValue(0)
        self.argo_ago_hours.setFixedWidth(55)
        self.argo_ago_hours.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.argo_ago_hours.setSuffix(" h")

        self.argo_ago_minutes = QSpinBox()
        self.argo_ago_minutes.setRange(0, 59)
        self.argo_ago_minutes.setValue(0)
        self.argo_ago_minutes.setFixedWidth(55)
        self.argo_ago_minutes.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.argo_ago_minutes.setSuffix(" min")

        set_death_btn = QPushButton("💀  Set")
        set_death_btn.setFixedWidth(60)

        clear_death_btn = QPushButton("✕")
        clear_death_btn.setFixedWidth(28)

        ago_layout.addWidget(self.argo_ago_hours)
        ago_layout.addWidget(self.argo_ago_minutes)
        ago_layout.addWidget(set_death_btn)
        ago_layout.addWidget(clear_death_btn)
        ago_layout.addStretch()
        form.addRow("Killed ago", ago_row)

        def _set_death():
            hours = self.argo_ago_hours.value()
            minutes = self.argo_ago_minutes.value()
            death_time_utc = datetime.now(timezone.utc) - timedelta(hours=hours, minutes=minutes)
            death_iso = death_time_utc.isoformat()
            death_time = death_time_utc.astimezone().replace(tzinfo=None)

            self.config.setdefault("argo_config", {})
            self.config["argo_config"]["death_time"] = death_iso
            self.config["argo_config"]["server_open"] = ""
            save_config(self.config)

            self.watcher._flush_argo_alarms()
            self.watcher.update_timers()
            self.watcher.send_argo_update(death_iso)

            respawn_local = death_time + timedelta(hours=12)
            self.argo_death_label.setText(
                f"Killed: {fmt_tw(death_time)}  →  UP: {fmt_tw(respawn_local)}"
            )
            self.argo_server_label.setText(_server_display_text())

        def _clear_death():
            self.watcher.clear_argo_timer()
            self.argo_death_label.setText("—")

        set_death_btn.clicked.connect(_set_death)
        clear_death_btn.clicked.connect(_clear_death)

        self.tabs.addTab(tab, "Argo")

    def build_shared_style_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        shared = self.config["shared_alerts"]

        self.server_url = QLineEdit(shared.get("server_url", ""))
        self.name = QLineEdit(shared.get("name", "Nyxsia"))
        self.admin_key = QLineEdit(shared.get("admin_key", ""))

        self.hotkey = HotkeyCaptureButton(shared.get("hotkey", ""))

        self.alert_font_family = QComboBox()
        self.alert_font_family.addItems(["Segoe UI Black", "Segoe UI Semibold", "Arial Black", "Arial", "Verdana", "Tahoma"])
        self.alert_font_family.setCurrentText(shared.get("alert_font_family", "Segoe UI Black"))

        self.alert_font_size = self.spinbox_no_arrows(14, 90, int(shared.get("alert_font_size", 36)), 70)

        self.alert_bold = QCheckBox()
        self.alert_bold.setChecked(bool(shared.get("alert_bold", True)))

        self.alert_color = self.color_button(shared.get("alert_color", "#ff961e"))
        self.alert_outline_color = self.color_button(shared.get("alert_outline_color", "#000000"))

        self.alert_duration = self.spinbox_no_arrows(1, 30, int(shared.get("alert_duration_sec", 8)), 70)


        form.addRow("Server URL", self.server_url)
        form.addRow("Name", self.name)
        form.addRow("Admin key", self.admin_key)
        form.addRow("Hotkey (ouvrir box)", self.hotkey)
        form.addRow("Alert font", self.alert_font_family)
        form.addRow("Alert size", self.alert_font_size)
        form.addRow("Alert bold", self.alert_bold)
        form.addRow("Alert color", self.alert_color)
        form.addRow("Outline color", self.alert_outline_color)
        form.addRow("Duration sec", self.alert_duration)

        self.tabs.addTab(tab, "Shared Alert Style")

    def apply_to_config(self):
        app = self.config["appearance"]
        app["icon_color"] = self.icon_color.property("color")
        app["title_color"] = self.title_color.property("color")
        app["timer_color"] = self.timer_color.property("color")
        app["background_color"] = self.background_color.property("color")
        app["background_opacity"] = self.background_opacity.value()
        app["layout"] = self.layout_mode.currentText()
        app["font_family"] = self.font_family.currentText()
        app["font_size"] = self.font_size.value()
        app["icon_size"] = self.icon_size.value()
        app["scale"] = self.scale.value()
        app["bold"] = self.bold.isChecked()
        app["alpha"] = self.alpha.value() / 100

        for key in ELEMENTS:
            self.config["display"][key] = self.display_vars[key].isChecked()
            self.config["labels"][key] = self.label_vars[key].text()

        self.config["order"] = sorted(ELEMENTS, key=lambda k: self.order_vars[k].value())

        self.config["alarms"]["enabled"] = self.alarms_enabled.isChecked()
        self.config["alarms"]["beep"] = self.beep_choice.currentData()
        for key in ELEMENTS + ["argo"]:
            self.config["alarms"]["events"][key] = {
                "enabled": self.alarm_enabled[key].isChecked(),
                "minutes": self.alarm_minutes[key].currentText(),
                "repeat_enabled": self.alarm_repeat[key].isChecked(),
                "repeat_count": self.alarm_count[key].value(),
                "repeat_every_sec": self.alarm_every[key].value()
            }

        simple = self.watcher.completion_state.setdefault("simple", {})
        today_key = completion_day_key(true_tw_now())
        week_key = completion_week_key(true_tw_now())
        siege_key = completion_siege_key(true_tw_now())
        simple["dailies"] = {"key": today_key, "done": self.completion_dailies.isChecked()}
        simple["corridors"] = {"key": siege_key, "done": self.completion_corridors.isChecked()}
        simple["battlefields"] = {"key": week_key, "done": self.completion_battlefields.isChecked()}
        save_completion_state(self.watcher.completion_state)

        # argo_config server_open is saved immediately via Set/Clear buttons in the tab

        shared = self.config["shared_alerts"]
        shared["server_url"] = self.server_url.text()
        shared["name"] = self.name.text()
        shared["admin_key"] = self.admin_key.text()
        shared["hotkey"] = self.hotkey.get_key_name()
        print(f"[config] hotkey sauvegardé = '{shared['hotkey']}'", flush=True)
        shared["alert_font_family"] = self.alert_font_family.currentText()
        shared["alert_font_size"] = self.alert_font_size.value()
        shared["alert_bold"] = self.alert_bold.isChecked()
        shared["alert_color"] = self.alert_color.property("color")
        shared["alert_outline_color"] = self.alert_outline_color.property("color")
        shared["alert_duration_sec"] = self.alert_duration.value()
        shared["box_text"] = "#ffffff"
        shared["box_border"] = "#ffffff"

        # Also apply Argo "Killed ago" when user changes the spinboxes
        # and presses the general Save button instead of the small Set button.
        try:
            hours = self.argo_ago_hours.value()
            minutes = self.argo_ago_minutes.value()
            if hours > 0 or minutes > 0:
                death_time_utc = datetime.now(timezone.utc) - timedelta(hours=hours, minutes=minutes)
                death_iso = death_time_utc.isoformat()

                self.config.setdefault("argo_config", {})
                self.config["argo_config"]["death_time"] = death_iso
                self.config["argo_config"]["server_open"] = ""

                self.watcher._flush_argo_alarms()
                self.watcher.update_timers()
                self.watcher.send_argo_update(death_iso)
        except Exception as e:
            print("[ARGO SAVE ERROR]", e, flush=True)


# V26_REAL_VERTICAL_COMPACT

# V28_LEFT_MARGIN_FIX

def _set_dpi_aware():
    """Must be called before QApplication — tells Windows not to rescale the window."""
    try:
        # Best: per-monitor DPI awareness v2 (Windows 10 1703+)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            # Fallback: system DPI aware
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main():
    _set_dpi_aware()

    # Tell Qt to pass DPI scale factors through without rounding — keeps pixel precision
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("AionWatcher Qt")
    watcher = AionWatcherQt()
    watcher.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    ensure_single_instance()
    main()
