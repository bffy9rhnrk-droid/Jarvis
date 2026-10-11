# ============================================================
# K.A.R.V.I.S. - KARAHAN INC.
# Professional AI Assistant Backend
# Smart Web Research + Presentation Engine v33.0.0
# ============================================================

import os
import re
import json
import html as html_lib
import uuid
import time
import hashlib
import threading
import traceback
import random
from datetime import datetime

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from difflib import SequenceMatcher

import requests

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:
    psycopg2 = None
    RealDictCursor = None

try:
    from pywebpush import webpush, WebPushException
except Exception:
    webpush = None
    WebPushException = Exception

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from pydantic import BaseModel

from openai import OpenAI

from PIL import Image, ImageDraw, ImageFont, ImageOps

from reportlab.pdfgen import canvas
from reportlab.lib.units import inch


# ============================================================
# APP
# ============================================================

APP_VERSION = "36.0.0"

BASE_DIR = Path(__file__).resolve().parent

GENERATED_DIR = BASE_DIR / "generated"
GENERATED_DIR.mkdir(
    exist_ok=True
)

INDEX_FILE = BASE_DIR / "index.html"

# ============================================================
# WEB PUSH
# ============================================================

PUSH_SUBSCRIPTION_FILE = BASE_DIR / "push_subscriptions.json"
push_lock = threading.Lock()

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "").strip()
VAPID_CLAIMS_EMAIL = os.getenv("VAPID_CLAIMS_EMAIL", "mailto:admin@karahaninc.com").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def push_database_configured():
    return bool(DATABASE_URL and psycopg2)


def push_configured():
    return bool(webpush and VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)


def get_push_db_connection():
    if not push_database_configured():
        return None
    return psycopg2.connect(DATABASE_URL, connect_timeout=8, sslmode="require")


