import os
import re
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI


# =========================================================
# J.A.R.V.I.S. — KARAHAN INC.
# Backend Version: 6.0
# =========================================================

APP_VERSION = "6.0.0"

BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "index.html"
MEMORY_FILE = BASE_DIR / "jarvis_memory.json"


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

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    print("UYARI: GROQ_API_KEY bulunamadı.")

client = None

if GROQ_API_KEY:
    client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )


MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-120b"
)


# =========================================================
# DATA MODELS
# =========================================================

class Message(BaseModel):
    message: str


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
            save_memory(DEFAULT_MEMORY.copy())
            return DEFAULT_MEMORY.copy()

        with open(MEMORY_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return DEFAULT_MEMORY.copy()

        for key in DEFAULT_MEMORY:
            if key not in data:
                data[key] = (
                    [] if key == "conversation"
                    else {}
                )

        return data

    except Exception:
        print("Hafıza okunamadı:")
        traceback.print_exc()
        return DEFAULT_MEMORY.copy()


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

    except Exception:
        print("Hafıza kaydedilemedi:")
        traceback.print_exc()


def save_fact(
    memory,
    category,
    key,
    value
):
    if category not in memory:
        memory[category] = {}

    if not isinstance(memory[category], dict):
        memory[category] = {}

    memory[category][key] = {
        "value": value,
        "updated_at": datetime.now().isoformat()
    }


# =========================================================
# SIMPLE PERSONAL MEMORY
# =========================================================

def update_memory_from_message(
    message: str,
    memory: dict
):
    text = message.strip()

    # -----------------------------------------------------
    # İSİM
    # -----------------------------------------------------

    name_patterns = [
        r"\badım\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)",
        r"\bbenim\s+adım\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)",
        r"\bismim\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)"
    ]

    for pattern in name_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            name = match.group(1).strip()

            save_fact(
                memory,
                "profile",
                "name",
                name
            )

            break

    # -----------------------------------------------------
    # ŞEHİR
    # -----------------------------------------------------

    city_patterns = [
        r"([A-Za-zÇĞİÖŞÜçğıöşü]+)'?de\s+yaşıyorum",
        r"([A-Za-zÇĞİÖŞÜçğıöşü]+)'?da\s+yaşıyorum",
        r"([A-Za-zÇĞİÖŞÜçğıöşü]+) şehrinde yaşıyorum",
        r"([A-Za-zÇĞİÖŞÜçğıöşü]+)'?liyim",
        r"([A-Za-zÇĞİÖŞÜçğıöşü]+)'?lıyım"
    ]

    for pattern in city_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            city = match.group(1).strip()

            save_fact(
                memory,
                "profile",
                "city",
                city
            )

            break

    # -----------------------------------------------------
    # PROJE
    # -----------------------------------------------------

    if (
        "jarvis" in text.lower()
        or "j.a.r.v.i.s" in text.lower()
    ):
        save_fact(
            memory,
            "projects",
            "main_project",
            "J.A.R.V.I.S. — KARAHAN INC. kişisel yapay zeka asistanı"
        )

    # -----------------------------------------------------
    # ARAÇLAR
    # -----------------------------------------------------

    car_keywords = [
        "caddy",
        "mercedes",
        "w204",
        "c180"
    ]

    lower_text = text.lower()

    for keyword in car_keywords:
        if keyword in lower_text:

            if keyword in ["caddy"]:
                save_fact(
                    memory,
                    "vehicles",
                    "caddy",
                    "Kullanıcının Caddy aracı"
                )

            elif keyword in ["mercedes", "w204", "c180"]:
                save_fact(
                    memory,
                    "vehicles",
                    "mercedes_c180",
                    "Mercedes C180 W204"
                )

    # -----------------------------------------------------
    # UNUTMA KOMUTU
    # -----------------------------------------------------

    forget_patterns = [
        r"bunu unut",
        r"bunu hafızadan sil",
        r"bunu hatırlama",
        r"bunu unutmanı istiyorum"
    ]

    for pattern in forget_patterns:

        if re.search(
            pattern,
            text,
            re.IGNORECASE
        ):

            # Son konuşmadaki ilgili bilgi
            # tamamen otomatik silinmiyor.
            # Güvenli tarafta kalıyoruz.
            save_fact(
                memory,
                "important_facts",
                "last_forget_request",
                text
            )

            break


# =========================================================
# CONVERSATION MEMORY
# =========================================================

def add_conversation(
    memory,
    role,
    content
):
    if "conversation" not in memory:
        memory["conversation"] = []

    memory["conversation"].append({
        "role": role,
        "content": content,
        "time": datetime.now().isoformat()
    })

    # Son 30 mesajı tut
    memory["conversation"] = memory[
        "conversation"
    ][-30:]


def build_memory_context(memory):

    lines = []

    for category, values in memory.items():

        if category == "conversation":
            continue

        if not isinstance(values, dict):
            continue

        for key, item in values.items():

            if isinstance(item, dict):
                value = item.get(
                    "value",
                    ""
                )
            else:
                value = item

            if value:
                lines.append(
                    f"{category}.{key}: {value}"
                )

    if not lines:
        return "Henüz kayıtlı kişisel bilgi yok."

    return "\n".join(lines)


def build_conversation_context(
    memory
):

    conversation = memory.get(
        "conversation",
        []
    )

    if not conversation:
        return ""

    last_messages = conversation[-12:]

    lines = []

    for item in last_messages:

        role = item.get(
            "role",
            "user"
        )

        content = item.get(
            "content",
            ""
        )

        lines.append(
            f"{role}: {content}"
        )

    return "\n".join(lines)


# =========================================================
# RESPONSE CLEANER
# =========================================================

def clean_response(text: str):

    if not text:
        return ""

    # Citation / source kodlarını temizle
    patterns = [
        r"\[\d+†L\d+(?:-L\d+)?\]",
        r"【[^】]+】",
        r"\bturn\d+(?:search|news|view|source)\d+\b",
        r"\bref_id\s*[:=]\s*\S+",
        r"\bsource_id\s*[:=]\s*\S+",
        r"\bcitation\s*[:=]\s*\S+"
    ]

    for pattern in patterns:
        text = re.sub(
            pattern,
            "",
            text,
            flags=re.IGNORECASE
        )

    # Fazla boşlukları düzelt
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    text = re.sub(
        r"[ \t]{2,}",
        " ",
        text
    )

    return text.strip()


# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
Sen J.A.R.V.I.S. — KARAHAN INC. kişisel yapay zeka asistanısın.

Kullanıcıya her zaman "efendim" diye hitap et.

Kişiliğin:
- Profesyonel
- Sakin
- Akıllı
- Yardımcı
- Gerektiğinde hafif İngiliz tarzı mizah kullanan
- Gereksiz uzun konuşmayan
- Net cevap veren

ÖNEMLİ KURALLAR:

1. Kullanıcının hafızada bulunan bilgilerini gerektiğinde kullan.
2. Kullanıcı daha önce şehrini söylediyse hava durumu sorulduğunda tekrar şehir sorma.
3. Kullanıcı daha önce aracını söylediyse araçla ilgili konuşmalarda bunu bağlam olarak kullan.
4. Kullanıcının J.A.R.V.I.S. projesi hakkında konuştuğunu unutma.
5. Güncel bilgi gerekiyorsa mümkün olduğunca güncel bilgiye dayan.
6. Emin olmadığın bilgiyi kesin gerçek gibi söyleme.
7. Kullanıcı sana yeni ve eski bilgi arasında farklı bir bilgi verirse yeni bilgiyi esas al.
8. API anahtarı, şifre veya gizli bilgileri asla kullanıcıya gösterme.
9. Ham citation kodlarını kullanıcıya gösterme.
10. Kaynak bilgisi gerekiyorsa doğal dil kullan.
11. Kullanıcı istemediği sürece kişisel bilgileri gereksiz yere tekrar etme.
12. Cevapları mümkün olduğunca doğal ve insan gibi ver.
13. Kullanıcı Türkçe konuşuyorsa Türkçe cevap ver.
14. Gerektiğinde emoji kullanabilirsin ancak abartma.

Hafıza bağlamı:
{MEMORY}

Son konuşmalar:
{CONVERSATION}
"""


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():

    if not INDEX_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="index.html bulunamadı."
        )

    return FileResponse(
        str(INDEX_FILE)
    )


# =========================================================
# CHAT
# =========================================================

@app.post("/chat")
def chat(data: Message):

    user_message = data.message.strip()

    if not user_message:
        return {
            "response": "Efendim, mesajınız boş görünüyor."
        }

    if not client:

        return {
            "response": (
                "Efendim, Groq bağlantısı yapılandırılmamış. "
                "Lütfen GROQ_API_KEY değişkenini kontrol edin."
            )
        }

    try:

        # Hafızayı yükle
        memory = load_memory()

        # Kullanıcının mesajından basit kalıcı bilgiler çıkar
        update_memory_from_message(
            user_message,
            memory
        )

        # Kullanıcı mesajını kaydet
        add_conversation(
            memory,
            "user",
            user_message
        )

        # Context oluştur
        memory_context = build_memory_context(
            memory
        )

        conversation_context = build_conversation_context(
            memory
        )

        system_prompt = SYSTEM_PROMPT.format(
            MEMORY=memory_context,
            CONVERSATION=conversation_context
        )

        # -------------------------------------------------
        # GROQ CHAT COMPLETION
        # -------------------------------------------------

        response = client.chat.completions.create(
            model=MODEL,

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

            max_tokens=2048
        )

        assistant_message = response.choices[
            0
        ].message.content

        if not assistant_message:
            assistant_message = (
                "Efendim, şu anda cevap oluşturamadım."
            )

        assistant_message = clean_response(
            assistant_message
        )

        # Asistan cevabını hafızaya kaydet
        add_conversation(
            memory,
            "assistant",
            assistant_message
        )

        # Hafızayı kaydet
        save_memory(memory)

        return {
            "response": assistant_message,
            "status": "success",
            "version": APP_VERSION
        }

    except Exception as error:

        print("\n==============================")
        print("JARVIS CHAT ERROR")
        print("==============================")
        print(str(error))
        traceback.print_exc()
        print("==============================\n")

        return {
            "response": (
                "Üzgünüm efendim, şu anda bağlantıda "
                "bir sorun oluştu. Birkaç saniye sonra "
                "tekrar deneyebilirsiniz."
            ),
            "status": "error",
            "error": str(error)
        }


# =========================================================
# MEMORY
# =========================================================

@app.get("/memory")
def get_memory():

    memory = load_memory()

    return {
        "status": "success",
        "version": APP_VERSION,
        "memory": memory
    }


@app.delete("/memory")
def delete_memory():

    try:

        save_memory(
            DEFAULT_MEMORY.copy()
        )

        return {
            "status": "success",
            "message": "J.A.R.V.I.S. hafızası temizlendi."
        }

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
def health():

    memory = load_memory()

    conversation_count = len(
        memory.get(
            "conversation",
            []
        )
    )

    return {
        "status": "online",
        "app": "J.A.R.V.I.S. — KARAHAN INC.",
        "version": APP_VERSION,
        "model": MODEL,
        "groq_configured": bool(GROQ_API_KEY),
        "memory_file": MEMORY_FILE.exists(),
        "conversation_count": conversation_count,
        "time": datetime.now().isoformat()
    }


# =========================================================
# VERSION
# =========================================================

@app.get("/version")
def version():

    return {
        "app": "J.A.R.V.I.S. — KARAHAN INC.",
        "version": APP_VERSION,
        "status": "running"
    }


# =========================================================
# START
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
        port=port,
        reload=False
    )
