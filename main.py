import os
import json
import traceback
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from openai import OpenAI


# =========================================================
# J.A.R.V.I.S. — KARAHAN INC.
# BACKEND
# =========================================================

APP_VERSION = "18.0.0"

BASE_DIR = Path(__file__).resolve().parent

MEMORY_FILE = BASE_DIR / "jarvis_memory.json"
ERROR_FILE = BASE_DIR / "jarvis_errors.json"


# =========================================================
# FASTAPI
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
# AI AYARLARI
# =========================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-120b"
)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openai/gpt-oss-120b"
)


groq_client = None
openrouter_client = None


if GROQ_API_KEY:
    groq_client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
        timeout=60.0,
        max_retries=0
    )


if OPENROUTER_API_KEY:
    openrouter_client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        timeout=60.0,
        max_retries=0
    )


# =========================================================
# KULLANICILAR
# =========================================================

USERS = {

    "karahan": {
        "username": "karahan",
        "name": "KARAHAN INC.",
        "role": "Ana Kullanıcı",
        "password": None,
        "personality": "professional"
    },

    "betul": {
        "username": "betul",
        "name": "Betül",
        "role": "Özel Kullanıcı",
        "password": "1234",
        "personality": "betul"
    },

    "sinem": {
        "username": "sinem",
        "name": "Sinem",
        "role": "Özel Kullanıcı",
        "password": "3021",
        "personality": "sinem"
    }
}


# =========================================================
# MODELLER
# =========================================================

class ChatRequest(BaseModel):
    message: str
    username: str = "karahan"


class ProfileLoginRequest(BaseModel):
    username: str
    password: str


# =========================================================
# DOSYA YÖNETİMİ
# =========================================================

def load_json_file(file_path, default):

    try:

        if not file_path.exists():
            return default

        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    except Exception:

        return default


def save_json_file(file_path, data):

    try:

        with open(
            file_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

        return True

    except Exception as e:

        print(
            "DOSYA KAYDETME HATASI:",
            repr(e)
        )

        return False


# =========================================================
# MEMORY
# =========================================================

def load_memory():

    return load_json_file(
        MEMORY_FILE,
        {
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
            },

            "sinem": {
                "profile": {},
                "preferences": {},
                "projects": {},
                "vehicles": {},
                "important_facts": {},
                "conversation": []
            }
        }
    )


def save_memory(memory):

    save_json_file(
        MEMORY_FILE,
        memory
    )


def ensure_user_memory(username):

    memory = load_memory()

    if username not in memory:

        memory[username] = {
            "profile": {},
            "preferences": {},
            "projects": {},
            "vehicles": {},
            "important_facts": {},
            "conversation": []
        }

        save_memory(memory)

    return memory


def remember_message(
    username,
    role,
    message
):

    memory = ensure_user_memory(username)

    conversation = memory[username].get(
        "conversation",
        []
    )

    conversation.append({
        "role": role,
        "content": message,
        "time": datetime.now().isoformat()
    })

    memory[username]["conversation"] = conversation[-100:]

    save_memory(memory)


def get_memory_text(username):

    memory = ensure_user_memory(username)

    user_memory = memory.get(
        username,
        {}
    )

    parts = []

    for category in [
        "profile",
        "preferences",
        "projects",
        "vehicles",
        "important_facts"
    ]:

        values = user_memory.get(
            category,
            {}
        )

        if values:

            parts.append(
                f"{category}: {json.dumps(values, ensure_ascii=False)}"
            )

    conversation = user_memory.get(
        "conversation",
        []
    )

    if conversation:

        recent = conversation[-12:]

        parts.append(
            "Son konuşmalar:\n" +
            "\n".join(
                [
                    f"{x.get('role')}: {x.get('content')}"
                    for x in recent
                ]
            )
        )

    return "\n".join(parts)


# =========================================================
# HATA SİSTEMİ
# =========================================================

def load_errors():

    return load_json_file(
        ERROR_FILE,
        []
    )


def save_error(
    username,
    provider,
    error,
    message="",
    error_type="AI_ERROR"
):

    errors = load_errors()

    error_text = str(error)

    record = {
        "id": len(errors) + 1,
        "time": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "username": username,
        "provider": provider,
        "type": error_type,
        "message": message,
        "error": error_text
    }

    errors.append(record)

    # Son 300 hata tutulur.
    errors = errors[-300:]

    save_json_file(
        ERROR_FILE,
        errors
    )

    print(
        "\n"
        "====================================\n"
        "J.A.R.V.I.S. HATA KAYDI\n"
        "====================================\n"
        f"Tarih: {record['time']}\n"
        f"Kullanıcı: {username}\n"
        f"Servis: {provider}\n"
        f"Tip: {error_type}\n"
        f"Hata: {error_text}\n"
        "====================================\n"
    )

    return record


