import os
import json
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from openai import OpenAI


# =========================================================
# J.A.R.V.I.S. - KARAHAN INC.
# VERSION 10.1
# =========================================================

APP_VERSION = "10.1.0"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-20b"
)

MEMORY_FILE = "jarvis_memory.json"


# =========================================================
# FASTAPI
# =========================================================

app = FastAPI(
    title="J.A.R.V.I.S. - KARAHAN INC.",
    version=APP_VERSION
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# =========================================================
# GROQ CLIENT
# =========================================================

client = None

if GROQ_API_KEY:
    client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
        timeout=45.0,
        max_retries=0
    )


# =========================================================
# MEMORY
# =========================================================

DEFAULT_MEMORY = {
    "profile": {},
    "preferences": {},
    "projects": {},
    "vehicles": {},
    "important_facts": {}
}


def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {
            "profile": {},
            "preferences": {},
            "projects": {},
            "vehicles": {},
            "important_facts": {}
        }

    try:
        with open(
            MEMORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        for key in DEFAULT_MEMORY:
            if key not in data:
                data[key] = {}

        return data

    except Exception:
        return {
            "profile": {},
            "preferences": {},
            "projects": {},
            "vehicles": {},
            "important_facts": {}
        }


def save_memory(data):
    try:
        with open(
            MEMORY_FILE,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

    except Exception as error:
        print("Memory save error:", str(error))


memory = load_memory()


# =========================================================
# MEMORY LEARNING
# =========================================================

def remember_from_message(text):
    global memory

    lower_text = text.lower()

    # -------------------------
    # İSİM
    # -------------------------

    name_patterns = [
        r"\badım\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)",
        r"\bbenim adım\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)",
        r"\bismim\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)"
    ]

    for pattern in name_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            memory["profile"]["name"] = match.group(1)
            break

    # -------------------------
    # ŞEHİR
    # -------------------------

    city_patterns = [
        r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]+)'de yaşıyorum",
        r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]+)'da yaşıyorum",
        r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]+)de yaşıyorum",
        r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]+)da yaşıyorum"
    ]

    for pattern in city_patterns:
        match = re.search(pattern, text)

        if match:
            memory["profile"]["city"] = match.group(1)
            break

    # -------------------------
    # JARVIS PROJESİ
    # -------------------------

    if (
        "jarvis" in lower_text
        or "j.a.r.v.i.s" in lower_text
        or "karahan inc" in lower_text
    ):
        memory["projects"]["jarvis"] = (
            "J.A.R.V.I.S. - KARAHAN INC. "
            "kişisel yapay zeka asistanı."
        )

    # -------------------------
    # CADDY
    # -------------------------

    if "caddy" in lower_text:
        memory["vehicles"]["caddy"] = (
            "Volkswagen Caddy"
        )

    # -------------------------
    # MERCEDES
    # -------------------------

    if (
        "mercedes" in lower_text
        or "w204" in lower_text
        or "c180" in lower_text
    ):
        memory["vehicles"]["mercedes"] = (
            "Mercedes-Benz C180 W204"
        )

    save_memory(memory)


# =========================================================
# MEMORY SUMMARY
# =========================================================

def get_memory_summary():
    parts = []

    profile = memory.get("profile", {})

    if profile.get("name"):
        parts.append(
            "Kullanıcının adı: "
            + str(profile["name"])
        )

    if profile.get("city"):
        parts.append(
            "Yaşadığı şehir: "
            + str(profile["city"])
        )

    projects = memory.get("projects", {})

    for value in projects.values():
        parts.append(
            "Proje: " + str(value)
        )

    vehicles = memory.get("vehicles", {})

    for value in vehicles.values():
        parts.append(
            "Araç: " + str(value)
        )

    preferences = memory.get("preferences", {})

    for key, value in preferences.items():
        parts.append(
            str(key) + ": " + str(value)
        )

    important_facts = memory.get(
        "important_facts",
        {}
    )

    for key, value in important_facts.items():
        parts.append(
            str(key) + ": " + str(value)
        )

    if not parts:
        return "Kayıtlı kullanıcı bilgisi bulunmuyor."

    return "\n".join(parts[:15])


# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
Sen J.A.R.V.I.S. - KARAHAN INC. kişisel yapay zeka asistanısın.

Her zaman Türkçe konuş.

Kullanıcıya gerektiğinde "efendim" diye hitap et.

Profesyonel, doğal ve yardımcı ol.

Basit sorulara kısa cevap ver.

Kullanıcı ayrıntılı açıklama isterse ayrıntılı cevap ver.

Bilmediğin bilgileri kesinmiş gibi söyleme.

Kullanıcı sana kalıcı bir kişisel bilgi verdiğinde,
bu bilgi sistem tarafından hafızaya kaydedilebilir.

Kendini J.A.R.V.I.S. olarak tanıt.

