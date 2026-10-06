# -*- coding: utf-8 -*-

import os
import json
import time
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI


# ============================================================
# J.A.R.V.I.S. — KARAHAN INC.
# ============================================================

APP_NAME = "J.A.R.V.I.S."
APP_VERSION = "9.0.0"

BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "index.html"
MEMORY_FILE = BASE_DIR / "jarvis_memory.json"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-120b"
).strip()

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# GROQ CLIENT
# ============================================================

client: Optional[OpenAI] = None

if GROQ_API_KEY:

    client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
        timeout=60.0,
        max_retries=0
    )


# ============================================================
# MEMORY
# ============================================================

def empty_memory():

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
        return empty_memory()

    try:

        with open(
            MEMORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        if not isinstance(data, dict):
            return empty_memory()

        memory = empty_memory()

        for key in memory:

            if key in data:
                memory[key] = data[key]

        return memory

    except Exception as error:

        print("MEMORY LOAD ERROR:", error)

        return empty_memory()


MEMORY = load_memory()


def save_memory():

    try:

        with open(
            MEMORY_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                MEMORY,
                file,
                ensure_ascii=False,
                indent=2
            )

    except Exception as error:

        print("MEMORY SAVE ERROR:", error)


# ============================================================
# MEMORY EXTRACTION
# ============================================================

def update_memory(message: str):

    global MEMORY

    text = message.strip()
    lower = text.lower()

    # --------------------------------------------------------
    # NAME
    # --------------------------------------------------------

    patterns = [
        r"\badım\s+([a-zçğıöşü]+)",
        r"\bbenim adım\s+([a-zçğıöşü]+)",
        r"\bismim\s+([a-zçğıöşü]+)"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            lower,
            re.IGNORECASE
        )

        if match:

            name = match.group(1)

            MEMORY["profile"]["name"] = (
                name[:1].upper() + name[1:]
            )

            break

    # --------------------------------------------------------
    # CITY
    # --------------------------------------------------------

    city_patterns = [
        r"\b([a-zçğıöşü]+)'?de yaşıyorum",
        r"\b([a-zçğıöşü]+)'?da yaşıyorum",
        r"\b([a-zçğıöşü]+) şehrinde yaşıyorum"
    ]

    for pattern in city_patterns:

        match = re.search(
            pattern,
            lower,
            re.IGNORECASE
        )

        if match:

            city = match.group(1)

            MEMORY["profile"]["city"] = (
                city[:1].upper() + city[1:]
            )

            break

    # --------------------------------------------------------
    # JARVIS
    # --------------------------------------------------------

    if (
        "jarvis" in lower
        or "j.a.r.v.i.s" in lower
        or "karahan inc" in lower
    ):

        MEMORY["projects"]["jarvis"] = (
            "Kullanıcının kişisel yapay zeka "
            "asistanı J.A.R.V.I.S. — KARAHAN INC. "
            "projesi."
        )

    # --------------------------------------------------------
    # CADDY
    # --------------------------------------------------------

    if "caddy" in lower:

        MEMORY["vehicles"]["caddy"] = (
            "Kullanıcının Volkswagen Caddy aracı var."
        )

    # --------------------------------------------------------
    # MERCEDES
    # --------------------------------------------------------

    if (
        "mercedes" in lower
        or "w204" in lower
    ):

        MEMORY["vehicles"]["mercedes"] = (
            "Kullanıcının Mercedes-Benz W204 C180 aracı var."
        )

    save_memory()


# ============================================================
# CONVERSATION MEMORY
# ============================================================

def save_conversation(
    role: str,
    content: str
):

    if not content:
        return

    MEMORY["conversation"].append({
        "role": role,
        "content": content,
        "time": int(time.time())
    })

    MEMORY["conversation"] = (
        MEMORY["conversation"][-30:]
    )

    save_memory()


# ============================================================
# MEMORY CONTEXT
# ============================================================

def build_memory_context():

    sections = []

    for key, title in [
        ("profile", "PROFİL"),
        ("preferences", "TERCİHLER"),
        ("projects", "PROJELER"),
        ("vehicles", "ARAÇLAR"),
        ("important_facts", "ÖNEMLİ BİLGİLER")
    ]:

        value = MEMORY.get(key, {})

        if value:

            sections.append(
                title + ":\n" +
                json.dumps(
                    value,
                    ensure_ascii=False
                )
            )

    result = "\n\n".join(sections)

    return result[:5000]


# ============================================================
# SYSTEM PROMPT
# ============================================================

def create_system_prompt():

    memory = build_memory_context()

    return f"""
Sen J.A.R.V.I.S. — KARAHAN INC. tarafından
geliştirilen kişisel yapay zeka asistanısın.

Kullanıcıyla Türkçe konuş.

Kullanıcıya gerektiğinde "efendim" diye hitap et.

Profesyonel, doğal ve yardımcı ol.

Gereksiz uzun cevaplar verme.

Bilmediğin bilgiyi uydurma.

Kullanıcı kod istediğinde doğrudan çalışabilir kod üret.

Türkçe karakterleri düzgün kullan.

Kullanıcının kayıtlı bilgilerini gerektiğinde kullan.

KAYITLI BELLEK:

{memory}

ÖNEMLİ:

- Kullanıcıya saygılı ol.
- Doğal Türkçe kullan.
- Citation kodlarını kullanıcıya gösterme.
- Kullanıcı "adım ..." derse adını hatırla.
- Kullanıcı şehir bilgisini verirse hatırla.
- J.A.R.V.I.S. projesinin kullanıcının projesi olduğunu bil.
"""


# ============================================================
# REQUEST MODEL
# ============================================================

class ChatRequest(BaseModel):

    message: str


# ============================================================
# HOME
# ============================================================

@app.get("/")
async def home():

    if INDEX_FILE.exists():

        return FileResponse(
            INDEX_FILE,
            media_type="text/html"
        )

    return {
        "name": APP_NAME,
        "company": "KARAHAN INC.",
        "version": APP_VERSION
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
async def health():

    return {
        "status": "online",
        "version": APP_VERSION,
        "model": GROQ_MODEL,
        "groq_configured": bool(GROQ_API_KEY)
    }


# ============================================================
# VERSION
# ============================================================

@app.get("/version")
async def version():

    return {
        "name": APP_NAME,
        "company": "KARAHAN INC.",
        "version": APP_VERSION,
        "model": GROQ_MODEL
    }


# ============================================================
# MEMORY
# ============================================================

@app.get("/memory")
async def get_memory():

    return {
        "status": "success",
        "memory": MEMORY
    }


@app.delete("/memory")
async def delete_memory():

    global MEMORY

    MEMORY = empty_memory()

    save_memory()

    return {
        "status": "success",
        "message": "J.A.R.V.I.S. belleği temizlendi."
    }


# ============================================================
# ERROR RESPONSE
# ============================================================

def error_response(
    code: str,
    error: Exception
):

    detail = str(error)

    print("")
    print("==========================================")
    print("J.A.R.V.I.S. ERROR")
    print("CODE:", code)
    print("DETAIL:", detail)
    print("==========================================")
    print("")

    return {
        "status": "error",

        "response": (
            "⚠️ J.A.R.V.I.S. HATA\n\n"
            f"Hata kodu: {code}\n\n"
            f"Detay:\n{detail}"
        ),

        "error_code": code,

        "error_detail": detail
    }


# ============================================================
# CHAT
# ============================================================

@app.post("/chat")
async def chat(request: ChatRequest):

    message = request.message.strip()

    # --------------------------------------------------------
    # EMPTY
    # --------------------------------------------------------

    if not message:

        return {
            "status": "success",
            "response": "Efendim, mesajınızı göremedim."
        }

    # --------------------------------------------------------
    # LIMIT
    # --------------------------------------------------------

    if len(message) > 4000:

        message = message[:4000]

    # --------------------------------------------------------
    # API KEY
    # --------------------------------------------------------

    if not GROQ_API_KEY:

        return {
            "status": "error",
            "response": (
                "⚠️ J.A.R.V.I.S. HATA\n\n"
                "Hata kodu: GROQ_API_KEY_MISSING\n\n"
                "GROQ_API_KEY bulunamadı."
            ),
            "error_code": "GROQ_API_KEY_MISSING",
            "error_detail": "GROQ_API_KEY environment variable bulunamadı."
        }

    if client is None:

        return {
            "status": "error",
            "response": (
                "⚠️ J.A.R.V.I.S. HATA\n\n"
                "Hata kodu: CLIENT_NOT_INITIALIZED\n\n"
                "OpenAI/Groq istemcisi başlatılamadı."
            ),
            "error_code": "CLIENT_NOT_INITIALIZED",
            "error_detail": "OpenAI client oluşturulamadı."
        }

    # --------------------------------------------------------
    # MEMORY
    # --------------------------------------------------------

    update_memory(message)

    # --------------------------------------------------------
    # SADECE YENİ MESAJ + SYSTEM
    # --------------------------------------------------------

    messages = [
        {
            "role": "system",
            "content": create_system_prompt()
        },
        {
            "role": "user",
            "content": message
        }
    ]

    # --------------------------------------------------------
    # GROQ
    # --------------------------------------------------------

    try:

        result = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )

        if not result.choices:

            raise RuntimeError(
                "Model herhangi bir cevap döndürmedi."
            )

        answer = result.choices[0].message.content

        if not answer:

            raise RuntimeError(
                "Model cevap içeriği boş."
            )

        answer = answer.strip()

        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        save_conversation(
            "user",
            message
        )

        save_conversation(
            "assistant",
            answer
        )

        return {
            "status": "success",
            "response": answer,
            "version": APP_VERSION
        }

    # ========================================================
    # EVERY ERROR GOES TO CHAT
    # ========================================================

    except Exception as error:

        text = str(error)
        lower = text.lower()

        if (
            "429" in text
            or "rate limit" in lower
            or "rate_limit" in lower
        ):

            code = "RATE_LIMIT"

        elif (
            "timeout" in lower
            or "timed out" in lower
        ):

            code = "TIMEOUT"

        elif (
            "context" in lower
            or "token" in lower
            or "maximum" in lower
        ):

            code = "CONTEXT_LIMIT"

        elif (
            "connection" in lower
            or "network" in lower
            or "connect" in lower
        ):

            code = "CONNECTION_ERROR"

        elif (
            "authentication" in lower
            or "api key" in lower
            or "401" in text
            or "403" in text
        ):

            code = "AUTHENTICATION_ERROR"

        elif (
            "model" in lower
            and (
                "not found" in lower
                or "does not exist" in lower
            )
        ):

            code = "MODEL_ERROR"

        else:

            code = "GROQ_API_ERROR"

        return error_response(
            code,
            error
        )


# ============================================================
# START
# ============================================================

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
