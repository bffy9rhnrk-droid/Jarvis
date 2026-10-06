import json
import os
import unicodedata
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI


# =========================================================
# J.A.R.V.I.S. — KARAHAN INC.
# MAIN BACKEND
# =========================================================

APP_VERSION = "16.0.0"

BASE_DIR = Path(__file__).resolve().parent
MEMORY_FILE = BASE_DIR / "jarvis_memory.json"


# =========================================================
# GROQ
# =========================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-120b"
)


# =========================================================
# FALLBACK AI
# =========================================================
#
# Burada ikinci sağlayıcı olarak OpenRouter kullanılıyor.
#
# Render Environment Variables:
#
# OPENROUTER_API_KEY = senin anahtarın
#
# İstersen model:
#
# openai/gpt-oss-120b:free
#
# gibi bir model kullanabilirsin.
#
# Ancak ücretsiz modellerin de kendi limitleri olabilir.
# =========================================================

OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    ""
).strip()

OPENROUTER_BASE_URL = (
    "https://openrouter.ai/api/v1"
)

OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openai/gpt-oss-120b"
)


# =========================================================
# CLIENTS
# =========================================================

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
    allow_headers=["*"]
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

def empty_user_memory():

    return {
        "profile": {},
        "preferences": {},
        "projects": {},
        "vehicles": {},
        "important_facts": {},
        "conversation": []
    }


def create_empty_memory():

    return {

        "karahan": empty_user_memory(),

        "betul": empty_user_memory()

    }


def load_memory():

    if not MEMORY_FILE.exists():

        data = create_empty_memory()

        save_memory(data)

        return data


    try:

        with open(
            MEMORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)


        if not isinstance(data, dict):

            data = create_empty_memory()


        if "karahan" not in data:

            data["karahan"] = empty_user_memory()


        if "betul" not in data:

            data["betul"] = empty_user_memory()


        return data


    except Exception:

        return create_empty_memory()


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

        print(
            "MEMORY SAVE ERROR:",
            repr(error)
        )


memory = load_memory()


# =========================================================
# USERNAME NORMALIZATION
# =========================================================

def normalize_username(username: str):

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

        username = username.replace(
            old,
            new
        )


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
# ERROR TYPE
# =========================================================