ChatGPT olduğunu söyleme.

Gereksiz tekrar yapma.

Cevaplarını mümkün olduğunca anlaşılır ve doğal tut.
"""


# =========================================================
# REQUEST MODEL
# =========================================================

class ChatRequest(BaseModel):
    message: str


# =========================================================
# ERROR RESPONSE
# =========================================================

def error_response(code, detail):
    return JSONResponse(
        status_code=200,
        content={
            "status": "error",
            "response": (
                "J.A.R.V.I.S. HATA\n\n"
                "Hata kodu: "
                + code
                + "\n\n"
                "Detay:\n"
                + detail
            ),
            "error_code": code,
            "error_detail": detail
        }
    )


# =========================================================
# HOME
# =========================================================

@app.get("/")
async def home():
    return FileResponse("index.html")


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
        "memory": True
    }


# =========================================================
# VERSION
# =========================================================

@app.get("/version")
async def version():
    return {
        "app": "J.A.R.V.I.S. - KARAHAN INC.",
        "version": APP_VERSION,
        "model": GROQ_MODEL
    }


# =========================================================
# GET MEMORY
# =========================================================

@app.get("/memory")
async def get_memory():
    return {
        "status": "success",
        "memory": memory
    }


# =========================================================
# DELETE MEMORY
# =========================================================

@app.delete("/memory")
async def delete_memory():
    global memory

    memory = {
        "profile": {},
        "preferences": {},
        "projects": {},
        "vehicles": {},
        "important_facts": {}
    }

    save_memory(memory)

    return {
        "status": "success",
        "message": "J.A.R.V.I.S. hafızası temizlendi."
    }


# =========================================================
# CHAT
# =========================================================

@app.post("/chat")
async def chat(request: ChatRequest):

    user_message = request.message.strip()

    if not user_message:
        return error_response(
            "EMPTY_MESSAGE",
            "Mesaj boş gönderildi."
        )

    if not GROQ_API_KEY:
        return error_response(
            "MISSING_API_KEY",
            "GROQ_API_KEY bulunamadı."
        )

    if client is None:
        return error_response(
            "CLIENT_ERROR",
            "Groq istemcisi oluşturulamadı."
        )

    # Hafızaya kaydet
    try:
        remember_from_message(user_message)

    except Exception as error:
        print(
            "Memory warning:",
            str(error)
        )

    # Kısa hafıza
    user_memory = get_memory_summary()

    system_message = (
        SYSTEM_PROMPT
        + "\n\n"
        + "Kullanıcı hakkında kayıtlı bilgiler:"
        + "\n"
        + user_memory
    )

    try:

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": system_message
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            max_tokens=500,
            temperature=0.6
        )

        if not response.choices:
            return error_response(
                "EMPTY_RESPONSE",
                "Model cevap döndürmedi."
            )

        answer = response.choices[0].message.content

        if answer is None:
            return error_response(
                "EMPTY_RESPONSE",
                "Model boş cevap döndürdü."
            )

        answer = answer.strip()

        if not answer:
            return error_response(
                "EMPTY_RESPONSE",
                "Model boş cevap döndürdü."
            )

        return {
            "status": "success",
            "response": answer,
            "model": GROQ_MODEL
        }

    except Exception as error:

        detail = str(error)

        print(
            "GROQ ERROR:",
            detail
        )

        lower_detail = detail.lower()

        # Rate limit
        if (
            "429" in detail
            or "rate limit" in lower_detail
            or "rate_limit" in lower_detail
        ):
            return error_response(
                "RATE_LIMIT",
                detail
            )

        # Authentication
        if (
            "401" in detail
            or "403" in detail
            or "authentication" in lower_detail
            or "api key" in lower_detail
        ):
            return error_response(
                "AUTHENTICATION_ERROR",
                detail
            )

        # Model
        if (
            "model" in lower_detail
            and (
                "not found" in lower_detail
                or "does not exist" in lower_detail
            )
        ):
            return error_response(
                "MODEL_ERROR",
                detail
            )

        # Timeout
        if (
            "timeout" in lower_detail
            or "timed out" in lower_detail
        ):
            return error_response(
                "TIMEOUT",
                detail
            )

        # Connection
        if (
            "connection" in lower_detail
            or "network" in lower_detail
        ):
            return error_response(
                "CONNECTION_ERROR",
                detail
            )

        # Token / context
        if (
            "token" in lower_detail
            or "context" in lower_detail
        ):
            return error_response(
                "TOKEN_LIMIT",
                detail
            )

        # Genel hata
        return error_response(
            "GROQ_API_ERROR",
            detail
        )


# =========================================================
# LOCAL START
# =========================================================

if __name__ == "__main__":

    import uvicorn

    port = int(
        os.getenv(
            "PORT",
            "8000"
        )
    )

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port
    )
