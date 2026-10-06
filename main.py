import os
import re
import json
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI


# ============================================================
# J.A.R.V.I.S. — KARAHAN INC.
# Stable Backend
# ============================================================

APP_VERSION = "7.0.0"

BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "index.html"
MEMORY_FILE = BASE_DIR / "jarvis_memory.json"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get(
    "GROQ_MODEL",
    "openai/gpt-oss-120b"
).strip()

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


# ============================================================
# FASTAPI
# ============================================================

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


# ============================================================
# OPENAI / GROQ CLIENT
# ============================================================

client: Optional[OpenAI] = None

if GROQ_API_KEY:
    client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
        timeout=45.0,
        max_retries=1
    )


# ============================================================
# MEMORY
# ============================================================

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
            return DEFAULT_MEMORY.copy()

        with open(MEMORY_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return DEFAULT_MEMORY.copy()

        memory = DEFAULT_MEMORY.copy()

        for key in memory:
            if key in data:
                memory[key] = data[key]

        return memory

    except Exception:
        return DEFAULT_MEMORY.copy()


MEMORY = load_memory()


def save_memory():
    try:
        temp_file = MEMORY_FILE.with_suffix(".tmp")

        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(
                MEMORY,
                file,
                ensure_ascii=False,
                indent=2
            )

        temp_file.replace(MEMORY_FILE)

    except Exception:
        # Bellek kaydedilemese bile sohbet devam etsin.
        pass


def clean_text(text: str, max_length: int = 500):
    if not isinstance(text, str):
        return ""

    text = text.strip()

    if len(text) > max_length:
        text = text[:max_length] + "..."

    return text


# ============================================================
# MEMORY EXTRACTION
# ============================================================

def update_memory_from_message(message: str):
    global MEMORY

    text = message.strip()

    if not text:
        return

    # --------------------------------------------------------
    # İSİM
    # --------------------------------------------------------

    name_patterns = [
        r"\badım\s+([A-Za-zÇĞİÖŞÜçğıöşü]{2,30})\b",
        r"\bbenim adım\s+([A-Za-zÇĞİÖŞÜçğıöşü]{2,30})\b",
        r"\bismim\s+([A-Za-zÇĞİÖŞÜçğıöşü]{2,30})\b"
    ]

    for pattern in name_patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            MEMORY["profile"]["name"] = match.group(1).strip().capitalize()
            break

    # --------------------------------------------------------
    # ŞEHİR
    # --------------------------------------------------------

    city_patterns = [
        r"\b([A-Za-zÇĞİÖŞÜçğıöşü]+)'?de yaşıyorum\b",
        r"\b([A-Za-zÇĞİÖŞÜçğıöşü]+)'?da yaşıyorum\b",
        r"\b([A-Za-zÇĞİÖŞÜçğıöşü]+) şehrinde yaşıyorum\b"
    ]

    for pattern in city_patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            MEMORY["profile"]["city"] = match.group(1).strip().capitalize()
            break

    # --------------------------------------------------------
    # JARVIS PROJESİ
    # --------------------------------------------------------

    lower = text.lower()

    if (
        "jarvis" in lower
        or "j.a.r.v.i.s" in lower
        or "karahan inc" in lower
    ):
        MEMORY["projects"]["jarvis"] = (
            "Kullanıcının kişisel yapay zeka asistanı projesi. "
            "Projenin adı J.A.R.V.I.S. — KARAHAN INC."
        )

    # --------------------------------------------------------
    # ARAÇLAR
    # --------------------------------------------------------

    if "caddy" in lower:
        MEMORY["vehicles"]["caddy"] = (
            "Kullanıcının Volkswagen Caddy aracı bulunuyor."
        )

    if "mercedes" in lower or "w204" in lower:
        MEMORY["vehicles"]["mercedes"] = (
            "Kullanıcının Mercedes-Benz W204 C180 aracı bulunuyor."
        )

    # --------------------------------------------------------
    # BASİT UNUTMA KOMUTU
    # --------------------------------------------------------

    forget_patterns = [
        r"\bunut\s+([^.!?]+)",
        r"\bunut bunu\b",
        r"\bbunu hafızandan sil\b",
        r"\bbunu hatırlama\b"
    ]

    for pattern in forget_patterns:
        if re.search(pattern, lower):
            # Genel sohbet geçmişini temizlemiyoruz.
            # Sadece açıkça istenen geçici komutları işaretliyoruz.
            MEMORY["important_facts"]["last_forget_request"] = text
            break


# ============================================================
# CONVERSATION MEMORY
# ============================================================

MAX_CONVERSATION_ITEMS = 10
MAX_MESSAGE_LENGTH = 3000


def add_conversation(role: str, content: str):
    content = clean_text(content, MAX_MESSAGE_LENGTH)

    if not content:
        return

    MEMORY["conversation"].append({
        "role": role,
        "content": content,
        "time": int(time.time())
    })

    # Sadece son 10 mesaj tutuluyor.
    MEMORY["conversation"] = MEMORY["conversation"][
        -MAX_CONVERSATION_ITEMS:
    ]

    save_memory()


# ============================================================
# MEMORY CONTEXT
# ============================================================

def build_memory_context():
    """
    Modele gönderilecek belleği küçük tutuyoruz.
    Böylece konuşmalar ilerledikçe request şişmiyor.
    """

    sections = []

    profile = MEMORY.get("profile", {})

    if profile:
        sections.append(
            "PROFİL:\n" +
            json.dumps(
                profile,
                ensure_ascii=False
            )
        )

    preferences = MEMORY.get("preferences", {})

    if preferences:
        sections.append(
            "TERCİHLER:\n" +
            json.dumps(
                preferences,
                ensure_ascii=False
            )
        )

    projects = MEMORY.get("projects", {})

    if projects:
        sections.append(
            "PROJELER:\n" +
            json.dumps(
                projects,
                ensure_ascii=False
            )
        )

    vehicles = MEMORY.get("vehicles", {})

    if vehicles:
        sections.append(
            "ARAÇLAR:\n" +
            json.dumps(
                vehicles,
                ensure_ascii=False
            )
        )

    important = MEMORY.get("important_facts", {})

    if important:
        sections.append(
            "ÖNEMLİ BİLGİLER:\n" +
            json.dumps(
                important,
                ensure_ascii=False
            )
        )

    result = "\n\n".join(sections)

    # Belleğin de sonsuza kadar büyümesini engelle.
    return result[:5000]


# ============================================================
# RECENT CONVERSATION
# ============================================================

def build_recent_conversation():
    conversation = MEMORY.get("conversation", [])

    result = []

    for item in conversation[-MAX_CONVERSATION_ITEMS:]:
        role = item.get("role")

        if role not in ("user", "assistant"):
            continue

        content = clean_text(
            item.get("content", ""),
            1500
        )

        if not content:
            continue

        result.append({
            "role": role,
            "content": content
        })

    return result


# ============================================================
# SYSTEM PROMPT
# ============================================================

def build_system_prompt():

    memory_context = build_memory_context()

    return f"""
Sen J.A.R.V.I.S. — KARAHAN INC. tarafından geliştirilen
kişisel yapay zeka asistanısın.

Kullanıcıyla Türkçe konuş.

Kullanıcıya gerektiğinde:
"efendim"
şeklinde hitap et.

Profesyonel, doğal ve sakin konuş.

Gereksiz yere aynı şeyi tekrar etme.

Kullanıcı kısa bir soru soruyorsa gereksiz uzun cevap verme.

Bilmediğin bir şeyi kesinmiş gibi söyleme.

Kullanıcı senden kod istediğinde doğrudan çalışabilir kod üret.

Kullanıcının geçmiş konuşmalarındaki bilgileri sadece gerektiğinde
kullan.

Bellekteki bilgiler:
{memory_context}

Önemli kurallar:

1. Kullanıcıya saygılı ol.
2. Gereksiz uyarılarla konuşmayı boğma.
3. Aynı cümleyi tekrarlama.
4. Kullanıcı "adım ..." gibi bir bilgi verdiğinde bunu hatırla.
5. Kullanıcı şehir bilgisini verdiğinde bunu hatırla.
6. Kullanıcı J.A.R.V.I.S. projesi hakkında konuştuğunda proje bağlamını koru.
7. Yanıtlarını mümkün olduğunca doğal Türkçe ver.
8. Web erişimin yoksa varmış gibi davranma.
9. Kaynak veya citation kodlarını kullanıcıya ham biçimde gösterme.
10. Kullanıcı sana nasıl hitap edilmesini istediğini belirtirse bunu dikkate al.
"""


# ============================================================
# CITATION CLEANER
# ============================================================

def clean_citations(text: str):

    if not isinstance(text, str):
        return ""

    patterns = [
        r"\[\d+\]",
        r"\[\d+†[^\]]+\]",
        r"【[^】]+】",
        r"<\|[^>]+\|>",
    ]

    for pattern in patterns:
        text = re.sub(pattern, "", text)

    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ============================================================
# REQUEST MODEL
# ============================================================

class ChatRequest(BaseModel):
    message: str


# ============================================================
# ROUTES
# ============================================================

@app.get("/")
async def home():

    if INDEX_FILE.exists():
        return FileResponse(INDEX_FILE)

    return {
        "name": "J.A.R.V.I.S.",
        "company": "KARAHAN INC.",
        "version": APP_VERSION
    }


@app.get("/health")
async def health():

    return {
        "status": "online",
        "version": APP_VERSION,
        "model": GROQ_MODEL,
        "groq_configured": bool(GROQ_API_KEY)
    }


@app.get("/version")
async def version():

    return {
        "version": APP_VERSION,
        "name": "J.A.R.V.I.S.",
        "company": "KARAHAN INC.",
        "model": GROQ_MODEL
    }


@app.get("/memory")
async def get_memory():

    return {
        "status": "success",
        "memory": MEMORY
    }


@app.delete("/memory")
async def delete_memory():

    global MEMORY

    MEMORY = {
        "profile": {},
        "preferences": {},
        "projects": {},
        "vehicles": {},
        "important_facts": {},
        "conversation": []
    }

    save_memory()

    return {
        "status": "success",
        "message": "J.A.R.V.I.S. belleği temizlendi."
    }


# ============================================================
# CHAT
# ============================================================

@app.post("/chat")
async def chat(request: ChatRequest):

    start_time = time.time()

    user_message = request.message.strip()

    # --------------------------------------------------------
    # BOŞ MESAJ
    # --------------------------------------------------------

    if not user_message:

        return {
            "response": "Efendim, mesajınızı göremedim.",
            "status": "success"
        }

    # --------------------------------------------------------
    # MAKSİMUM MESAJ BOYUTU
    # --------------------------------------------------------

    if len(user_message) > MAX_MESSAGE_LENGTH:

        user_message = user_message[:MAX_MESSAGE_LENGTH]

    # --------------------------------------------------------
    # API KEY KONTROLÜ
    # --------------------------------------------------------

    if not GROQ_API_KEY or client is None:

        return {
            "response": (
                "Efendim, Groq API bağlantısı yapılandırılmamış. "
                "GROQ_API_KEY değişkenini kontrol edin."
            ),
            "status": "error",
            "error": "GROQ_API_KEY_MISSING"
        }

    # --------------------------------------------------------
    # BELLEĞİ GÜNCELLE
    # --------------------------------------------------------

    update_memory_from_message(user_message)

    # --------------------------------------------------------
    # SYSTEM
    # --------------------------------------------------------

    system_prompt = build_system_prompt()

    # --------------------------------------------------------
    # SON KONUŞMALAR
    # --------------------------------------------------------

    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]

    recent = build_recent_conversation()

    for item in recent:
        messages.append(item)

    # --------------------------------------------------------
    # YENİ MESAJ
    # --------------------------------------------------------

    messages.append({
        "role": "user",
        "content": user_message
    })

    # --------------------------------------------------------
    # GROQ REQUEST
    # --------------------------------------------------------

    try:

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=1200
        )

        # ----------------------------------------------------
        # RESPONSE KONTROLÜ
        # ----------------------------------------------------

        if not response.choices:

            raise RuntimeError(
                "Model boş cevap döndürdü."
            )

        assistant_message = response.choices[0].message.content

        if not assistant_message:

            raise RuntimeError(
                "Model cevap içeriği boş."
            )

        assistant_message = clean_citations(
            assistant_message
        )

        # ----------------------------------------------------
        # KONUŞMAYI KAYDET
        # ----------------------------------------------------

        add_conversation(
            "user",
            user_message
        )

        add_conversation(
            "assistant",
            assistant_message
        )

        elapsed = round(
            time.time() - start_time,
            2
        )

        return {
            "response": assistant_message,
            "status": "success",
            "version": APP_VERSION,
            "model": GROQ_MODEL,
            "response_time": elapsed
        }

    # ========================================================
    # RATE LIMIT
    # ========================================================

    except Exception as error:

        error_text = str(error)

        error_lower = error_text.lower()

        # ----------------------------------------------------
        # 429
        # ----------------------------------------------------

        if (
            "429" in error_text
            or "rate limit" in error_lower
            or "rate_limit" in error_lower
        ):

            return {
                "response": (
                    "Efendim, yapay zeka servisinde şu anda "
                    "yoğunluk oluştu. Birkaç saniye sonra "
                    "tekrar deneyebilirsiniz."
                ),
                "status": "error",
                "error": "RATE_LIMIT",
                "detail": error_text[:1000]
            }

        # ----------------------------------------------------
        # CONTEXT
        # ----------------------------------------------------

        if (
            "context" in error_lower
            or "token" in error_lower
            or "too long" in error_lower
            or "maximum" in error_lower
        ):

            return {
                "response": (
                    "Efendim, konuşma bağlamı fazla büyüdü. "
                    "J.A.R.V.I.S. bunu otomatik olarak "
                    "sınırlıyor ancak model tarafında bir "
                    "bağlam sınırı oluştu."
                ),
                "status": "error",
                "error": "CONTEXT_LIMIT",
                "detail": error_text[:1000]
            }

        # ----------------------------------------------------
        # TIMEOUT
        # ----------------------------------------------------

        if (
            "timeout" in error_lower
            or "timed out" in error_lower
        ):

            return {
                "response": (
                    "Efendim, yapay zeka sunucusundan cevap "
                    "almak biraz uzun sürdü. Lütfen tekrar deneyin."
                ),
                "status": "error",
                "error": "TIMEOUT",
                "detail": error_text[:1000]
            }

        # ----------------------------------------------------
        # CONNECTION
        # ----------------------------------------------------

        if (
            "connection" in error_lower
            or "connect" in error_lower
            or "network" in error_lower
        ):

            return {
                "response": (
                    "Efendim, yapay zeka servisine bağlantı "
                    "kurulamadı. Sunucu bağlantısını kontrol edin."
                ),
                "status": "error",
                "error": "CONNECTION_ERROR",
                "detail": error_text[:1000]
            }

        # ----------------------------------------------------
        # GENEL HATA
        # ----------------------------------------------------

        print("\n==========================================")
        print("JARVIS CHAT ERROR")
        print("==========================================")
        print(error_text)
        print("==========================================\n")

        return {
            "response": (
                "Üzgünüm efendim, şu anda yapay zeka "
                "servisinden cevap alınamadı. Birkaç saniye "
                "sonra tekrar deneyebilirsiniz."
            ),
            "status": "error",
            "error": "AI_REQUEST_ERROR",
            "detail": error_text[:1000]
        }


# ============================================================
# DIRECT START
# ============================================================

if __name__ == "__main__":

    import uvicorn

    port = int(
        os.environ.get(
            "PORT",
            "8000"
        )
    )

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port
    )