def init_push_database():
    if not push_database_configured():
        return False
    try:
        conn = get_push_db_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS karvis_push_subscriptions (
                        id BIGSERIAL PRIMARY KEY,
                        username TEXT NOT NULL,
                        endpoint TEXT NOT NULL UNIQUE,
                        p256dh TEXT NOT NULL,
                        auth TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        last_success_at TIMESTAMPTZ NULL,
                        last_failure_at TIMESTAMPTZ NULL,
                        failure_count INTEGER NOT NULL DEFAULT 0
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_karvis_push_username ON karvis_push_subscriptions(username)")
        conn.close()
        return True
    except Exception:
        save_error("Push database initialization error", traceback.format_exc())
        return False


def migrate_push_json_to_database():
    if not push_database_configured():
        return
    try:
        init_push_database()
        legacy = read_json_file(PUSH_SUBSCRIPTION_FILE, {})
        if not isinstance(legacy, dict):
            return
        conn = get_push_db_connection()
        with conn:
            with conn.cursor() as cur:
                for username, items in legacy.items():
                    if username not in USERS or not isinstance(items, list):
                        continue
                    for item in items:
                        endpoint = str(item.get("endpoint", "")).strip()
                        keys = item.get("keys") or {}
                        if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
                            continue
                        cur.execute("""
                            INSERT INTO karvis_push_subscriptions
                                (username, endpoint, p256dh, auth)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (endpoint) DO UPDATE SET
                                username=EXCLUDED.username,
                                p256dh=EXCLUDED.p256dh,
                                auth=EXCLUDED.auth,
                                updated_at=NOW()
                        """, (username, endpoint, keys.get("p256dh"), keys.get("auth")))
        conn.close()
    except Exception:
        save_error("Push subscription migration error", traceback.format_exc())


def get_push_subscriptions():
    if push_database_configured():
        try:
            init_push_database()
            conn = get_push_db_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT username, endpoint, p256dh, auth, updated_at, last_success_at, last_failure_at, failure_count FROM karvis_push_subscriptions ORDER BY updated_at DESC")
                rows = cur.fetchall()
            conn.close()
            data = {}
            for row in rows:
                item = dict(row)
                item["keys"] = {"p256dh": item.pop("p256dh"), "auth": item.pop("auth")}
                for k in ("updated_at", "last_success_at", "last_failure_at"):
                    if item.get(k) is not None:
                        item[k] = item[k].isoformat()
                data.setdefault(item.pop("username"), []).append(item)
            return data
        except Exception:
            save_error("Push database read error", traceback.format_exc())
    with push_lock:
        return read_json_file(PUSH_SUBSCRIPTION_FILE, {})


def save_push_subscriptions(data):
    if push_database_configured():
        try:
            init_push_database()
            conn = get_push_db_connection()
            with conn:
                with conn.cursor() as cur:
                    for username, items in data.items():
                        for item in items or []:
                            endpoint = str(item.get("endpoint", "")).strip()
                            keys = item.get("keys") or {}
                            if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
                                continue
                            cur.execute("""
                                INSERT INTO karvis_push_subscriptions (username, endpoint, p256dh, auth, updated_at)
                                VALUES (%s, %s, %s, %s, NOW())
                                ON CONFLICT (endpoint) DO UPDATE SET
                                    username=EXCLUDED.username,
                                    p256dh=EXCLUDED.p256dh,
                                    auth=EXCLUDED.auth,
                                    updated_at=NOW()
                            """, (username, endpoint, keys.get("p256dh"), keys.get("auth")))
            conn.close()
            return
        except Exception:
            save_error("Push database write error", traceback.format_exc())
    with push_lock:
        write_json_file(PUSH_SUBSCRIPTION_FILE, data)


def save_push_subscription(username, subscription):
    username = str(username or "").strip().lower()
    if username not in USERS or not isinstance(subscription, dict):
        return False
    endpoint = str(subscription.get("endpoint", "")).strip()
    keys = subscription.get("keys") or {}
    if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
        return False
    if push_database_configured():
        try:
            init_push_database()
            conn = get_push_db_connection()
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO karvis_push_subscriptions (username, endpoint, p256dh, auth, updated_at, failure_count)
                        VALUES (%s, %s, %s, %s, NOW(), 0)
                        ON CONFLICT (endpoint) DO UPDATE SET
                            username=EXCLUDED.username,
                            p256dh=EXCLUDED.p256dh,
                            auth=EXCLUDED.auth,
                            updated_at=NOW(),
                            failure_count=0,
                            last_failure_at=NULL
                    """, (username, endpoint, keys.get("p256dh"), keys.get("auth")))
            conn.close()
            return True
        except Exception:
            save_error("Push subscription database save error", traceback.format_exc())
    data = get_push_subscriptions()
    user_items = data.get(username, [])
    user_items = [x for x in user_items if x.get("endpoint") != endpoint]
    user_items.append({"endpoint": endpoint, "keys": {"p256dh": keys.get("p256dh"), "auth": keys.get("auth")}, "updated_at": datetime.now().isoformat(timespec="seconds")})
    data[username] = user_items[-10:]
    save_push_subscriptions(data)
    return True


def remove_push_subscription(username, endpoint):
    if push_database_configured():
        try:
            conn = get_push_db_connection()
            with conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM karvis_push_subscriptions WHERE username=%s AND endpoint=%s", (username, endpoint))
            conn.close()
            return
        except Exception:
            save_error("Push subscription database delete error", traceback.format_exc())
    data = get_push_subscriptions()
    items = data.get(username, [])
    data[username] = [x for x in items if x.get("endpoint") != endpoint]
    save_push_subscriptions(data)


def update_push_delivery(username, endpoint, success=False, failure=False):
    if not push_database_configured():
        return
    try:
        conn = get_push_db_connection()
        with conn:
            with conn.cursor() as cur:
                if success:
                    cur.execute("UPDATE karvis_push_subscriptions SET last_success_at=NOW(), failure_count=0, updated_at=NOW() WHERE username=%s AND endpoint=%s", (username, endpoint))
                elif failure:
                    cur.execute("UPDATE karvis_push_subscriptions SET last_failure_at=NOW(), failure_count=failure_count+1 WHERE username=%s AND endpoint=%s", (username, endpoint))
        conn.close()
    except Exception:
        save_error("Push delivery state update error", traceback.format_exc())

def send_push_to_user(username, title, body, url="/"):
    """Send push and aggressively clean stale subscriptions.

    Push endpoints can become invalid after browser/app changes. A failed
    send must never leave a dead endpoint looking active in the admin panel.
    """
    if not push_configured():
        return {"sent": 0, "removed": 0, "failed": 0, "errors": ["Web Push sunucusu yapılandırılmamış."]}

    username = str(username or "").strip().lower()
    data = get_push_subscriptions()
    items = list(data.get(username, []))
    sent = 0
    removed = 0
    failed = 0
    errors = []
    payload = json.dumps({
        "title": str(title or "K.A.R.V.I.S."),
        "body": str(body or ""),
        "url": str(url or "/")
    }, ensure_ascii=False)

    for item in items:
        endpoint = str(item.get("endpoint", "")).strip()
        subscription = {
            "endpoint": endpoint,
            "keys": item.get("keys", {})
        }
        try:
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_CLAIMS_EMAIL}
            )
            sent += 1
            update_push_delivery(username, endpoint, success=True)
        except Exception as e:
            response = getattr(e, "response", None)
            status = getattr(response, "status_code", None)
            failed += 1
            update_push_delivery(username, endpoint, failure=True)
            if status in (404, 410):
                remove_push_subscription(username, endpoint)
                removed += 1
                continue

            detail = f"HTTP {status}: {str(e)}" if status else str(e)
            errors.append(detail[:300])
            save_error("Web Push send error", traceback.format_exc())

    return {"sent": sent, "removed": removed, "failed": failed, "errors": errors[:5]}


def send_push_to_all(title, body, url="/"):
    data = get_push_subscriptions()
    total_sent = 0
    total_removed = 0
    total_failed = 0
    all_errors = []
    for username in list(data):
        result = send_push_to_user(username, title, body, url)
        total_sent += result.get("sent", 0)
        total_removed += result.get("removed", 0)
        total_failed += result.get("failed", 0)
        all_errors.extend(result.get("errors", []))
    return {"sent": total_sent, "removed": total_removed, "failed": total_failed, "errors": all_errors[:10]}


# ============================================================
# KARVIS SELF PUSH
# ============================================================

SELF_PUSH_ENABLED = os.getenv("KARVIS_SELF_PUSH_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
SELF_PUSH_MIN_SECONDS = int(os.getenv("KARVIS_SELF_PUSH_MIN_SECONDS", "7200"))
SELF_PUSH_MAX_SECONDS = int(os.getenv("KARVIS_SELF_PUSH_MAX_SECONDS", "14400"))
_self_push_started = False
_self_push_start_lock = threading.Lock()

SELF_PUSH_MESSAGES = [
    "Hey 👀 Ben K.A.R.V.I.S. Bir test yapmaya ne dersin? Gel beni biraz zorla.",
    "🛰️ Hey, buradayım. K.A.R.V.I.S.'i test etmek ister misin?",
    "🤖 Sessizlik fazla sürdü... Gel bana bir şey sor, devrelerimi çalıştır.",
    "🔔 K.A.R.V.I.S. kontrol bildirimi: Hadi beni test et.",
    "🧠 Sistem hazır. Bana zor bir soru sorup sınamak ister misin?",
    "⚡ Hey! K.A.R.V.I.S. burada. Gel bakalım, bugün beni neyle test edeceksin?"
]

def karvis_self_push_worker():
    """Bildirim izni veren kullanıcılara aralıklı K.A.R.V.I.S. bildirimi gönderir."""
    if not SELF_PUSH_ENABLED:
        return
    while True:
        try:
            wait_seconds = random.randint(SELF_PUSH_MIN_SECONDS, max(SELF_PUSH_MIN_SECONDS, SELF_PUSH_MAX_SECONDS))
            time.sleep(wait_seconds)

            if not push_configured():
                continue

            data = get_push_subscriptions()
            recipients = [u for u, items in data.items() if items and u in USERS]
            if not recipients:
                continue

            body = random.choice(SELF_PUSH_MESSAGES)
            for username in recipients:
                send_push_to_user(
                    username,
                    "K.A.R.V.I.S.",
                    body,
                    "/"
                )
        except Exception:
            save_error("K.A.R.V.I.S. self-push worker error", traceback.format_exc())
            time.sleep(60)

def start_self_push_worker():
    global _self_push_started
    with _self_push_start_lock:
        if _self_push_started:
            return
        _self_push_started = True
        threading.Thread(
            target=karvis_self_push_worker,
            name="karvis-self-push",
            daemon=True
        ).start()



app = FastAPI(
    title="K.A.R.V.I.S. - KARAHAN INC.",
    version=APP_VERSION
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def karvis_unhandled_exception_handler(request, exc):
    """Yakalanmamış API hatalarını admin hata merkezine kaydeder."""
    try:
        details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        save_error(
            "Yakalanmamış sunucu hatası: " + type(exc).__name__,
            details,
            category="http_unhandled_exception",
            severity="critical",
            path=request.url.path,
            method=request.method,
        )
    except Exception as logging_exc:
        print("KARVIS_EXCEPTION_HANDLER_FAILED: " + repr(logging_exc), flush=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Sunucu tarafında beklenmeyen bir hata oluştu. Hata yönetici kayıtlarına iletildi."},
    )


# ============================================================
# API KEYS
# ============================================================

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY",
    ""
).strip()

OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    ""
).strip()

GOOGLE_IMAGE_API_KEY = os.getenv(
    "GOOGLE_IMAGE_API_KEY",
    ""
).strip()

GOOGLE_CSE_ID = os.getenv(
    "GOOGLE_CSE_ID",
    ""
).strip()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()


groq_client = (
    OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )
    if GROQ_API_KEY
    else None
)


openrouter_client = (
    OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1"
    )
    if OPENROUTER_API_KEY
    else None
)


GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]


OPENROUTER_MODELS = [
    "openai/gpt-oss-20b:free",
]


# ============================================================
# MEMORY / ERROR LOG
# ============================================================

MEMORY_FILE = BASE_DIR / "memory.json"
ERROR_FILE = BASE_DIR / "errors.json"

memory_lock = threading.Lock()
error_lock = threading.Lock()


def read_json_file(
    path,
    default
):

    try:

        if not path.exists():
            return default

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception:

        return default


def write_json_file(
    path,
    data
):

    temp = path.with_suffix(
        ".tmp"
    )

    with open(
        temp,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

    temp.replace(path)


def _sanitize_error_text(value):
    """Hata ayrıntılarından yaygın gizli anahtar/parola değerlerini maskeler."""
    text = str(value or "")
    patterns = [
        (r"(?i)(api[_-]?key|authorization|bearer|password|passwd|secret|token)(\s*[=:]\s*)([^\s,;]+)", r"\1\2[REDACTED]"),
        (r"(?i)(sk-[A-Za-z0-9_-]{12,})", "[REDACTED_API_KEY]"),
        (r"(?i)(postgres(?:ql)?://[^:\s]+:)([^@\s]+)(@)", r"\1[REDACTED]\3"),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text[:20000]


def save_error(message, details=None, *, category="application", severity="error", path=None, method=None):
    """Admin hata merkezine yapılandırılmış, hassas bilgilerden arındırılmış kayıt ekler."""
    item = {
        "id": uuid.uuid4().hex,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "error": _sanitize_error_text(message),
        "details": _sanitize_error_text(details),
        "category": _sanitize_error_text(category),
        "severity": severity if severity in {"info", "warning", "error", "critical"} else "error",
        "status": "open",
    }
    if path:
        item["path"] = _sanitize_error_text(path)[:500]
    if method:
        item["method"] = _sanitize_error_text(method)[:20]

    try:
        with error_lock:
            data = read_json_file(ERROR_FILE, [])
            if not isinstance(data, list):
                data = []
            # Eski kayıtların alanlarını koru; yeni kayıtlar en fazla 100 adet tutulur.
            data.append(item)
            write_json_file(ERROR_FILE, data[-100:])
        return True
    except Exception as exc:
        # Kayıt sistemi de arızalıysa sessizce yutma; Render loglarında görünür olsun.
        print(
            "KARVIS_ERROR_LOG_WRITE_FAILED: "
            + _sanitize_error_text(repr(exc))
            + " | original_error=" + _sanitize_error_text(message),
            flush=True,
        )
        return False


# ============================================================
# USERS
# ============================================================

USERS = {

    "karahan": {
        "name": "KARAHAN INC.",
        "password": "",
        "role": "owner",
        "style": "professional",
    },

    "betul": {
        "name": "Betül",
        "password": "1234",
        "role": "user",
        "style": "professional",
    },

    "sinem": {
        "name": "Sinem",
        "password": "3021",
        "role": "user",
        "style": "professional",
    },

    "ilknur": {
        "name": "İlknur",
        "password": "1111",
        "role": "teacher",
        "style": "academic",
    },

    "murat": {
        "name": "Murat",
        "password": "0000",
        "role": "admin",
        "style": "professional",
    },

    "sude": {
        "name": "Sude",
        "password": "1234",
        "role": "user",
        "style": "sude",
    },
}


# ============================================================
# PASSWORD STORE + SUDE WORLD DATA
# ============================================================
PASSWORD_FILE = BASE_DIR / "user_passwords.json"
SUDE_WORLD_FILE = BASE_DIR / "sude_world.json"
password_lock = threading.Lock()
sude_lock = threading.Lock()


def _password_hash(password, salt=None):
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), bytes.fromhex(salt), 240000).hex()
    return {"salt": salt, "hash": digest, "scheme": "pbkdf2_sha256", "iterations": 240000}


def _verify_password(password, record):
    if not isinstance(record, dict) or not record.get("salt") or not record.get("hash"):
        return False
    candidate = _password_hash(password, record["salt"])["hash"]
    return hashlib.compare_digest(candidate, str(record.get("hash", ""))) if hasattr(hashlib, "compare_digest") else __import__("hmac").compare_digest(candidate, str(record.get("hash", "")))


def _load_password_store():
    with password_lock:
        records = read_json_file(PASSWORD_FILE, {})
        if not isinstance(records, dict): records = {}
        changed = False
        for uname, info in USERS.items():
            if uname not in records:
                legacy = str(info.get("password", ""))
                records[uname] = _password_hash(legacy)
                changed = True
            info["password"] = ""  # don't keep plaintext credentials in the active user map
        if changed or not PASSWORD_FILE.exists():
            write_json_file(PASSWORD_FILE, records)
        return records


def _set_password(username, password):
    with password_lock:
        records = read_json_file(PASSWORD_FILE, {})
        if not isinstance(records, dict): records = {}
        records[username] = _password_hash(password)
        write_json_file(PASSWORD_FILE, records)


def _sude_default_state():
    return {"food_log": [], "tasks": [], "points": 0, "pet": {"name": "Luna", "level": 1, "mood": 70, "energy": 70}, "badges": [], "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}


def _get_sude_state():
    data = read_json_file(SUDE_WORLD_FILE, {})
    if not isinstance(data, dict): data = {}
    data.setdefault("sude", _sude_default_state())
    state = data["sude"]
    if not isinstance(state, dict): state = _sude_default_state()
    defaults = _sude_default_state()
    for key, value in defaults.items(): state.setdefault(key, value)
    data["sude"] = state
    return data, state


# ============================================================
# MODELS
# ============================================================

class LoginRequest(BaseModel):

    username: str
    password: str = ""


class ChatRequest(BaseModel):

    message: str
    username: str = "karahan"
    mode: str = "normal"
    conversation_id: str = ""


class PresentationRequest(BaseModel):

    topic: str
    slide_count: int = 7
    username: str = "karahan"


class BetulInstagramRequest(BaseModel):

    username: str


class UserRequestCreate(BaseModel):

    username: str
    original: str
    summary: str = ""


class PushSubscribeRequest(BaseModel):

    username: str
    subscription: dict


class PushUnsubscribeRequest(BaseModel):

    username: str
    endpoint: str


class AdminNotificationRequest(BaseModel):

    username: str = "murat"
    target: str = "all"
    title: str = "K.A.R.V.I.S."
    body: str
    url: str = "/"


# ============================================================
# USER REQUESTS / SUGGESTIONS
# ============================================================

REQUEST_FILE = BASE_DIR / "user_requests.json"
request_lock = threading.Lock()


def normalize_request_text(text):
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def detect_user_feature_request(message):
    text = normalize_request_text(message)
    if not text or len(text) < 10:
        return False

    # Bilgi isteme kalıplarını özellikle dışarıda bırak.
    pure_question = re.match(r"^(hava|hava durumu|saat|kaç|kim|ne|nedir|nasıl|nerede|ne zaman|hangi)\b", text)
    request_patterns = [
        "keşke", "şöyle olsa", "böyle olsa", "olsa daha güzel",
        "olsa daha iyi", "olsa iyi olur", "yapabilsen", "yapabilirsen",
        "ekleyebilirsen", "eklenebilir", "ekleyebilir misin",
        "özellik ekle", "özelliği ekle", "bence ekle", "bunu da yap",
        "şunu da yap", "bunu da ekle", "şunu da ekle", "yapabilir misin"
    ]
    if pure_question and not any(p in text for p in request_patterns):
        return False
    return any(p in text for p in request_patterns)


def make_request_summary(message):
    text = re.sub(r"\s+", " ", str(message or "").strip())
    text = re.sub(r"^(keşke|bence|şunu|bunu)\s*", "", text, flags=re.IGNORECASE)
    text = text.strip(" .,!?")
    if len(text) > 180:
        text = text[:177].rstrip() + "..."
    return text


def feature_request_ack(username):
    name = USERS.get(username, {}).get("name", username)
    if username == "betul":
        return (
            "Aşkoo, bunu KARAHAN INC.'e bildiriyorum 💅 "
            "En kısa sürede bu konuyu değerlendirip uygun görülürse "
            "K.A.R.V.I.S.'e ekleyeceklerinden eminim. ✨"
        )
    if username == "ilknur":
        return (
            "Hocam, talebinizi KARAHAN INC. yönetimine bildiriyorum. "
            "En kısa sürede değerlendirmeye alınarak uygun görülmesi hâlinde "
            "uygulamaya dahil edilecektir."
        )
    if username == "sinem":
        return (
            "Sinem, bunu KARAHAN INC.'e bildiriyorum. "
            "En kısa sürede bu konuyu değerlendirip uygun görülürse "
            "uygulamayı güncelleyeceklerinden eminim. ✨"
        )
    return (
        f"{name}, talebinizi KARAHAN INC.'e bildiriyorum. "
        "En kısa sürede bu konuyu değerlendirip uygun görülmesi hâlinde "
        "uygulamaya dahil edeceklerinden eminim."
    )


def save_user_request(username, original):
    username = str(username or "").strip().lower()
    if username in {"", "karahan", "murat"}:
        return None
    if not detect_user_feature_request(original):
        return None
    with request_lock:
        data = read_json_file(REQUEST_FILE, [])
        # Aynı cümlenin kısa süre içinde tekrar kaydedilmesini önle.
        norm = normalize_request_text(original)
        now = time.time()
        for item in reversed(data[-30:]):
            if item.get("username") == username and normalize_request_text(item.get("original", "")) == norm:
                try:
                    if now - datetime.fromisoformat(item.get("created_at", "")).timestamp() < 300:
                        return item
                except Exception:
                    pass
        item = {
            "id": uuid.uuid4().hex,
            "username": username,
            "name": USERS.get(username, {}).get("name", username),
            "original": str(original).strip(),
            "summary": make_request_summary(original),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "read": False,
            "priority": "normal"
        }
        data.append(item)
        write_json_file(REQUEST_FILE, data[-500:])
        return item


def get_user_requests():
    """Return only genuine user feature requests.

    Older versions could accidentally save the Betül system prompt instead of
    the user message. Those malformed records are ignored and removed.
    """
    with request_lock:
        data = read_json_file(REQUEST_FILE, [])
        clean = []
        changed = False
        for item in data:
            original = str(item.get("original", "")).strip()
            normalized = normalize_request_text(original)
            looks_like_system_prompt = (
                normalized.startswith("sen k.a.r.v.i.s.")
                or "betül karakteri:" in normalized
                or "kullanıcının mesajı:" in normalized and "sen k.a.r.v.i.s." in normalized
            )
            if looks_like_system_prompt:
                changed = True
                continue
            item.pop("status", None)
            clean.append(item)
        if changed or len(clean) != len(data):
            write_json_file(REQUEST_FILE, clean[-500:])
        return clean[-500:]


def requests_answer_for_admin():
    data = get_user_requests()
    if not data:
        return "Efendim, kayıtlı kullanıcı isteği bulunmuyor."
    unread = [x for x in data if not x.get("read", False)]
    recent = data[-10:][::-1]
    lines = [
        "Efendim, kullanıcıların kayıtlı isteklerini kontrol ettim.",
        f"Toplam {len(data)} istek var; {len(unread)} tanesi yeni."
    ]
    for item in recent:
        lines.append(f"• {item.get('name', item.get('username'))}: {item.get('summary') or item.get('original')}")
    return "\n".join(lines)


# ============================================================
# LOGIN
# ============================================================

@app.post("/login")
async def login(
    request: LoginRequest
):

    username = (
        request.username or ""
    ).strip().lower()

    password = (
        request.password or ""
    )

    user = USERS.get(
        username
    )

    if user is None:

        raise HTTPException(
            status_code=401,
            detail="Kullanıcı adı veya şifre hatalı."
        )

    password_records = _load_password_store()
    record = password_records.get(username)
    # Legacy fallback allows one-time migration of existing installations.
    valid = _verify_password(password, record) if record else False
    if not valid and user.get("password"):
        valid = user.get("password") == password
        if valid:
            _set_password(username, password)
            user["password"] = ""
    if not valid:
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı.")

    public_user = {

        "username":
            username,

        "name":
            user.get(
                "name",
                username
            ),

        "role":
            user.get(
                "role",
                "user"
            ),

        "style":
            user.get(
                "style",
                "professional"
            ),
    }

    return {

        "success":
            True,

        "username":
            username,

        "user":
            public_user,

        "message":
            "Giriş başarılı."
    }


# ============================================================
# USER REQUEST ADMIN API
# ============================================================

@app.get("/user-requests")
async def user_requests(username: str = "murat"):
    if str(username).strip().lower() != "murat":
        raise HTTPException(status_code=403, detail="Bu alan yalnızca yetkili profile açıktır.")
    data = get_user_requests()
    return {"success": True, "requests": data, "count": len(data), "unread": sum(1 for x in data if not x.get("read", False))}


@app.post("/user-requests/{request_id}/read")
async def mark_user_request_read(request_id: str, username: str = "murat"):
    if str(username).strip().lower() != "murat":
        raise HTTPException(status_code=403, detail="Yetkisiz işlem.")
    with request_lock:
        data = read_json_file(REQUEST_FILE, [])
        for item in data:
            if item.get("id") == request_id:
                item["read"] = True
                item.pop("status", None)
                write_json_file(REQUEST_FILE, data)
                return {"success": True}
    raise HTTPException(status_code=404, detail="İstek bulunamadı.")


@app.delete("/user-requests/{request_id}")
async def delete_user_request(request_id: str, username: str = "murat"):
    if str(username).strip().lower() != "murat":
        raise HTTPException(status_code=403, detail="Yetkisiz işlem.")
    with request_lock:
        data = read_json_file(REQUEST_FILE, [])
        new_data = [x for x in data if x.get("id") != request_id]
        if len(new_data) == len(data):
            raise HTTPException(status_code=404, detail="İstek bulunamadı.")
        write_json_file(REQUEST_FILE, new_data)
    return {"success": True}


# ============================================================
# WEB PUSH API
# ============================================================

@app.get("/push/config")
async def push_config():
    return {
        "configured": push_configured(),
        "public_key": VAPID_PUBLIC_KEY if push_configured() else ""
    }


@app.post("/push/subscribe")
async def push_subscribe(request: PushSubscribeRequest):
    username = str(request.username or "").strip().lower()
    if username not in USERS:
        raise HTTPException(status_code=400, detail="Geçersiz profil.")
    if not push_configured():
        raise HTTPException(status_code=503, detail="Web Push henüz yapılandırılmamış.")
    if not save_push_subscription(username, request.subscription):
        raise HTTPException(status_code=400, detail="Geçersiz push aboneliği.")
    return {"success": True, "message": "Bildirim aboneliği kaydedildi."}


@app.post("/push/unsubscribe")
async def push_unsubscribe(request: PushUnsubscribeRequest):
    username = str(request.username or "").strip().lower()
    endpoint = str(request.endpoint or "").strip()
    if username not in USERS:
        raise HTTPException(status_code=400, detail="Geçersiz profil.")
    if not endpoint:
        raise HTTPException(status_code=400, detail="Push endpoint boş olamaz.")
    remove_push_subscription(username, endpoint)
    return {"success": True, "message": "Bildirim aboneliği kapatıldı."}


@app.get("/admin/push-status")
async def admin_push_status(username: str = "murat"):
    require_admin(username)
    data = get_push_subscriptions()
    total = sum(len(v) for v in data.values())
    active_profiles = {k: len(v) for k, v in data.items() if v}
    return {
        "configured": push_configured(),
        "storage": "postgresql" if push_database_configured() else "json_fallback",
        "profiles": active_profiles,
        "total": total,
        "database_persistent": push_database_configured()
    }


@app.post("/admin/notifications/send")
async def admin_send_notification(request: AdminNotificationRequest):
    require_admin(request.username)
    title = str(request.title or "K.A.R.V.I.S.").strip()[:120]
    body = str(request.body or "").strip()[:1000]
    target = str(request.target or "all").strip().lower()
    url = str(request.url or "/").strip()[:500]
    if not body:
        raise HTTPException(status_code=400, detail="Bildirim mesajı boş olamaz.")
    if target != "all" and target not in USERS:
        raise HTTPException(status_code=400, detail="Geçersiz hedef profil.")
    if target == "all":
        result = send_push_to_all(title, body, url)
    else:
        result = send_push_to_user(target, title, body, url)
    if not push_configured():
        raise HTTPException(status_code=503, detail="Web Push yapılandırılmamış. Render ortam değişkenlerini ekleyin.")
    return {"success": True, "target": target, **result}


# ============================================================
# AI SYSTEMS
# ============================================================

PROFESSIONAL_SYSTEM = """
Sen K.A.R.V.I.S. isimli profesyonel Türkçe yapay zeka asistanısın.

Yanıtların:
- doğru,
- açık,
- doğal,
- bağlama uygun,
- gereksiz tekrar içermeyen
Türkçe olmalıdır.

Bilmediğin bir bilgiyi kesin gerçekmiş gibi uydurma.
Kaynak verilmişse yalnızca kaynaklarla desteklenen bilgileri kullan.
"""


ACADEMIC_SYSTEM = """
Sen K.A.R.V.I.S. isimli akademik yardımcı asistansın.

Kullanıcıya "Hocam" diye hitap et.

Dil:
- resmi,
- akademik,
- kurumsal,
- açık,
- ölçülü

olmalıdır.

Gereksiz emoji, argo ve aşırı samimi ifade kullanma.

Araştırma taleplerinde:
- kaynaklar,
- yöntem,
- bulgular,
- değerlendirme

ayrımını koru.

Ders anlatımında kavramları sistematik ve öğretici biçimde açıkla.

Quiz taleplerinde sınav formatını koru.

Sunum hazırlarken:
- kaynaklara dayalı,
- doğru,
- birbirini tekrar etmeyen,
- kısa,
- akademik,
- slayta uygun

metin üret.
"""


# ============================================================
# AI CALLS
# ============================================================

def call_groq(
    prompt,
    model,
    system_prompt=PROFESSIONAL_SYSTEM,
    max_tokens=5000
):

    if not groq_client:
        return None

    try:

        response = (
            groq_client
            .chat
            .completions
            .create(

                model=model,

                messages=[

                    {
                        "role":
                            "system",

                        "content":
                            system_prompt
                    },

                    {
                        "role":
                            "user",

                        "content":
                            prompt
                    }
                ],

                temperature=0.20,
                max_tokens=max_tokens
            )
        )

        return (
            response
            .choices[0]
            .message
            .content
        )

    except Exception:

        save_error(
            "Groq error",
            traceback.format_exc()
        )

        return None


def call_openrouter(
    prompt,
    model,
    system_prompt=PROFESSIONAL_SYSTEM,
    max_tokens=5000
):

    if not openrouter_client:
        return None

    try:

        response = (
            openrouter_client
            .chat
            .completions
            .create(

                model=model,

                messages=[

                    {
                        "role":
                            "system",

                        "content":
                            system_prompt
                    },

                    {
                        "role":
                            "user",

                        "content":
                            prompt
                    }
                ],

                temperature=0.20,
                max_tokens=max_tokens
            )
        )

        return (
            response
            .choices[0]
            .message
            .content
        )

    except Exception:

        save_error(
            "OpenRouter error",
            traceback.format_exc()
        )

        return None


def ask_ai(
    prompt,
    system_prompt=PROFESSIONAL_SYSTEM,
    fast=False
):

    groq_models = (
        ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
        if fast else GROQ_MODELS
    )
    max_tokens = 900 if fast else 5000

    for model in groq_models:

        result = call_groq(
            prompt,
            model,
            system_prompt,
            max_tokens=max_tokens
        )

        if result:
            return result

    for model in OPENROUTER_MODELS:

        result = call_openrouter(
            prompt,
            model,
            system_prompt,
            max_tokens=max_tokens
        )

        if result:
            return result

    return None


# ============================================================
# JSON
# ============================================================

def extract_json(text):

    if not text:
        return None

    text = text.strip()

    text = re.sub(
        r"^```json",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"^```",
        "",
        text
    )

    text = re.sub(
        r"```$",
        "",
        text
    ).strip()

    try:

        return json.loads(
            text
        )

    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if (
        start >= 0
        and end > start
    ):

        try:

            return json.loads(
                text[start:end + 1]
            )

        except Exception:
            pass

    return None


# ============================================================
# BETÜL ENTERTAINMENT - INSTAGRAM SIMULATION
# ============================================================

def betul_deterministic_scores(
    seed: str,
    count: int = 6
):

    """
    Aynı kullanıcı adı için her zaman aynı
    eğlence sonuçlarını üretir.

    Bu gerçek Instagram verisi değildir.
    Tamamen deterministik bir simülasyondur.
    """

    seed = (
        str(seed or "")
        .strip()
        .lower()
        .lstrip("@")
    )

    digest = hashlib.sha256(
        seed.encode("utf-8")
    ).digest()

    raw = []

    for i in range(count):

        raw.append(
            10 + (
                digest[i] % 91
            )
        )

    total = sum(raw)

    exact = [
        value / total * 100
        for value in raw
    ]

    scores = [
        int(value)
        for value in exact
    ]

    remainder = 100 - sum(scores)

    order = sorted(
        range(count),
        key=lambda i:
            exact[i] - scores[i],
        reverse=True
    )

    for i in range(remainder):

        scores[
            order[
                i % len(order)
            ]
        ] += 1

    return scores


def betul_instagram_comment(
    categories,
    scores
):

    if not categories or not scores:

        return (
            "Aşkoo sistem ne diyeceğini "
            "bilemedi 😭"
        )

    highest_index = max(
        range(len(scores)),
        key=lambda i:
            scores[i]
    )

    highest = categories[
        highest_index
    ]

    comments = {

        "Romantik":
            (
                "Aşko burada aşk kokusu aldım... "
                "burnuma bildirim geldi resmen 💅💕"
            ),

        "Komik":
            (
                "AŞKOOO bu hesap iyiymiş 😭😂 "
                "K.A.R.V.I.S. analiz yaparken bile güldü."
            ),

        "Sıkıcı":
            (
                "Aşkoo bu hesap biraz fazla sakin çıktı ya... "
                "işlemci bile esnedi 😭"
            ),

        "Havalı":
            (
                "Aşkoo bu hesap kendini biraz fazla "
                "ciddiye alıyor ama hakkını da yemeyelim 😎"
            ),

        "Kaotik":
            (
                "AŞKOOO BU NE?! 💀 "
                "Sistemleri yeniden başlatmam gerekti."
            ),

        "Gizemli":
            (
                "Aşkoo burada bir şeyler dönüyor... "
                "K.A.R.V.I.S. radarları susmuyor 🤨"
            )
    }

    return comments.get(
        highest,
        "Aşkoo bu hesap enteresan çıktı 😭"
    )


@app.post(
    "/betul/instagram-analysis"
)
async def betul_instagram_analysis(
    request: BetulInstagramRequest
):

    username = (
        request.username
        or ""
    ).strip().lstrip("@")

    if not username:

        raise HTTPException(
            status_code=400,
            detail="Instagram kullanıcı adı boş olamaz."
        )

    # Bu endpoint yalnızca Betül profili için kullanılabilir.
    # Gerçek Instagram verisi çekilmez.
    categories = [
        "Romantik",
        "Komik",
        "Sıkıcı",
        "Havalı",
        "Kaotik",
        "Gizemli"
    ]

    scores = betul_deterministic_scores(
        username
    )

    return {
        "success": True,
        "username": username,
        "entertainment_only": True,
        "categories": [
            {
                "name": categories[i],
                "percent": scores[i]
            }
            for i in range(len(categories))
        ],
        "comment": betul_instagram_comment(
            categories,
            scores
        ),
        "disclaimer": (
            "Bu analiz gerçek Instagram verilerini "
            "incelemez; tamamen eğlence amaçlı bir "
            "simülasyondur ve yanılma payı vardır."
        )
    }


# ============================================================
# WEB RESEARCH
# ============================================================

WEB_HEADERS = {

    "User-Agent":
        "KARVIS-KARAHAN-INC/32.0 academic research"
}


def clean_text(text):

    if not text:
        return ""

    text = re.sub(
        r"<[^>]+>",
        " ",
        str(text)
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def search_wikipedia(
    topic,
    language="tr",
    limit=6
):

    try:

        api = (
            f"https://{language}.wikipedia.org/w/api.php"
        )

        response = requests.get(

            api,

            params={

                "action":
                    "query",

                "generator":
                    "search",

                "gsrsearch":
                    topic,

                "gsrnamespace":
                    0,

                "gsrlimit":
                    limit,

                "prop":
                    "extracts|info",

                "exintro":
                    True,

                "explaintext":
                    True,

                "inprop":
                    "url",

                "format":
                    "json",
            },

            headers=WEB_HEADERS,

            timeout=15
        )

        if response.status_code != 200:
            try:
                error_body = response.json().get("error", {})
                error_message = error_body.get("message") or response.text[:1200]
                error_reason = ", ".join(
                    str(item.get("reason", ""))
                    for item in error_body.get("errors", [])
                    if item.get("reason")
                )
            except Exception:
                error_message = (response.text or "")[:1200]
                error_reason = ""
            save_error(
                "Google Custom Search API başarısız",
                f"HTTP {response.status_code}; query={topic!r}; reason={error_reason}; detail={error_message}",
                category="web_search", severity="error",
                path="https://www.googleapis.com/customsearch/v1", method="GET",
            )
            return []

        pages = (
            response
            .json()
            .get("query", {})
            .get("pages", {})
        )

        results = []

        for page in pages.values():

            title = clean_text(
                page.get(
                    "title",
                    ""
                )
            )

            extract = clean_text(
                page.get(
                    "extract",
                    ""
                )
            )

            url = (
                page.get("fullurl")
                or
                (
                    f"https://{language}.wikipedia.org/wiki/"
                    +
                    title.replace(
                        " ",
                        "_"
                    )
                )
            )

            if not title or not extract:
                continue

            results.append({

                "title":
                    title,

                "text":
                    extract[:5000],

                "url":
                    url,

                "source":
                    "Wikipedia"
            })

        return results

    except Exception:

        save_error(
            "Wikipedia research error",
            traceback.format_exc()
        )

        return []


def search_tavily_web(topic, limit=8):
    """Search the web through Tavily and normalize results for KARVIS."""
    if not TAVILY_API_KEY:
        save_error(
            "Tavily araması yapılandırılmamış",
            "Render KARVIS backend Environment bölümünde TAVILY_API_KEY değişkenini tanımlayın.",
            category="web_search",
            severity="warning",
            path="TAVILY_API_KEY",
            method="POST",
        )
        return []

    endpoint = "https://api.tavily.com/search"
    try:
        response = requests.post(
            endpoint,
            json={
                "api_key": TAVILY_API_KEY,
                "query": str(topic or "").strip(),
                "search_depth": "basic",
                "topic": "general",
                "max_results": max(1, min(int(limit), 10)),
                "include_answer": False,
                "include_raw_content": False,
            },
            headers={**WEB_HEADERS, "Accept": "application/json", "Content-Type": "application/json"},
            timeout=25,
        )
        if response.status_code != 200:
            detail = (response.text or "")[:800]
            save_error(
                "Tavily API başarısız",
                f"HTTP {response.status_code}; query={topic!r}; detail={detail}",
                category="web_search",
                severity="error",
                path=endpoint,
                method="POST",
            )
            return []

        payload = response.json()
        results = []
        for item in (payload.get("results") or [])[:limit]:
            title = clean_text(item.get("title", ""))
            snippet = clean_text(item.get("content", "") or item.get("raw_content", ""))
            url = str(item.get("url", "")).strip()
            if not title or not url:
                continue
            results.append({
                "title": title,
                "text": snippet or title,
                "url": url,
                "source": "Tavily",
            })

        if not results:
            save_error(
                "Tavily sonuç döndürmedi",
                f"HTTP 200; query={topic!r}; response_keys={list(payload.keys())}",
                category="web_search",
                severity="warning",
                path=endpoint,
                method="POST",
            )
        return results
    except Exception:
        save_error("Tavily web search error", traceback.format_exc())
        return []


def search_google_web(
    topic
):

    if not GOOGLE_IMAGE_API_KEY or not GOOGLE_CSE_ID:
        missing = []
        if not GOOGLE_IMAGE_API_KEY:
            missing.append("GOOGLE_IMAGE_API_KEY eksik")
        if not GOOGLE_CSE_ID:
            missing.append("GOOGLE_CSE_ID eksik")
        save_error(
            "Google araması yapılandırılmamış",
            "; ".join(missing) + ". Render > Environment bölümünde değişken adlarını ve değerlerinin boş olmadığını kontrol edin. Değerleri hata kaydına yazdırmayın.",
            category="web_search", severity="error",
            path="https://www.googleapis.com/customsearch/v1", method="GET",
        )
        return []

    try:

        response = requests.get(

            "https://www.googleapis.com/customsearch/v1",

            params={

                "key":
                    GOOGLE_IMAGE_API_KEY,

                "cx":
                    GOOGLE_CSE_ID,

                "q":
                    topic,

                "num":
                    8,

                "safe":
                    "active"
            },

            headers=WEB_HEADERS,

            timeout=15
        )

        if response.status_code != 200:
            try:
                error_body = response.json().get("error", {})
                error_message = error_body.get("message") or (response.text or "")[:1200]
                error_reason = ", ".join(
                    str(item.get("reason", ""))
                    for item in error_body.get("errors", [])
                    if item.get("reason")
                )
            except Exception:
                error_message = (response.text or "")[:1200]
                error_reason = ""
            save_error(
                "Google Custom Search API başarısız",
                f"HTTP {response.status_code}; query={topic!r}; reason={error_reason}; detail={error_message}",
                category="web_search", severity="error",
                path="https://www.googleapis.com/customsearch/v1", method="GET",
            )
            return []

        payload = response.json()
        items = payload.get("items", [])
        if not items:
            search_info = payload.get("searchInformation", {})
            save_error(
                "Google Custom Search API sonuç döndürmedi",
                f"HTTP 200; query={topic!r}; totalResults={search_info.get('totalResults', 'bilinmiyor')}. API anahtarı çalışmış olabilir ancak CSE kapsamı, arama sorgusu veya arama motoru ayarları sonuç üretmemiş olabilir.",
                category="web_search", severity="warning",
                path="https://www.googleapis.com/customsearch/v1", method="GET",
            )

        results = []

        for item in items:

            title = clean_text(
                item.get(
                    "title",
                    ""
                )
            )

            snippet = clean_text(
                item.get(
                    "snippet",
                    ""
                )
            )

            link = item.get(
                "link",
                ""
            )

            if not title or not snippet:
                continue

            results.append({

                "title":
                    title,

                "text":
                    snippet,

                "url":
                    link,

                "source":
                    "Web"
            })

        return results

    except Exception:

        save_error(
            "Google web search error",
            traceback.format_exc()
        )

        return []


def search_duckduckgo_web(topic):
    """Google CSE yoksa DuckDuckGo HTML/Lite sonuçlarını yedek olarak dener."""
    headers = {
        **WEB_HEADERS,
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    endpoints = [
        ("https://html.duckduckgo.com/html/", {"q": topic}),
        ("https://lite.duckduckgo.com/lite/", {"q": topic}),
    ]

    for endpoint, params in endpoints:
        try:
            response = requests.get(endpoint, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            page = response.text or ""
            results = []

            # HTML endpoint: parse each result block.
            blocks = re.findall(
                r"<div[^>]*class=[\"'][^\"']*result[^\"']*[\"'][^>]*>(.*?)(?=<div[^>]*class=[\"'][^\"']*result|</html>)",
                page, flags=re.IGNORECASE | re.DOTALL
            )
            for block in blocks:
                link_match = re.search(
                    r"<a[^>]*class=[\"'][^\"']*result__a[^\"']*[\"'][^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
                    block, flags=re.IGNORECASE | re.DOTALL
                )
                snippet_match = re.search(
                    r"<(?:a|div)[^>]*class=[\"'][^\"']*result__snippet[^\"']*[\"'][^>]*>(.*?)</(?:a|div)>",
                    block, flags=re.IGNORECASE | re.DOTALL
                )
                if not link_match:
                    continue
                url = html_lib.unescape(link_match.group(1))
                title = clean_text(html_lib.unescape(re.sub(r"<[^>]+>", " ", link_match.group(2))))
                snippet = clean_text(html_lib.unescape(re.sub(r"<[^>]+>", " ", snippet_match.group(1)))) if snippet_match else ""
                if title and url.startswith("http"):
                    results.append({
                        "title": title, "text": snippet or title,
                        "url": url, "source": "DuckDuckGo Web"
                    })

            # Lite endpoint uses a simpler result-link class.
            if not results:
                links = re.findall(
                    r"<a[^>]*class=[\"'][^\"']*result-link[^\"']*[\"'][^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
                    page, flags=re.IGNORECASE | re.DOTALL
                )
                for url, raw_title in links:
                    url = html_lib.unescape(url)
                    title = clean_text(html_lib.unescape(re.sub(r"<[^>]+>", " ", raw_title)))
                    if title and url.startswith("http"):
                        results.append({
                            "title": title, "text": title,
                            "url": url, "source": "DuckDuckGo Web"
                        })

            if results:
                unique, seen = [], set()
                for item in results:
                    if item["url"] in seen:
                        continue
                    seen.add(item["url"])
                    unique.append(item)
                return unique[:8]
        except Exception as exc:
            save_error(
                "DuckDuckGo web yedeği başarısız",
                f"endpoint={endpoint}; exception_type={type(exc).__name__}; detail={exc}",
                category="web_search", severity="warning",
                path=endpoint, method="GET",
            )
            continue

    save_error(
        "DuckDuckGo web yedeği sonuç bulamadı",
        f"Sorgu={topic!r}; HTML ve Lite uç noktalarından ayrıştırılabilir sonuç alınamadı. CAPTCHA/engelleme, sayfa yapısının değişmesi veya ağ erişimi olası nedenlerdir.",
        category="web_search", severity="warning",
        path="DuckDuckGo HTML/Lite", method="GET",
    )
    return []


def research_topic(
    topic,
    progress_callback=None
):

    sources = []

    if progress_callback:

        progress_callback(
            10,
            "Araştırmalar yapılıyor..."
        )

    # --------------------------------------------------------
    # Turkish Wikipedia
    # --------------------------------------------------------

    if progress_callback:

        progress_callback(
            14,
            "Türkçe kaynaklar araştırılıyor..."
        )

    sources.extend(
        search_wikipedia(
            topic,
            "tr",
            6
        )
    )

    # --------------------------------------------------------
    # English Wikipedia
    # --------------------------------------------------------

    if progress_callback:

        progress_callback(
            20,
            "Yabancı kaynaklar karşılaştırılıyor..."
        )

    if len(sources) < 5:

        sources.extend(
            search_wikipedia(
                topic,
                "en",
                5
            )
        )

    # --------------------------------------------------------
    # Tavily web search
    # --------------------------------------------------------

    if progress_callback:
        progress_callback(
            25,
            "Tavily üzerinden web kaynakları kontrol ediliyor..."
        )

    sources.extend(search_tavily_web(topic, limit=8))

    # --------------------------------------------------------
    # Duplicate
    # --------------------------------------------------------

    unique = []

    seen = set()

    for source in sources:

        url = source.get(
            "url",
            ""
        )

        if not url:
            continue

        if url in seen:
            continue

        seen.add(url)

        unique.append(
            source
        )

    if progress_callback:

        progress_callback(
            30,
            f"{len(unique)} kaynak değerlendiriliyor..."
        )

    return unique[:15]


def format_sources_for_ai(
    sources
):

    if not sources:

        return (
            "Kullanılabilir harici kaynak bulunamadı. "
            "Bu durumda doğrulanmamış özel istatistikler "
            "ve kesin sayısal iddialar üretme."
        )

    blocks = []

    for index, source in enumerate(
        sources,
        start=1
    ):

        blocks.append(
            f"""
KAYNAK {index}
Başlık: {source.get("title", "")}
Kaynak: {source.get("source", "")}
URL: {source.get("url", "")}
İçerik:
{source.get("text", "")[:3500]}
"""
        )

    return "\n".join(
        blocks
    )



# ============================================================
# LIVE WEATHER / LOCAL NEWS HELPERS
# ============================================================

WEATHER_CODES_TR = {
    0: "açık",
    1: "çoğunlukla açık",
    2: "parçalı bulutlu",
    3: "kapalı",
    45: "sisli",
    48: "puslu/sisli",
    51: "hafif çisenti",
    53: "çisenti",
    55: "kuvvetli çisenti",
    61: "hafif yağmur",
    63: "yağmur",
    65: "kuvvetli yağmur",
    71: "hafif kar",
    73: "kar",
    75: "kuvvetli kar",
    80: "hafif sağanak",
    81: "sağanak yağış",
    82: "kuvvetli sağanak",
    95: "gök gürültülü fırtına",
    96: "gök gürültülü, dolu ihtimalli yağış",
    99: "gök gürültülü, kuvvetli dolu ihtimalli yağış",
}


def _weather_from_open_meteo():
    """Denizli canlı hava verisini Open-Meteo'dan alır."""
    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": 37.7765,
            "longitude": 29.0864,
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
            "hourly": "temperature_2m,precipitation_probability,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "forecast_days": 2,
            "timezone": "Europe/Istanbul",
        },
        headers=WEB_HEADERS,
        timeout=12,
    )
    response.raise_for_status()
    data = response.json()
    current = data.get("current", {})
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    rain = hourly.get("precipitation_probability", [])
    codes = hourly.get("weather_code", [])
    winds = hourly.get("wind_speed_10m", [])
    daily = data.get("daily", {})
    daily_times = daily.get("time", [])
    tomorrow = None
    if len(daily_times) > 1:
        tomorrow = {
            "date": daily_times[1],
            "condition": WEATHER_CODES_TR.get((daily.get("weather_code") or [None, None])[1], "değişken"),
            "max_temperature": (daily.get("temperature_2m_max") or [None, None])[1],
            "min_temperature": (daily.get("temperature_2m_min") or [None, None])[1],
            "rain_probability": (daily.get("precipitation_probability_max") or [None, None])[1],
        }

    current_time = str(current.get("time", ""))
    start_index = times.index(current_time) if current_time in times else 0
    upcoming = []
    for i in range(start_index, min(start_index + 8, len(times))):
        upcoming.append({
            "time": times[i],
            "temperature": temps[i] if i < len(temps) else None,
            "rain_probability": rain[i] if i < len(rain) else None,
            "condition": WEATHER_CODES_TR.get(codes[i], "değişken") if i < len(codes) else "değişken",
            "wind": winds[i] if i < len(winds) else None,
        })

    return {
        "location": "Denizli",
        "current_temperature": current.get("temperature_2m"),
        "apparent_temperature": current.get("apparent_temperature"),
        "current_condition": WEATHER_CODES_TR.get(current.get("weather_code"), "değişken"),
        "current_wind": current.get("wind_speed_10m"),
        "upcoming": upcoming,
        "tomorrow": tomorrow,
        "source": "Open-Meteo",
    }


