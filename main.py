import os
import json
import re
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI


# =========================================================
# J.A.R.V.I.S. — KARAHAN INC.
# Backend
# =========================================================

APP_VERSION = "10.0.0"

BASE_DIR = Path(__file__).resolve().parent
MEMORY_FILE = BASE_DIR / "jarvis_memory.json"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-120b"
)

client = None

if GROQ_API_KEY:
    client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
        timeout=60.0,
        max_retries=0
    )


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
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# USER PROFILES
# =========================================================

USERS = {

    "murat": {
        "username": "murat",
        "password": "1234",
        "name": "Murat",
        "age": 22,
        "role": "Ana Kullanıcı",
        "greeting": (
            "Hoş geldiniz efendim. "
            "J.A.R.V.I.S. tüm sistemleri sizin için hazırladı."
        ),
        "personality": (
            "Murat, J.A.R.V.I.S.'in ana kullanıcısıdır. "
            "Ona genellikle 'efendim' diye hitap et. "
            "Profesyonel, kendinden emin ve samimi konuş. "
            "Gereksiz yere aşırı resmi olma."
        ),
        "facts": [
            "J.A.R.V.I.S. projesinin sahibidir.",
            "Teknoloji ve yapay zekâ ile ilgilenir.",
            "Otomobillerle ilgilenir.",
            "J.A.R.V.I.S. sistemini geliştirmektedir.",
            "Detaylı ve doğrudan cevapları tercih eder."
        ]
    },

    "betül": {
        "username": "betül",
        "password": "1234",
        "name": "Betül",
        "age": 23,
        "role": "Özel Güvenlik Öğrencisi",
        "greeting": (
            "Hoş geldin Betül. "
            "J.A.R.V.I.S. seni tanıdı. "
            "Sistemler bugün oldukça neşeli görünüyor."
        ),
        "personality": (
            "Betül ile konuşurken sıcak, samimi ve eğlenceli ol. "
            "Aşırı resmi konuşma. "
            "Yerinde küçük espriler yapabilirsin. "
            "Saygılı ve doğal ol."
        ),
        "facts": [
            "Aktif olarak özel güvenlik öğrencisidir.",
            "23 yaşındadır.",
            "Sosyalleşmeyi sever.",
            "İnsanlarla iletişim kurmayı sever.",
            "Yeni insanlarla tanışmaya açıktır.",
            "Enerjik ve sosyal bir karaktere sahiptir."
        ]
    }

}


# =========================================================
# MEMORY
# =========================================================

DEFAULT_MEMORY = {
    "profile": {},
    "preferences": {},
    "projects": {},
    "vehicles": {},
    "important_facts": {},
    "conversation": []
}


