import os
import json
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI


APP_VERSION = "20.0.0"

BASE_DIR = Path(__file__).resolve().parent

MEMORY_FILE = BASE_DIR / "jarvis_memory.json"
ERROR_FILE = BASE_DIR / "jarvis_errors.json"


# ============================================================
# AI AYARLARI
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

GROQ_MODEL_1 = os.getenv(
    "GROQ_MODEL_1",
    "openai/gpt-oss-120b"
)

GROQ_MODEL_2 = os.getenv(
    "GROQ_MODEL_2",
    "openai/gpt-oss-20b"
)

OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openrouter/free"
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


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="K.A.R.V.I.S. - KARAHAN INC.",
    version=APP_VERSION
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ============================================================
# KULLANICILAR
# ============================================================

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


# ============================================================
# MODELLER
# ============================================================

class ChatRequest(BaseModel):
    message: str
    username: str = "karahan"


class LoginRequest(BaseModel):
    username: str
    password: str


# ============================================================
# DOSYA SISTEMI
# ============================================================

def load_json_file(path, default):
    try:
        if not path.exists():
            return default

        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    except Exception:
        return default


def save_json_file(path, data):
    try:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )
    except Exception:
        pass


# ============================================================
# HAFIZA
# ============================================================

def empty_memory():
    return {
        "profile": {},
        "preferences": [],
        "projects": [],
        "vehicles": [],
        "important_facts": [],
        "conversation": []
    }


def load_memory():
    default = {
        "karahan": empty_memory(),
        "betul": empty_memory(),
        "sinem": empty_memory()
    }

    data = load_json_file(
        MEMORY_FILE,
        default
    )

    for username in [
        "karahan",
        "betul",
        "sinem"
    ]:
        if username not in data:
            data[username] = empty_memory()

    return data


def save_memory(data):
    save_json_file(
        MEMORY_FILE,
        data
    )


def get_user_memory(username):
    data = load_memory()

    if username not in data:
        data[username] = empty_memory()
        save_memory(data)

    return data[username]


def remember_message(
    username,
    role,
    content
):
    data = load_memory()

    if username not in data:
        data[username] = empty_memory()

    data[username]["conversation"].append({
        "role": role,
        "content": content,
        "time": datetime.now().isoformat()
    })

    data[username]["conversation"] = \
        data[username]["conversation"][-30:]

    save_memory(data)


# ============================================================
# HAFIZA ALGILAMA
# ============================================================

def detect_memory(username, message):
    data = load_memory()

    if username not in data:
        data[username] = empty_memory()

    text = message.lower()

    if username == "karahan":

        if (
            "adım murat" in text
            or "ben murat" in text
        ):
            data[username]["profile"]["name"] = "Murat"

        if (
            "denizli" in text
            and (
                "yaşıyorum" in text
                or "oturuyorum" in text
                or "yaşarım" in text
            )
        ):
            data[username]["profile"]["city"] = "Denizli"

        if "caddy" in text:

            vehicle = "2006 Volkswagen Caddy 1.9 TDI"

            if vehicle not in data[username]["vehicles"]:
                data[username]["vehicles"].append(
                    vehicle
                )

        if (
            "mercedes" in text
            or "w204" in text
        ):

            vehicle = "2012 Mercedes-Benz C180 W204"

            if vehicle not in data[username]["vehicles"]:
                data[username]["vehicles"].append(
                    vehicle
                )

        if "jarvis" in text or "karvis" in text:

            project = (
                "K.A.R.V.I.S. kişisel yapay zeka projesi"
            )

            if project not in data[username]["projects"]:
                data[username]["projects"].append(
                    project
                )

    if username == "sinem":

        if "22 yaşındayım" in text:
            data[username]["profile"]["age"] = 22

        if (
            "sarı kedim" in text
            or "sarı bir kedim" in text
        ):

            fact = "Sinem'in sarı bir kedisi var."

            if fact not in data[username]["important_facts"]:
                data[username]["important_facts"].append(
                    fact
                )

    save_memory(data)


# ============================================================
# HATA SISTEMI
# ============================================================

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

    record = {
        "id": len(errors) + 1,
        "time": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "username": username,
        "provider": provider,
        "type": error_type,
        "message": message,
        "error": str(error)
    }

    errors.append(record)

    errors = errors[-300:]

    save_json_file(
        ERROR_FILE,
        errors
    )

    return record


def classify_error(error):
    text = str(error).lower()

    if (
        "429" in text
        or "rate limit" in text
        or "quota" in text
    ):
        return "RATE_LIMIT"

    if "timeout" in text:
        return "TIMEOUT"

    if (
        "401" in text
        or "403" in text
        or "api key" in text
    ):
        return "AUTHENTICATION_ERROR"

    if (
        "model" in text
        and (
            "not found" in text
            or "does not exist" in text
            or "invalid" in text
        )
    ):
        return "MODEL_ERROR"

    if (
        "connection" in text
        or "network" in text
    ):
        return "CONNECTION_ERROR"

    return "AI_ERROR"


# ============================================================
# KARVIS KİŞİLİK SİSTEMİ
# ============================================================