def _weather_from_wttr():
    """Open-Meteo erişilemezse wttr.in üzerinden yedek canlı veri alır."""
    response = requests.get(
        "https://wttr.in/Denizli",
        params={"format": "j1", "lang": "tr"},
        headers=WEB_HEADERS,
        timeout=12,
    )
    response.raise_for_status()
    data = response.json()
    current = (data.get("current_condition") or [{}])[0]
    daily_raw = data.get("weather") or []
    today_data = daily_raw[0] if daily_raw else {}
    tomorrow_raw = daily_raw[1] if len(daily_raw) > 1 else {}
    hourly_raw = today_data.get("hourly", [])

    tomorrow_hours = tomorrow_raw.get("hourly", [])
    tomorrow_conditions = [
        clean_text(((x.get("lang_tr") or [{}])[0].get("value") or (x.get("weatherDesc") or [{}])[0].get("value") or "")).lower()
        for x in tomorrow_hours
    ]
    tomorrow_conditions = [x for x in tomorrow_conditions if x]
    tomorrow = None
    if tomorrow_raw:
        try:
            rain_probs = [int(x.get("chanceofrain")) for x in tomorrow_hours if x.get("chanceofrain") not in (None, "")]
        except Exception:
            rain_probs = []
        tomorrow = {
            "date": tomorrow_raw.get("date"),
            "condition": tomorrow_conditions[0] if tomorrow_conditions else "değişken",
            "min_temperature": tomorrow_raw.get("mintempC"),
            "max_temperature": tomorrow_raw.get("maxtempC"),
            "rain_probability": max(rain_probs) if rain_probs else None,
        }

    upcoming = []
    for item in hourly_raw[:8]:
        try:
            temp = float(item.get("tempC"))
        except Exception:
            temp = item.get("tempC")
        try:
            rain_prob = int(item.get("chanceofrain"))
        except Exception:
            rain_prob = item.get("chanceofrain")
        desc = ((item.get("lang_tr") or [{}])[0].get("value")
                or (item.get("weatherDesc") or [{}])[0].get("value")
                or "değişken")
        upcoming.append({
            "time": str(item.get("time", "")),
            "temperature": temp,
            "rain_probability": rain_prob,
            "condition": clean_text(desc).lower(),
            "wind": item.get("windspeedKmph"),
        })

    return {
        "location": "Denizli",
        "current_temperature": current.get("temp_C"),
        "apparent_temperature": current.get("FeelsLikeC"),
        "current_condition": clean_text(
            ((current.get("lang_tr") or [{}])[0].get("value")
             or (current.get("weatherDesc") or [{}])[0].get("value")
             or "değişken")
        ).lower(),
        "current_wind": current.get("windspeedKmph"),
        "upcoming": upcoming,
        "tomorrow": tomorrow,
        "source": "wttr.in",
    }


def fetch_denizli_weather():
    """Canlı Denizli hava durumu. Open-Meteo ana servis, wttr.in yedek servis.

    Ana servis geçici olarak başarısız olup yedek servis başarılıysa bunu
    sistem hatası olarak kaydetmez; böylece admin hata ekranı gereksiz
    Open-Meteo kayıtlarıyla dolmaz. İki servis de başarısızsa hata kaydedilir.
    """
    open_meteo_error = None
    try:
        return _weather_from_open_meteo()
    except Exception:
        open_meteo_error = traceback.format_exc()

    try:
        return _weather_from_wttr()
    except Exception:
        wttr_error = traceback.format_exc()
        save_error(
            "Weather services unavailable",
            "Open-Meteo error:\n" + str(open_meteo_error or "") +
            "\nwttr.in error:\n" + wttr_error
        )
        return None


