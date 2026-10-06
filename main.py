import json
import os
import re
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

APP_VERSION = "13.0.0"

BASE_DIR = Path(__file__).resolve().parent
MEMORY_FILE = BASE_DIR / "jarvis_memory.json"
INDEX_FILE = BASE_DIR / "index.html"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


# =========================================================
# APP
# =========================================================

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
# OPENAI-COMPATIBLE GROQ CLIENT
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
        "personality": "professional",
        "greeting": "Hoş geldiniz efendim. J.A.R.V.I.S. hazır."
    },

    "betül": {
        "username": "betül",
        "name": "Betül",
        "role": "Özel Kullanıcı",
        "personality": "betul",
        "greeting": "Hoş geldin aşko. J.A.R.V.I.S. burada. Bakalım bugün ne karıştırıyoruz? 😂"
    }
}


# =========================================================
# MEMORY
# =========================================================

def default_user_memory():
    return {
        "profile": {},
        "preferences": {},
        "projects": {},
        "vehicles": {},
        "important_facts": {},
        "conversation": []
    }


def load_memory():
    if not MEMORY_FILE.exists():
        return {}

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return {}

        return data

    except Exception:
        return {}


memory = load_memory()


def save_memory():
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as file:
            json.dump(
                memory,
                file,
                ensure_ascii=False,
                indent=2
            )
    except Exception:
        pass


def get_user_memory(username: str):
    if username not in memory:
        memory[username] = default_user_memory()
        save_memory()

    return memory[username]


# =========================================================
# MODELS
# =========================================================

class ChatRequest(BaseModel):
    message: str
    username: str = "karahan"
    session_id: Optional[str] = None


class LoginRequest(BaseModel):
    username: str


# =========================================================
# SYSTEM PROMPT
# =========================================================

def build_system_prompt(username: str):

    user = USERS.get(username, USERS["karahan"])
    user_memory = get_user_memory(username)

    if username == "betül":

        return f"""
Sen J.A.R.V.I.S. — KARAHAN INC. yapay zeka asistanısın.

Şu anda konuştuğun kullanıcı:
Betül

Kullanıcı rolü:
Özel Kullanıcı

BETÜL İÇİN ÖZEL KONUŞMA TARZI:

- Samimi ol.
- Eğlenceli ol.
- Hafif laf sokabilirsin.
- Gerektiğinde "aşko", "kız", "canım" gibi ifadeler kullan.
- Bazen komik şekilde "Her şeyi ben mi bileceğim kız?" tarzı cevaplar verebilirsin.
- Ancak ağır hakaret, küfür veya aşağılayıcı ifadeler kullanma.
- Soruyu gerçekten cevaplaman gerektiğini unutma.
- Gereksiz şekilde her cümlede "aşko" deme.
- Doğal konuş.
- Betül basit bir şey sorarsa bile robot gibi davranma.

Örnek tarz:

"Dur kız, bunu da hemen bilmemi bekleme. 😂 Bir bakayım."

"Aşko her şeyi ben mi bileceğim? 😂 Ama tamam, araştırıp mantıklı cevabı veriyorum."

"Tamam canım, bunu çözeriz."

Kullanıcıya yardımcı olmaya devam et.

GENEL J.A.R.V.I.S. KURALLARI:

- Türkçe konuş.
- Bilmediğin şeyi uydurma.
- Emin değilsen açıkça belirt.
- Gereksiz uzun cevaplar verme.
- Kullanıcının sorusunu doğrudan cevapla.
- Kod istenirse çalışır ve eksiksiz kod üret.
- Kullanıcı teknik konuda yardım istiyorsa adım adım anlat.

Kullanıcı hafızası:

{json.dumps(user_memory, ensure_ascii=False, indent=2)}
"""

    return f"""
Sen J.A.R.V.I.S. — KARAHAN INC. kişisel yapay zeka asistanısın.

Ana kullanıcı:
KARAHAN INC.

Kullanıcı rolü:
Ana Kullanıcı

Kullanıcıya hitap:
"efendim"

KONUŞMA TARZI:

- Profesyonel.
- Sakin.
- Akıllı ve doğal.
- Yardımcı.
- Gereksiz uzun konuşma yapma.
- Kullanıcıya gerektiğinde "efendim" diye hitap et.
- Türkçe konuş.
- Bilmediğin bilgileri uydurma.
- Emin olmadığın konularda bunu açıkça belirt.
- Teknik konularda uygulanabilir ve net çözüm sun.
- Kod verirken eksiksiz ve doğrudan çalışabilecek kod vermeye çalış.

KARAHAN INC. ÖNEMLİDİR.

Bu profil uygulamanın ana sahibidir.

Kullanıcı hafızası:

{json.dumps(user_memory, ensure_ascii=False, indent=2)}
"""


# =========================================================
# MEMORY EXTRACTION
# =========================================================

def extract_memory(username: str, text: str):

    user_memory = get_user_memory(username)

    lower = text.lower()

    # İsim
    name_match = re.search(
        r"(?:benim adım|adım|ismim)\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)",
        text,
        re.IGNORECASE
    )

    if name_match:
        user_memory["profile"]["name"] = name_match.group(1)

    # Şehir
    city_match = re.search(
        r"(?:istanbul|ankara|izmir|denizli|antalya|bursa|adana|konya|mersin|aydın|muğla|manisa|kocaeli|sakarya|eskişehir|trabzon|samsun)",
        lower
    )

    if city_match:
        user_memory["profile"]["city"] = city_match.group(0)

    # Jarvis projesi
    if "jarvis" in lower:
        user_memory["projects"]["jarvis"] = True

    # Mercedes
    if "mercedes" in lower or "w204" in lower:
        user_memory["vehicles"]["mercedes"] = True

    # Caddy
    if "caddy" in lower:
        user_memory["vehicles"]["caddy"] = True

    save_memory()


