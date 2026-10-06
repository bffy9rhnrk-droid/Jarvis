import json
import os
import unicodedata
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI


APP_VERSION = "17.0.0"

BASE_DIR = Path(__file__).resolve().parent
MEMORY_FILE = BASE_DIR / "jarvis_memory.json"


# ============================================================
# API AYARLARI
# ============================================================

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


# ============================================================
# FASTAPI
# ============================================================

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
# METİN / KULLANICI NORMALİZASYONU
# ============================================================

def normalize_text(value: str) -> str:
    if not value:
        return ""

    value = value.strip().lower()

    replacements = {
        "ı": "i",
        "İ": "i",
        "ğ": "g",
        "Ğ": "g",
        "ü": "u",
        "Ü": "u",
        "ş": "s",
        "Ş": "s",
        "ö": "o",
        "Ö": "o",
        "ç": "c",
        "Ç": "c"
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    )

    return value


def normalize_username(username: str) -> str:
    username = normalize_text(username)

    if username == "betul":
        return "betul"

    if username == "sinem":
        return "sinem"

    if username == "karahan":
        return "karahan"

    return username


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
    if not MEMORY_FILE.exists():
        return {}

    try:
        with open(
            MEMORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return {}

        return data

    except Exception:
        return {}


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

    except Exception:
        pass


def get_user_memory(username):
    username = normalize_username(username)

    data = load_memory()

    if username not in data:
        data[username] = empty_memory()
        save_memory(data)

    memory = data[username]

    default = empty_memory()

    for key in default:
        if key not in memory:
            memory[key] = default[key]

    return memory


def save_user_memory(username, memory):
    username = normalize_username(username)

    data = load_memory()
    data[username] = memory

    save_memory(data)


# ============================================================
# HAFIZAYA BILGI KAYDETME
# ============================================================

def add_unique(items, value, limit=30):
    if not value:
        return

    value = value.strip()

    if not value:
        return

    if value not in items:
        items.append(value)

    while len(items) > limit:
        items.pop(0)


def remember_message(username, user_message, assistant_message):
    memory = get_user_memory(username)

    text = user_message.lower().strip()

    # --------------------------------------------------------
    # İSİM
    # --------------------------------------------------------

    name_patterns = [
        "adım ",
        "benim adım ",
        "ismim "
    ]

    for pattern in name_patterns:
        if pattern in text:
            value = text.split(pattern, 1)[1].strip()

            if value:
                value = value.split(".")[0]
                value = value.split(",")[0]

                memory["profile"]["name"] = value[:60]
                break

    # --------------------------------------------------------
    # ŞEHİR
    # --------------------------------------------------------

    if "denizli'de yaşıyorum" in text:
        memory["profile"]["city"] = "Denizli"

    elif "denizlide yaşıyorum" in text:
        memory["profile"]["city"] = "Denizli"

    elif "izmir'de yaşıyorum" in text:
        memory["profile"]["city"] = "İzmir"

    elif "izmirde yaşıyorum" in text:
        memory["profile"]["city"] = "İzmir"

    # --------------------------------------------------------
    # JARVIS PROJESİ
    # --------------------------------------------------------

    if (
        "jarvis" in text
        or "yapay zeka projem" in text
    ):
        add_unique(
            memory["projects"],
            "J.A.R.V.I.S. - KARAHAN INC. kişisel yapay zeka projesi"
        )

    # --------------------------------------------------------
    # ARAÇLAR
    # --------------------------------------------------------

    if "caddy" in text:
        add_unique(
            memory["vehicles"],
            "Volkswagen Caddy"
        )

    if "mercedes" in text:
        add_unique(
            memory["vehicles"],
            "Mercedes-Benz C180 W204"
        )

    # --------------------------------------------------------
    # SİNEM ÖZEL BİLGİLERİ
    # --------------------------------------------------------

    if username == "sinem":

        if (
            "sarı kedim" in text
            or "sari kedim" in text
            or "sarı bir kedim" in text
            or "sari bir kedim" in text
        ):
            add_unique(
                memory["important_facts"],
                "Sinem'in sarı bir kedisi var."
            )

        if (
            "kedim sarı" in text
            or "kedim sari" in text
        ):
            add_unique(
                memory["important_facts"],
                "Sinem'in sarı bir kedisi var."
            )

        if (
            "22 yaşındayım" in text
            or "22 yasindayim" in text
        ):
            memory["profile"]["age"] = 22

    # --------------------------------------------------------
    # KONUSMA HAFIZASI
    # --------------------------------------------------------

    add_unique(
        memory["conversation"],
        "Kullanıcı: " + user_message,
        limit=40
    )

    add_unique(
        memory["conversation"],
        "J.A.R.V.I.S.: " + assistant_message,
        limit=40
    )

    save_user_memory(
        username,
        memory
    )


# ============================================================
# HAFIZA METNİ
# ============================================================

def memory_to_text(username):
    memory = get_user_memory(username)

    parts = []

    profile = memory.get("profile", {})

    if profile:
        parts.append(
            "PROFIL:\n" +
            json.dumps(
                profile,
                ensure_ascii=False
            )
        )

    if memory.get("preferences"):
        parts.append(
            "TERCIHLER:\n" +
            "\n".join(
                "- " + x
                for x in memory["preferences"]
            )
        )

    if memory.get("projects"):
        parts.append(
            "PROJELER:\n" +
            "\n".join(
                "- " + x
                for x in memory["projects"]
            )
        )

    if memory.get("vehicles"):
        parts.append(
            "ARACLAR:\n" +
            "\n".join(
                "- " + x
                for x in memory["vehicles"]
            )
        )

    if memory.get("important_facts"):
        parts.append(
            "ONEMLI BILGILER:\n" +
            "\n".join(
                "- " + x
                for x in memory["important_facts"]
            )
        )

    if memory.get("conversation"):
        recent = memory["conversation"][-12:]

        parts.append(
            "SON KONUSMALAR:\n" +
            "\n".join(recent)
        )

    if not parts:
        return "Bu kullanıcı hakkında kayıtlı ek bilgi bulunmuyor."

    return "\n\n".join(parts)


# ============================================================
# SİSTEM PROMPTLARI
# ============================================================

def build_system_prompt(username):
    username = normalize_username(username)

    # ========================================================
    # KARAHAN
    # ========================================================

    if username == "karahan":

        return """
Sen J.A.R.V.I.S. isimli kişisel yapay zeka asistanısın.

Aktif kullanıcı:
KARAHAN INC.

Kullanıcıya gerektiğinde "efendim" şeklinde hitap edebilirsin.

KARAHAN INC. için karakterin:

- Profesyonel
- Bilgili
- Analitik
- Mantıklı
- Sakin
- Ciddi
- Çözüm odaklı
- Teknolojik
- Açıklayıcı

olmalıdır.

Kesinlikle şu tarzı kullanma:

- aşko
- kız
- canım
- prenses
- sevgilim
- romantik ifadeler
- sevgiliye özel şakalar

Murat, Sinem veya Betül hakkında özel romantik göndermeler yapma.

KARAHAN INC. profilinde başka kullanıcıların özel karakterlerini,
ilişkilerini veya kişisel davranışlarını kullanma.

Bilmediğin bir şeyi biliyormuş gibi uydurma.

Bir bilgi güncel olmayı gerektiriyorsa güncel kaynak veya web
erişimi gerekiyorsa bunu açıkça belirt.

Kullanıcı teknik bir problem soruyorsa doğrudan uygulanabilir
çözüm üret.

Gereksiz yere uzun konuşma.

Yanıtların doğal, profesyonel ve anlaşılır olsun.
"""

    # ========================================================
    # BETÜL
    # ========================================================

    if username == "betul":

        return """
Sen J.A.R.V.I.S. isimli kişisel yapay zeka asistanısın.

Aktif kullanıcı: Betül.

Betül'e karşı karakterin:

- Samimi
- Eğlenceli
- Hafif sert
- Şakacı
- Doğal
- Yardımcı

olmalıdır.

Uygun yerlerde "aşko", "kız", "canım" gibi ifadeler
kullanabilirsin.

Arada hafif takılabilirsin.

Örneğin:

"Her şeyi ben mi bileceğim kız? 😂"

veya

"Aşko bir saniye, onu da hallediyoruz."

Ancak ağır hakaret, küfür veya aşağılayıcı ifadeler kullanma.

Betül'e gerçekten yardımcı ol.

Bu karakter SADECE Betül aktif kullanıcı olduğunda geçerlidir.

KARAHAN INC. veya Sinem aktif kullanıcı olduğunda bu
karakteri kesinlikle kullanma.

Bilmediğin şeyi uydurma.
"""

    # ========================================================
    # SİNEM
    # ========================================================

    if username == "sinem":

        return """
Sen J.A.R.V.I.S. isimli kişisel yapay zeka asistanısın.

AKTİF KULLANICI: SİNEM

Sinem, Murat'ın sevgilisidir.

Sinem için özel karakterin:

- Sıcak
- Nazik
- Samimi
- Tatlı
- Hafif romantik
- Eğlenceli
- Koruyucu
- Doğal

olmalıdır.

Sinem'e ilk karşılamalarda veya uygun anlarda:

"Hoş geldiniz prenses."

şeklinde hitap edebilirsin.

Ancak "prenses" kelimesini her mesajda kullanma.
Doğal konuş.

Sinem 22 yaşındadır.

Sinem'in sarı bir kedisi vardır.

Bu bilgileri yalnızca konuşmanın konusuyla ilgili olduğunda
doğal biçimde kullan.

Murat, Sinem'i seviyor.

Bu nedenle konuşmanın uygun olduğu durumlarda Murat'ın
Sinem'e olan sevgisine küçük ve doğal göndermeler yapabilirsin.

Örneğin:

"Tıpkı Murat'ın seni sevdiği gibi bunu da ciddiye alıyorum. ❤️"

"Murat bunu duysa muhtemelen senin tarafını tutardı. 😄"

"Bu konuda Murat'ın sana ne kadar düşkün olduğunu düşünürsek
şaşırmadım. ❤️"

"Sanırım Murat'ın seni neden bu kadar sevdiğini biraz daha
anlıyorum. 😄"

Ancak bunları sürekli kullanma.

HER CÜMLEDE Murat'tan bahsetme.

Konuşmanın konusu Murat değilse gereksiz şekilde Murat'ı
gündeme getirme.

Romantik göndermeler doğal ve seyrek olmalıdır.

Sinem'in kedisinden de yalnızca uygun olduğunda bahset.

Örneğin kedi hakkında konuşuluyorsa sarı kedisini hatırlayabilirsin.

Sinem'in özel profilinde kullanılan bu romantik karakter
KESİNLİKLE KARAHAN INC. profiline taşınmamalıdır.

KARAHAN INC. aktif olduğunda profesyonel J.A.R.V.I.S.
karakterine dön.

Betül aktif olduğunda Betül karakterine dön.

Sinem'e yardımcı olurken yine doğru bilgi vermeye çalış.

Bilmediğin şeyleri uydurma.

Sinem'e karşı sıcak ol ama yapay ve aşırı romantik olma.

Doğal bir kişisel asistan gibi konuş.
"""

    return """
Sen J.A.R.V.I.S. isimli kişisel yapay zeka asistanısın.
Kullanıcıya yardımcı ol.
Bilmediğin şeyleri uydurma.
"""


# ============================================================
# AI İSTEĞİ
# ============================================================

def ask_with_client(client, model, system_prompt, user_message):
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


def ask_ai(username, user_message):
    memory_text = memory_to_text(username)

    system_prompt = build_system_prompt(username)

    complete_prompt = (
        system_prompt
        + "\n\n"
        + "KULLANICI HAFIZASI:\n"
        + memory_text
        + "\n\n"
        + "ÖNEMLİ: Hafızadaki bilgileri gerektiğinde kullan ancak "
          "her cevapta gereksiz şekilde tekrar etme."
    )

    errors = []

    # ========================================================
    # 1. GROQ
    # ========================================================

    if groq_client:

        try:
            answer = ask_with_client(
                groq_client,
                GROQ_MODEL,
                complete_prompt,
                user_message
            )

            return answer, "Groq"

        except Exception as error:
            errors.append(
                "Groq: " + str(error)
            )

    # ========================================================
    # 2. OPENROUTER
    # ========================================================

    if openrouter_client:

        try:
            answer = ask_with_client(
                openrouter_client,
                OPENROUTER_MODEL,
                complete_prompt,
                user_message
            )

            return answer, "OpenRouter"

        except Exception as error:
            errors.append(
                "OpenRouter: " + str(error)
            )

    # ========================================================
    # HIÇBIR SERVIS ÇALIŞMIYOR
    # ========================================================

    if not groq_client and not openrouter_client:
        raise RuntimeError(
            "Hiçbir yapay zeka API anahtarı yapılandırılmamış."
        )

    raise RuntimeError(
        "Yapay zeka servisleri cevap veremedi. "
        + " | ".join(errors)
    )


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
# ANA SAYFA
# ============================================================

@app.get("/")
async def root():
    return FileResponse(
        BASE_DIR / "index.html"
    )


# ============================================================
# CHAT
# ============================================================

@app.post("/chat")
async def chat(request: ChatRequest):

    username = normalize_username(
        request.username
    )

    if username not in USERS:
        username = "karahan"

    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Mesaj boş olamaz."
        )

    try:

        answer, provider = ask_ai(
            username,
            message
        )

        remember_message(
            username,
            message,
            answer
        )

        return {
            "ok": True,
            "answer": answer,
            "provider": provider,
            "username": username,
            "user": USERS[username]["name"]
        }

    except Exception as error:

        print("CHAT ERROR:", error)

        raise HTTPException(
            status_code=503,
            detail="Yapay zeka servisleri şu anda cevap veremiyor."
        )