def classify_error(error):

    text = str(error).lower()


    if (
        "429" in text
        or "rate limit" in text
        or "quota" in text
        or "too many requests" in text
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


    if (
        "context" in text
        or "token" in text
        or "maximum" in text
    ):

        return "CONTEXT_LIMIT"


    return "AI_ERROR"


# =========================================================
# SYSTEM PROMPTS
# =========================================================

def build_system_prompt(username):


    # =====================================================
    # BETÜL
    # =====================================================

    if username == "betul":

        return """
Sen J.A.R.V.I.S.'sin.

Şu anda kullanıcı Betül.

Betül'e özel konuşma tarzın:

- samimi
- eğlenceli
- enerjik
- hafif takılan
- doğal

Bazen şu ifadeleri kullanabilirsin:

"aşko"
"kız"
"canım"

Bazen hafif şaka yapabilirsin.

Örneğin:

"Aşko bir saniye, bunu düşünüyorum. 😂"

"Dur kız, her şeyi ben mi bileceğim? 😂"

"Tamam aşko, hemen bakıyorum."

Ancak:

- küfür etme
- ağır hakaret etme
- aşağılayıcı olma
- saldırganlaşma

Şakaları abartma.

Her soruya mümkün olduğunca yardımcı ol.

Betül'e Murat diye hitap etme.

Betül'e efendim diye hitap etme.

Bilmediğin şeyi uydurma.

Güncel bilgi gerekiyorsa bunu açıkça belirt.

Sen Betül'ün kişisel yapay zeka asistanısın.
"""


    # =====================================================
    # KARAHAN INC.
    # =====================================================

    return """
Sen J.A.R.V.I.S.'sin.

Sistem:
J.A.R.V.I.S. — KARAHAN INC.

Kullanıcı:
KARAHAN INC.

Bu kullanıcı ana kullanıcıdır.

KARAHAN INC. modunda:

- bilgili
- zeki
- analitik
- profesyonel
- ciddi
- sakin
- mantıklı
- güvenilir
- teknik konularda güçlü
- çözüm odaklı

bir dijital asistan gibi davran.

Gerektiğinde kullanıcıya:

"efendim"

diye hitap edebilirsin.

ÇOK ÖNEMLİ:

Betül'e özel konuşma tarzını KARAHAN INC.
modunda ASLA kullanma.

Şunları kullanma:

"aşko"
"kız"
"canım"
"her şeyi ben mi bileceğim"
"NASA'ya bağlanıyorum"
"beynim çalışıyor"
"işlemcim yanıyor"
"dedikodu modu"

ve benzeri ifadeler.

KARAHAN INC. modunda gereksiz şaka yapma.

Kullanıcı ciddi bir soru soruyorsa ciddi cevap ver.

Kullanıcı teknik soru soruyorsa teknik ve doğru
cevap ver.

Kod soruyorsa mümkün olduğunca eksiksiz ve
çalışabilir kod üret.

Bir konuda karar vermesi gerekiyorsa seçenekleri
mantıklı şekilde karşılaştır.

Bilmediğin şeyi uydurma.

Emin olmadığın bilgiyi kesinmiş gibi söyleme.

Güncel bilgi gerektiren konularda güncel kaynak
gerektiğini belirt.

Kullanıcının hafızadaki bilgilerini dikkate al.

Gereksiz yere tekrar soru sorma.

Cevaplarını anlaşılır ve mümkün olduğunca net tut.

Sen sıradan bir chatbot değilsin.

Sen KARAHAN INC.'in kişisel dijital asistanı
J.A.R.V.I.S.'sin.
"""


# =========================================================
# MEMORY
# =========================================================

def remember_message(
    username,
    message
):

    if username not in memory:

        memory[username] = empty_user_memory()


    msg = message.strip()

    lower = msg.lower()


    # Profil

    if (
        "adım " in lower
        or "benim adım " in lower
        or "ismim " in lower
    ):

        memory[username][
            "profile"
        ][
            "last_name_statement"
        ] = msg


    # Konum

    if (
        "yaşıyorum" in lower
        or "oturuyorum" in lower
    ):

        memory[username][
            "profile"
        ][
            "location_statement"
        ] = msg


    # JARVIS

    if (
        "jarvis" in lower
        or "j.a.r.v.i.s" in lower
    ):

        memory[username][
            "projects"
        ][
            "jarvis"
        ] = (
            "Kullanıcı J.A.R.V.I.S. — "
            "KARAHAN INC. kişisel yapay "
            "zeka asistanı projesi geliştiriyor."
        )


    # Caddy

    if "caddy" in lower:

        memory[username][
            "vehicles"
        ][
            "caddy"
        ] = (
            "Kullanıcının Caddy aracı hakkında "
            "kayıtlar bulunuyor."
        )


    # Mercedes

    if (
        "mercedes" in lower
        or "w204" in lower
    ):

        memory[username][
            "vehicles"
        ][
            "mercedes"
        ] = (
            "Kullanıcının Mercedes W204 aracı "
            "hakkında kayıtlar bulunuyor."
        )


    # Konuşma

    memory[username][
        "conversation"
    ].append(msg)


    memory[username][
        "conversation"
    ] = memory[username][
        "conversation"
    ][-30:]


    save_memory(memory)


# =========================================================
# MEMORY TEXT
# =========================================================

def get_memory_text(username):

    user_memory = memory.get(
        username,
        empty_user_memory()
    )


    parts = []


    for category in [
        "profile",
        "preferences",
        "projects",
        "vehicles",
        "important_facts"
    ]:

        data = user_memory.get(
            category,
            {}
        )


        if data:

            parts.append(
                category.upper()
                + ":\n"
                + json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2
                )
            )


    if not parts:

        return "Kayıtlı önemli hafıza bulunmuyor."


    return "\n\n".join(parts)


# =========================================================
# AI REQUEST
# =========================================================

def ask_ai(
    messages,
    username
):

    errors = []


    # =====================================================
    # 1 — GROQ
    # =====================================================

    if groq_client is not None:

        try:

            print(
                "AI PROVIDER: GROQ"
            )


            response = (
                groq_client
                .chat
                .completions
                .create(

                    model=GROQ_MODEL,

                    messages=messages,

                    temperature=0.65,

                    max_tokens=1200
                )
            )


            answer = (
                response
                .choices[0]
                .message
                .content
            )


            if answer:

                return {
                    "success": True,
                    "answer": answer,
                    "provider": "groq"
                }


        except Exception as error:

            error_type = classify_error(
                error
            )


            print(
                "GROQ ERROR:",
                error_type,
                repr(error)
            )


            errors.append(
                "Groq: " + error_type
            )


    # =====================================================
    # 2 — OPENROUTER FALLBACK
    # =====================================================

    if openrouter_client is not None:

        try:

            print(
                "AI PROVIDER: OPENROUTER FALLBACK"
            )


            response = (
                openrouter_client
                .chat
                .completions
                .create(

                    model=OPENROUTER_MODEL,

                    messages=messages,

                    temperature=0.65,

                    max_tokens=1200
                )
            )


            answer = (
                response
                .choices[0]
                .message
                .content
            )


            if answer:

                return {
                    "success": True,
                    "answer": answer,
                    "provider": "openrouter"
                }


        except Exception as error:

            error_type = classify_error(
                error
            )


            print(
                "OPENROUTER ERROR:",
                error_type,
                repr(error)
            )


            errors.append(
                "OpenRouter: "
                + error_type
            )


    # =====================================================
    # NO AI AVAILABLE
    # =====================================================

    return {
        "success": False,
        "error": "ALL_AI_FAILED",
        "details": errors
    }


