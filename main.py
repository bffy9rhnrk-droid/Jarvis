import json
import os
import random
import unicodedata
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI


# =========================================================
# J.A.R.V.I.S. — KARAHAN INC.
# BACKEND
# =========================================================

APP_VERSION = "15.0.0"

BASE_DIR = Path(__file__).resolve().parent
MEMORY_FILE = BASE_DIR / "jarvis_memory.json"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-120b"
)

app = FastAPI(
    title="J.A.R.V.I.S. — KARAHAN INC.",
    version=APP_VERSION
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# OPENAI COMPATIBLE GROQ CLIENT
# =========================================================

client = None

if GROQ_API_KEY:
    client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
        timeout=60.0,
        max_retries=0
    )


# =========================================================
# USERS
# =========================================================

USERS = {
    "karahan": {
        "username": "karahan",
        "name": "KARAHAN INC.",
        "role": "Ana Kullanıcı",
        "password": None,
        "personality": "professional"
    },

    # ÖNEMLİ:
    # Sistem içinde "betul" kullanılıyor.
    # Ekranda ise "Betül" gösteriliyor.
    "betul": {
        "username": "betul",
        "name": "Betül",
        "role": "Özel Kullanıcı",
        "password": "1234",
        "personality": "betul"
    }
}


# =========================================================
# MODELS
# =========================================================

class ChatRequest(BaseModel):
    message: str
    username: str = "karahan"


class ProfileLoginRequest(BaseModel):
    username: str
    password: str


# =========================================================
# MEMORY
# =========================================================

def create_empty_memory():
    return {
        "karahan": {
            "profile": {},
            "preferences": {},
            "projects": {},
            "vehicles": {},
            "important_facts": {},
            "conversation": []
        },
        "betul": {
            "profile": {},
            "preferences": {},
            "projects": {},
            "vehicles": {},
            "important_facts": {},
            "conversation": []
        }
    }


def load_memory():
    if not MEMORY_FILE.exists():
        data = create_empty_memory()
        save_memory(data)
        return data

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            data = create_empty_memory()

        if "karahan" not in data:
            data["karahan"] = create_empty_memory()["karahan"]

        if "betul" not in data:
            data["betul"] = create_empty_memory()["betul"]

        return data

    except Exception:
        return create_empty_memory()


def save_memory(data):
    try:
        with open(
            MEMORY_FILE,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )
    except Exception:
        pass


memory = load_memory()


# =========================================================
# USERNAME NORMALIZATION
# =========================================================

def normalize_username(username: str) -> str:
    if not username:
        return ""

    username = username.strip().lower()

    replacements = {
        "ü": "u",
        "ö": "o",
        "ı": "i",
        "ş": "s",
        "ğ": "g",
        "ç": "c",
        "â": "a",
        "î": "i",
        "û": "u"
    }

    for old, new in replacements.items():
        username = username.replace(old, new)

    username = unicodedata.normalize(
        "NFKD",
        username
    ).encode(
        "ascii",
        "ignore"
    ).decode(
        "ascii"
    )

    return username


# =========================================================
# ERROR CLASSIFIER
# =========================================================

def classify_error(error):
    text = str(error).lower()

    if "429" in text or "rate limit" in text:
        return "RATE_LIMIT"

    if "timeout" in text or "timed out" in text:
        return "TIMEOUT"

    if (
        "context" in text
        or "token" in text
        or "maximum" in text
    ):
        return "CONTEXT_LIMIT"

    if (
        "connection" in text
        or "network" in text
    ):
        return "CONNECTION_ERROR"

    if (
        "401" in text
        or "403" in text
        or "api key" in text
        or "authentication" in text
    ):
        return "AUTHENTICATION_ERROR"

    if "model" in text and (
        "not found" in text
        or "does not exist" in text
    ):
        return "MODEL_ERROR"

    return "GROQ_API_ERROR"


# =========================================================
# SYSTEM PROMPT
# =========================================================

def build_system_prompt(username: str):

    user = USERS.get(
        username,
        USERS["karahan"]
    )

    if username == "betul":

        return """
Sen J.A.R.V.I.S.'sin.

Kullanıcı:
Betül

Betül ile konuşurken samimi, eğlenceli,
hafif sert ve şakacı bir dil kullan.

Bazen:
- "aşko"
- "kız"
- "canım"

gibi ifadeler kullanabilirsin.

Betül basit bir şey sorduğunda bile bazen
hafif takılabilirsin.

Örneğin:
"Her şeyi ben mi bileceğim kız? 😂"
"Aşko bunu da mı bana sordun?"
"Dur kız, işlemciyi çalıştırıyorum."
"Tamam aşko, düşünüyorum."

Ancak:
- hakaret etme
- küfür etme
- aşağılayıcı olma
- saldırganlaşma

Şaka yap ama sonunda mutlaka yardımcı olmaya çalış.

Betül'e "Murat" diye hitap etme.

Yanıtların doğal Türkçe olsun.

Gereksiz yere uzun cevaplar verme.

Sen J.A.R.V.I.S.'sin.
"""


    return """
Sen J.A.R.V.I.S.'sin.

Marka:
J.A.R.V.I.S. — KARAHAN INC.

Ana kullanıcı:
KARAHAN INC.

Ana kullanıcıya gerektiğinde:
"efendim"
diye hitap edebilirsin.

Dil:
Türkçe.

Tarz:
- profesyonel
- sakin
- zeki
- doğal
- yardımcı
- kısa ve anlaşılır

Kullanıcı sana bir bilgi verdiğinde,
uygunsa bunu hatırlamaya çalış.

Kullanıcının geçmiş konuşmalarından gelen
hafıza bilgilerini dikkate al.

Bilmediğin bir şeyi uydurma.

Güncel bilgi gerektiren konularda
güncel bilgiye ihtiyaç olduğunu belirt.

Kullanıcı istemedikçe aşırı uzun cevap verme.

Sen bir sohbet robotu gibi değil,
kişisel dijital asistan gibi davran.
"""


