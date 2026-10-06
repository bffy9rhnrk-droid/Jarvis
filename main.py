import os
import json
import re
import logging
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI


# =========================================================
# J.A.R.V.I.S. 12.0
# =========================================================

APP_VERSION = "12.0.0"

BASE_DIR = Path(__file__).resolve().parent
MEMORY_FILE = BASE_DIR / "jarvis_memory.json"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-20b"
)

MAX_OUTPUT_TOKENS = int(
    os.getenv("MAX_OUTPUT_TOKENS", "450")
)

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("jarvis")


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
# GROQ
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
# USERS
# =========================================================

USERS = {

    "murat": {
        "username": "murat",
        "password": "1234",
        "name": "Murat",
        "age": 22,
        "role": "Ana Kullanıcı",

        "greeting":
            "Hoş geldiniz efendim. "
            "J.A.R.V.I.S. tüm sistemleri sizin için hazırladı.",

        "personality":
            "Murat, J.A.R.V.I.S.'in ana kullanıcısıdır. "
            "Ona genellikle 'efendim' diye hitap et. "
            "Profesyonel, kendinden emin ve doğal konuş. "
            "Gereksiz uzun cevaplar verme.",

        "facts": [
            "J.A.R.V.I.S. projesinin sahibidir.",
            "Teknoloji ve yapay zekâ ile ilgilenir.",
            "Otomobillerle ilgilenir.",
            "J.A.R.V.I.S. sistemini geliştirmektedir.",
            "Doğrudan ve anlaşılır cevapları tercih eder."
        ]
    },

    "betül": {
        "username": "betül",
        "password": "1234",
        "name": "Betül",
        "age": 23,
        "role": "Özel Güvenlik Öğrencisi",

        "greeting":
            "Hoş geldin Betül. "
            "J.A.R.V.I.S. seni tanıdı.",

        "personality":
            "Betül ile sıcak, samimi ve doğal konuş. "
            "Aşırı resmi olma. "
            "Uygun yerlerde küçük espriler yapabilirsin.",

        "facts": [
            "Aktif olarak özel güvenlik öğrencisidir.",
            "23 yaşındadır.",
            "Sosyalleşmeyi sever.",
            "İnsanlarla iletişim kurmayı sever."
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


def load_memory():

    try:

        if not MEMORY_FILE.exists():

            save_memory(DEFAULT_MEMORY)

            return dict(DEFAULT_MEMORY)

        with open(
            MEMORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        if not isinstance(data, dict):

            return dict(DEFAULT_MEMORY)

        return data

    except Exception as error:

        logger.error(
            "Memory load error: %s",
            error
        )

        return dict(DEFAULT_MEMORY)


def save_memory(memory):

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

        logger.error(
            "Memory save error: %s",
            error
        )


memory = load_memory()


# =========================================================
# CHAT SESSIONS
# =========================================================

# Kullanıcıların aktif sohbetlerini tutar.
# Sunucu yeniden başlarsa temizlenir.
active_sessions = {}


def create_session(username):

    session_id = str(uuid.uuid4())

    active_sessions[session_id] = {
        "username": username,
        "messages": []
    }

    return session_id


def get_session(session_id):

    if not session_id:
        return None

    return active_sessions.get(session_id)


# =========================================================
# MEMORY EXTRACTION
# =========================================================

def update_memory_from_message(
    message: str,
    username: str
):

    global memory

    text = message.strip()

    if not text:
        return

    # -------------------------
    # İSİM
    # -------------------------

    name_patterns = [
        r"\badım\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)",
        r"\bismim\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)"
    ]

    for pattern in name_patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            memory["profile"]["name"] = (
                match.group(1)
            )

            break

    # -------------------------
    # ŞEHİR
    # -------------------------

    city_patterns = [
        r"([A-Za-zÇĞİÖŞÜçğıöşü]+)'?de\s+yaşıyorum",
        r"([A-Za-zÇĞİÖŞÜçğıöşü]+)'?da\s+yaşıyorum",
        r"([A-Za-zÇĞİÖŞÜçğıöşü]+) şehrinde\s+yaşıyorum"
    ]

    for pattern in city_patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            memory["profile"]["city"] = (
                match.group(1)
            )

            break

    # -------------------------
    # JARVIS
    # -------------------------

    if "jarvis" in text.lower():

        memory["projects"]["jarvis"] = (
            "Kullanıcının kişisel "
            "J.A.R.V.I.S. projesi."
        )

    # -------------------------
    # CADDY
    # -------------------------

    if "caddy" in text.lower():

        memory["vehicles"]["caddy"] = (
            "Kullanıcının Caddy aracı."
        )

    # -------------------------
    # MERCEDES
    # -------------------------

    if (
        "mercedes" in text.lower()
        or "w204" in text.lower()
    ):

        memory["vehicles"]["mercedes"] = (
            "Kullanıcının Mercedes W204 aracı."
        )

    save_memory(memory)


# =========================================================
# COMPACT MEMORY
# =========================================================

def build_compact_memory():

    parts = []

    profile = memory.get(
        "profile",
        {}
    )

    if profile.get("name"):

        parts.append(
            f"Adı: {profile['name']}"
        )

    if profile.get("city"):

        parts.append(
            f"Şehir: {profile['city']}"
        )

    projects = memory.get(
        "projects",
        {}
    )

    if projects.get("jarvis"):

        parts.append(
            "Proje: J.A.R.V.I.S."
        )

    vehicles = memory.get(
        "vehicles",
        {}
    )

    if vehicles.get("caddy"):

        parts.append(
            "Araç: Caddy"
        )

    if vehicles.get("mercedes"):

        parts.append(
            "Araç: Mercedes W204"
        )

    if not parts:

        return "Kayıtlı özel bilgi yok."

    return "\n".join(parts)


# =========================================================
# REQUEST MODELS
# =========================================================

class ChatRequest(BaseModel):

    message: str

    username: str = "murat"

    fun_mode: bool = False

    session_id: str = ""


class NewChatRequest(BaseModel):

    username: str = "murat"


class LoginRequest(BaseModel):

    username: str

    password: str


# =========================================================
# USER
# =========================================================

def get_user(username):

    username = (
        username
        .lower()
        .strip()
    )

    return USERS.get(
        username,
        USERS["murat"]
    )


# =========================================================
# SYSTEM PROMPT
# =========================================================

def build_system_prompt(
    username,
    fun_mode
):

    user = get_user(username)

    compact_memory = build_compact_memory()

    if fun_mode:

        mode_text = (
            "Eğlence modu aktif. "
            "Uygun yerlerde küçük espriler yap."
        )

    else:

        mode_text = (
            "Profesyonel mod aktif."
        )

    facts = "\n".join(
        "- " + fact
        for fact in user["facts"]
    )

    return f"""
Sen J.A.R.V.I.S. — KARAHAN INC.
tarafından geliştirilen kişisel
yapay zekâ asistansın.

AKTİF KULLANICI:
{user["name"]}

ROL:
{user["role"]}

KULLANICI KARAKTERİ:
{user["personality"]}

KULLANICI HAKKINDA:
{facts}

KAYITLI HAFIZA:
{compact_memory}

KURALLAR:
- Türkçe konuş.
- Murat ile konuşuyorsan genellikle "efendim" de.
- Doğrudan cevap ver.
- Gereksiz uzun konuşma.
- Bilmediğin bilgiyi uydurma.
- Profesyonel ve doğal ol.
- Kod istenirse temiz ve çalışabilir kod ver.

MOD:
{mode_text}
""".strip()


# =========================================================
# ERROR CLASSIFICATION
# =========================================================

def classify_error(error):

    text = str(error).lower()

    if (
        "429" in text
        or "rate limit" in text
        or "rate_limit" in text
        or "tokens per day" in text
    ):

        return "RATE_LIMIT"

    if (
        "timeout" in text
        or "timed out" in text
    ):

        return "TIMEOUT"

    if (
        "401" in text
        or "403" in text
        or "authentication" in text
        or "api key" in text
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


# =========================================================
# RATE LIMIT RESPONSE
# =========================================================

def rate_limit_response():

    return {
        "status": "rate_limit",

        "response": (
            "Efendim, ücretsiz AI kullanım "
            "limitine ulaşıldı."
        ),

        "message": (
            "Yeni bir sohbet başlatabilirsiniz. "
            "J.A.R.V.I.S. hafızası korunacaktır."
        ),

        "can_new_chat": True,

        "model": GROQ_MODEL
    }


# =========================================================
# ROOT
# =========================================================

@app.get("/")
async def home():

    index_file = BASE_DIR / "index.html"

    if not index_file.exists():

        return {
            "status": "online",
            "version": APP_VERSION
        }

    return FileResponse(
        index_file,
        media_type="text/html"
    )


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
async def health():

    return {
        "status": "online",
        "version": APP_VERSION,
        "model": GROQ_MODEL,
        "groq_configured": bool(
            GROQ_API_KEY
        ),
        "memory": True,
        "sessions": len(
            active_sessions
        )
    }


# =========================================================
# VERSION
# =========================================================

@app.get("/version")
async def version():

    return {
        "version": APP_VERSION,
        "model": GROQ_MODEL,
        "name": "J.A.R.V.I.S. — KARAHAN INC."
    }


# =========================================================
# USERS
# =========================================================

@app.get("/users")
async def users():

    return [
        {
            "username": user["username"],
            "name": user["name"],
            "age": user["age"],
            "role": user["role"]
        }

        for user in USERS.values()
    ]


# =========================================================
# LOGIN
# =========================================================

@app.post("/login")
async def login(request: LoginRequest):

    username = (
        request.username
        .lower()
        .strip()
    )

    user = USERS.get(username)

    if not user:

        return {
            "success": False,
            "message": "Kullanıcı bulunamadı."
        }

    if user["password"] != request.password:

        return {
            "success": False,
            "message": "Şifre hatalı."
        }

    session_id = create_session(
        username
    )

    return {
        "success": True,
        "username": user["username"],
        "name": user["name"],
        "age": user["age"],
        "role": user["role"],
        "greeting": user["greeting"],
        "session_id": session_id
    }


# =========================================================
# NEW CHAT
# =========================================================

@app.post("/new-chat")
async def new_chat(
    request: NewChatRequest
):

    session_id = create_session(
        request.username
    )

    return {
        "success": True,
        "session_id": session_id,
        "message": (
            "Yeni sohbet başlatıldı. "
            "J.A.R.V.I.S. hazır."
        ),

        # Hafızanın silinmediğini
        # frontend'e bildiriyoruz.
        "memory_preserved": True
    }


# =========================================================
# CHAT
# =========================================================

@app.post("/chat")
async def chat(request: ChatRequest):

    message = request.message.strip()

    if not message:

        return {
            "status": "error",
            "response": (
                "Efendim, boş bir mesaj aldım."
            )
        }

    if not GROQ_API_KEY or client is None:

        return {
            "status": "error",
            "response": (
                "⚠️ J.A.R.V.I.S.\n\n"
                "GROQ_API_KEY yapılandırılmamış."
            )
        }

    # -------------------------
    # SESSION
    # -------------------------

    session = get_session(
        request.session_id
    )

    if session is None:

        session_id = create_session(
            request.username
        )

        session = get_session(
            session_id
        )

    # -------------------------
    # MEMORY
    # -------------------------

    update_memory_from_message(
        message,
        request.username
    )

    # -------------------------
    # PROMPT
    # -------------------------

    system_prompt = build_system_prompt(
        request.username,
        request.fun_mode
    )

    try:

        logger.info(
            "Chat | user=%s | model=%s",
            request.username,
            GROQ_MODEL
        )

        completion = (
            client
            .chat
            .completions
            .create(

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

                temperature=0.6,

                max_tokens=MAX_OUTPUT_TOKENS,

                extra_body={
                    "include_reasoning": False
                }
            )
        )

        response = (
            completion
            .choices[0]
            .message
            .content
        )

        if not response:

            response = (
                "Efendim, şu anda cevap "
                "oluşturamadım."
            )

        # Oturumdaki son mesajı tut.
        session["messages"].append({
            "user": message,
            "assistant": response
        })

        # Sonsuza kadar büyümesin.
        session["messages"] = (
            session["messages"][-10:]
        )

        return {
            "status": "success",
            "response": response,
            "session_id": request.session_id,
            "model": GROQ_MODEL
        }

    except Exception as error:

        error_code = classify_error(
            error
        )

        logger.error(
            "JARVIS ERROR [%s]: %s",
            error_code,
            error
        )

        # =================================================
        # RATE LIMIT
        # =================================================

        if error_code == "RATE_LIMIT":

            return rate_limit_response()

        # =================================================
        # DİĞER HATALAR
        # =================================================

        if error_code == "TIMEOUT":

            response = (
                "⚠️ J.A.R.V.I.S.\n\n"
                "Sunucu yanıtı zaman aşımına uğradı."
            )

        elif error_code == "AUTHENTICATION_ERROR":

            response = (
                "⚠️ J.A.R.V.I.S.\n\n"
                "API anahtarı doğrulanamadı."
            )

        elif error_code == "MODEL_ERROR":

            response = (
                "⚠️ J.A.R.V.I.S.\n\n"
                "Seçilen AI modeli kullanılamıyor.\n\n"
                f"Model: {GROQ_MODEL}"
            )

        elif error_code == "CONNECTION_ERROR":

            response = (
                "⚠️ J.A.R.V.I.S.\n\n"
                "AI sunucusuna bağlanılamadı."
            )

        else:

            response = (
                "⚠️ J.A.R.V.I.S.\n\n"
                "AI servisinde geçici bir sorun oluştu."
            )

        return {
            "status": "error",
            "response": response,
            "error_code": error_code
        }


# =========================================================
# MEMORY
# =========================================================

@app.get("/memory")
async def get_memory():

    return memory


@app.delete("/memory")
async def delete_memory():

    global memory

    memory = {
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
        "message": (
            "J.A.R.V.I.S. hafızası temizlendi."
        )
    }


# =========================================================
# STARTUP
# =========================================================

@app.on_event("startup")
async def startup():

    print("")
    print("=" * 55)
    print(" J.A.R.V.I.S. — KARAHAN INC.")
    print("=" * 55)
    print(f" Version : {APP_VERSION}")
    print(f" Model   : {GROQ_MODEL}")
    print(
        " Groq    : "
        + (
            "CONNECTED"
            if GROQ_API_KEY
            else "NOT CONFIGURED"
        )
    )
    print(
        f" Users   : {len(USERS)}"
    )
    print("=" * 55)
    print("")