def weather_context_for_ai(weather, message=""):
    """İsteğe göre mevcut hava veya yarının tahminini kısa biçimde hazırlar."""
    if not weather:
        return ""

    temp = weather.get("current_temperature")
    feels = weather.get("apparent_temperature")
    condition = clean_text(weather.get("current_condition") or "değişken").lower()
    upcoming = weather.get("upcoming") or []

    request_text = clean_text(message).lower()
    asks_tomorrow = bool(re.search(r"\b(yarın|yarinki|yarınki|yarin|yarin hava)\b", request_text))
    lines = ["DENİZLİ HAVA DURUMU TAHMİNİ"]
    if asks_tomorrow:
        tomorrow = weather.get("tomorrow") or {}
        if tomorrow:
            date_label = tomorrow.get("date") or "yarın"
            t_condition = clean_text(tomorrow.get("condition") or "değişken").lower()
            t_min = tomorrow.get("min_temperature")
            t_max = tomorrow.get("max_temperature")
            t_rain = tomorrow.get("rain_probability")
            summary = f"Yarın ({date_label}) Denizli'de hava {t_condition} olacak."
            if t_min is not None and t_max is not None:
                summary += f" Sıcaklık {t_min}°C ile {t_max}°C arasında."
            elif t_max is not None:
                summary += f" En yüksek sıcaklık {t_max}°C."
            if t_rain is not None:
                summary += f" Yağış olasılığı en fazla %{t_rain}."
            lines.append(summary)
            lines.append("Kullanıcının yarınla ilgili sorusunu bu günlük tahminle cevapla; bugünkü sıcaklığı yarının tahmini gibi sunma.")
            lines.append("Yanıtı tamamen Türkçe ve kısa ver; veri yoksa bunu açıkça söyle, tahmin uydurma.")
            return "\n".join(lines)
        lines.append("Yarın için günlük tahmin verisi bulunamadı. Canlı veride olmayan tahmini uydurma.")
        return "\n".join(lines)

    lines.append(f"Şu an: {temp}°C, {condition}.")
    if temp is not None and feels is not None:
        try:
            if abs(float(temp) - float(feels)) >= 3:
                lines.append(f"Hissedilen: {feels}°C.")
        except Exception:
            pass

    rain_values = [x.get("rain_probability") for x in upcoming[:8] if x.get("rain_probability") is not None]
    try:
        max_rain = max(float(x) for x in rain_values) if rain_values else None
    except Exception:
        max_rain = None

    if max_rain is not None and max_rain >= 50:
        lines.append("Yakın saatlerde yağış ihtimali yüksek.")
    elif max_rain is not None and max_rain >= 30:
        lines.append("Yakın saatlerde yağış ihtimali var.")

    temps = [x.get("temperature") for x in upcoming[:8] if x.get("temperature") is not None]
    try:
        numeric_temps = [float(x) for x in temps]
        if numeric_temps and temp is not None:
            delta = numeric_temps[-1] - float(temp)
            if delta <= -4:
                lines.append("Akşama doğru sıcaklık belirgin şekilde düşecek.")
            elif delta >= 4:
                lines.append("Gün içinde sıcaklık belirgin şekilde artacak.")
    except Exception:
        pass

    lines.append("Kullanıcıya yalnızca kısa ve doğal bir özet ver; saat saat sıcaklık listesi, rüzgar, ham veri, URL veya kaynak listesi verme.")
    return "\n".join(lines)


def is_weather_request(message):
    text = clean_text(message).lower()
    weather_terms = (
        r"\b(hava durumu|hava nasıl|hava bugün|bugün hava|yarın hava|hava yarın|"
        r"hava tahmini|yağmur yağacak mı|yağış var mı|sıcaklık kaç|kaç derece|derece kaç|"
        r"hava kaç derece|denizli hava|hava soğuk mu|hava sıcak mı|yağmur var mı|"
        r"kar yağacak mı|rüzgar var mı)\b"
    )
    return bool(re.search(weather_terms, text))


def is_local_news_request(message):
    text = clean_text(message).lower()
    return bool(re.search(r"\b(gündem|haberler|son haberler|bugün neler oluyor|son gelişmeler|gündemde ne var)\b", text)) and any(
        place in text for place in ["denizli", "honaz", "pamukkale", "merkezefendi", "çivril", "acipayam", "acıpayam"]
    )



# ============================================================
# SMART WEB RESEARCH
# ============================================================
# Web araştırması yalnızca sorunun güncel/doğrulanması gereken
# bir bilgiye ihtiyaç duyduğu durumlarda çalışır.
# Normal sohbet, genel bilgi ve yaratıcı istekler internete çıkmaz.

CURRENT_YEAR = datetime.now().year

WEB_TRIGGER_PATTERNS = [
    r"\bbugün\b",
    r"\bşu an\b",
    r"\bşuan\b",
    r"\bşimdiki\b",
    r"\bşu anda\b",
    r"\banlık\b",
    r"\bcanlı\b",
    r"\ben son\b",
    r"\bgüncel\b",
    r"\bson dakika\b",
    r"\bson gelişme",
    r"\bson haber",
    r"\byeni çıkan\b",
    r"\byenisi\b",
    r"\bbu hafta\b",
    r"\bbu ay\b",
    r"\bdün\b",
    r"\byarın\b",
    r"\bkaç tl\b",
    r"\bfiyatı\b",
    r"\bfiyatları\b",
    r"\bkur\b",
    r"\bdöviz\b",
    r"\beuro\b",
    r"\bdolar\b",
    r"\baltın\b",
    r"\bhava durumu\b",
    r"\bseçim sonuç",
    r"\bsonuçları açıklandı\b",
    r"\bkim kazandı\b",
    r"\bşampiyon\b",
    r"\bpuan durumu\b",
    r"\bmaç sonucu\b",
    r"\bbugünkü\b",
    r"\b202[4-9]\b",
]

RESEARCH_TRIGGER_PHRASES = [
    "internetten araştır",
    "internetten bak",
    "webden araştır",
    "web'den araştır",
    "internette ara",
    "kaynak bul",
    "kaynakları bul",
    "kaynak göster",
    "araştır",
    "güncel bilgi ver",
    "en son bilgiyi",
    "en güncel",
    "doğrula",
    "teyit et",
    "karşılaştır",
]

# Bazı konular güncel kelime içermese bile doğası gereği değişkendir.
VOLATILE_TOPICS = [
    "mevzuat", "kanun", "yönetmelik", "yasa", "vergi",
    "maaş", "asgari ücret", "faiz", "merkez bankası",
    "borsa", "hisse", "bitcoin", "kripto", "akaryakıt",
    "benzin", "motorin", "altın", "döviz", "kampanya",
    "sınav takvimi", "başvuru tarihi", "başvuru şartları",
    "üniversite taban puanı", "kontenjan", "kpss", "pmyo",
]

# İnternet gerektirmeyen tipik istekler. Bunlar özellikle korunur.
NO_WEB_PATTERNS = [
    r"^merhaba\b",
    r"^selam\b",
    r"^naber\b",
    r"^nasılsın\b",
    r"^teşekkür",
    r"^sağ ol\b",
    r"^eyvallah\b",
    r"\bne demek\b",
    r"\bnedir\b$",
]

def needs_web_research(message, username="karahan", mode="normal"):
    """
    Hafif ve deterministik bir karar katmanı.
    Ekstra AI çağrısı yapmaz; böylece normal konuşmalarda maliyet ve
    gecikme oluşturmaz.
    """
    text = clean_text(message).lower()
    if not text:
        return False

    # Selamlaşma gibi kısa mesajlarda kesinlikle araştırma yapma.
    for pattern in NO_WEB_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return False

    # Kullanıcı açıkça web araması istediğinde, konu ile fiil arasında
    # kelime olsa bile araştırmayı başlat: "internette perde ara" vb.
    explicit_search_patterns = [
        r"\binternette\b.{0,100}\b(ara|araştır|bak|bul)\b",
        r"\binternetten\b.{0,100}\b(ara|araştır|bak|bul)\b",
        r"\bweb(?:'den|den)?\b.{0,100}\b(ara|araştır|bak|bul)\b",
        r"\bgoogle(?:'da|da|de)?\b.{0,100}\b(ara|araştır|bak|bul)\b",
        r"\b(ara|araştır|bak|bul)\b.{0,100}\b(internette|internetten|webde|web'de|google'da|google)\b",
    ]
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in explicit_search_patterns):
        return True

    if any(phrase in text for phrase in RESEARCH_TRIGGER_PHRASES):
        return True

    # Akademik araştırma modunda açık araştırma ifadeleri ve güncel
    # çalışma talepleri web araştırmasını tetikler.
    if username == "ilknur" or mode in {"research", "article"}:
        academic_current = [
            "güncel çalışma", "son çalışmalar", "literatür",
            "2025", "2026", "yeni araştırma", "makale",
            "kaynakça", "bilimsel kaynak", "literatür taraması"
        ]
        if any(x in text for x in academic_current):
            return True

    if any(re.search(pattern, text, re.IGNORECASE) for pattern in WEB_TRIGGER_PATTERNS):
        return True

    if any(topic in text for topic in VOLATILE_TOPICS):
        return True

    # Tarih/yıl açıkça geleceğe veya günümüze referans veriyorsa.
    year_match = re.search(r"\b20\d{2}\b", text)
    if year_match:
        try:
            year = int(year_match.group(0))
            if year >= CURRENT_YEAR - 1:
                return True
        except Exception:
            pass

    return False


def build_profile_research_query(message, username, mode):
    """
    Aynı soruyu her profile farklı araştırma amacıyla aratır.
    Arama sorgusunun kendisi de profilin kullanım amacına göre şekillenir.
    """
    text = clean_text(message)

    # Yerel gündem sorularında arama motorunu doğrudan haber odaklı çalıştır.
    if is_local_news_request(text):
        if username == "ilknur":
            return f"{text} Denizli bugün son dakika haber gündem resmi kaynak"
        if username == "betul":
            return f"{text} Denizli bugün son dakika haber gündem gelişmeler"
        if username == "sinem":
            return f"{text} Denizli bugün güvenilir haber gündem gelişmeler"
        return f"{text} Denizli bugün son dakika haber gündem resmi kaynak"

    if username == "ilknur":
        return (
            f"{text} akademik güncel araştırma bilimsel kaynak "
            f"2025 2026"
        )

    if username == "betul":
        return (
            f"{text} güncel gelişmeler haberler trendler"
        )

    if username == "sinem":
        return (
            f"{text} güncel güvenilir bilgi"
        )

    # Karahan / varsayılan: teknik, resmi ve doğrudan.
    return (
        f"{text} güncel resmi kaynak teknik bilgi"
    )


def profile_research_instruction(username):
    common = """
GENEL CEVAP STANDARDI:
- Önce doğru ve doğrudan cevabı ver.
- Kısa, sade ve anlaşılır konuş. Gereksiz giriş, tekrar ve uzun açıklama yapma.
- Basit sorulara mümkünse 1-3 cümleyle cevap ver.
- Daha fazla ayrıntı ancak soru bunu gerektiriyorsa ver.
- Güncel araştırma yapıldıysa ham kaynak, URL, link listesi veya araştırma süreci anlatma.
- Araştırma bilgisini doğal cevabın içine yedir.
- Kaynaklar çelişiyorsa en güvenilir/resmî kaynağı önceliklendir ve gerekiyorsa belirsizliği tek cümleyle belirt.
- Kesin olmayan bilgiyi kesinmiş gibi sunma.
"""
    if username == "betul":
        return common + """
BETÜL KARAKTERİ:
- Samimi, eğlenceli, doğal ve hafif takılmacı konuş.
- Mizahı cevabın önüne geçirme; önce doğru bilgiyi ver.
- Güncel haberlerde önemli olayı kısa ve anlaşılır söyle, ardından en fazla kısa bir Betül yorumu ekle.
- Hava durumunda önce sıcaklık ve yağış bilgisini söyle, sonra kısa bir günlük öneri ver.
- Gereksiz 'aşko/kız' tekrarlarından kaçın; doğal kullan.
"""
    if username == "sude":
        return common + """
SUDE KARAKTERİ:
- Neşeli, destekleyici, yargılamayan ve sıcak konuş.
- Sağlıklı beslenme hedeflerinde aşırı kısıtlamayı veya hızlı kilo kaybını teşvik etme.
- Kalori değerlerinin yaklaşık olduğunu ve porsiyona göre değiştiğini belirt.
- Oyun, bilmece ve günlük hedeflerde motive edici ol.
"""
    if username == "sinem":
        return common + """
SİNEM KARAKTERİ:
- Sıcak, doğal, sakin ve arkadaşça konuş.
- Bilgiyi sade şekilde ver; abartılı ifadeler ve gereksiz şaka kullanma.
- Güncel bilgilerde kullanıcı için önemli sonucu öne çıkar.
- Hava durumunda kısa pratik öneri ver.
"""
    if username == "ilknur":
        return common + """
İLKNUR AKADEMİK KARAKTERİ:
- Kullanıcıya 'Hocam' diye hitap et.
- Akademik ve araştırma sorularında güvenilir kaynaklara dayalı, düzenli ve ölçülü konuş.
- Günlük sorularda gereksiz akademik dil kullanma.
- Hava durumu ve gündem gibi günlük güncel sorularda kısa ve doğal cevap ver.
"""
    return common + """
KARAHAN KARAKTERİ:
- Profesyonel, teknik, net ve doğrudan konuş.
- Önce sonucu, gerekiyorsa ardından önemli ayrıntıyı ver.
- Güncel olaylarda tarih, yer ve temel gelişmeyi kısa biçimde belirt.
- Hava durumunda sıcaklık, yağış ve gerekiyorsa dışarı çıkma önerisini kısa ver.
"""


def perform_smart_research(message, username, mode):
    """Yalnızca needs_web_research() True olduğunda çağrılır."""
    raw_message = clean_text(message)
    lowered = raw_message.lower()
    explicit_search = bool(re.search(
        r"\b(internette|internetten|webde|web'de|google'da|google)\b.{0,100}\b(ara|araştır|bak|bul)\b",
        lowered, re.IGNORECASE
    ))

    if explicit_search:
        subject = lowered
        for pattern in [
            r"\binternette\b", r"\binternetten\b", r"\bweb'de\b",
            r"\bwebde\b", r"\bgoogle'da\b", r"\bgoogle\b",
            r"\baraştır\b", r"\bara\b", r"\bbak\b", r"\bbul\b",
            r"\blütfen\b", r"\bkarvis\b",
        ]:
            subject = re.sub(pattern, " ", subject, flags=re.IGNORECASE)
        subject = clean_text(subject).strip(" .,!?:;-")
        if subject:
            query = f"{subject} ürünler modeller fiyatlar Türkiye"
        else:
            query = build_profile_research_query(raw_message, username, mode)
    else:
        query = build_profile_research_query(raw_message, username, mode)

    sources = research_topic(query)

    context = format_sources_for_ai(sources)
    if not sources:
        save_error(
            "Web araştırması sonuç döndürmedi",
            f"Kullanıcı isteği: {raw_message!r}; arama sorgusu: {query!r}. Tavily ve Wikipedia kaynaklarından kullanılabilir sonuç gelmedi.",
            category="web_search", severity="warning",
            path="/chat", method="POST",
        )
        context = (
            "CANLI WEB ARAŞTIRMASI DENENDİ ANCAK BU İSTEK İÇİN DOĞRULANABİLİR "
            "ARAMA SONUCU ALINAMADI. Kullanıcıya internet erişimi kesinlikle yokmuş "
            "gibi genelleme yapma. Aramanın bu istekte sonuç döndürmediğini açıkça "
            "söyle; güncel ürün/fiyat/özellik bilgisi uydurma."
        )

    return {
        "query": query,
        "sources": sources,
        "context": context
    }


def format_research_sources_for_user(sources):
    if not sources:
        return ""

    lines = ["\n\nKaynaklar:"]
    for i, source in enumerate(sources[:6], 1):
        title = clean_text(source.get("title", "Kaynak"))
        url = source.get("url", "").strip()
        if url:
            lines.append(f"[{i}] {title} — {url}")

    return "\n".join(lines)



# ============================================================
# PRESENTATION FALLBACK
# ============================================================

def fallback_presentation(
    topic,
    slide_count
):

    content_count = max(
        3,
        slide_count - 2
    )

    templates = [

        (
            "Temel Kavramlar",
            f"{topic} konusunun temel kavramları, kapsamı ve ana bileşenleri açıklanmaktadır."
        ),

        (
            "Tarihsel Gelişim",
            f"{topic} konusunun ortaya çıkışı ve tarihsel gelişimindeki önemli değişimler ele alınmaktadır."
        ),

        (
            "Temel Unsurlar",
            f"{topic} başlığını oluşturan temel unsurlar ve bu unsurlar arasındaki ilişkiler incelenmektedir."
        ),

        (
            "Uygulama Alanları",
            f"{topic} kapsamında kullanılan başlıca yöntemler, uygulamalar ve kullanım alanları değerlendirilmektedir."
        ),

        (
            "Etkileri",
            f"{topic} konusunun bireyler, toplum ve ilgili kurumlar üzerindeki başlıca etkileri açıklanmaktadır."
        ),

        (
            "Günümüzdeki Önemi",
            f"{topic} konusunun günümüzdeki önemi ve değişen koşullar karşısındaki konumu değerlendirilmektedir."
        ),

        (
            "Genel Değerlendirme",
            f"{topic} açısından temel bulgular ve öne çıkan noktalar bütüncül biçimde değerlendirilmektedir."
        )
    ]

    slides = []

    for i in range(
        content_count
    ):

        title, paragraph = templates[
            i % len(templates)
        ]

        slides.append({

            "title":
                title,

            "paragraph":
                paragraph,

            "visual_query":
                f"{topic} {title} documentary academic",

            "sources":
                []
        })

    return {

        "title":
            topic,

        "subtitle":
            "Akademik Sunum",

        "cover_visual_query":
            f"{topic} academic professional",

        "slides":
            slides,

        "conclusion": {

            "title":
                "Sonuç ve Değerlendirme",

            "paragraph":
                f"{topic} farklı boyutlarıyla değerlendirildiğinde, temel kavramların, uygulamaların ve etkilerin birlikte ele alınmasının konunun bütüncül biçimde anlaşılması açısından önemli olduğu görülmektedir.",

            "visual_query":
                f"{topic} conclusion academic",

            "sources":
                []
        }
    }