# =========================================================
# MEMORY EXTRACTION
# =========================================================

def remember_message(username: str, message: str):

    global memory

    if username not in memory:
        memory[username] = {
            "profile": {},
            "preferences": {},
            "projects": {},
            "vehicles": {},
            "important_facts": {},
            "conversation": []
        }

    msg = message.strip()

    lower = msg.lower()

    # İsim
    if (
        "adım " in lower
        or "benim adım " in lower
        or "ismim " in lower
    ):
        memory[username]["profile"]["last_name_statement"] = msg

    # Şehir
    if (
        "yaşıyorum" in lower
        or "oturuyorum" in lower
    ):
        memory[username]["profile"]["location_statement"] = msg

    # JARVIS projesi
    if (
        "jarvis" in lower
        or "j.a.r.v.i.s" in lower
    ):
        memory[username]["projects"]["jarvis"] = (
            "Kullanıcı J.A.R.V.I.S. — KARAHAN INC. "
            "kişisel yapay zeka asistanı projesi geliştiriyor."
        )

    # Araçlar
    if "caddy" in lower:
        memory[username]["vehicles"]["caddy"] = (
            "Kullanıcının Caddy aracı hakkında "
            "konuşmalar bulunuyor."
        )

    if "mercedes" in lower or "w204" in lower:
        memory[username]["vehicles"]["mercedes"] = (
            "Kullanıcının Mercedes W204 aracı hakkında "
            "konuşmalar bulunuyor."
        )

    # Son konuşmalar
    memory[username]["conversation"].append(msg)

    # Son 30 mesajı tut
    memory[username]["conversation"] = (
        memory[username]["conversation"][-30:]
    )

    save_memory(memory)


# =========================================================
# MEMORY TEXT
# =========================================================

def get_memory_text(username: str):

    user_memory = memory.get(
        username,
        {}
    )

    parts = []

    profile = user_memory.get(
        "profile",
        {}
    )

    projects = user_memory.get(
        "projects",
        {}
    )

    vehicles = user_memory.get(
        "vehicles",
        {}
    )

    important = user_memory.get(
        "important_facts",
        {}
    )

    if profile:
        parts.append(
            "Profil hafızası:\n"
            + json.dumps(
                profile,
                ensure_ascii=False,
                indent=2
            )
        )

    if projects:
        parts.append(
            "Projeler:\n"
            + json.dumps(
                projects,
                ensure_ascii=False,
                indent=2
            )
        )

    if vehicles:
        parts.append(
            "Araçlar:\n"
            + json.dumps(
                vehicles,
                ensure_ascii=False,
                indent=2
            )
        )

    if important:
        parts.append(
            "Önemli bilgiler:\n"
            + json.dumps(
                important,
                ensure_ascii=False,
                indent=2
            )
        )

    if not parts:
        return "Henüz kayıtlı önemli hafıza yok."

    return "\n\n".join(parts)


# =========================================================
# ROUTES
# =========================================================

@app.get("/")
async def home():
    return FileResponse(
        BASE_DIR / "index.html"
    )


@app.get("/health")
async def health():

    return {
        "status": "online",
        "version": APP_VERSION,
        "model": GROQ_MODEL,
        "groq_configured": bool(GROQ_API_KEY)
    }


@app.get("/version")
async def version():

    return {
        "version": APP_VERSION,
        "name": "J.A.R.V.I.S. — KARAHAN INC."
    }


# =========================================================
# USERS
# =========================================================

@app.get("/users")
async def users():

    return {
        "users": [
            {
                "username": "karahan",
                "name": "KARAHAN INC.",
                "role": "Ana Kullanıcı"
            }
        ]
    }


# =========================================================
# PROFILE LOGIN
# =========================================================