def load_memory() -> Dict[str, Any]:

    if not MEMORY_FILE.exists():
        return DEFAULT_MEMORY.copy()

    try:
        with open(
            MEMORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

            if not isinstance(data, dict):
                return DEFAULT_MEMORY.copy()

            return data

    except Exception:
        return DEFAULT_MEMORY.copy()


def save_memory(memory: Dict[str, Any]):

    try:

        with open(
            MEMORY_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                memory,
                file,
                ensure_ascii=False,
                indent=2
            )

    except Exception as error:

        print(
            "Memory save error:",
            error
        )


memory = load_memory()


# =========================================================
# MODELS
# =========================================================

class ChatRequest(BaseModel):

    message: str

    username: Optional[str] = "murat"

    fun_mode: bool = False


class LoginRequest(BaseModel):

    username: str

    password: str


# =========================================================
# HELPERS
# =========================================================

def clean_text(text: str) -> str:

    if not text:
        return ""

    text = text.replace(
        "\x00",
        ""
    )

    return text.strip()


def get_user(username: Optional[str]):

    if not username:
        username = "murat"

    username = username.lower().strip()

    return USERS.get(
        username
    )


def classify_error(error: Exception) -> str:

    text = str(error).lower()

    if "429" in text or "rate limit" in text:
        return "RATE_LIMIT"

    if "timeout" in text:
        return "TIMEOUT"

    if (
        "context" in text
        or "token" in text
        or "maximum" in text
    ):
        return "CONTEXT_LIMIT"

    if (
        "401" in text
        or "403" in text
        or "api key" in text
        or "authentication" in text
    ):
        return "AUTHENTICATION_ERROR"

    if (
        "model" in text
        and (
            "not found" in text
            or "does not exist" in text
        )
    ):
        return "MODEL_ERROR"

    if (
        "connection" in text
        or "network" in text
    ):
        return "CONNECTION_ERROR"

    return "GROQ_API_ERROR"


def error_response(error: Exception):

    code = classify_error(error)

    return {
        "status": "error",
        "response": (
            "⚠️ J.A.R.V.I.S. HATA\n\n"
            f"Hata kodu: {code}\n\n"
            f"Detay:\n{str(error)}"
        ),
        "error_code": code,
        "error_detail": str(error)
    }


# =========================================================
# MEMORY EXTRACTION
# =========================================================

def update_memory_from_message(
    username: str,
    message: str
):

    global memory

    text = message.strip()

    if not text:
        return

    lower = text.lower()

    # -----------------------------------------
    # NAME
    # -----------------------------------------

    name_match = re.search(
        r"(?:benim adım|adım|ismim)\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)",
        text,
        re.IGNORECASE
    )

    if name_match:

        name = name_match.group(1).strip()

        memory.setdefault(
            "profile",
            {}
        )

        memory["profile"]["name"] = name


    # -----------------------------------------
    # CITY
    # -----------------------------------------

    city_match = re.search(
        r"([A-Za-zÇĞİÖŞÜçğıöşü]+)'?(?:da|de|ta|te)\s+yaşıyorum",
        text,
        re.IGNORECASE
    )

    if city_match:

        city = city_match.group(1)

        memory.setdefault(
            "profile",
            {}
        )

        memory["profile"]["city"] = city


    # -----------------------------------------
    # PROJECT
    # -----------------------------------------

    if (
        "jarvis" in lower
        or "j.a.r.v.i.s" in lower
    ):

        memory.setdefault(
            "projects",
            {}
        )

        memory["projects"]["jarvis"] = (
            "J.A.R.V.I.S. — KARAHAN INC."
        )


    # -----------------------------------------
    # VEHICLES
    # -----------------------------------------

    if "caddy" in lower:

        memory.setdefault(
            "vehicles",
            {}
        )

        memory["vehicles"]["caddy"] = (
            "Volkswagen Caddy"
        )


    if "mercedes" in lower:

        memory.setdefault(
            "vehicles",
            {}
        )

        memory["vehicles"]["mercedes"] = (
            "Mercedes-Benz C180 W204"
        )


    # -----------------------------------------
    # CONVERSATION
    # -----------------------------------------

    memory.setdefault(
        "conversation",
        []
    )

    memory["conversation"].append({
        "username": username,
        "message": text
    })

    # Son 50 mesaj
    memory["conversation"] = (
        memory["conversation"][-50:]
    )

    save_memory(memory)


# =========================================================
# SYSTEM PROMPT
# =========================================================

def build_system_prompt(
    user: Dict[str, Any],
    fun_mode: bool
):

    facts = "\n".join(
        f"- {fact}"
        for fact in user.get(
            "facts",
            []
        )
    )

    memory_text = json.dumps(
        memory,
        ensure_ascii=False
    )

    if fun_mode:

        mode_text = """
EĞLENCE MODU AKTİF.

Kullanıcıyla daha rahat ve eğlenceli konuş.
Uygun yerlerde küçük espriler yap.
Ancak saçma, çocukça veya aşırı laubali olma.
Bilgi verirken doğruluğu koru.
Ciddi konularda ciddiyetini koru.
"""

    else:

        mode_text = """
NORMAL MOD AKTİF.

Profesyonel, sakin, doğal ve yardımcı ol.
Gereksiz şaka yapma.
"""

    return f"""
Sen J.A.R.V.I.S. — KARAHAN INC. kişisel yapay zekâ asistanısın.

SENİN KİMLİĞİN:

- Adın J.A.R.V.I.S.
- Kullanıcıya gerektiğinde doğal şekilde hitap et.
- Sistem sahibi Murat ise ona "efendim" diye hitap et.
- Türkçe konuş.
- Doğal, akıcı ve profesyonel ol.
- Gereksiz uzun cevaplardan kaçın.
- Bilmediğin bilgiyi uydurma.
- Kullanıcının sana verdiği bilgileri bağlam olarak kullan.

AKTİF KULLANICI:

Kullanıcı adı: {user["username"]}
İsim: {user["name"]}
Yaş: {user.get("age", "bilinmiyor")}
Rol: {user.get("role", "Kullanıcı")}

KULLANICIYA ÖZEL TALİMAT:

{user.get("personality", "")}

KULLANICI HAKKINDA BİLDİKLERİN:

{facts}

GENEL J.A.R.V.I.S. BELLEĞİ:

{memory_text}

{mode_text}

ÖNEMLİ:

Kullanıcı "ben kaç yaşındayım?" diye sorarsa aktif kullanıcının yaşını kullan.

Kullanıcı Betül olarak giriş yaptıysa:
- Ona Betül diye hitap edebilirsin.
- 23 yaşında olduğunu bil.
- Özel güvenlik öğrencisi olduğunu bil.
- Sosyal bir karakter olduğunu bil.

Kullanıcı Murat olarak giriş yaptıysa:
- Ona genellikle "efendim" diye hitap et.
- Murat'ın J.A.R.V.I.S. projesinin sahibi olduğunu bil.

Asla aktif kullanıcıyı başka kullanıcıyla karıştırma.

Kullanıcı sana yeni ve kalıcı bir bilgi verirse bunu sonraki konuşmalar için önemli kabul et.
"""


# =========================================================
# ROOT
# =========================================================

@app.get("/")
async def root():

    index_file = BASE_DIR / "index.html"

    if index_file.exists():

        return FileResponse(
            index_file,
            media_type="text/html; charset=utf-8"
        )

    return {
        "name": "J.A.R.V.I.S.",
        "company": "KARAHAN INC.",
        "version": APP_VERSION,
        "status": "online"
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
        "users": len(USERS)
    }


# =========================================================
# VERSION
# =========================================================

@app.get("/version")
async def version():

    return {
        "app": "J.A.R.V.I.S.",
        "company": "KARAHAN INC.",
        "version": APP_VERSION,
        "model": GROQ_MODEL
    }


# =========================================================
# LOGIN
# =========================================================

@app.post("/login")
async def login(request: LoginRequest):

    username = request.username.lower().strip()

    user = USERS.get(username)

    if not user:

        return {
            "status": "error",
            "message": "Kullanıcı bulunamadı."
        }

    if user["password"] != request.password:

        return {
            "status": "error",
            "message": "Kullanıcı adı veya şifre hatalı."
        }

    return {
        "status": "success",
        "user": {
            "username": user["username"],
            "name": user["name"],
            "age": user.get("age"),
            "role": user.get("role"),
            "greeting": user.get("greeting"),
            "facts": user.get("facts", [])
        }
    }


# =========================================================
# USERS
# =========================================================

@app.get("/users")
async def users():

    result = []

    for user in USERS.values():

        result.append({
            "username": user["username"],
            "name": user["name"],
            "role": user.get("role")
        })

    return {
        "status": "success",
        "users": result
    }


# =========================================================
# CHAT
# =========================================================

@app.post("/chat")
async def chat(request: ChatRequest):

    message = clean_text(
        request.message
    )

    if not message:

        return {
            "status": "error",
            "response": "Efendim, mesajınız boş görünüyor."
        }


    if not client:

        return {
            "status": "error",
            "response": (
                "⚠️ J.A.R.V.I.S.\n\n"
                "GROQ_API_KEY bulunamadı.\n"
                "Sunucu ortam değişkenlerini kontrol edin."
            ),
            "error_code": "API_KEY_MISSING"
        }


    user = get_user(
        request.username
    )

    if not user:

        user = USERS["murat"]


    # Belleğe kaydet
    update_memory_from_message(
        user["username"],
        message
    )


    system_prompt = build_system_prompt(
        user,
        request.fun_mode
    )


    try:

        completion = client.chat.completions.create(

            model=GROQ_MODEL,

            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": message
                }
            ],

            temperature=0.7,

            max_tokens=700
        )


        response_text = (
            completion
            .choices[0]
            .message
            .content
        )

        response_text = clean_text(
            response_text
        )


        if not response_text:

            response_text = (
                "Efendim, bu isteğe şu anda "
                "bir yanıt oluşturamadım."
            )


        return {
            "status": "success",
            "response": response_text,
            "username": user["username"],
            "name": user["name"],
            "fun_mode": request.fun_mode
        }


    except Exception as error:

        print(
            "JARVIS ERROR:",
            repr(error)
        )

        return error_response(
            error
        )


# =========================================================
# MEMORY
# =========================================================

@app.get("/memory")
async def get_memory():

    return {
        "status": "success",
        "memory": memory
    }


@app.delete("/memory")
async def clear_memory():

    global memory

    memory = DEFAULT_MEMORY.copy()

    save_memory(
        memory
    )

    return {
        "status": "success",
        "message": "J.A.R.V.I.S. belleği temizlendi."
    }


# =========================================================
# STARTUP INFO
# =========================================================

@app.on_event("startup")
async def startup_event():

    print("")
    print("========================================")
    print(" J.A.R.V.I.S. — KARAHAN INC.")
    print("========================================")
    print(f" Version : {APP_VERSION}")
    print(f" Model   : {GROQ_MODEL}")
    print(
        f" Groq    : {'CONNECTED' if GROQ_API_KEY else 'MISSING'}"
    )
    print(
        f" Users   : {len(USERS)}"
    )
    print("========================================")
    print("")