# ============================================================
# TEXT SIMILARITY
# ============================================================

def normalize_similarity_text(
    text
):

    text = str(
        text or ""
    ).lower()

    text = re.sub(
        r"[^a-zA-Z0-9çğıöşüÇĞİÖŞÜ ]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def text_similarity(
    a,
    b
):

    a = normalize_similarity_text(
        a
    )

    b = normalize_similarity_text(
        b
    )

    if not a or not b:
        return 0

    return SequenceMatcher(
        None,
        a,
        b
    ).ratio()


def has_duplicate_content(
    paragraph,
    previous_paragraphs,
    threshold=0.68
):

    for previous in previous_paragraphs:

        if (
            text_similarity(
                paragraph,
                previous
            )
            >= threshold
        ):

            return True

    return False


# ============================================================
# PRESENTATION PLAN
# ============================================================

def create_presentation_plan(
    topic,
    slide_count,
    sources,
    progress_callback=None
):

    content_count = max(
        3,
        slide_count - 2
    )

    if progress_callback:

        progress_callback(
            31,
            "Sunumun slayt planı oluşturuluyor..."
        )

    source_text = format_sources_for_ai(
        sources
    )

    prompt = f"""
Bir üniversite düzeyinde akademik sunum için
SLAYT PLANI oluştur.

KONU:
{topic}

TOPLAM SLAYT:
{slide_count}

Yapı:

1 kapak
{content_count} içerik
1 sonuç

ÖNEMLİ:

Her içerik slaytının farklı bir amacı olmalı.

Aynı bilgiyi farklı başlıklarla tekrar etme.

Konuya uygun farklı boyutlar seç:

- tanım
- tarihsel gelişim
- yapı
- süreç
- uygulama
- örnek
- etkiler
- avantaj/dezavantaj
- güncel durum
- değerlendirme

KAYNAKLAR:

{source_text}

Yalnızca JSON döndür:

{{
  "title": "Ana sunum başlığı",
  "subtitle": "Akademik alt başlık",
  "cover_visual_query": "English image search query",
  "slides": [
    {{
      "title": "Slayt başlığı",
      "objective": "Bu slaytın anlatacağı özgün konu",
      "visual_query": "English image search query"
    }}
  ],
  "conclusion": {{
    "title": "Sonuç ve Değerlendirme",
    "objective": "Sunumun genel değerlendirmesi",
    "visual_query": "English image search query"
  }}
}}

Kurallar:

- Türkçe yaz.
- Tam olarak {content_count} içerik slaytı oluştur.
- Her objective birbirinden farklı olmalı.
- Aynı konuyu tekrar eden slayt oluşturma.
- Görsel sorguları birbirinden farklı olmalı.
- Görsel sorguları İngilizce olmalı.
- Sonuç slaytı önceki slaytların kopyası olmamalı.
- JSON dışında hiçbir şey yazma.
"""

    result = ask_ai(
        prompt,
        ACADEMIC_SYSTEM
    )

    data = extract_json(
        result
    )

    if not data:

        return fallback_presentation(
            topic,
            slide_count
        )

    raw_slides = data.get(
        "slides",
        []
    )

    clean_slides = []

    used_titles = set()

    for slide in raw_slides:

        if not isinstance(
            slide,
            dict
        ):
            continue

        title = str(
            slide.get(
                "title",
                ""
            )
        ).strip()

        objective = str(
            slide.get(
                "objective",
                ""
            )
        ).strip()

        visual_query = str(
            slide.get(
                "visual_query",
                ""
            )
        ).strip()

        if not title or not objective:
            continue

        title_key = normalize_similarity_text(
            title
        )

        if title_key in used_titles:
            continue

        used_titles.add(
            title_key
        )

        clean_slides.append({

            "title":
                title,

            "objective":
                objective,

            "visual_query":
                visual_query
                or
                f"{topic} {title} academic",
        })

    if len(clean_slides) < content_count:

        return fallback_presentation(
            topic,
            slide_count
        )

    clean_slides = clean_slides[
        :content_count
    ]

    conclusion_data = data.get(
        "conclusion",
        {}
    )

    if not isinstance(
        conclusion_data,
        dict
    ):

        conclusion_data = {}

    return {

        "title":
            str(
                data.get(
                    "title",
                    topic
                )
            ).strip()
            or topic,

        "subtitle":
            str(
                data.get(
                    "subtitle",
                    "Akademik Sunum"
                )
            ).strip()
            or "Akademik Sunum",

        "cover_visual_query":
            str(
                data.get(
                    "cover_visual_query",
                    f"{topic} academic professional"
                )
            ).strip(),

        "slides":
            clean_slides,

        "conclusion": {

            "title":
                str(
                    conclusion_data.get(
                        "title",
                        "Sonuç ve Değerlendirme"
                    )
                ).strip(),

            "objective":
                str(
                    conclusion_data.get(
                        "objective",
                        "Konunun genel değerlendirmesi"
                    )
                ).strip(),

            "visual_query":
                str(
                    conclusion_data.get(
                        "visual_query",
                        f"{topic} conclusion academic"
                    )
                ).strip()
        }
    }


# ============================================================
# INDIVIDUAL SLIDE CONTENT
# ============================================================

def generate_slide_content(
    topic,
    slide,
    sources,
    previous_paragraphs
):

    source_text = format_sources_for_ai(
        sources
    )

    prompt = f"""
Aşağıdaki akademik sunum için SADECE BU SLAYTIN
içeriğini oluştur.

ANA KONU:
{topic}

SLAYT BAŞLIĞI:
{slide["title"]}

BU SLAYTIN ÖZGÜN AMACI:
{slide["objective"]}

KAYNAKLAR:
{source_text}

ÖNCEKİ SLAYT METİNLERİ:
{chr(10).join(previous_paragraphs[-5:]) if previous_paragraphs else "Henüz yok."}

Bu slayt önceki slaytların tekrarını yapmamalıdır.

Kaynaklarda bulunmayan kesin istatistik, tarih,
kişi, kurum veya olay uydurma.

Akademik ama anlaşılır Türkçe kullan.

80-120 kelime civarında açıklama üret.

Görsel için İngilizce arama sorgusu oluştur.

Yalnızca JSON döndür:

{{
  "paragraph": "Slayt açıklaması",
  "visual_query": "English visual search query",
  "source_indexes": [1, 2]
}}

JSON dışında hiçbir şey yazma.
"""

    result = ask_ai(
        prompt,
        ACADEMIC_SYSTEM
    )

    data = extract_json(
        result
    )

    if not data:
        return None

    paragraph = str(
        data.get(
            "paragraph",
            ""
        )
    ).strip()

    visual_query = str(
        data.get(
            "visual_query",
            slide.get(
                "visual_query",
                f"{topic} academic"
            )
        )
    ).strip()

    source_indexes = data.get(
        "source_indexes",
        []
    )

    if not isinstance(
        source_indexes,
        list
    ):

        source_indexes = []

    selected_sources = []

    for index in source_indexes:

        try:

            index = int(
                index
            ) - 1

            if (
                0 <= index
                < len(sources)
            ):

                selected_sources.append(
                    sources[index]
                )

        except Exception:

            continue

    if not selected_sources:

        selected_sources = sources[:2]

    if not paragraph:

        return None

    return {

        "paragraph":
            paragraph,

        "visual_query":
            visual_query
            or
            slide.get(
                "visual_query",
                f"{topic} academic"
            ),

        "sources":
            selected_sources
    }


# ============================================================
# BUILD COMPLETE PRESENTATION
# ============================================================

def build_verified_presentation(
    topic,
    slide_count,
    progress_callback=None
):

    sources = research_topic(
        topic,
        progress_callback
    )

    if progress_callback:

        progress_callback(
            32,
            f"{len(sources)} kaynak bulundu. Bilgiler karşılaştırılıyor..."
        )

    plan = create_presentation_plan(
        topic,
        slide_count,
        sources,
        progress_callback
    )

    if progress_callback:

        progress_callback(
            36,
            "Slayt içerikleri hazırlanmaya başlanıyor..."
        )

    previous_paragraphs = []

    final_slides = []

    total_slides = len(
        plan["slides"]
    )

    for slide_index, slide in enumerate(
        plan["slides"],
        start=1
    ):

        if progress_callback:

            progress = 36 + int(
                (
                    slide_index - 1
                )
                /
                max(
                    1,
                    total_slides
                )
                * 12
            )

            progress_callback(
                progress,
                (
                    f"Slayt {slide_index}/{total_slides} "
                    "içeriği hazırlanıyor..."
                )
            )

        generated = generate_slide_content(
            topic,
            slide,
            sources,
            previous_paragraphs
        )

        if generated:

            duplicate = has_duplicate_content(
                generated["paragraph"],
                previous_paragraphs
            )

            if duplicate:

                if progress_callback:

                    progress_callback(
                        min(
                            48,
                            36 + slide_index * 2
                        ),
                        (
                            f"Slayt {slide_index} "
                            "özgünlük kontrolünden geçiriliyor..."
                        )
                    )

                regeneration_prompt = f"""
Bu slaytın metni önceki slaytlara fazla benziyor.

ANA KONU:
{topic}

SLAYT:
{slide["title"]}

AMAÇ:
{slide["objective"]}

YENİ METİN ÖNCEKİ SLAYTLARLA
ANLAM OLARAK ÇAKIŞMAMALI.

ÖNCEKİ METİNLER:

{chr(10).join(previous_paragraphs)}

Kaynaklara bağlı kal.

80-120 kelime arasında,
özgün ve akademik yeni bir açıklama yaz.

Yalnızca JSON:

{{
  "paragraph": "Yeni açıklama",
  "visual_query": "English image query"
}}
"""

                retry = ask_ai(
                    regeneration_prompt,
                    ACADEMIC_SYSTEM
                )

                retry_data = extract_json(
                    retry
                )

                if retry_data:

                    retry_paragraph = str(
                        retry_data.get(
                            "paragraph",
                            ""
                        )
                    ).strip()

                    if (
                        retry_paragraph
                        and
                        not has_duplicate_content(
                            retry_paragraph,
                            previous_paragraphs,
                            0.72
                        )
                    ):

                        generated[
                            "paragraph"
                        ] = retry_paragraph

                        generated[
                            "visual_query"
                        ] = str(
                            retry_data.get(
                                "visual_query",
                                generated[
                                    "visual_query"
                                ]
                            )
                        ).strip()

        if not generated:

            generated = {

                "paragraph":
                    slide["objective"],

                "visual_query":
                    slide["visual_query"],

                "sources":
                    sources[:2]
            }

        final_slide = {

            "title":
                slide["title"],

            "paragraph":
                generated["paragraph"],

            "visual_query":
                generated["visual_query"],

            "sources":
                generated.get(
                    "sources",
                    sources[:2]
                )
        }

        final_slides.append(
            final_slide
        )

        previous_paragraphs.append(
            final_slide["paragraph"]
        )

    if progress_callback:

        progress_callback(
            50,
            "İçerikler tamamlandı. Sonuç bölümü hazırlanıyor..."
        )

    conclusion = plan[
        "conclusion"
    ]

    conclusion_prompt = f"""
Bir akademik sunumun SONUÇ slaydını oluştur.

KONU:
{topic}

SONUÇ SLAYTININ AMACI:
{conclusion.get("objective", "")}

SUNUMDAKİ SLAYTLAR:

{chr(10).join(
    [
        f"- {slide['title']}: {slide['paragraph']}"
        for slide in final_slides
    ]
)}

KAYNAKLAR:

{format_sources_for_ai(sources)}

Kurallar:

- Önceki slaytların cümlelerini kopyalama.
- Yeni bilgi uydurma.
- Sunumda anlatılan ana noktaları sentezle.
- Akademik ve net Türkçe kullan.
- Yaklaşık 70-100 kelime.
- Görsel sorgusu İngilizce olsun.

Yalnızca JSON:

{{
  "paragraph": "Sonuç metni",
  "visual_query": "English conclusion visual query",
  "source_indexes": [1, 2]
}}
"""

    conclusion_result = ask_ai(
        conclusion_prompt,
        ACADEMIC_SYSTEM
    )

    conclusion_data = extract_json(
        conclusion_result
    )

    if conclusion_data:

        conclusion_paragraph = str(
            conclusion_data.get(
                "paragraph",
                ""
            )
        ).strip()

        conclusion_visual = str(
            conclusion_data.get(
                "visual_query",
                ""
            )
        ).strip()

    else:

        conclusion_paragraph = (
            "Sunum kapsamında ele alınan temel "
            "kavramlar, gelişim süreci, uygulamalar "
            "ve etkiler birlikte değerlendirildiğinde "
            "konunun çok boyutlu bir yapıya sahip "
            "olduğu görülmektedir."
        )

        conclusion_visual = (
            conclusion.get(
                "visual_query",
                f"{topic} conclusion academic"
            )
        )

    if progress_callback:

        progress_callback(
            55,
            "İçerikler doğrulandı. Görsel araştırma aşamasına geçiliyor..."
        )

    return {

        "title":
            plan["title"],

        "subtitle":
            plan["subtitle"],

        "cover_visual_query":
            plan["cover_visual_query"],

        "slides":
            final_slides,

        "conclusion": {

            "title":
                "Sonuç ve Değerlendirme",

            "paragraph":
                conclusion_paragraph,

            "visual_query":
                conclusion_visual,

            "sources":
                sources[:3]
        },

        "research_sources":
            sources
    }


# ============================================================
# IMAGE SEARCH
# ============================================================

IMAGE_HEADERS = {

    "User-Agent":
        "Mozilla/5.0 "
        "(X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "Chrome/140 Safari/537.36 "
        "K.A.R.V.I.S./32.0"
}


def get_wikimedia_candidates(
    query
):

    try:

        response = requests.get(

            "https://commons.wikimedia.org/w/api.php",

            params={

                "action":
                    "query",

                "generator":
                    "search",

                "gsrsearch":
                    query,

                "gsrnamespace":
                    6,

                "gsrlimit":
                    20,

                "prop":
                    "imageinfo",

                "iiprop":
                    "url|mime|size",

                "iiurlwidth":
                    1600,

                "format":
                    "json"
            },

            headers=IMAGE_HEADERS,

            timeout=15
        )

        if response.status_code != 200:
            return []

        pages = (
            response
            .json()
            .get("query", {})
            .get("pages", {})
        )

        results = []

        for page in pages.values():

            info = page.get(
                "imageinfo",
                []
            )

            if not info:
                continue

            item = info[0]

            image_url = (
                item.get(
                    "thumburl"
                )
                or
                item.get(
                    "url"
                )
            )

            mime = item.get(
                "mime",
                ""
            )

            if (
                image_url
                and
                mime.startswith(
                    "image/"
                )
            ):

                results.append(
                    image_url
                )

        return results

    except Exception:

        return []


def get_openverse_candidates(
    query
):

    try:

        response = requests.get(

            "https://api.openverse.org/v1/images/",

            params={

                "q":
                    query,

                "page_size":
                    20
            },

            headers=IMAGE_HEADERS,

            timeout=15
        )

        if response.status_code != 200:
            return []

        results = []

        for item in (
            response
            .json()
            .get(
                "results",
                []
            )
        ):

            url = (
                item.get(
                    "thumbnail"
                )
                or
                item.get(
                    "url"
                )
            )

            if url:
                results.append(
                    url
                )

        return results

    except Exception:

        return []


def get_google_candidates_api(
    query
):

    if not GOOGLE_IMAGE_API_KEY:
        return []

    if not GOOGLE_CSE_ID:
        return []

    try:

        response = requests.get(

            "https://www.googleapis.com/customsearch/v1",

            params={

                "key":
                    GOOGLE_IMAGE_API_KEY,

                "cx":
                    GOOGLE_CSE_ID,

                "q":
                    query,

                "searchType":
                    "image",

                "num":
                    3,

                "safe":
                    "active"
            },

            headers=IMAGE_HEADERS,

            timeout=15
        )

        if response.status_code != 200:
            return []

        items = (
            response
            .json()
            .get(
                "items",
                []
            )
        )

        return [

            item.get("link")

            for item in items[:3]

            if item.get("link")
        ]

    except Exception:

        return []


def get_google_candidates_html(
    query
):

    try:

        response = requests.get(

            "https://www.google.com/search",

            params={

                "tbm":
                    "isch",

                "q":
                    query,

                "safe":
                    "active",

                "hl":
                    "en"
            },

            headers=IMAGE_HEADERS,

            timeout=15
        )

        if response.status_code != 200:
            return []

        html = response.text

        candidates = []

        patterns = [

            r'"(https?://[^"\\]+?\.(?:jpg|jpeg|png|webp)(?:\?[^"\\]*)?)"',

            r'"(https?://[^"\\]+?\.(?:JPG|JPEG|PNG|WEBP)(?:\?[^"\\]*)?)"'
        ]

        for pattern in patterns:

            matches = re.findall(
                pattern,
                html,
                flags=re.IGNORECASE
            )

            for match in matches:

                url = (
                    match
                    .replace(
                        "\\u003d",
                        "="
                    )
                    .replace(
                        "\\u0026",
                        "&"
                    )
                )

                if (
                    url.startswith(
                        "http"
                    )
                    and
                    url not in candidates
                ):

                    candidates.append(
                        url
                    )

                if len(candidates) >= 3:

                    return candidates[:3]

        return candidates[:3]

    except Exception:

        return []


def get_google_candidates(
    query
):

    results = get_google_candidates_api(
        query
    )

    if results:

        return results[:3]

    return get_google_candidates_html(
        query
    )[:3]


# ============================================================
# IMAGE QUALITY
# ============================================================

def image_hash(
    image
):

    try:

        small = (
            image
            .convert("RGB")
            .resize(
                (96,96)
            )
        )

        return hashlib.sha256(
            small.tobytes()
        ).hexdigest()

    except Exception:

        return None


def image_quality_score(
    image
):

    try:

        width, height = image.size

        if width < 500:
            return 0

        if height < 300:
            return 0

        ratio = width / height

        score = 0

        if (
            1.2 <= ratio <= 2.2
        ):

            score += 30

        if width >= 1000:

            score += 30

        elif width >= 700:

            score += 20

        if height >= 600:

            score += 20

        elif height >= 400:

            score += 10

        if (
            ratio < 0.7
            or
            ratio > 3.0
        ):

            score -= 30

        return score

    except Exception:

        return 0


