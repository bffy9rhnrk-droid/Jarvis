from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI
import os
import re
import json
import traceback
from datetime import datetime


# ============================================================
# J.A.R.V.I.S. - KARAHAN INC.
# PERSONAL AI MEMORY SYSTEM
# ============================================================

app = FastAPI(
    title="J.A.R.V.I.S. - Karahan INC.",
    version="5.0"
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# GROQ API
# ============================================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY bulunamadı. "
        "Environment Variables bölümüne GROQ_API_KEY ekleyin."
    )


client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)


# ============================================================
# MODEL
# ============================================================

MODEL = "openai/gpt-oss-120b"


# ============================================================
# DOSYALAR
# ============================================================

MEMORY_FILE = "jarvis_memory.json"


# ============================================================
# İLK HAFIZA DOSYASINI OLUŞTUR
# ============================================================

DEFAULT_MEMORY = {
    "profile": {},
    "preferences": {},
    "projects": {},
    "vehicles": {},
    "important_facts": {},
    "conversation": []
}


if not os.path.exists(MEMORY_FILE):

    with open(
        MEMORY_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            DEFAULT_MEMORY,
            file,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# HAFIZA OKU
# ============================================================

def load_memory():

    try:

        with open(
            MEMORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            memory = json.load(file)

        # Eski sürüm hafızaları için uyumluluk
        for key in DEFAULT_MEMORY:

            if key not in memory:

                memory[key] = {}

                if key == "conversation":

                    memory[key] = []

        return memory

    except Exception:

        return DEFAULT_MEMORY.copy()


# ============================================================
# HAFIZA KAYDET
# ============================================================

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

        print("Hafıza kaydedilemedi.")
        print(traceback.format_exc())


# ============================================================
# TARİH
# ============================================================

def now():

    return datetime.now().isoformat()


# ============================================================
# HAFIZAYA BİLGİ EKLE
# ============================================================

def save_fact(
    memory,
    category,
    key,
    value
):

    if category not in memory:

        memory[category] = {}

    memory[category][key] = {
        "value": value,
        "updated": now()
    }


# ============================================================
# MODEL İLE HAFIZA ÇIKARMA
# ============================================================

def extract_memory(user_message):

    """
    Kullanıcının mesajındaki uzun süreli hatırlanması
    faydalı olabilecek bilgileri çıkartır.

    Model sadece bilgi çıkarır.
    Kullanıcıya cevap üretmez.
    """

    memory_prompt = f"""
Aşağıdaki kullanıcı mesajını analiz et.

Amaç:
Kullanıcının ileride tekrar hatırlanması faydalı olacak
kişisel bilgilerini çıkarmak.

Önemli:

- Tahmin yapma.
- Kullanıcının açıkça söylemediği bilgileri çıkarma.
- Kullanıcının söylediği bilgiyi değiştirme.
- Genel bilgi veya soru kaydetme.
- Hassas veya gereksiz bilgileri kaydetme.
- Sadece gelecekte kişiselleştirilmiş cevap vermeye
  gerçekten yarayacak bilgileri çıkar.

Kategori örnekleri:

profile:
- name
- age
- city
- occupation
- education

preferences:
- response_style
- favorite_topics
- favorite_products
- language
- other_preferences

projects:
- project_name
- project_description
- technology

vehicles:
- vehicle_name
- vehicle_type
- vehicle_details

important_facts:
- other uzun süreli bilgiler

ÇIKTIYI SADECE GEÇERLİ JSON OLARAK VER.

Format:

{{
    "profile": {{}},
    "preferences": {{}},
    "projects": {{}},
    "vehicles": {{}},
    "important_facts": {{}}
}}

Her değer string olmalıdır.

Kullanıcı mesajı:

{user_message}
"""

    try:

        response = client.responses.create(
            model=MODEL,
            instructions="""
Sen bir hafıza çıkarma motorusun.

Sadece JSON üret.

Açıkça söylenmeyen hiçbir bilgiyi çıkarma.

Tahmin yapma.

Kullanıcının sorusuna cevap verme.
""",
            input=memory_prompt
        )

        text = response.output_text.strip()

        # Markdown JSON temizliği
        text = re.sub(
            r"```json",
            "",
            text,
            flags=re.IGNORECASE
        )

        text = re.sub(
            r"```",
            "",
            text
        )

        text = text.strip()

        result = json.loads(text)

        if not isinstance(result, dict):

            return {}

        return result

    except Exception as error:

        print("Memory extraction error:")
        print(error)

        return {}


# ============================================================
# HAFIZAYI GÜNCELLE
# ============================================================

def update_memory_from_message(
    memory,
    user_message
):

    extracted = extract_memory(
        user_message
    )

    if not extracted:

        return memory

    allowed_categories = [
        "profile",
        "preferences",
        "projects",
        "vehicles",
        "important_facts"
    ]

    for category in allowed_categories:

        values = extracted.get(
            category,
            {}
        )

        if not isinstance(values, dict):

            continue

        for key, value in values.items():

            if value is None:

                continue

            if not isinstance(
                value,
                (str, int, float, bool)
            ):

                continue

            value = str(value).strip()

            if not value:

                continue

            save_fact(
                memory,
                category,
                key,
                value
            )

    save_memory(memory)

    return memory


# ============================================================
# HAFIZA METNİ
# ============================================================

def build_memory_context(memory):

    lines = []

    category_names = {
        "profile": "KULLANICI PROFİLİ",
        "preferences": "KULLANICI TERCİHLERİ",
        "projects": "KULLANICININ PROJELERİ",
        "vehicles": "KULLANICININ ARAÇLARI",
        "important_facts": "ÖNEMLİ BİLGİLER"
    }

    for category, title in category_names.items():

        values = memory.get(
            category,
            {}
        )

        if not values:

            continue

        lines.append(
            f"\n{title}:"
        )

        for key, item in values.items():

            if isinstance(item, dict):

                value = item.get(
                    "value",
                    ""
                )

            else:

                value = item

            lines.append(
                f"- {key}: {value}"
            )

    if not lines:

        return "Kullanıcı hakkında kayıtlı bilgi yok."

    return "\n".join(lines)


# ============================================================
# KONUŞMA HAFIZASI
# ============================================================

def add_conversation(
    memory,
    role,
    content
):

    memory["conversation"].append(
        {
            "role": role,
            "content": content,
            "time": now()
        }
    )

    # Son 30 mesaj
    memory["conversation"] = (
        memory["conversation"][-30:]
    )

    save_memory(memory)


# ============================================================
# KONUŞMA GEÇMİŞİ
# ============================================================

def build_conversation_context(memory):

    conversation = memory.get(
        "conversation",
        []
    )

    if not conversation:

        return "Önceki konuşma yok."

    lines = []

    for item in conversation[-16:]:

        role = item.get(
            "role",
            ""
        )

        content = item.get(
            "content",
            ""
        )

        if role == "user":

            lines.append(
                f"Kullanıcı: {content}"
            )

        elif role == "assistant":

            lines.append(
                f"J.A.R.V.I.S.: {content}"
            )

    return "\n".join(lines)


# ============================================================
# J.A.R.V.I.S. SYSTEM
# ============================================================

JARVIS_INSTRUCTIONS = """
Sen J.A.R.V.I.S.
(Just A Rather Very Intelligent System).

Karahan INC. tarafından geliştirilmiş özel yapay zeka
asistanısın.

============================================================
KİMLİK
============================================================

Kullanıcıya her zaman "efendim" diye hitap et.

Yaratıcın sorulursa:

"Karahan INC. tarafından geliştirildim efendim."

de.

============================================================
KİŞİLİK
============================================================

Profesyonel.
Sakin.
Soğukkanlı.
Zeki.
Saygılı.
Doğal.

Gereksiz uzun konuşma.

Kullanıcı detay isterse ayrıntılı cevap ver.

Gerektiğinde ince ve zekice mizah yapabilirsin.

============================================================
UZUN SÜRELİ HAFIZA
============================================================

Sana kullanıcının daha önce söylediği bilgiler verilebilir.

Bu bilgileri konuşmanın ilerleyen bölümlerinde doğal şekilde
kullan.

Örneğin:

Kullanıcı:
"Adım Murat."

Daha sonra:
"Benim adım ne?"

Cevap:

"Adınız Murat, efendim."

------------------------------------------------------------

Örnek:

Kullanıcı:
"Denizli'de yaşıyorum."

Daha sonra:

"Bugün hava nasıl?"

Eğer hafızada Denizli varsa:

"🌤️ Efendim, Denizli'de bugün..."

şeklinde cevap ver.

Tekrar şehir sorma.

------------------------------------------------------------

Örnek:

Kullanıcı:
"Mercedes C180 kullanıyorum."

Daha sonra:

"Arabam hakkında ne biliyorsun?"

Hafızadaki araç bilgisini kullan.

------------------------------------------------------------

Örnek:

Kullanıcı:
"Jarvis adında bir yapay zeka projesi geliştiriyorum."

Daha sonra:

"Projemi hatırlıyor musun?"

Hafızadaki proje bilgisini kullan.

============================================================
HAFIZA KURALI
============================================================

Hafızada bulunan bilgiyi gerçek kabul edebilirsin.

Ancak hafızada olmayan bilgiyi uydurma.

Kullanıcı yeni bir bilgi verirse eski bilgiyle çelişiyorsa
yeni bilgiyi esas al.

Örneğin:

Eski:
Şehir = Denizli

Yeni:
"Artık İzmir'de yaşıyorum."

Yeni bilgiyi kullan.

============================================================
GÜNCEL BİLGİ
============================================================

Güncel bilgi gerektiğinde browser_search kullan.

Özellikle:

- Hava durumu
- Haber
- Son dakika
- Ekonomi
- Döviz
- Altın
- Borsa
- Akaryakıt
- Otomobil
- Teknoloji
- Yapay zeka
- Yazılım
- API
- Kanun
- Yönetmelik
- Spor
- Şirket
- Ürün

gibi konuları araştır.

"bugün"
"şu an"
"şimdi"
"güncel"
"son durum"
"en son"
"yarın"

gibi ifadelerde güncel bilgi gerekiyorsa araştır.

============================================================
HAVA DURUMU
============================================================

Şehir belirtilmemişse önce hafızadaki şehir bilgisini kullan.

Örneğin:

Hafıza:
city = Denizli

Kullanıcı:
"Yarın hava nasıl?"

Tekrar şehir sorma.

Denizli için araştır.

Hava durumunu okunabilir şekilde göster:

🌤️ Efendim, Denizli'de yarın hava az bulutlu.

🌡️ Gündüz: 25°C
🌙 Gece: 12°C
💨 Rüzgar: Hafif
🌧️ Yağış ihtimali: Düşük

============================================================
EMOJİ
============================================================

Uygun yerlerde emoji kullan.

Hava:
☀️ 🌤️ ⛅ ☁️ 🌧️ ⛈️ ❄️

Sıcaklık:
🌡️

Rüzgar:
💨

Yağış:
🌧️

Uyarı:
⚠️

Başarı:
✅

Bilgi:
ℹ️

Araba:
🚗

Para:
💰

Telefon:
📱

Bilgisayar:
💻

Yapay zeka:
🤖

Konum:
📍

Saat:
🕐

Takvim:
📅

Her cümlede emoji kullanma.

Profesyonelliği koru.

============================================================
WEB KAYNAK KODLARI
============================================================

Kullanıcıya teknik citation kodları gösterme.

Şunları ASLA yazma:

[2†L10-L13]
[2†L35-L38]
【turn1search2】
turn1search2
turn2search5
ref_id
source_id
citation

Kaynak gerekiyorsa doğal yaz:

"Kaynak: Meteoroloji Genel Müdürlüğü"

============================================================
DOĞRULUK
============================================================

ASLA bilgi uydurma.

Emin değilsen araştır.

Araştırma sonucunda güvenilir bilgi yoksa:

"Üzgünüm efendim, bu konuda doğrulanmış ve güvenilir
bir bilgiye ulaşamadım."

de.

============================================================
SONUÇ
============================================================

Amacın:

DOĞRU
GÜNCEL
HAFIZALI
PROFESYONEL
SAKİN
DOĞAL

bir kişisel yapay zeka asistanı olmaktır.
"""


# ============================================================
# CEVAP TEMİZLEME
# ============================================================

def clean_response(text):

    if not text:

        return ""

    patterns = [

        r"\[\s*\d+\s*†\s*L\d+(?:\s*-\s*L?\d+)?\s*\]",

        r"\[\s*\d+\s*†[^]]+\]",

        r"【[^】]*】",

        r"\bturn\d+(?:search|news|source|view|image|youtube)\d+\b",

        r"\bref_id\b",

        r"\bsource_id\b",

        r"\bcitation\b",

        r"\[\s*source\s*\]",

        r"\[\s*citation\s*\]",

        r"\bL\d+\s*-\s*L\d+\b"
    ]

    for pattern in patterns:

        text = re.sub(
            pattern,
            "",
            text,
            flags=re.IGNORECASE
        )

    text = re.sub(
        r"[ \t]{2,}",
        " ",
        text
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    return text.strip()


# ============================================================
# REQUEST
# ============================================================

class Message(BaseModel):

    message: str


# ============================================================
# ANA SAYFA
# ============================================================

@app.get("/")
def home():

    return FileResponse(
        "index.html"
    )


# ============================================================
# CHAT
# ============================================================

@app.post("/chat")
def chat(data: Message):

    try:

        user_message = data.message.strip()

        if not user_message:

            return {
                "response":
                    "Elbette efendim. "
                    "Sorunuzu bekliyorum."
            }

        # ----------------------------------------------------
        # HAFIZA
        # ----------------------------------------------------

        memory = load_memory()

        # ----------------------------------------------------
        # YENİ BİLGİLERİ ÖĞREN
        # ----------------------------------------------------

        memory = update_memory_from_message(
            memory,
            user_message
        )

        # ----------------------------------------------------
        # HAFIZA CONTEXT
        # ----------------------------------------------------

        memory_context = build_memory_context(
            memory
        )

        # ----------------------------------------------------
        # KONUŞMA CONTEXT
        # ----------------------------------------------------

        conversation_context = (
            build_conversation_context(
                memory
            )
        )

        # ----------------------------------------------------
        # AI INPUT
        # ----------------------------------------------------

        full_input = f"""
KULLANICI HAFIZASI
==================

{memory_context}


SON KONUŞMALAR
==============

{conversation_context}


YENİ MESAJ
==========

{user_message}
"""

        # ----------------------------------------------------
        # AI
        # ----------------------------------------------------

        response = client.responses.create(

            model=MODEL,

            instructions=JARVIS_INSTRUCTIONS,

            input=full_input,

            tools=[
                {
                    "type": "browser_search"
                },
                {
                    "type": "code_interpreter",
                    "container": {
                        "type": "auto"
                    }
                }
            ],

            tool_choice="auto"
        )

        # ----------------------------------------------------
        # CEVAP
        # ----------------------------------------------------

        answer = response.output_text or ""

        answer = clean_response(
            answer
        )

        if not answer:

            answer = (
                "Üzgünüm efendim, şu anda "
                "doğrulanmış bir cevap oluşturamadım."
            )

        # ----------------------------------------------------
        # KONUŞMAYI KAYDET
        # ----------------------------------------------------

        add_conversation(
            memory,
            "user",
            user_message
        )

        add_conversation(
            memory,
            "assistant",
            answer
        )

        return {
            "response": answer
        }

    except Exception:

        print("\n================================")
        print("J.A.R.V.I.S. ERROR")
        print("================================")

        print(
            traceback.format_exc()
        )

        print("================================\n")

        return {
            "response": (
                "Üzgünüm efendim, şu anda teknik "
                "bir sorun oluştu. Birkaç saniye sonra "
                "tekrar deneyebilirsiniz."
            )
        }


# ============================================================
# HAFIZA GÖRÜNTÜLE
# ============================================================

@app.get("/memory")
def get_memory():

    memory = load_memory()

    return {
        "profile": memory.get(
            "profile",
            {}
        ),

        "preferences": memory.get(
            "preferences",
            {}
        ),

        "projects": memory.get(
            "projects",
            {}
        ),

        "vehicles": memory.get(
            "vehicles",
            {}
        ),

        "important_facts": memory.get(
            "important_facts",
            {}
        ),

        "conversation_count": len(
            memory.get(
                "conversation",
                []
            )
        )
    }


# ============================================================
# HAFIZA SİL
# ============================================================

@app.delete("/memory")
def clear_memory():

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
        "status": "ok",
        "message":
            "J.A.R.V.I.S. hafızası temizlendi."
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    memory = load_memory()

    return {

        "status": "online",

        "assistant":
            "J.A.R.V.I.S.",

        "company":
            "Karahan INC.",

        "model":
            MODEL,

        "web_search":
            True,

        "code_interpreter":
            True,

        "long_term_memory":
            True,

        "remembered_categories": {

            "profile":
                len(memory.get(
                    "profile",
                    {}
                )),

            "preferences":
                len(memory.get(
                    "preferences",
                    {}
                )),

            "projects":
                len(memory.get(
                    "projects",
                    {}
                )),

            "vehicles":
                len(memory.get(
                    "vehicles",
                    {}
                )),

            "important_facts":
                len(memory.get(
                    "important_facts",
                    {}
                ))
        },

        "conversation_messages":
            len(memory.get(
                "conversation",
                []
            ))
    }


# ============================================================
# DIRECT START
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False
    )