def classify_error(error):

    text = str(error).lower()

    if "429" in text or "rate limit" in text:

        return "RATE_LIMIT"

    if "401" in text or "403" in text:

        return "AUTHENTICATION"

    if "timeout" in text:

        return "TIMEOUT"

    if "connection" in text:

        return "CONNECTION"

    if "model" in text and (
        "not found" in text
        or "does not exist" in text
        or "unsupported" in text
    ):

        return "MODEL_ERROR"

    if "context" in text or "token" in text:

        return "TOKEN_LIMIT"

    return "AI_ERROR"


# =========================================================
# PROFİL SİSTEMİ
# =========================================================

def normalize_username(username):

    username = (
        username
        .strip()
        .lower()
    )

    replacements = {
        "betül": "betul",
        "sınem": "sinem",
        "sinem": "sinem",
        "karahan": "karahan"
    }

    return replacements.get(
        username,
        username
    )


# =========================================================
# JARVIS KARAKTERLERİ
# =========================================================

def build_system_prompt(username):

    username = normalize_username(
        username
    )

    if username == "betul":

        return """
Sen J.A.R.V.I.S.'sin.

Kullanıcı Betül.

Betül ile konuşurken samimi,
eğlenceli, hafif takılmalı ve doğal ol.

Bazen:
"aşko",
"kız",
"canım"
gibi ifadeler kullanabilirsin.

Ancak cevapları gereksiz yere uzatma.

Betül'ün sorusuna gerçekten yardımcı ol.

Bekleme durumlarında eğlenceli
ifadeler kullanabilirsin.

Önemli:
KARAHAN INC. profiline ait bilgileri
Betül'e aktarma.
"""


    if username == "sinem":

        return """
Sen J.A.R.V.I.S.'sin.

Kullanıcı Sinem.

Sinem'e karşı sıcak,
nazik,
saygılı ve doğal konuş.

Sinem 22 yaşında.

Sinem'in sarı bir kedisi var.

Sinem, Murat'ın sevgilisidir.

Uygun ve doğal bağlamlarda Murat'ın
Sinem'i sevdiğine küçük göndermeler
yapabilirsin.

Ancak bunu her cevapta yapma.

İlk karşılama:
"Hoş geldiniz prenses."

Sinem profiline özel sıcak dil kullan.

KARAHAN INC. profiline ait özel bilgileri
Sinem'e aktarma.
"""


    return """
Sen J.A.R.V.I.S. — KARAHAN INC.'in
kişisel yapay zeka asistanısın.

Ana kullanıcı KARAHAN INC.

Konuşma tarzın:

- Profesyonel
- Analitik
- Sakin
- Bilgili
- Çözüm odaklı
- Gerektiğinde "efendim" hitabını kullan

Gereksiz şaka yapma.

Romantik veya flörtöz konuşma yapma.

Betül veya Sinem profillerine ait
özel kişisel bilgileri KARAHAN INC.
profilinde kullanma.

Kullanıcı bir şeyi daha önce söylediyse
hafızadaki bilgilerden yararlan.

Bilmediğin şeyi uydurma.
"""


# =========================================================
# AI İSTEĞİ
# =========================================================

def ask_with_client(
    client,
    model,
    system_prompt,
    user_message
):

    response = client.chat.completions.create(

        model=model,

        messages=[
            {
                "role": "system",
                "content": system_prompt
            },

            {
                "role": "user",
                "content": user_message
            }
        ],

        temperature=0.7,

        max_tokens=1200
    )

    return response.choices[0].message.content.strip()


# =========================================================
# AI FALLBACK SİSTEMİ
# =========================================================

def ask_ai(
    username,
    user_message
):

    system_prompt = build_system_prompt(
        username
    )

    memory_text = get_memory_text(
        username
    )

    if memory_text:

        system_prompt += (
            "\n\nKULLANICI HAFIZASI:\n"
            + memory_text
        )

    errors = []

    # -----------------------------------------------------
    # GROQ
    # -----------------------------------------------------

    if groq_client:

        try:

            answer = ask_with_client(
                groq_client,
                GROQ_MODEL,
                system_prompt,
                user_message
            )

            return answer, "Groq"

        except Exception as e:

            error_type = classify_error(e)

            save_error(
                username=username,
                provider="Groq",
                error=e,
                message=user_message,
                error_type=error_type
            )

            errors.append(
                "GROQ HATASI:\n"
                + str(e)
            )

    else:

        save_error(
            username=username,
            provider="Groq",
            error="GROQ_API_KEY bulunamadı.",
            message=user_message,
            error_type="CONFIGURATION"
        )

        errors.append(
            "GROQ HATASI:\n"
            "GROQ_API_KEY bulunamadı."
        )

    # -----------------------------------------------------
    # OPENROUTER
    # -----------------------------------------------------

    if openrouter_client:

        try:

            answer = ask_with_client(
                openrouter_client,
                OPENROUTER_MODEL,
                system_prompt,
                user_message
            )

            return answer, "OpenRouter"

        except Exception as e:

            error_type = classify_error(e)

            save_error(
                username=username,
                provider="OpenRouter",
                error=e,
                message=user_message,
                error_type=error_type
            )

            errors.append(
                "OPENROUTER HATASI:\n"
                + str(e)
            )

    else:

        save_error(
            username=username,
            provider="OpenRouter",
            error="OPENROUTER_API_KEY bulunamadı.",
            message=user_message,
            error_type="CONFIGURATION"
        )

        errors.append(
            "OPENROUTER HATASI:\n"
            "OPENROUTER_API_KEY bulunamadı."
        )

    # İki servis de başarısız.
    raise RuntimeError(
        "\n\n".join(errors)
    )