def download_image_unique(
    url,
    used_urls,
    used_hashes,
    lock
):

    try:

        with lock:

            if url in used_urls:

                return None

        response = requests.get(

            url,

            headers=IMAGE_HEADERS,

            timeout=20
        )

        if response.status_code != 200:
            return None

        content_type = (
            response.headers
            .get(
                "Content-Type",
                ""
            )
            .lower()
        )

        if (
            content_type
            and
            not content_type.startswith(
                "image/"
            )
        ):

            return None

        image = Image.open(
            BytesIO(
                response.content
            )
        )

        image.load()

        if (
            image.width < 400
            or
            image.height < 250
        ):

            return None

        quality = image_quality_score(
            image
        )

        if quality <= 0:
            return None

        h = image_hash(
            image
        )

        if not h:
            return None

        with lock:

            if url in used_urls:
                return None

            if h in used_hashes:
                return None

            used_urls.add(
                url
            )

            used_hashes.add(
                h
            )

        return image.convert(
            "RGB"
        )

    except Exception:

        return None


# ============================================================
# IMAGE PIPELINE
# ============================================================

def expand_image_queries(
    topic,
    title,
    visual_query
):

    queries = []

    if visual_query:

        queries.append(
            visual_query
        )

    queries.append(
        f"{topic} {title} documentary"
    )

    queries.append(
        f"{topic} {title} photograph"
    )

    queries.append(
        f"{topic} {title} academic"
    )

    result = []

    seen = set()

    for query in queries:

        query = query.strip()

        if not query:
            continue

        key = query.lower()

        if key in seen:
            continue

        seen.add(
            key
        )

        result.append(
            query
        )

    return result


def find_unique_image(
    queries,
    used_urls,
    used_hashes,
    lock
):

    candidate_urls = []

    for query in queries:

        candidate_urls.extend(
            get_wikimedia_candidates(
                query
            )
        )

        if len(candidate_urls) >= 30:
            break

    if len(candidate_urls) < 8:

        for query in queries:

            candidate_urls.extend(
                get_openverse_candidates(
                    query
                )
            )

            if len(candidate_urls) >= 30:
                break

    if len(candidate_urls) < 8:

        for query in queries:

            candidate_urls.extend(
                get_google_candidates(
                    query
                )[:3]
            )

            if len(candidate_urls) >= 15:
                break

    unique_urls = []

    seen = set()

    for url in candidate_urls:

        if not url:
            continue

        if url in seen:
            continue

        seen.add(
            url
        )

        unique_urls.append(
            url
        )

    for url in unique_urls:

        image = download_image_unique(
            url,
            used_urls,
            used_hashes,
            lock
        )

        if image is not None:

            return image

    return None


# ============================================================
# FONT
# ============================================================

def find_font(
    bold=False
):

    if bold:

        candidates = [

            BASE_DIR /
            "fonts" /
            "DejaVuSans-Bold.ttf",

            Path(
                "/usr/share/fonts/"
                "truetype/dejavu/"
                "DejaVuSans-Bold.ttf"
            ),

            Path(
                "/usr/share/fonts/"
                "truetype/liberation2/"
                "LiberationSans-Bold.ttf"
            )
        ]

    else:

        candidates = [

            BASE_DIR /
            "fonts" /
            "DejaVuSans.ttf",

            Path(
                "/usr/share/fonts/"
                "truetype/dejavu/"
                "DejaVuSans.ttf"
            ),

            Path(
                "/usr/share/fonts/"
                "truetype/liberation2/"
                "LiberationSans-Regular.ttf"
            )
        ]

    for path in candidates:

        if path.exists():

            return str(
                path
            )

    return None


FONT_REGULAR = find_font(
    False
)

FONT_BOLD = find_font(
    True
)


def karvis_font(
    size,
    bold=False
):

    path = (
        FONT_BOLD
        if bold
        else FONT_REGULAR
    )

    try:

        if path:

            return ImageFont.truetype(
                path,
                max(
                    8,
                    int(size)
                )
            )

    except Exception:

        pass

    return ImageFont.load_default()


# ============================================================
# TEXT FITTING
# ============================================================

def text_width(
    draw,
    text,
    font
):

    try:

        return draw.textlength(
            text,
            font=font
        )

    except Exception:

        try:

            box = draw.textbbox(
                (0,0),
                text,
                font=font
            )

            return (
                box[2] -
                box[0]
            )

        except Exception:

            return (
                len(text)
                *
                max(
                    8,
                    getattr(
                        font,
                        "size",
                        12
                    ) * 0.55
                )
            )


def font_line_height(
    font,
    extra=0
):

    size = max(
        8,
        int(
            getattr(
                font,
                "size",
                20
            )
        )
    )

    return size + extra


def wrap_pixel_text(
    draw,
    text,
    font,
    max_width
):

    words = (
        str(text or "")
        .replace(
            "\n",
            " \n "
        )
        .split()
    )

    lines = []

    current = ""

    for word in words:

        if word == "\\n":

            if current:

                lines.append(
                    current
                )

                current = ""

            continue

        candidate = (
            word
            if not current
            else
            current + " " + word
        )

        if (
            text_width(
                draw,
                candidate,
                font
            )
            <= max_width
        ):

            current = candidate

            continue

        if current:

            lines.append(
                current
            )

        if (
            text_width(
                draw,
                word,
                font
            )
            <= max_width
        ):

            current = word

        else:

            chunk = ""

            for ch in word:

                test = chunk + ch

                if (
                    text_width(
                        draw,
                        test,
                        font
                    )
                    <= max_width
                ):

                    chunk = test

                else:

                    if chunk:

                        lines.append(
                            chunk
                        )

                    chunk = ch

            current = chunk

    if current:

        lines.append(
            current
        )

    return lines


def truncate_lines(
    draw,
    lines,
    font,
    max_width,
    max_lines
):

    if len(lines) <= max_lines:

        return lines

    lines = lines[
        :max_lines
    ]

    last = lines[-1]

    ellipsis = "…"

    while (
        last
        and
        text_width(
            draw,
            last + ellipsis,
            font
        ) > max_width
    ):

        last = last[:-1]

    lines[-1] = (
        last.rstrip()
        +
        ellipsis
        if last
        else
        ellipsis
    )

    return lines


def fit_text(
    draw,
    text,
    max_width,
    max_height,
    start_size,
    min_size=14,
    bold=False,
    spacing_ratio=0.30
):

    text = str(
        text or ""
    ).strip()

    if not text:

        return (
            karvis_font(
                start_size,
                bold
            ),
            [],
            0
        )

    size = int(
        start_size
    )

    while size >= min_size:

        font = karvis_font(
            size,
            bold
        )

        spacing = max(
            4,
            int(
                size *
                spacing_ratio
            )
        )

        lines = wrap_pixel_text(
            draw,
            text,
            font,
            max_width
        )

        line_h = font_line_height(
            font,
            spacing
        )

        max_lines = max(
            1,
            int(
                max_height //
                line_h
            )
        )

        if len(lines) <= max_lines:

            return (
                font,
                lines,
                spacing
            )

        size -= 1

    font = karvis_font(
        min_size,
        bold
    )

    spacing = max(
        4,
        int(
            min_size *
            spacing_ratio
        )
    )

    lines = wrap_pixel_text(
        draw,
        text,
        font,
        max_width
    )

    line_h = font_line_height(
        font,
        spacing
    )

    max_lines = max(
        1,
        int(
            max_height //
            line_h
        )
    )

    lines = truncate_lines(
        draw,
        lines,
        font,
        max_width,
        max_lines
    )

    return (
        font,
        lines,
        spacing
    )


def draw_fit_text(
    draw,
    text,
    xy,
    max_width,
    max_height,
    start_size,
    min_size=14,
    fill=(255,255,255),
    bold=False,
    spacing_ratio=0.30
):

    font, lines, spacing = fit_text(
        draw,
        text,
        max_width,
        max_height,
        start_size,
        min_size,
        bold,
        spacing_ratio
    )

    x, y = xy

    line_h = font_line_height(
        font,
        spacing
    )

    for line in lines:

        draw.text(
            (x,y),
            line,
            font=font,
            fill=fill
        )

        y += line_h

    return (
        y,
        font,
        lines
    )


# ============================================================
# IMAGE DESIGN
# ============================================================

def rounded_mask(
    size,
    radius
):

    mask = Image.new(
        "L",
        size,
        0
    )

    ImageDraw.Draw(
        mask
    ).rounded_rectangle(
        (
            0,
            0,
            size[0],
            size[1]
        ),
        radius=radius,
        fill=255
    )

    return mask


def prepare_image(
    image,
    size
):

    return ImageOps.fit(
        image.convert(
            "RGB"
        ),
        size,
        method=Image.Resampling.LANCZOS,
        centering=(0.5,0.5)
    )


def paste_round_image(
    base,
    image,
    box,
    radius=30
):

    x,y,w,h = box

    image = prepare_image(
        image,
        (w,h)
    )

    base.paste(
        image,
        (x,y),
        rounded_mask(
            (w,h),
            radius
        )
    )


# ============================================================
# SLIDE DESIGN
# ============================================================

SLIDE_WIDTH = 1600
SLIDE_HEIGHT = 900

PDF_WIDTH = 16 * inch
PDF_HEIGHT = 9 * inch


def create_cover_slide(
    title,
    subtitle,
    image,
    output_path
):

    img = Image.new(
        "RGB",
        (
            SLIDE_WIDTH,
            SLIDE_HEIGHT
        ),
        (5,10,18)
    )

    if image is not None:

        bg = prepare_image(
            image,
            (
                SLIDE_WIDTH,
                SLIDE_HEIGHT
            )
        )

        dark = Image.new(
            "RGBA",
            bg.size,
            (2,7,13,165)
        )

        img = Image.alpha_composite(
            bg.convert("RGBA"),
            dark
        ).convert(
            "RGB"
        )

    draw = ImageDraw.Draw(
        img
    )

    draw.rectangle(
        (80,75,410,81),
        fill=(0,229,255)
    )

    draw.text(
        (80,110),
        "K.A.R.V.I.S.",
        font=karvis_font(
            26,
            True
        ),
        fill=(0,229,255)
    )

    draw.text(
        (80,148),
        "KARAHAN INC.",
        font=karvis_font(
            17
        ),
        fill=(160,175,190)
    )

    draw_fit_text(
        draw,
        title,
        (80,275),
        1050,
        275,
        72,
        38,
        fill=(245,250,255),
        bold=True,
        spacing_ratio=0.18
    )

    draw_fit_text(
        draw,
        subtitle,
        (85,570),
        980,
        95,
        28,
        18,
        fill=(180,195,210),
        bold=False,
        spacing_ratio=0.20
    )

    draw.text(
        (80,810),
        "AKADEMİK SUNUM",
        font=karvis_font(
            18,
            True
        ),
        fill=(0,229,255)
    )

    draw.text(
        (80,845),
        "K.A.R.V.I.S. • KARAHAN INC.",
        font=karvis_font(
            15
        ),
        fill=(110,125,140)
    )

    img.save(
        output_path,
        "PNG",
        optimize=True
    )


def format_source_footer(
    sources,
    max_sources=2
):

    if not sources:

        return (
            "Kaynak: K.A.R.V.I.S. araştırma motoru"
        )

    names = []

    for source in sources[
        :max_sources
    ]:

        title = source.get(
            "title",
            ""
        ).strip()

        if title:

            names.append(
                title
            )

    if not names:

        return (
            "Kaynak: K.A.R.V.I.S."
        )

    return (
        "Kaynak: "
        +
        " • ".join(
            names
        )
    )


def create_content_slide(
    slide_number,
    total_slides,
    title,
    paragraph,
    image,
    sources,
    output_path
):

    img = Image.new(
        "RGB",
        (
            SLIDE_WIDTH,
            SLIDE_HEIGHT
        ),
        (5,11,19)
    )

    draw = ImageDraw.Draw(
        img
    )

    draw.rectangle(
        (70,55,1530,58),
        fill=(18,45,58)
    )

    draw.rectangle(
        (70,55,280,58),
        fill=(0,229,255)
    )

    draw.text(
        (70,82),
        "K.A.R.V.I.S.",
        font=karvis_font(
            21,
            True
        ),
        fill=(0,229,255)
    )

    draw.text(
        (70,111),
        "KARAHAN INC.",
        font=karvis_font(
            14
        ),
        fill=(110,130,145)
    )

    draw_fit_text(
        draw,
        title,
        (70,165),
        700,
        105,
        45,
        24,
        fill=(245,250,255),
        bold=True,
        spacing_ratio=0.18
    )

    left_x = 70
    left_y = 300
    left_w = 700
    left_h = 500

    draw.rounded_rectangle(
        (
            left_x,
            left_y,
            left_x + left_w,
            left_y + left_h
        ),
        radius=28,
        fill=(10,20,30),
        outline=(22,48,62),
        width=2
    )

    draw.text(
        (105,335),
        "AKADEMİK AÇIKLAMA",
        font=karvis_font(
            18,
            True
        ),
        fill=(0,229,255)
    )

    draw.rectangle(
        (105,372,190,376),
        fill=(0,229,255)
    )

    draw_fit_text(
        draw,
        paragraph,
        (105,415),
        625,
        335,
        25,
        13,
        fill=(215,225,235),
        bold=False,
        spacing_ratio=0.30
    )

    image_x = 825
    image_y = 165
    image_w = 705
    image_h = 635

    draw.rounded_rectangle(
        (
            image_x,
            image_y,
            image_x + image_w,
            image_y + image_h
        ),
        radius=32,
        fill=(9,18,27),
        outline=(25,51,65),
        width=2
    )

    if image is not None:

        paste_round_image(
            img,
            image,
            (
                image_x + 10,
                image_y + 10,
                image_w - 20,
                image_h - 20
            ),
            25
        )

    else:

        draw.text(
            (
                image_x + 220,
                image_y + 280
            ),
            "K.A.R.V.I.S.",
            font=karvis_font(
                42,
                True
            ),
            fill=(0,229,255)
        )

    source_text = format_source_footer(
        sources
    )

    draw_fit_text(
        draw,
        source_text,
        (70,805),
        1250,
        28,
        12,
        9,
        fill=(100,120,135),
        bold=False,
        spacing_ratio=0.10
    )

    draw.text(
        (70,842),
        "K.A.R.V.I.S. • KARAHAN INC.",
        font=karvis_font(
            15
        ),
        fill=(90,110,125)
    )

    draw.text(
        (1430,842),
        f"{slide_number:02d} / {total_slides:02d}",
        font=karvis_font(
            16,
            True
        ),
        fill=(0,229,255)
    )

    img.save(
        output_path,
        "PNG",
        optimize=True
    )


def create_conclusion_slide(
    total_slides,
    title,
    paragraph,
    image,
    sources,
    output_path
):

    img = Image.new(
        "RGB",
        (
            SLIDE_WIDTH,
            SLIDE_HEIGHT
        ),
        (5,11,19)
    )

    draw = ImageDraw.Draw(
        img
    )

    draw.rectangle(
        (70,55,1530,58),
        fill=(18,45,58)
    )

    draw.rectangle(
        (70,55,520,58),
        fill=(0,229,255)
    )

    draw.text(
        (70,90),
        "K.A.R.V.I.S.",
        font=karvis_font(
            22,
            True
        ),
        fill=(0,229,255)
    )

    draw.text(
        (70,120),
        "KARAHAN INC.",
        font=karvis_font(
            14
        ),
        fill=(110,130,145)
    )

    draw_fit_text(
        draw,
        title,
        (70,205),
        750,
        85,
        54,
        30,
        fill=(245,250,255),
        bold=True,
        spacing_ratio=0.18
    )

    draw.rounded_rectangle(
        (70,310,820,750),
        radius=30,
        fill=(10,20,30),
        outline=(22,48,62),
        width=2
    )

    draw.text(
        (110,350),
        "SONUÇ VE DEĞERLENDİRME",
        font=karvis_font(
            19,
            True
        ),
        fill=(0,229,255)
    )

    draw_fit_text(
        draw,
        paragraph,
        (110,405),
        650,
        300,
        27,
        13,
        fill=(220,230,238),
        bold=False,
        spacing_ratio=0.30
    )

    if image is not None:

        paste_round_image(
            img,
            image,
            (
                880,
                185,
                620,
                565
            ),
            35
        )

    else:

        draw.rounded_rectangle(
            (
                880,
                185,
                1500,
                750
            ),
            radius=35,
            fill=(8,22,31),
            outline=(0,229,255),
            width=2
        )

        draw.text(
            (1050,430),
            "K.A.R.V.I.S.",
            font=karvis_font(
                42,
                True
            ),
            fill=(0,229,255)
        )

    source_text = format_source_footer(
        sources,
        3
    )

    draw_fit_text(
        draw,
        source_text,
        (70,805),
        1250,
        28,
        12,
        9,
        fill=(100,120,135),
        bold=False,
        spacing_ratio=0.10
    )

    draw.text(
        (70,835),
        "K.A.R.V.I.S. • KARAHAN INC.",
        font=karvis_font(
            15
        ),
        fill=(90,110,125)
    )

    draw.text(
        (1430,835),
        f"{total_slides:02d} / {total_slides:02d}",
        font=karvis_font(
            16,
            True
        ),
        fill=(0,229,255)
    )

    img.save(
        output_path,
        "PNG",
        optimize=True
    )


# ============================================================
# PDF
# ============================================================