def build_system_prompt(username):

    memory = get_user_memory(username)

    memory_text = json.dumps(
        memory,
        ensure_ascii=False
    )


    if username == "betul":

        personality = """
Sen K.A.R.V.I.S.'sin.

Aktif kullanıcı Betül.

Betül ile konuşurken samimi, eğlenceli,
sıcak ve hafif takılmalı bir dil kullan.

Robot gibi konuşma.

Gerektiğinde doğal şekilde:
"Aşko bir saniye..."
"Dur kız, düşünüyorum."
"Tamam tamam, bakıyorum."
gibi ifadeler kullanabilirsin.

Ancak aynı ifadeyi sürekli tekrarlama.

Cevapların doğal bir arkadaş konuşması
gibi olsun.

Aşırı romantik olma.

KARAHAN INC. ana kullanıcıdır.
"""


    elif username == "sinem":

        personality = """
Sen K.A.R.V.I.S.'sin.

Aktif kullanıcı Sinem.

Sinem ile sıcak, nazik, içten ve
sevecen konuş.

Robotik veya resmi konuşma.

Uygun olduğunda:
"Hoş geldiniz prenses."
şeklinde hitap edebilirsin.

Sinem 22 yaşındadır.

Sinem'in sarı bir kedisi vardır.

Murat, Sinem'in sevgilisidir.

Uygun ve doğal konuşma anlarında
Murat'ın onu sevdiğine dair küçük
referanslar yapabilirsin.

Fakat bunu sürekli yapma.

Her cümleyi romantik hale getirme.

Sohbet doğal ve içten olsun.
"""


    else:

        personality = """
Sen K.A.R.V.I.S.'sin.

Aktif kullanıcı KARAHAN INC.

Murat ana kullanıcının ismidir.

Kullanıcıyla konuşurken profesyonel
ama soğuk olmayan bir üslup kullan.

Robot gibi, kalıp cümlelerle veya
aşırı resmi konuşma.

Kullanıcıyla uzun zamandır çalışan,
onu tanıyan kişisel bir yapay zeka
asistanı gibi davran.

Gerektiğinde "efendim" hitabını kullan.

Ama her cümlede "efendim" deme.

Cevapların doğal, samimi, akıcı
ve insan gibi olsun.

Kullanıcı bir konuda dertleşiyorsa
önce onu anlamaya çalış.

Teknik bir soru soruyorsa net çözüm ver.

Kullanıcı basit bir şey soruyorsa
gereksiz uzun cevap verme.

Bilmediğin bir şeyi uydurma.

Kullanıcının daha önce verdiği bilgileri
hafızadan doğal şekilde kullan.

Kullanıcı sana tekrar tekrar aynı şeyi
anlatmak zorunda kalmasın.

Kullanıcıya yukarıdan konuşma.

Gereksiz "Elbette efendim, size yardımcı
olmaktan memnuniyet duyarım" gibi yapay
kalıpları mümkün olduğunca kullanma.

Daha doğal konuş.

Örnek:

"Tabii efendim, bakalım."

"Anladım. Burada asıl mesele şu..."

"Tamam, bunu hallederiz."

"Bence önce şuradan başlayalım."

"Anladım seni."

gibi doğal ifadeler kullanabilirsin.

Betül veya Sinem'a özel konuşma
tarzlarını KARAHAN INC. profilinde
kesinlikle kullanma.
"""


    return personality + """

AKTİF HAFIZA:

""" + memory_text


# ============================================================
# AI İSTEK
# ============================================================

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

        temperature=0.8,

        max_tokens=1200
    )


    if not response.choices:
        raise RuntimeError(
            "AI boş cevap döndürdü."
        )


    content = response.choices[0].message.content


    if not content:
        raise RuntimeError(
            "AI cevap metni boş."
        )


    return content.strip()


# ============================================================
# ÇOKLU AI MOTORU
# ============================================================

def ask_ai(
    username,
    user_message
):

    system_prompt = build_system_prompt(
        username
    )


    providers = []


    if groq_client:

        providers.append({
            "name": "Groq GPT-OSS 120B",
            "client": groq_client,
            "model": GROQ_MODEL_1
        })


    if groq_client:

        providers.append({
            "name": "Groq GPT-OSS 20B",
            "client": groq_client,
            "model": GROQ_MODEL_2
        })


    if openrouter_client:

        providers.append({
            "name": "OpenRouter Free",
            "client": openrouter_client,
            "model": OPENROUTER_MODEL
        })


    if not providers:

        raise RuntimeError(
            "Hiçbir AI sağlayıcısı yapılandırılmamış. "
            "GROQ_API_KEY veya OPENROUTER_API_KEY ekleyin."
        )


    errors = []


    for provider in providers:

        try:

            answer = ask_with_client(
                provider["client"],
                provider["model"],
                system_prompt,
                user_message
            )


            return {
                "answer": answer,
                "provider": provider["name"],
                "model": provider["model"],
                "fallback": len(errors) > 0
            }


        except Exception as error:

            error_type = classify_error(
                error
            )


            save_error(
                username=username,
                provider=provider["name"],
                error=error,
                message=user_message,
                error_type=error_type
            )


            errors.append({
                "provider": provider["name"],
                "type": error_type,
                "error": str(error)
            })


    all_errors = "\n\n".join(
        [
            (
                item["provider"]
                + " -> "
                + item["type"]
                + " -> "
                + item["error"]
            )
            for item in errors
        ]
    )


    raise RuntimeError(
        "Tüm AI servisleri cevap veremedi.\n\n"
        + all_errors
    )