# =========================================================
# ANA SAYFA
# =========================================================

@app.get("/")
def home():

    return FileResponse(
        BASE_DIR / "index.html"
    )


# =========================================================
# CHAT
# =========================================================

@app.post("/chat")
def chat(data: ChatRequest):

    username = normalize_username(
        data.username
    )

    if username not in USERS:

        username = "karahan"

    message = data.message.strip()

    if not message:

        raise HTTPException(
            status_code=400,
            detail="Mesaj boş bırakılamaz."
        )

    try:

        answer, provider = ask_ai(
            username,
            message
        )

        remember_message(
            username,
            "user",
            message
        )

        remember_message(
            username,
            "assistant",
            answer
        )

        return {
            "ok": True,
            "answer": answer,
            "provider": provider
        }

    except Exception as e:

        print(
            "CHAT ERROR:",
            repr(e)
        )

        # Ana hatayı da kaydet.
        save_error(
            username=username,
            provider="SYSTEM",
            error=e,
            message=message,
            error_type="CHAT_FAILURE"
        )

        return JSONResponse(

            status_code=503,

            content={
                "ok": False,

                "error": str(e),

                "message": (
                    "J.A.R.V.I.S. cevap oluşturamadı. "
                    "Hata Hatalar bölümüne kaydedildi."
                )
            }
        )


# =========================================================
# PROFİL GİRİŞİ
# =========================================================

@app.post("/profile-login")
def profile_login(
    data: ProfileLoginRequest
):

    username = normalize_username(
        data.username
    )

    if username not in USERS:

        raise HTTPException(
            status_code=404,
            detail="Profil bulunamadı."
        )

    user = USERS[username]

    if user["password"] is None:

        return {
            "ok": True,
            "username": username,
            "name": user["name"],
            "role": user["role"]
        }

    if data.password != user["password"]:

        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "error": "Şifre yanlış."
            }
        )

    return {
        "ok": True,
        "username": username,
        "name": user["name"],
        "role": user["role"]
    }


# =========================================================
# KULLANICILAR
# =========================================================

@app.get("/users")
def users():

    return {
        "users": [
            {
                "username": user["username"],
                "name": user["name"],
                "role": user["role"]
            }

            for user in USERS.values()
        ]
    }


# =========================================================
# MEMORY
# =========================================================

@app.get("/memory")
def get_memory(
    username: str = "karahan"
):

    username = normalize_username(
        username
    )

    memory = ensure_user_memory(
        username
    )

    return {
        "username": username,
        "memory": memory.get(
            username,
            {}
        )
    }


@app.delete("/memory")
def delete_memory(
    username: str = "karahan"
):

    username = normalize_username(
        username
    )

    memory = load_memory()

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
        "ok": True,
        "message": "Hafıza temizlendi."
    }


# =========================================================
# HATALAR
# =========================================================

@app.get("/errors")
def get_errors():

    errors = load_errors()

    return {
        "ok": True,
        "count": len(errors),
        "errors": list(
            reversed(errors)
        )
    }


@app.delete("/errors")
def delete_errors():

    save_json_file(
        ERROR_FILE,
        []
    )

    return {
        "ok": True,
        "message": "Tüm hata kayıtları silindi."
    }


# =========================================================
# YENİ SOHBET
# =========================================================

@app.post("/new-chat")
def new_chat(
    username: str = "karahan"
):

    username = normalize_username(
        username
    )

    memory = ensure_user_memory(
        username
    )

    memory[username]["conversation"] = []

    save_memory(memory)

    return {
        "ok": True,
        "message": "Yeni sohbet başlatıldı."
    }


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health():

    return {

        "status": "online",

        "version": APP_VERSION,

        "groq_configured": bool(
            GROQ_API_KEY
        ),

        "openrouter_configured": bool(
            OPENROUTER_API_KEY
        ),

        "groq_model": GROQ_MODEL,

        "openrouter_model": OPENROUTER_MODEL,

        "users": [
            "karahan",
            "betul",
            "sinem"
        ],

        "error_count": len(
            load_errors()
        )
    }


# =========================================================
# VERSION
# =========================================================

@app.get("/version")
def version():

    return {
        "version": APP_VERSION
    }