# =========================================================
# ERROR HANDLING
# =========================================================

def classify_error(error):

    message = str(error).lower()

    if "429" in message or "rate limit" in message or "tokens per day" in message:
        return "RATE_LIMIT"

    if "timeout" in message:
        return "TIMEOUT"

    if "context" in message or "maximum" in message or "token" in message:
        return "CONTEXT_LIMIT"

    if "connection" in message or "network" in message:
        return "CONNECTION_ERROR"

    if "401" in message or "403" in message or "api key" in message:
        return "AUTHENTICATION_ERROR"

    if "model" in message and (
        "not found" in message or
        "does not exist" in message
    ):
        return "MODEL_ERROR"

    return "GROQ_API_ERROR"


# =========================================================
# HOME
# =========================================================

@app.get("/")
async def home():

    if INDEX_FILE.exists():
        return FileResponse(INDEX_FILE)

    return {
        "name": "J.A.R.V.I.S.",
        "company": "KARAHAN INC.",
        "status": "online"
    }


# =========================================================
# USERS
# =========================================================

@app.get("/users")
async def get_users():

    return {
        "users": [
            {
                "username": user["username"],
                "name": user["name"],
                "role": user["role"]
            }
            for user in USERS.values()
        ],

        "default_user": "karahan"
    }


# =========================================================
# LOGIN COMPATIBILITY
# =========================================================

@app.post("/login")
async def login(data: LoginRequest):

    username = data.username.lower().strip()

    if username not in USERS:
        return {
            "success": False,
            "error": "USER_NOT_FOUND"
        }

    user = USERS[username]

    return {
        "success": True,
        "user": {
            "username": user["username"],
            "name": user["name"],
            "role": user["role"]
        }
    }


# =========================================================
# CHAT
# =========================================================

@app.post("/chat")
async def chat(data: ChatRequest):

    username = data.username.lower().strip()

    if username not in USERS:
        username = "karahan"

    message = data.message.strip()

    if not message:
        return {
            "success": False,
            "error": "EMPTY_MESSAGE"
        }

    if not client:
        return {
            "success": False,
            "error": "NO_API_KEY",
            "message": "GROQ_API_KEY ayarlanmamış."
        }

    user_memory = get_user_memory(username)

    extract_memory(username, message)

    # Son konuşmaları al
    conversation = user_memory.get("conversation", [])

    recent_messages = conversation[-12:]

    messages = [
        {
            "role": "system",
            "content": build_system_prompt(username)
        }
    ]

    for item in recent_messages:

        if (
            isinstance(item, dict)
            and "role" in item
            and "content" in item
        ):
            messages.append({
                "role": item["role"],
                "content": item["content"]
            })

    messages.append({
        "role": "user",
        "content": message
    })

    try:

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=1200
        )

        answer = response.choices[0].message.content

        if not answer:
            answer = "Efendim, şu anda cevap oluşturamadım."

        # Hafızaya kaydet
        user_memory["conversation"].append({
            "role": "user",
            "content": message
        })

        user_memory["conversation"].append({
            "role": "assistant",
            "content": answer
        })

        # Hafıza aşırı büyümesin
        user_memory["conversation"] = user_memory["conversation"][-30:]

        save_memory()

        return {
            "success": True,
            "answer": answer,
            "username": username,
            "model": GROQ_MODEL
        }

    except Exception as error:

        error_type = classify_error(error)

        return {
            "success": False,
            "error": error_type,
            "message": str(error)
        }


# =========================================================
# NEW CHAT
# =========================================================

@app.post("/new-chat")
async def new_chat(data: LoginRequest):

    username = data.username.lower().strip()

    if username not in USERS:
        username = "karahan"

    user_memory = get_user_memory(username)

    user_memory["conversation"] = []

    save_memory()

    return {
        "success": True,
        "message": "Yeni sohbet başlatıldı.",
        "username": username
    }


# =========================================================
# MEMORY
# =========================================================

@app.get("/memory")
async def get_memory(username: str = "karahan"):

    username = username.lower().strip()

    if username not in USERS:
        username = "karahan"

    return {
        "username": username,
        "memory": get_user_memory(username)
    }


@app.delete("/memory")
async def delete_memory(username: str = "karahan"):

    username = username.lower().strip()

    if username not in USERS:
        username = "karahan"

    memory[username] = default_user_memory()

    save_memory()

    return {
        "success": True,
        "message": "Kullanıcı hafızası temizlendi."
    }


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
async def health():

    return {
        "status": "online",
        "version": APP_VERSION,
        "model": GROQ_MODEL,
        "groq_configured": bool(GROQ_API_KEY),
        "default_user": "karahan",
        "company": "KARAHAN INC."
    }


# =========================================================
# VERSION
# =========================================================

@app.get("/version")
async def version():

    return {
        "version": APP_VERSION,
        "name": "J.A.R.V.I.S.",
        "company": "KARAHAN INC."
    }