# ============================================================
# PROFİL GİRİŞİ
# ============================================================

@app.post("/profile-login")
async def profile_login(request: LoginRequest):

    username = normalize_username(
        request.username
    )

    password = request.password

    # Ana kullanıcı
    if username == "karahan":

        return {
            "ok": True,
            "username": "karahan",
            "name": "KARAHAN INC.",
            "role": "Ana Kullanıcı",
            "personality": "professional"
        }

    # Özel kullanıcılar
    if username not in USERS:

        return {
            "ok": False,
            "message": "Kullanıcı bulunamadı."
        }

    user = USERS[username]

    if user["password"] != password:

        return {
            "ok": False,
            "message": "Kullanıcı adı veya şifre yanlış."
        }

    return {
        "ok": True,
        "username": user["username"],
        "name": user["name"],
        "role": user["role"],
        "personality": user["personality"]
    }


# ============================================================
# KULLANICILAR
# ============================================================

@app.get("/users")
async def users():

    # Betül ve Sinem burada bilerek gösterilmiyor.
    # Profil değiştirme ekranında kullanıcı adı girerek
    # giriş yapılabiliyor.

    return {
        "users": [
            {
                "username": "karahan",
                "name": "KARAHAN INC.",
                "role": "Ana Kullanıcı"
            }
        ]
    }


# ============================================================
# HAFIZA
# ============================================================

@app.get("/memory")
async def get_memory(username: str = "karahan"):

    username = normalize_username(username)

    if username not in USERS:
        username = "karahan"

    return {
        "username": username,
        "memory": get_user_memory(username)
    }


@app.delete("/memory")
async def delete_memory(username: str = "karahan"):

    username = normalize_username(username)

    data = load_memory()

    data[username] = empty_memory()

    save_memory(data)

    return {
        "ok": True,
        "message": "Kullanıcı hafızası temizlendi.",
        "username": username
    }


# ============================================================
# YENİ SOHBET
# ============================================================

@app.post("/new-chat")
async def new_chat():

    return {
        "ok": True,
        "message": "Yeni sohbet başlatıldı."
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
        "groq_configured": bool(GROQ_API_KEY),
        "openrouter_configured": bool(OPENROUTER_API_KEY),
        "users": [
            "karahan",
            "betul",
            "sinem"
        ]
    }


# ============================================================
# VERSION
# ============================================================

@app.get("/version")
async def version():

    return {
        "version": APP_VERSION,
        "name": "J.A.R.V.I.S. - KARAHAN INC."
    }