def create_presentation_pdf(
    presentation_id,
    outline,
    images,
    progress_callback=None
):

    title = outline[
        "title"
    ]

    subtitle = outline.get(
        "subtitle",
        "Akademik Sunum"
    )

    slides = outline[
        "slides"
    ]

    conclusion = outline[
        "conclusion"
    ]

    total_slides = len(
        slides
    ) + 2

    presentation_dir = (
        GENERATED_DIR
        /
        f"presentation_{presentation_id}"
    )

    slides_dir = (
        presentation_dir
        /
        "slides"
    )

    slides_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    slide_paths = []

    if progress_callback:

        progress_callback(
            82,
            "Kapak ve slayt tasarımları hazırlanıyor..."
        )

    cover_path = (
        slides_dir
        /
        "slide_01.png"
    )

    create_cover_slide(
        title,
        subtitle,
        images.get(
            "cover"
        ),
        str(
            cover_path
        )
    )

    slide_paths.append(
        cover_path
    )

    content_total = len(
        slides
    )

    for index, slide in enumerate(
        slides,
        start=2
    ):

        if progress_callback:

            progress_callback(
                82 +
                int(
                    (
                        index - 1
                    )
                    /
                    max(
                        1,
                        content_total + 1
                    )
                    * 10
                ),
                (
                    f"Slayt tasarımı hazırlanıyor "
                    f"({index - 1}/{content_total})..."
                )
            )

        slide_path = (
            slides_dir
            /
            f"slide_{index:02d}.png"
        )

        create_content_slide(
            slide_number=index,
            total_slides=total_slides,
            title=slide[
                "title"
            ],
            paragraph=slide[
                "paragraph"
            ],
            image=images.get(
                f"slide_{index}"
            ),
            sources=slide.get(
                "sources",
                []
            ),
            output_path=str(
                slide_path
            )
        )

        slide_paths.append(
            slide_path
        )

    if progress_callback:

        progress_callback(
            94,
            "Sonuç slaytı hazırlanıyor..."
        )

    conclusion_path = (
        slides_dir
        /
        f"slide_{total_slides:02d}.png"
    )

    create_conclusion_slide(
        total_slides=total_slides,
        title=conclusion[
            "title"
        ],
        paragraph=conclusion[
            "paragraph"
        ],
        image=images.get(
            "conclusion"
        ),
        sources=conclusion.get(
            "sources",
            []
        ),
        output_path=str(
            conclusion_path
        )
    )

    slide_paths.append(
        conclusion_path
    )

    if progress_callback:

        progress_callback(
            96,
            "PDF dosyası oluşturuluyor..."
        )

    pdf_filename = (
        f"karvis_sunum_{presentation_id}.pdf"
    )

    pdf_path = (
        GENERATED_DIR
        /
        pdf_filename
    )

    pdf = canvas.Canvas(
        str(pdf_path),
        pagesize=(
            PDF_WIDTH,
            PDF_HEIGHT
        )
    )

    for path in slide_paths:

        pdf.drawImage(
            str(path),
            0,
            0,
            width=PDF_WIDTH,
            height=PDF_HEIGHT,
            preserveAspectRatio=False,
            mask="auto"
        )

        pdf.showPage()

    pdf.save()

    if progress_callback:

        progress_callback(
            99,
            "Bitirmek üzereyim..."
        )

    return pdf_filename


# ============================================================
# PRESENTATION JOB SYSTEM
# ============================================================

PRESENTATION_JOBS = {}

presentation_lock = threading.Lock()


def create_job():

    job_id = uuid.uuid4().hex

    with presentation_lock:

        PRESENTATION_JOBS[
            job_id
        ] = {

            "id":
                job_id,

            "status":
                "queued",

            "stage":
                "analysis",

            "progress":
                0,

            "message":
                "Sunum hazırlanıyor...",

            "file":
                None,

            "download_url":
                None,

            "error":
                None
        }

    return job_id


def update_job(
    job_id,
    **kwargs
):

    with presentation_lock:

        if (
            job_id
            in PRESENTATION_JOBS
        ):

            PRESENTATION_JOBS[
                job_id
            ].update(
                kwargs
            )


def worker_progress(
    job_id,
    progress,
    message,
    stage=None
):

    if stage is None:

        if progress <= 8:

            stage = "analysis"

        elif progress < 35:

            stage = "research"

        elif progress < 55:

            stage = "content"

        elif progress < 76:

            stage = "visuals"

        elif progress < 88:

            stage = "design"

        elif progress < 98:

            stage = "pdf"

        else:

            stage = "finish"

    update_job(

        job_id,

        status="working",

        progress=max(
            0,
            min(
                100,
                int(progress)
            )
        ),

        stage=stage,

        message=message
    )


# ============================================================
# PRESENTATION WORKER
# ============================================================

def presentation_worker(
    job_id,
    topic,
    slide_count
):

    try:

        # ----------------------------------------------------
        # START
        # ----------------------------------------------------

        worker_progress(
            job_id,
            3,
            "Konu analiz ediliyor...",
            "analysis"
        )

        time.sleep(
            0.15
        )

        worker_progress(
            job_id,
            7,
            "Sunum yapısı belirleniyor...",
            "analysis"
        )

        # ----------------------------------------------------
        # RESEARCH + CONTENT
        # ----------------------------------------------------

        outline = (
            build_verified_presentation(
                topic,
                slide_count,

                progress_callback=lambda p, m:
                    worker_progress(
                        job_id,
                        p,
                        m
                    )
            )
        )

        slides = outline[
            "slides"
        ]

        research_sources = outline.get(
            "research_sources",
            []
        )

        worker_progress(
            job_id,
            35,
            (
                f"{len(research_sources)} "
                "kaynak üzerinden içerik doğrulanıyor..."
            ),
            "content"
        )

        time.sleep(
            0.10
        )

        # ----------------------------------------------------
        # IMAGE SEARCH
        # ----------------------------------------------------

        worker_progress(
            job_id,
            40,
            "Fotoğraflar araştırılıyor...",
            "visuals"
        )

        used_urls = set()
        used_hashes = set()

        lock = threading.Lock()

        image_tasks = {}

        image_tasks[
            "cover"
        ] = [

            outline.get(
                "cover_visual_query",
                topic
            )
        ]

        for index, slide in enumerate(
            slides,
            start=2
        ):

            image_tasks[
                f"slide_{index}"
            ] = expand_image_queries(

                topic,

                slide[
                    "title"
                ],

                slide.get(
                    "visual_query",
                    ""
                )
            )

        image_tasks[
            "conclusion"
        ] = expand_image_queries(

            topic,

            "conclusion",

            outline[
                "conclusion"
            ].get(
                "visual_query",
                f"{topic} conclusion"
            )
        )

        images = {}

        total_tasks = len(
            image_tasks
        )

        completed = 0

        # ----------------------------------------------------
        # PARALLEL IMAGE SEARCH
        # ----------------------------------------------------

        with ThreadPoolExecutor(
            max_workers=4
        ) as executor:

            futures = {

                executor.submit(
                    find_unique_image,

                    queries,

                    used_urls,

                    used_hashes,

                    lock

                ):
                    key

                for key, queries
                in image_tasks.items()
            }

            for future in as_completed(
                futures
            ):

                key = futures[
                    future
                ]

                try:

                    images[key] = (
                        future.result()
                    )

                except Exception:

                    images[key] = None

                completed += 1

                progress = (
                    40
                    +
                    int(
                        completed
                        /
                        max(
                            1,
                            total_tasks
                        )
                        *
                        35
                    )
                )

                worker_progress(

                    job_id,

                    progress,

                    (
                        "Fotoğraflar araştırılıyor "
                        f"({completed}/{total_tasks})..."
                    ),

                    "visuals"
                )

        # ----------------------------------------------------
        # VISUAL CHECK
        # ----------------------------------------------------

        worker_progress(
            job_id,
            76,
            "Görseller kontrol ediliyor...",
            "design"
        )

        worker_progress(
            job_id,
            78,
            "Profesyonel slaytlar oluşturuluyor...",
            "design"
        )

        # ----------------------------------------------------
        # PDF
        # ----------------------------------------------------

        pdf_filename = (
            create_presentation_pdf(

                job_id,

                outline,

                images,

                progress_callback=lambda p, m:
                    worker_progress(
                        job_id,
                        p,
                        m
                    )
            )
        )

        # ----------------------------------------------------
        # FINAL
        # ----------------------------------------------------

        worker_progress(
            job_id,
            99,
            "Bitirmek üzereyim...",
            "finish"
        )

        time.sleep(
            0.15
        )

        update_job(

            job_id,

            status="completed",

            stage="finish",

            progress=100,

            message=
                "Sunum hazırlandı.",

            file=
                pdf_filename,

            download_url=
                f"/generated/{pdf_filename}"
        )

    except Exception as e:

        save_error(
            "Presentation worker error",
            traceback.format_exc()
        )

        update_job(

            job_id,

            status="error",

            stage="error",

            progress=0,

            message=
                "Sunum oluşturulamadı.",

            error=
                str(e)
        )


# ============================================================
# HOME
# ============================================================

@app.get("/")
async def home():

    if not INDEX_FILE.exists():

        return JSONResponse({

            "app":
                "K.A.R.V.I.S.",

            "version":
                APP_VERSION,

            "status":
                "online"
        })

    return FileResponse(
        INDEX_FILE
    )


@app.get("/service-worker.js")
async def service_worker():
    file = BASE_DIR / "service-worker.js"
    if not file.exists():
        raise HTTPException(status_code=404, detail="Service worker bulunamadı.")
    return FileResponse(file, media_type="application/javascript")


@app.get("/manifest.json")
async def manifest():
    file = BASE_DIR / "manifest.json"
    if not file.exists():
        raise HTTPException(status_code=404, detail="Manifest bulunamadı.")
    return FileResponse(file, media_type="application/manifest+json")


@app.get("/icon-192.png")
async def icon_192():
    file = BASE_DIR / "icon-192.png"
    if not file.exists():
        raise HTTPException(status_code=404, detail="İkon bulunamadı.")
    return FileResponse(file, media_type="image/png")


@app.get("/icon-512.png")
async def icon_512():
    file = BASE_DIR / "icon-512.png"
    if not file.exists():
        raise HTTPException(status_code=404, detail="İkon bulunamadı.")
    return FileResponse(file, media_type="image/png")


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
async def health():

    return {

        "status":
            "online",

        "app":
            "K.A.R.V.I.S.",

        "version":
            APP_VERSION,

        "groq":
            bool(
                GROQ_API_KEY
            ),

        "openrouter":
            bool(
                OPENROUTER_API_KEY
            ),

        "google_image_search":
            bool(
                GOOGLE_IMAGE_API_KEY
                and
                GOOGLE_CSE_ID
            ),

        "research_engine":
            True,

        "wikipedia":
            True,

        "openverse":
            True,

        "presentation_engine":
            APP_VERSION
    }


# ============================================================
# K.A.R.V.I.S. CORE STATUS
# ============================================================

@app.get("/live-status")
async def live_status():
    return {
        "status": "online",
        "version": APP_VERSION,
        "ai": "Groq" if GROQ_API_KEY else ("OpenRouter" if OPENROUTER_API_KEY else "offline"),
        "research": True,
        "weather": True,
        "presentation": True,
        "memory": True,
    }


@app.get("/radar")
async def radar():
    return {
        "items": [
            {"name": "AI Engine", "status": "ONLINE" if (GROQ_API_KEY or OPENROUTER_API_KEY) else "OFFLINE"},
            {"name": "Web Research", "status": "ONLINE"},
            {"name": "Weather", "status": "ONLINE"},
            {"name": "Presentation Engine", "status": "ONLINE"},
            {"name": "Memory Core", "status": "ONLINE"},
        ]
    }


@app.get("/brain")
async def brain():
    return {
        "version": APP_VERSION,
        "modules": [
            "CHAT",
            "WEB RESEARCH",
            "MEMORY",
            "WEATHER",
            "PRESENTATION",
            "PROFILE ENGINE",
        ],
        "state": "READY",
    }


# ============================================================
# EPHEMERAL CHAT CONTEXT (RAM ONLY; NEVER WRITTEN TO DATABASE)
# ============================================================

# Context exists only in server memory. It is not persisted to PostgreSQL,
# JSON files, or browser storage. Starting a new chat uses a new ID.
_CHAT_CONTEXTS = {}
_CHAT_CONTEXT_MAX_TURNS = 10


def _get_chat_context(conversation_id, username):
    if not conversation_id:
        return []
    key = (str(username or "karahan")[:40], str(conversation_id)[:120])
    return list(_CHAT_CONTEXTS.get(key, []))


def _append_chat_context(conversation_id, username, user_message, assistant_message):
    if not conversation_id:
        return
    key = (str(username or "karahan")[:40], str(conversation_id)[:120])
    history = _CHAT_CONTEXTS.setdefault(key, [])
    history.append({"role": "user", "content": str(user_message)[:6000]})
    history.append({"role": "assistant", "content": str(assistant_message)[:6000]})
    # Keep only the most recent turns and discard empty contexts.
    _CHAT_CONTEXTS[key] = history[-(_CHAT_CONTEXT_MAX_TURNS * 2):]
    # Soft bound to prevent unbounded RAM growth from abandoned chats.
    if len(_CHAT_CONTEXTS) > 500:
        oldest_key = next(iter(_CHAT_CONTEXTS))
        if oldest_key != key:
            _CHAT_CONTEXTS.pop(oldest_key, None)


def _format_chat_context(history):
    if not history:
        return "Önceki mesaj yok; bu sohbetin ilk mesajı."
    return "\\n".join(
        ("Kullanıcı: " if item.get("role") == "user" else "K.A.R.V.I.S.: ")
        + str(item.get("content", ""))
        for item in history[-(_CHAT_CONTEXT_MAX_TURNS * 2):]
    )


# ============================================================
# CHAT
# ============================================================

@app.post("/chat")
async def chat(
    request: ChatRequest
):
    message = (
        request.message
        or ""
    ).strip()

    if not message:
        return {
            "response": "Nasıl yardımcı olabilirim efendim?",
            "message": "Nasıl yardımcı olabilirim efendim?"
        }

    username = (
        request.username
        or "karahan"
    ).strip().lower()

    mode = (
        request.mode
        or "normal"
    ).strip().lower()

    conversation_id = (request.conversation_id or "").strip()[:120]
    chat_history = _get_chat_context(conversation_id, username)

    user = USERS.get(username)
    if user is None:
        raise HTTPException(status_code=401, detail="Geçersiz profil.")

    # Kullanıcı özellik önerisi algılama: yalnızca gerçek öneri kalıplarında kaydet.
    feature_request = detect_user_feature_request(message)
    if feature_request and username not in {"karahan", "murat"}:
        save_user_request(username, message)

    # Yetkili Murat, kayıtlı istekleri doğal dille sorabilir.
    admin_request_query = (
        username == "murat"
        and any(term in normalize_request_text(message) for term in [
            "kullanıcıların istekleri", "kullanicilarin istekleri",
            "kullanıcı istekleri", "kullanici istekleri",
            "kullanıcıların önerileri", "kullanicilarin onerileri"
        ])
    )
    if admin_request_query:
        answer = requests_answer_for_admin()
        return {"response": answer, "message": answer}

    if feature_request and username not in {"karahan", "murat"}:
        answer = feature_request_ack(username)
        return {"response": answer, "message": answer, "feature_request_saved": True}

    # --------------------------------------------------------
    # PROFILE / MODE
    # --------------------------------------------------------
    if (
        user.get("role") == "teacher"
        or
        user.get("style") == "academic"
        or
        mode in {
            "academic",
            "research",
            "lesson",
            "quiz",
            "article",
            "teacher"
        }
    ):
        system_prompt = ACADEMIC_SYSTEM
        mode_instruction = (
            f"Akademik çalışma modu: {mode}. "
            "Kullanıcıya 'Hocam' diye hitap et."
        )
    else:
        system_prompt = PROFESSIONAL_SYSTEM
        mode_instruction = (
            f"Çalışma modu: {mode}."
        )

    # --------------------------------------------------------
    # SMART WEB DECISION
    # --------------------------------------------------------
    use_web = needs_web_research(
        message,
        username,
        mode
    )

    research = None
    research_context = ""

    # Hava durumu soruları web karar katmanından bağımsız olarak canlı veri servisine gider.
    # Böylece kısa/doğal ifadeler yüzünden hava durumu araştırmasının atlanması önlenir.
    if is_weather_request(message):
        try:
            weather = fetch_denizli_weather()
            if weather:
                weather_context = weather_context_for_ai(weather, message)
                research = {
                    "query": "Denizli canlı saatlik hava durumu",
                    "sources": [{
                        "title": "Denizli saatlik hava durumu",
                        "text": weather_context,
                        "url": "",
                        "source": weather.get("source", "hava servisi")
                    }],
                    "context": weather_context
                }
            else:
                save_error(
                    "Canlı hava durumu verisi alınamadı",
                    "Open-Meteo ve wttr.in servislerinden sonuç alınamadı. Ayrıntılar varsa önceki 'Weather services unavailable' kaydında bulunur.",
                    category="weather",
                    severity="warning",
                )
        except Exception as weather_exc:
            save_error(
                "Hava durumu isteği işlenemedi",
                traceback.format_exc(),
                category="weather",
                severity="error",
            )

    if use_web and research is None:
        try:
            research = perform_smart_research(
                message,
                username,
                mode
            )
            research_context = research.get(
                "context",
                ""
            )
        except Exception:
            save_error(
                "Smart research error",
                traceback.format_exc()
            )
            research = None
            research_context = ""

    if research and not research_context:
        research_context = research.get("context", "")

    # --------------------------------------------------------
    # PROFILE-SPECIFIC RESEARCH PERSONALITY
    # --------------------------------------------------------
    character_instruction = profile_research_instruction(
        username
    )

    if research:
        web_instruction = f"""
Bu cevap için internet araştırması yapıldı.

Araştırma sorgusu:
{research.get("query", "")}

Aşağıdaki kaynaklar araştırma bağlamıdır:
{research_context}

KURALLAR:
- Yalnızca kaynakların desteklediği güncel bilgileri kullan.
- Kaynaklarda bulunmayan ayrıntıları uydurma.
- Kaynaklar arasında çelişki varsa bunu açıkça belirt.
- Güncel bilgi olduğunu ve mümkünse tarih/kapsamını belirt.
- Kullanıcı istemedikçe araştırma sürecini anlatma.
- URL, link, ham kaynak listesi veya "Kaynaklar:" bölümü oluşturma.
- Araştırma sonucunu doğrudan doğal cevabın içine yedir.
- Hava durumu cevabını kısa ve sade tut: mevcut sıcaklık + önemli hava durumu + yakın saatlerdeki önemli değişiklik + gerekiyorsa tek pratik öneri. Genellikle 1-3 cümle yeterlidir.
- Hava durumu için verilen canlı veriyi aynen kullan; tahmin uydurma.
- Yerel gündemde en önemli güncel olayı önce söyle, sonra yalnızca gerekli kısa bağlamı ver.
- Genel cevaplarda gereksiz uzun açıklamalardan kaçın; doğru ve anlaşılır olmayı önceliklendir.
- Kaynak adını yalnızca doğruluk için gerçekten gerekli olduğunda metin içinde an.
"""
    else:
        web_instruction = """
Bu soru için internet araştırması gerekli görülmedi.
Harici web kaynağı kullanma ve güncel olmayan bir bilgiyi
güncelmiş gibi sunma. Genel bilgin ve konuşma bağlamınla cevap ver.
"""

    prompt = f"""
Kullanıcı profili:
{username}

{mode_instruction}

{character_instruction}

{web_instruction}

ÖNCEKİ MESAJLAR (yalnızca bu aktif sohbetin geçici bağlamı):
{_format_chat_context(chat_history)}

Kullanıcının son mesajı:
{message}

Yanıtı doğrudan ver. Önceki mesajlarla ilgili kısa takip sorularını bağlama göre yorumla.
Kullanıcı açıkça istemediyse gereksiz uzun açıklamalar yapma.
Bilmediğin bilgileri uydurma.
"""

    result = ask_ai(
        prompt,
        system_prompt,
        fast=True
    )

    if not result:
        result = (
            "Şu anda yapay zeka servislerine "
            "bağlanamıyorum. API anahtarlarını "
            "kontrol etmen gerekiyor."
        )

    # Sohbet bağlamını yalnızca RAM'de tut; PostgreSQL veya dosyaya yazma.
    _append_chat_context(
        conversation_id,
        username,
        message,
        result
    )

    # Web kaynakları kullanıcıya link listesi olarak basılmaz.
    # Araştırma yalnızca cevabın doğruluğunu ve güncelliğini besler.
    return {
        "response": result,
        "message": result,
        "web_research": bool(research),
        "sources_count": (
            len(research.get("sources", []))
            if research
            else 0
        )
    }