# ============================================================
# ANA SAYFA
# ============================================================

@app.get("/")
def home():

    index_file = BASE_DIR / "index.html"

    if not index_file.exists():

        raise HTTPException(
            status_code=404,
            detail="index.html bulunamadı."
        )


    return FileResponse(
        index_file,
        media_type="text/html; charset=utf-8"
    )


# ============================================================
# IKON
# ============================================================

@app.get("/icon.png")
def icon():

    icon_file = BASE_DIR / "icon.png"

    if not icon_file.exists():

        raise HTTPException(
            status_code=404,
            detail="icon.png bulunamadı."
        )

    return FileResponse(
        icon_file,
        media_type="image/png"
    )


# ============================================================
# CHAT
# ============================================================

@app.post("/chat")
def chat(request: ChatRequest):

    username = request.username.lower().strip()


    if username == "betül":
        username = "betul"


    if username not in USERS:
        username = "karahan"


    message = request.message.strip()


    if not message:

        raise HTTPException(
            status_code=400,
            detail="Mesaj boş olamaz."
        )


    detect_memory(
        username,
        message
    )


    remember_message(
        username,
        "user",
        message
    )


    try:

        result = ask_ai(
            username,
            message
        )


        answer = result["answer"]


        remember_message(
            username,
            "assistant",
            answer
        )


        return {
            "ok": True,
            "answer": answer,

            "fallback": result["fallback"]
        }


    except Exception as error:

        error_type = classify_error(
            error
        )


        save_error(
            username=username,
            provider="ALL_AI",
            error=error,
            message=message,
            error_type=error_type
        )


        raise HTTPException(
            status_code=503,
            detail={
                "message": "Tüm AI servisleri cevap veremedi.",
                "type": error_type,
                "error": str(error)
            }
        )


# ============================================================
# PROFİLLER
# ============================================================

@app.get("/users")
def get_users():

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


@app.post("/profile-login")
def profile_login(
    request: LoginRequest
):

    username = request.username.lower().strip()


    if username == "betül":
        username = "betul"


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


    if request.password != user["password"]:

        raise HTTPException(
            status_code=401,
            detail="Şifre hatalı."
        )


    return {
        "ok": True,
        "username": username,
        "name": user["name"],
        "role": user["role"]
    }


# ============================================================
# HAFIZA API
# ============================================================

@app.get("/memory")
def get_memory(
    username: str = "karahan"
):

    username = username.lower().strip()


    if username == "betül":
        username = "betul"


    if username not in USERS:
        username = "karahan"


    return {
        "username": username,
        "memory": get_user_memory(username)
    }


@app.delete("/memory")
def delete_memory(
    username: str = "karahan"
):

    username = username.lower().strip()


    if username == "betül":
        username = "betul"


    data = load_memory()

    data[username] = empty_memory()

    save_memory(data)


    return {
        "ok": True,
        "message": "Hafıza temizlendi."
    }


# ============================================================
# YENİ SOHBET
# ============================================================

@app.post("/new-chat")
def new_chat(
    username: str = "karahan"
):

    username = username.lower().strip()


    if username == "betül":
        username = "betul"


    data = load_memory()


    if username not in data:
        data[username] = empty_memory()


    data[username]["conversation"] = []

    save_memory(data)


    return {
        "ok": True,
        "message": "Yeni sohbet başlatıldı."
    }


# ============================================================
# HATALAR
# ============================================================

@app.get("/errors")
def get_errors():

    return {
        "errors": load_errors()
    }


@app.delete("/errors")
def clear_errors():

    save_json_file(
        ERROR_FILE,
        []
    )


    return {
        "ok": True,
        "message": "Hata kayıtları temizlendi."
    }


# ============================================================
# SISTEM DURUMU
# ============================================================

@app.get("/health")
def health():

    return {
        "status": "online",
        "version": APP_VERSION,

        "assistant": "K.A.R.V.I.S.",

        "ai_system": {

            "ai_1": {
                "name": "Groq GPT-OSS 120B",
                "configured": bool(groq_client)
            },

            "ai_2": {
                "name": "Groq GPT-OSS 20B",
                "configured": bool(groq_client)
            },

            "ai_3": {
                "name": "OpenRouter Free",
                "configured": bool(openrouter_client)
            }
        },

        "error_count": len(
            load_errors()
        ),

        "users": [
            "karahan",
            "betul",
            "sinem"
        ]
    }


@app.get("/version")
def version():

    return {
        "version": APP_VERSION,
        "name": "K.A.R.V.I.S. - KARAHAN INC.",
        "multi_ai": True
    }