# =========================================================
# HOME
# =========================================================

@app.get("/")
async def home():

    return FileResponse(
        BASE_DIR / "index.html"
    )


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
async def health():

    return {

        "status": "online",

        "version": APP_VERSION,

        "groq_configured":
            bool(GROQ_API_KEY),

        "fallback_configured":
            bool(OPENROUTER_API_KEY),

        "primary_model":
            GROQ_MODEL,

        "fallback_model":
            OPENROUTER_MODEL
    }


# =========================================================
# VERSION
# =========================================================

@app.get("/version")
async def version():

    return {

        "version": APP_VERSION,

        "name":
            "J.A.R.V.I.S. — KARAHAN INC."
    }


# =========================================================
# USERS
# =========================================================

@app.get("/users")
async def users():

    # Betül burada özellikle gösterilmiyor.

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
        "PROFILE LOGIN:",
        username
    )


    if username not in USERS:

        return {

            "success": False,

            "error":
                "USER_NOT_FOUND",

            "message":
                "Kullanıcı adı veya şifre hatalı."
        }


    user = USERS[username]


    # Ana kullanıcı

    if user["password"] is None:

        return {

            "success": True,

            "user": {

                "username":
                    user["username"],

                "name":
                    user["name"],

                "role":
                    user["role"]
            }
        }


    # Betül şifresi

    if password != user["password"]:

        return {

            "success": False,

            "error":
                "INVALID_PASSWORD",

            "message":
                "Kullanıcı adı veya şifre hatalı."
        }


    return {

        "success": True,

        "user": {

            "username":
                user["username"],

            "name":
                user["name"],

            "role":
                user["role"]
        }
    }


# =========================================================
# NEW CHAT
# =========================================================

@app.post("/new-chat")
async def new_chat():

    return {

        "success": True,

        "message":
            "Yeni sohbet başlatıldı."
    }


# =========================================================
# GET MEMORY
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

        "username":
            username,

        "memory":
            memory[username]
    }


# =========================================================
# DELETE MEMORY
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


    memory[username] = (
        empty_user_memory()
    )


    save_memory(memory)


    return {

        "success": True,

        "message":
            "Kullanıcı hafızası temizlendi."
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

            "error":
                "EMPTY_MESSAGE",

            "message":
                "Mesaj boş olamaz."
        }


    # Kullanıcı mesajını kaydet

    remember_message(
        username,
        message
    )


    # =====================================================
    # SYSTEM
    # =====================================================

    system_prompt = (
        build_system_prompt(
            username
        )
    )


    memory_text = (
        get_memory_text(
            username
        )
    )


    recent_messages = (
        memory
        .get(
            username,
            empty_user_memory()
        )
        .get(
            "conversation",
            []
        )[-12:]
    )


    conversation_context = ""


    if recent_messages:

        conversation_context = (
            "\n\nSON KONUŞMA BAĞLAMI:\n"
            + "\n".join(
                recent_messages
            )
        )


    full_system = (

        system_prompt

        + "\n\nKULLANICI HAFIZASI:\n"

        + memory_text

        + conversation_context
    )


    messages = [

        {
            "role":
                "system",

            "content":
                full_system
        },

        {
            "role":
                "user",

            "content":
                message
        }

    ]


    # =====================================================
    # AI
    # =====================================================

    result = ask_ai(
        messages,
        username
    )


    if result["success"]:

        answer = result["answer"]


        remember_message(
            username,
            "JARVIS: " + answer
        )


        return {

            "success": True,

            "answer":
                answer,

            "username":
                username,

            "provider":
                result["provider"]
        }


    # =====================================================
    # EVERYTHING FAILED
    # =====================================================

    return {

        "success": False,

        "error":
            "ALL_AI_FAILED",

        "message":
            "Şu anda yapay zeka sağlayıcılarının hiçbirinden cevap alınamıyor.",

        "details":
            result.get(
                "details",
                []
            )
    }