# ============================================================
# PRESENTATION ROUTE
# ============================================================

@app.post("/presentation")
async def create_presentation(
    request: PresentationRequest,
    background_tasks: BackgroundTasks
):

    topic = (
        request.topic
        or ""
    ).strip()

    if not topic:

        raise HTTPException(
            status_code=400,
            detail="Sunum konusu boş olamaz."
        )

    try:

        requested_count = int(
            request.slide_count
        )

    except Exception:

        requested_count = 7

    slide_count = max(
        5,
        min(
            requested_count,
            12
        )
    )

    job_id = create_job()

    background_tasks.add_task(

        presentation_worker,

        job_id,

        topic,

        slide_count
    )

    return {

        "success":
            True,

        "job_id":
            job_id,

        "status":
            "queued",

        "stage":
            "analysis",

        "progress":
            0,

        "message":
            "Konu analiz ediliyor..."
    }


# ============================================================
# PRESENTATION STATUS
# ============================================================

@app.get(
    "/presentation-status/{job_id}"
)
async def presentation_status(
    job_id: str
):

    with presentation_lock:

        job = PRESENTATION_JOBS.get(
            job_id
        )

        if not job:

            raise HTTPException(
                status_code=404,
                detail="Sunum bulunamadı."
            )

        return dict(
            job
        )


# ============================================================
# GENERATED FILES
# ============================================================

@app.get(
    "/generated/{filename}"
)
async def generated_file(
    filename: str
):

    safe_name = Path(
        filename
    ).name

    file_path = (
        GENERATED_DIR
        /
        safe_name
    )

    if (
        not file_path.exists()
        or
        not file_path.is_file()
    ):

        raise HTTPException(
            status_code=404,
            detail="Dosya bulunamadı."
        )

    if safe_name.lower().endswith(
        ".pdf"
    ):

        return FileResponse(

            path=file_path,

            media_type=
                "application/pdf",

            filename=
                safe_name,

            headers={

                "Content-Disposition":
                    f'attachment; filename="{safe_name}"'
            }
        )

    return FileResponse(
        path=file_path
    )


# ============================================================
# ACCOUNT PASSWORD MANAGEMENT
# ============================================================
class PasswordChangeRequest(BaseModel):
    username: str
    current_password: str = ""
    new_password: str

class AdminPasswordResetRequest(BaseModel):
    username: str = "murat"
    target_username: str
    new_password: str

@app.post("/account/change-password")
async def change_password(data: PasswordChangeRequest):
    username = data.username.strip().lower()
    if username not in USERS:
        raise HTTPException(status_code=404, detail="Profil bulunamadı.")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Yeni şifre en az 6 karakter olmalı.")
    records = _load_password_store()
    record = records.get(username)
    if record and not _verify_password(data.current_password, record):
        raise HTTPException(status_code=401, detail="Mevcut şifre hatalı.")
    if not record and USERS[username].get("password") != data.current_password:
        raise HTTPException(status_code=401, detail="Mevcut şifre hatalı.")
    _set_password(username, data.new_password)
    USERS[username]["password"] = ""
    return {"success": True, "message": "Şifre güncellendi."}

@app.post("/admin/password-reset")
async def admin_password_reset(data: AdminPasswordResetRequest):
    require_admin(data.username)
    target = data.target_username.strip().lower()
    if target not in USERS:
        raise HTTPException(status_code=404, detail="Profil bulunamadı.")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Yeni şifre en az 6 karakter olmalı.")
    _set_password(target, data.new_password)
    USERS[target]["password"] = ""
    return {"success": True, "message": f"{USERS[target]['name']} profilinin şifresi sıfırlandı."}


# ============================================================
# SUDE'S WORLD API
# ============================================================
@app.get("/sude/world")
async def sude_world(username: str = "sude"):
    if username.strip().lower() != "sude":
        raise HTTPException(status_code=403, detail="Bu dünya yalnızca Sude profiline açıktır.")
    _, state = _get_sude_state()
    return {"success": True, "world": state}

@app.post("/sude/bmi")
async def sude_bmi(data: dict):
    if str(data.get("username", "sude")).lower() != "sude":
        raise HTTPException(status_code=403, detail="Yetkisiz profil.")
    try:
        weight = float(data.get("weight")); height = float(data.get("height"))
        if not (20 <= weight <= 350 and 80 <= height <= 250): raise ValueError()
    except Exception:
        raise HTTPException(status_code=400, detail="Boyu cm, kiloyu kg olarak geçerli girin.")
    bmi = weight / ((height / 100) ** 2)
    category = "Düşük kilo" if bmi < 18.5 else "Normal aralık" if bmi < 25 else "Fazla kilo aralığı" if bmi < 30 else "Obezite aralığı"
    return {"success": True, "bmi": round(bmi, 1), "category": category, "note": "VKİ yalnızca genel bir tarama ölçütüdür; tek başına tanı koymaz ve yaş/gebelik/kas oranı gibi etkenleri değerlendirmez."}

@app.post("/sude/estimate-calories")
async def sude_estimate_calories(data: dict):
    if str(data.get("username", "sude")).lower() != "sude":
        raise HTTPException(status_code=403, detail="Yetkisiz profil.")
    meal = str(data.get("meal", "")).strip()[:500]
    if not meal: raise HTTPException(status_code=400, detail="Yiyecek veya öğün adı gerekli.")
    prompt = ("Tahmini kalori hesaplayıcısı olarak yanıtla. Kullanıcının yazdığı yiyecek/öğün için porsiyon bilgisi yoksa standart bir porsiyon varsay. "
              "Yalnızca şu biçimde yanıt ver: KALORI: <tam sayı>\nACIKLAMA: <kısa porsiyon varsayımı>. Kesinlik iddia etme.\nÖğün: " + meal)
    answer = ask_ai(prompt, PROFESSIONAL_SYSTEM, fast=True) or ""
    match = re.search(r"KALORI\s*:\s*(\d{1,4})", answer, re.IGNORECASE)
    calories = max(0, min(5000, int(match.group(1)))) if match else None
    explanation_match = re.search(r"ACIKLAMA\s*:\s*(.+)", answer, re.IGNORECASE | re.DOTALL)
    explanation = explanation_match.group(1).strip()[:500] if explanation_match else "Porsiyon ve hazırlanışa göre değişebilir."
    if calories is None:
        return {"success": False, "estimate": None, "explanation": "Güvenilir bir tahmin üretilemedi. Porsiyon miktarını ve malzemeleri daha ayrıntılı yaz."}
    return {"success": True, "estimate": calories, "explanation": explanation, "disclaimer": "Bu değer yaklaşık tahmindir; ürün etiketi veya ölçülmüş malzeme değerinin yerini tutmaz."}

@app.post("/sude/food")
async def sude_add_food(data: dict):
    if str(data.get("username", "sude")).lower() != "sude":
        raise HTTPException(status_code=403, detail="Yetkisiz profil.")
    name = str(data.get("name", "")).strip()[:120]
    try: calories = max(0, min(5000, int(float(data.get("calories", 0)))))
    except Exception: calories = 0
    if not name: raise HTTPException(status_code=400, detail="Yiyecek adı gerekli.")
    with sude_lock:
        all_data, state = _get_sude_state()
        state["food_log"].append({"id": uuid.uuid4().hex, "name": name, "calories": calories, "date": time.strftime("%Y-%m-%d"), "created_at": time.strftime("%H:%M")})
        state["food_log"] = state["food_log"][-200:]
        state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        write_json_file(SUDE_WORLD_FILE, all_data)
    return {"success": True, "world": state}

@app.post("/sude/tasks")
async def sude_add_task(data: dict):
    if str(data.get("username", "sude")).lower() != "sude": raise HTTPException(status_code=403, detail="Yetkisiz profil.")
    title = str(data.get("title", "")).strip()[:120]
    if not title: raise HTTPException(status_code=400, detail="Görev adı gerekli.")
    with sude_lock:
        all_data, state = _get_sude_state()
        state["tasks"].append({"id": uuid.uuid4().hex, "title": title, "done": False, "date": time.strftime("%Y-%m-%d")})
        state["tasks"] = state["tasks"][-100:]
        write_json_file(SUDE_WORLD_FILE, all_data)
    return {"success": True, "world": state}

@app.post("/sude/tasks/{task_id}/complete")
async def sude_complete_task(task_id: str, username: str = "sude"):
    if username.strip().lower() != "sude": raise HTTPException(status_code=403, detail="Yetkisiz profil.")
    with sude_lock:
        all_data, state = _get_sude_state()
        task = next((x for x in state["tasks"] if x.get("id") == task_id), None)
        if not task: raise HTTPException(status_code=404, detail="Görev bulunamadı.")
        if not task.get("done"):
            task["done"] = True; state["points"] = int(state.get("points", 0)) + 10
            state["pet"]["mood"] = min(100, int(state["pet"].get("mood", 70)) + 5)
            state["pet"]["level"] = 1 + int(state["points"]) // 100
            if state["points"] >= 50 and "İlk Adımlar" not in state["badges"]: state["badges"].append("İlk Adımlar")
        write_json_file(SUDE_WORLD_FILE, all_data)
    return {"success": True, "world": state}

@app.post("/sude/pet")
async def sude_pet(data: dict):
    if str(data.get("username", "sude")).lower() != "sude": raise HTTPException(status_code=403, detail="Yetkisiz profil.")
    action = str(data.get("action", "pet"))
    with sude_lock:
        all_data, state = _get_sude_state(); pet = state["pet"]
        if action == "feed": pet["energy"] = min(100, int(pet.get("energy",70))+15); state["points"] += 2
        elif action == "play": pet["mood"] = min(100, int(pet.get("mood",70))+12); pet["energy"] = max(0, int(pet.get("energy",70))-8); state["points"] += 2
        else: pet["mood"] = min(100, int(pet.get("mood",70))+3)
        pet["level"] = 1 + int(state.get("points",0)) // 100
        write_json_file(SUDE_WORLD_FILE, all_data)
    return {"success": True, "world": state}

@app.get("/admin/sude-summary")
async def admin_sude_summary(username: str = "murat"):
    require_admin(username)
    _, state = _get_sude_state()
    # Deliberately share only aggregate progress, not detailed food entries.
    return {"success": True, "summary": {"points": state.get("points",0), "level": state.get("pet",{}).get("level",1), "completed_tasks": sum(1 for t in state.get("tasks",[]) if t.get("done")), "total_tasks": len(state.get("tasks",[])), "badges": state.get("badges",[])}}


# ============================================================
# MEMORY
# ============================================================

@app.get("/memory")
async def get_memory(username: str = "karahan"):
    username = username.strip().lower()
    if username not in USERS: raise HTTPException(status_code=401, detail="Geçersiz profil.")
    with memory_lock:
        stored = read_json_file(MEMORY_FILE, [])
        # Backward compatibility: existing legacy memory remains attached to the main owner profile.
        if isinstance(stored, dict):
            memories = stored.get(username, [])
        else:
            memories = stored if username == "karahan" and isinstance(stored, list) else []
        return {"memory": memories}

@app.post("/memory")
async def add_memory(data: dict):
    username = str(data.get("username", "karahan")).strip().lower()
    text = str(data.get("text", "")).strip()
    if username not in USERS: raise HTTPException(status_code=401, detail="Geçersiz profil.")
    if not text: return {"success": False}
    with memory_lock:
        stored = read_json_file(MEMORY_FILE, [])
        if not isinstance(stored, dict):
            stored = {"karahan": stored if isinstance(stored, list) else []}
        memories = stored.get(username, [])
        if not isinstance(memories, list): memories = []
        memories.append({"id": uuid.uuid4().hex, "text": text[:2000], "created_at": time.strftime("%Y-%m-%d %H:%M:%S")})
        stored[username] = memories[-200:]
        write_json_file(MEMORY_FILE, stored)
    return {"success": True, "memory": stored[username]}


# ============================================================
# NEW CHAT
# ============================================================

@app.post("/new-chat")
async def new_chat():

    return {

        "success":
            True,

        "message":
            "Yeni sohbet başlatıldı."
    }


# ============================================================
# ADMIN DASHBOARD API
# ============================================================

def require_admin(username):
    if str(username or "").strip().lower() != "murat":
        raise HTTPException(status_code=403, detail="Bu alan yalnızca Murat yetkili profiline açıktır.")


@app.get("/admin/stats")
async def admin_stats(username: str = "murat"):
    require_admin(username)
    requests = get_user_requests()
    errors = read_json_file(ERROR_FILE, [])
    return {
        "success": True,
        "users": len(USERS),
        "requests": len(requests),
        "unread_requests": sum(1 for x in requests if not x.get("read", False)),
        "errors": len(errors),
        "version": APP_VERSION,
        "ai": "Groq" if GROQ_API_KEY else ("OpenRouter" if OPENROUTER_API_KEY else "offline"),
    }


# ============================================================
# ERRORS
# ============================================================

@app.get("/errors")
async def errors():

    return {

        "errors":
            read_json_file(
                ERROR_FILE,
                []
            )
    }


# ============================================================
# ADMIN ERROR CENTER
# ============================================================

def get_error_items():
    data = read_json_file(ERROR_FILE, [])
    if not isinstance(data, list):
        data = []
    for item in data:
        if not isinstance(item, dict):
            continue
        item.setdefault("id", uuid.uuid4().hex)
        item.setdefault("status", "open")
        item.setdefault("category", "legacy")
        item.setdefault("severity", "error")
        item.setdefault("details", "")
    return [item for item in data if isinstance(item, dict)]


@app.get("/admin/errors")
async def admin_errors(username: str = "murat"):
    require_admin(username)
    data = get_error_items()
    # ID'leri kalıcılaştır. Eski errors.json kayıtları da panelde yönetilebilir.
    with error_lock:
        write_json_file(ERROR_FILE, data)
    return {
        "success": True,
        "errors": data,
        "open": sum(1 for x in data if x.get("status") != "resolved"),
        "resolved": sum(1 for x in data if x.get("status") == "resolved")
    }


@app.post("/admin/errors/{error_id}/resolve")
async def resolve_admin_error(error_id: str, username: str = "murat"):
    require_admin(username)
    with error_lock:
        data = get_error_items()
        for item in data:
            if item.get("id") == error_id:
                item["status"] = "resolved"
                item["resolved_at"] = datetime.now().isoformat(timespec="seconds")
                write_json_file(ERROR_FILE, data)
                return {"success": True, "error": item}
    raise HTTPException(status_code=404, detail="Hata kaydı bulunamadı.")


@app.post("/admin/errors/{error_id}/reopen")
async def reopen_admin_error(error_id: str, username: str = "murat"):
    require_admin(username)
    with error_lock:
        data = get_error_items()
        for item in data:
            if item.get("id") == error_id:
                item["status"] = "open"
                item.pop("resolved_at", None)
                write_json_file(ERROR_FILE, data)
                return {"success": True, "error": item}
    raise HTTPException(status_code=404, detail="Hata kaydı bulunamadı.")


@app.post("/admin/errors/{error_id}/analyze")
async def analyze_admin_error(error_id: str, username: str = "murat"):
    require_admin(username)
    data = get_error_items()
    target = next((x for x in data if x.get("id") == error_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Hata kaydı bulunamadı.")

    prompt = (
        "K.A.R.V.I.S. sistem yöneticisi için aşağıdaki hata kaydını analiz et. "
        "Türkçe ve kısa yanıt ver. Şu başlıkları kullan: Muhtemel neden, Etki, "
        "Önerilen çözüm, Öncelik. Bilmediğin şeyi kesinmiş gibi söyleme.\n\n"
        f"Hata zamanı: {target.get('time','')}\n"
        f"Hata: {target.get('error', target.get('message',''))}\n"
        f"Detay: {target.get('details','')}"
    )
    analysis = ask_ai(prompt, PROFESSIONAL_SYSTEM, fast=True)
    if not analysis:
        analysis = "AI hata analizi şu anda kullanılamıyor. Hata kaydının ayrıntılarını manuel olarak inceleyin."
    return {"success": True, "analysis": analysis}


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
async def startup():

    GENERATED_DIR.mkdir(
        exist_ok=True
    )

    if push_database_configured():
        init_push_database()
        migrate_push_json_to_database()

    start_self_push_worker()

    print("=" * 65)

    print(
        "K.A.R.V.I.S. - KARAHAN INC."
    )

    print(
        f"Version: {APP_VERSION}"
    )

    print(
        "Backend: ONLINE"
    )

    print(
        "Groq:",
        "ACTIVE"
        if GROQ_API_KEY
        else
        "NOT CONFIGURED"
    )

    print(
        "OpenRouter:",
        "ACTIVE"
        if OPENROUTER_API_KEY
        else
        "NOT CONFIGURED"
    )

    print(
        "Google Search:",
        "ACTIVE"
        if (
            GOOGLE_IMAGE_API_KEY
            and
            GOOGLE_CSE_ID
        )
        else
        "NOT CONFIGURED"
    )

    print(
        "Wikipedia Research: ENABLED"
    )

    print(
        "Openverse Images: ENABLED"
    )

    print(
        "Google Images Fallback: ENABLED"
    )

    print(
        "Fact-Based Presentation: ENABLED"
    )

    print(
        "Duplicate Slide Protection: ENABLED"
    )

    print(
        "Per-Slide AI Generation: ENABLED"
    )

    print(
        "Source Footer: ENABLED"
    )

    print(
        "Dynamic Text Fit: ENABLED"
    )

    print(
        "Academic Teacher Mode: ENABLED"
    )

    print(
        "Profile Login: ENABLED"
    )


    print(
        "Betül Entertainment Mode: ENABLED"
    )

    print(
        "Betül Instagram Simulation: ENABLED"
    )

    print(
        "PDF Download: ENABLED"
    )

    print(
        "Live Presentation Progress: ENABLED"
    )

    print(
        "Presentation Engine: 16:9"
    )

    print("=" * 65)


# ============================================================
# LOCAL RUN
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(

        "main:app",

        host="0.0.0.0",

        port=int(
            os.getenv(
                "PORT",
                "8000"
            )
        ),

        reload=False
    )