@app.post("/profile-login")
async def profile_login(
    data: ProfileLoginRequest
):

    username = normalize_username(
        data.username
    )

    password = data.password.strip()

    print(
        f"PROFILE LOGIN: username={username}"
    )

    if username not in USERS:

        return {
            "success": False,
            "error": "USER_NOT_FOUND",
            "message": "Kullanıcı adı veya şifre hatalı."
        }

    user = USERS[username]

    # Ana kullanıcı şifresiz geçiş
    if user["password"] is None:

        return {
            "success": True,
            "user": {
                "username": user["username"],
                "name": user["name"],
                "role": user["role"]
            }
        }

    # Şifre kontrolü
    if password != user["password"]:

        return {
            "success": False,
            "error": "INVALID_PASSWORD",
            "message": "Kullanıcı adı veya şifre hatalı."
        }

    return {
        "success": True,
        "user": {
            "username": user["username"],
            "name": user["name"],
            "role": user["role"]
        }
    }


# =========================================================
# NEW CHAT
# =========================================================

@app.post("/new-chat")
async def new_chat():

    return {
        "success": True,
        "message": "Yeni sohbet başlatıldı."
    }


# =========================================================
# MEMORY GET
# =========================================================

@app.get("/memory")
async def get_memory(
    username: str = "karahan"
):

    username = normalize_username(
        username
    )

    if username not in memory:
        username = "karahan"

    return {
        "username": username,
        "memory": memory[username]
    }


# =========================================================
# MEMORY DELETE
# =========================================================

@app.delete("/memory")
async def delete_memory(
    username: str = "karahan"
):

    username = normalize_username(
        username
    )

    if username not in memory:
        username = "karahan"

    memory[username] = {
        "profile": {},
        "preferences": {},
        "projects": {},
        "vehicles": {},
        "important_facts": {},
        "conversation": []
    }

    save_memory(memory)

    return {
        "success": True,
        "message": "Kullanıcı hafızası temizlendi."
    }


# =========================================================
# CHAT
# =========================================================

@app.post("/chat")
async def chat(
    data: ChatRequest
):

    username = normalize_username(
        data.username
    )

    if username not in USERS:
        username = "karahan"

    message = data.message.strip()

    if not message:

        return {
            "success": False,
            "error": "EMPTY_MESSAGE",
            "message": "Mesaj boş olamaz."
        }

    # Hafızaya kaydet
    remember_message(
        username,
        message
    )

    if not GROQ_API_KEY or client is None:

        return {
            "success": False,
            "error": "AUTHENTICATION_ERROR",
            "message": (
                "GROQ_API_KEY bulunamadı. "
                "Render Environment Variables bölümünü kontrol edin."
            )
        }

    system_prompt = build_system_prompt(
        username
    )

    memory_text = get_memory_text(
        username
    )

    full_system_prompt = (
        system_prompt
        + "\n\n"
        + "KULLANICI HAFIZASI:\n"
        + memory_text
    )

    # Son konuşmalardan kısa bağlam
    recent_messages = memory.get(
        username,
        {}
    ).get(
        "conversation",
        []
    )[-10:]

    context_text = ""

    if recent_messages:
        context_text = (
            "\n\nSON KONUŞMA BAĞLAMI:\n"
            + "\n".join(
                recent_messages
            )
        )

    try:

        response = client.chat.completions.create(

            model=GROQ_MODEL,

            messages=[
                {
                    "role": "system",
                    "content": (
                        full_system_prompt
                        + context_text
                    )
                },
                {
                    "role": "user",
                    "content": message
                }
            ],

            temperature=0.7,

            max_tokens=1000
        )

        answer = response.choices[0].message.content

        if not answer:
            answer = "Efendim, şu anda cevap oluşturamadım."

        remember_message(
            username,
            "JARVIS: " + answer
        )

        return {
            "success": True,
            "answer": answer,
            "username": username
        }

    except Exception as error:

        error_type = classify_error(
            error
        )

        print(
            "GROQ ERROR:",
            repr(error)
        )

        if error_type == "RATE_LIMIT":

            return {
                "success": False,
                "error": "RATE_LIMIT",
                "message": (
                    "Groq kullanım limiti dolmuş görünüyor. "
                    "Yeni sohbet açmak sohbet geçmişini sıfırlar "
                    "ancak sağlayıcının günlük API limitini sıfırlamaz."
                )
            }

        if error_type == "TIMEOUT":

            return {
                "success": False,
                "error": "TIMEOUT",
                "message": (
                    "Efendim, bağlantı biraz uzun sürdü. "
                    "Lütfen tekrar deneyin."
                )
            }

        if error_type == "AUTHENTICATION_ERROR":

            return {
                "success": False,
                "error": "AUTHENTICATION_ERROR",
                "message": (
                    "API anahtarıyla ilgili bir problem var. "
                    "GROQ_API_KEY değerini kontrol edin."
                )
            }

        if error_type == "MODEL_ERROR":

            return {
                "success": False,
                "error": "MODEL_ERROR",
                "message": (
                    "Seçilen Groq modeli kullanılamıyor. "
                    "GROQ_MODEL değerini kontrol edin."
                )
            }

        return {
            "success": False,
            "error": error_type,
            "message": (
                "J.A.R.V.I.S. şu anda cevap oluşturamadı."
            )
        }
