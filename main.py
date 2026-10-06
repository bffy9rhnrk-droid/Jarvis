import os
import re
import json
import uuid
import textwrap
import time
from pathlib import Path
from datetime import datetime
from io import BytesIO

import requests

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from openai import OpenAI

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ============================================================
# K.A.R.V.I.S. - KARAHAN INC.
# MAIN BACKEND
# ============================================================

APP_VERSION = "26.2.0"

BASE_DIR = Path(__file__).resolve().parent

FILES_DIR = BASE_DIR / "files"
GENERATED_DIR = BASE_DIR / "generated"
FONT_DIR = BASE_DIR / "fonts"

MEMORY_FILE = BASE_DIR / "memory.json"
ERROR_FILE = BASE_DIR / "errors.json"

FILES_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
FONT_DIR.mkdir(parents=True, exist_ok=True)


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

app.mount(
    "/files",
    StaticFiles(directory=str(FILES_DIR)),
    name="files"
)

app.mount(
    "/generated",
    StaticFiles(directory=str(GENERATED_DIR)),
    name="generated"
)


# ============================================================
# API ANAHTARLARI
# ============================================================

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY",
    ""
).strip()

OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    ""
).strip()


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
    },

    "ilknur": {
        "username": "ilknur",
        "name": "İlknur Hocam",
        "role": "Öğretmen / Akademik Kullanıcı",
        "password": "1111",
        "personality": "teacher"
    }
}


# ============================================================
# AKADEMİK MODLAR
# ============================================================

ACADEMIC_MODES = {
    "research": {
        "name": "🔬 Araştırma Modu",
        "description": "Kaynak ve güncel bilgi odaklı araştırma."
    },

    "academic": {
        "name": "📚 Akademik Mod",
        "description": "Akademik ve bilimsel anlatım."
    },

    "article": {
        "name": "📝 Makale Asistanı",
        "description": "Makale oluşturma ve düzenleme."
    },

    "lesson": {
        "name": "🎓 Ders Asistanı",
        "description": "Ders anlatımı ve öğrenci desteği."
    },

    "quiz": {
        "name": "🧪 Sınav / Quiz",
        "description": "Soru ve sınav hazırlama."
    },

    "presentation": {
        "name": "📊 Sunum Hazırlama",
        "description": "Profesyonel PDF sunumu hazırlama."
    }
}


# ============================================================
# PDF FONT SİSTEMİ
# ============================================================

REGULAR_FONT = "Helvetica"
BOLD_FONT = "Helvetica-Bold"

REGULAR_FONT_FILE = FONT_DIR / "DejaVuSans.ttf"
BOLD_FONT_FILE = FONT_DIR / "DejaVuSans-Bold.ttf"


def setup_pdf_fonts():

    global REGULAR_FONT
    global BOLD_FONT

    print("")
    print("======================================")
    print("PDF FONT SİSTEMİ BAŞLATILIYOR")
    print("======================================")

    print(
        "Normal font:",
        REGULAR_FONT_FILE
    )

    print(
        "Bold font:",
        BOLD_FONT_FILE
    )

    if not REGULAR_FONT_FILE.exists():

        print(
            "HATA: DejaVuSans.ttf bulunamadı."
        )

        return False

    if not BOLD_FONT_FILE.exists():

        print(
            "HATA: DejaVuSans-Bold.ttf bulunamadı."
        )

        return False

    try:

        pdfmetrics.registerFont(
            TTFont(
                "KarahanDejaVu",
                str(REGULAR_FONT_FILE)
            )
        )

        pdfmetrics.registerFont(
            TTFont(
                "KarahanDejaVuBold",
                str(BOLD_FONT_FILE)
            )
        )

        REGULAR_FONT = "KarahanDejaVu"
        BOLD_FONT = "KarahanDejaVuBold"

        print("======================================")
        print("TÜRKÇE PDF FONTU: AKTİF")
        print("DejaVu Sans başarıyla yüklendi.")
        print("Ç Ğ İ Ö Ş Ü ç ğ ı ö ş ü")
        print("======================================")
        print("")

        return True

    except Exception as error:

        print("======================================")
        print("UYARI: Türkçe PDF fontu yüklenemedi.")
        print("HATA:", error)
        print("======================================")
        print("")

        return False


setup_pdf_fonts()


# ============================================================
# JSON / MEMORY
# ============================================================

def load_json_file(path, default):

    try:

        if not path.exists():
            return default

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    except Exception:

        return default


def save_json_file(path, data):

    try:

        with open(
            path,
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
            "JSON kayıt hatası:",
            error
        )


MEMORY = load_json_file(
    MEMORY_FILE,
    {}
)

ERRORS = load_json_file(
    ERROR_FILE,
    []
)


# ============================================================
# HATA KAYDI
# ============================================================

def log_error(error, endpoint="unknown"):

    try:

        ERRORS.append({
            "time": datetime.now().isoformat(),
            "endpoint": endpoint,
            "error": str(error)
        })

        save_json_file(
            ERROR_FILE,
            ERRORS[-200:]
        )

    except Exception:
        pass


# ============================================================
# AI CLIENT
# ============================================================

groq_client = None
openrouter_client = None


if GROQ_API_KEY:

    try:

        groq_client = OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )

        print("Groq client: AKTİF")

    except Exception as error:

        print(
            "Groq client hatası:",
            error
        )


if OPENROUTER_API_KEY:

    try:

        openrouter_client = OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        )

        print("OpenRouter client: AKTİF")

    except Exception as error:

        print(
            "OpenRouter client hatası:",
            error
        )


# ============================================================
# AI MODELLERİ
# ============================================================

GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b"
]

OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openai/gpt-oss-20b:free"
)


# ============================================================
# REQUEST MODELLERİ
# ============================================================

class LoginRequest(BaseModel):

    username: str
    password: str = ""


class ChatRequest(BaseModel):

    message: str
    username: str = "karahan"
    mode: str = "normal"
    history: list = []


class ResearchRequest(BaseModel):

    topic: str
    username: str = "karahan"


class PresentationRequest(BaseModel):

    topic: str
    username: str = "ilknur"
    mode: str = "presentation"


# ============================================================
# KULLANICI MODU
# ============================================================

def get_user(username):

    username = str(
        username or "karahan"
    ).strip().lower()

    return USERS.get(
        username,
        USERS["karahan"]
    )


def get_user_mode(
    username,
    requested_mode="normal"
):

    username = str(
        username or "karahan"
    ).strip().lower()

    if username == "ilknur":

        if not requested_mode:
            return "lesson"

        if requested_mode == "normal":
            return "lesson"

    return requested_mode or "normal"


# ============================================================
# SYSTEM PROMPT
# ============================================================

def build_system_prompt(
    username="karahan",
    mode="normal"
):

    user = get_user(username)

    personality = user.get(
        "personality",
        "professional"
    )

    mode = get_user_mode(
        username,
        mode
    )

    prompt = """
Sen K.A.R.V.I.S. - KARAHAN INC. isimli
gelişmiş kişisel yapay zeka asistanısın.

Yanıtlarını Türkçe ver.

Doğal, akıcı ve profesyonel konuş.

Gereksiz yere kendini tekrar etme.

Kullanıcı kısa soru sorarsa gereksiz
uzun cevap verme.

Kullanıcı detay isterse ayrıntılı anlat.

Bilmediğin bilgiyi kesinmiş gibi uydurma.

Teknik konularda uygulanabilir ve
doğrudan çözüm üret.

Kod istendiğinde çalışabilir kod üret.

Türkçe karakterleri doğru kullan.

Kullanıcıya her mesajda Murat diye
hitap etme.

Kendini ChatGPT olarak tanıtma.

Sen K.A.R.V.I.S.'sin.
"""

    if personality == "professional":

        prompt += """
Ana kullanıcı için profesyonel,
doğrudan ve yardımcı ol.
"""

    elif personality == "betul":

        prompt += """
Betül ile konuşurken samimi,
nazik ve sıcak bir dil kullan.
"""

    elif personality == "sinem":

        prompt += """
Sinem ile konuşurken samimi
ve doğal bir dil kullan.
"""

    elif personality == "teacher":

        prompt += """
Kullanıcı İlknur Hocamdır.

Akademik, öğretici ve düzenli
bir dil kullan.

Ders anlatırken konuyu öğrencinin
anlayabileceği şekilde yapılandır.

Gerektiğinde örnekler ver.

Akademik doğruluğa dikkat et.
"""

    if mode == "research":

        prompt += """
ARAŞTIRMA MODU:

Konuyu sistematik şekilde incele.

Önemli bilgileri ayır.

Kesin bilgi ile yorumu birbirinden
ayır.

Güncel bilgi gerekiyorsa araştırma
yapılması gerektiğini belirt.
"""

    elif mode == "academic":

        prompt += """
AKADEMİK MOD:

Bilimsel ve akademik bir yaklaşım kullan.

Kavramları tanımla.

Neden-sonuç ilişkilerini açıkla.

Gerekirse kaynak öner.
"""

    elif mode == "article":

        prompt += """
MAKALE ASİSTANI:

Akademik makale düzenine uygun yaz.

Giriş, gelişme, sonuç ve kaynak
önerilerini gerektiğinde kullan.
"""

    elif mode == "lesson":

        prompt += """
DERS ASİSTANI:

Konuyu öğretmen anlatımı şeklinde düzenle.

Öğrencinin anlayabileceği açıklamalar yap.

Örnekler kullan.

Önemli kavramları belirginleştir.

Dersin sonunda kısa bir değerlendirme
veya soru önerilebilir.
"""

    elif mode == "quiz":

        prompt += """
SINAV / QUIZ MODU:

Soruları açık ve ölçülebilir hazırla.

Gerektiğinde cevap anahtarı oluştur.

Soruları kolay, orta ve zor seviyelere
ayırabilirsin.
"""

    elif mode == "presentation":

        prompt += """
SUNUM HAZIRLAMA MODU:

Profesyonel eğitim sunumu mantığıyla
içerik oluştur.

Başlıkları kısa tut.

Açıklamaları kapsamlı tut.

Görsel önerilerini konuya uygun seç.

Bilgi yoğunluğunu dengeli tut.
"""

    return prompt


# ============================================================
# AI SOR
# ============================================================

def ask_ai(
    message,
    username="karahan",
    mode="normal",
    history=None
):

    history = history or []

    mode = get_user_mode(
        username,
        mode
    )

    system_prompt = build_system_prompt(
        username,
        mode
    )

    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]

    for item in history[-12:]:

        if not isinstance(item, dict):
            continue

        role = item.get(
            "role"
        )

        content = item.get(
            "content"
        )

        if role in [
            "user",
            "assistant"
        ] and content:

            messages.append({
                "role": role,
                "content": str(content)
            })

    messages.append({
        "role": "user",
        "content": str(message)
    })

    if groq_client:

        for model in GROQ_MODELS:

            try:

                response = (
                    groq_client
                    .chat
                    .completions
                    .create(
                        model=model,
                        messages=messages,
                        temperature=0.7,
                        max_tokens=3500
                    )
                )

                answer = (
                    response
                    .choices[0]
                    .message
                    .content
                )

                if answer:

                    print(
                        "AI sağlayıcısı: Groq",
                        model
                    )

                    return answer.strip()

            except Exception as error:

                print(
                    "Groq model hatası:",
                    model,
                    error
                )

                log_error(
                    error,
                    "groq"
                )

    if openrouter_client:

        try:

            response = (
                openrouter_client
                .chat
                .completions
                .create(
                    model=OPENROUTER_MODEL,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=3500,
                    extra_headers={
                        "HTTP-Referer":
                            "https://karahan-inc.com",
                        "X-Title":
                            "K.A.R.V.I.S. - KARAHAN INC."
                    }
                )
            )

            answer = (
                response
                .choices[0]
                .message
                .content
            )

            if answer:

                print(
                    "AI sağlayıcısı: OpenRouter"
                )

                return answer.strip()

        except Exception as error:

            print(
                "OpenRouter hatası:",
                error
            )

            log_error(
                error,
                "openrouter"
            )

    return (
        "Efendim, şu anda yapay zeka "
        "servislerine bağlanamıyorum. "
        "Lütfen Render üzerindeki API "
        "anahtarlarını kontrol edin."
    )


# ============================================================
# İNTERNET ARAMA
# ============================================================

def internet_search(
    query,
    limit=8
):

    try:

        url = (
            "https://html.duckduckgo.com/html/"
        )

        response = requests.post(
            url,
            data={
                "q": str(query)
            },
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "KARVIS-KARAHAN-INC"
            },
            timeout=15
        )

        if response.status_code != 200:

            return []

        html = response.text

        results = []

        pattern = re.compile(
            r'class="result__a"[^>]*'
            r'href="([^"]+)"[^>]*>'
            r'(.*?)</a>',
            re.S
        )

        for match in pattern.finditer(
            html
        ):

            link = match.group(1)

            title = re.sub(
                r"<.*?>",
                "",
                match.group(2)
            )

            title = title.strip()

            if title and link:

                results.append({
                    "title": title,
                    "url": link
                })

            if len(results) >= limit:

                break

        return results

    except Exception as error:

        log_error(
            error,
            "internet_search"
        )

        return []


# ============================================================
# ARAŞTIRMA
# ============================================================

def research_topic(topic):

    results = internet_search(
        topic,
        limit=8
    )

    if not results:

        return {
            "success": False,
            "message": (
                "Araştırma sonucu bulunamadı."
            ),
            "results": []
        }

    return {
        "success": True,
        "results": results
    }


# ============================================================
# SUNUM OUTLINE
# ============================================================

def generate_presentation_outline(
    topic
):

    prompt = f"""
Aşağıdaki konu için profesyonel,
eğitim amaçlı ve akademik bir sunum hazırla:

KONU:

{topic}

SADECE GEÇERLİ JSON DÖNDÜR.

Şu yapıyı kullan:

{{
  "title": "Sunum başlığı",
  "subtitle": "Kısa açıklama",
  "slides": [
    {{
      "title": "Kısa başlık",
      "paragraph": "Uzun açıklayıcı paragraf",
      "bullets": [
        "Önemli nokta 1",
        "Önemli nokta 2",
        "Önemli nokta 3"
      ],
      "note": "Öğretmen notu",
      "visual_query": "English visual search query"
    }}
  ]
}}

6 ile 8 arasında slayt oluştur.

HER SLAYTTA MUTLAKA ŞUNLAR OLSUN:

title
paragraph
bullets
note
visual_query

BAŞLIK:

2-6 kelime arasında kısa bir başlık olsun.

PARAGRAPH:

Yaklaşık 80-130 kelimelik açıklayıcı
ve öğretici bir metin oluştur.

Paragraf sadece maddeleri tekrar etmesin.

Konunun neden önemli olduğunu,
temel özelliklerini ve gerekiyorsa
neden-sonuç ilişkilerini açıklasın.

BULLETS:

3 veya 4 önemli madde oluştur.

NOTE:

Öğretmenin sınıfta kullanabileceği
faydalı bir anlatım notu oluştur.

Çok uzun olmasın.

VISUAL_QUERY:

İngilizce yaz.

Gerçek fotoğraf, harita, bilimsel
diyagram, tarihi fotoğraf veya konuya
uygun görsel bulunabilecek şekilde
hazırla.

Örnekler:

"solar system planets NASA"

"human heart anatomy diagram"

"Turkey physical geography map"

"Turkish War of Independence historical photograph"

"industrial revolution factory historical photograph"

Bilgi uydurma.

Türkçe karakterleri doğru kullan.

SADECE JSON DÖNDÜR.
"""

    result = ask_ai(
        prompt,
        username="karahan",
        mode="presentation"
    )

    try:

        result = result.strip()

        result = re.sub(
            r"^```json",
            "",
            result,
            flags=re.I
        )

        result = re.sub(
            r"^```",
            "",
            result
        )

        result = re.sub(
            r"```$",
            "",
            result
        )

        data = json.loads(
            result.strip()
        )

        if (
            isinstance(data, dict)
            and "slides" in data
        ):

            return data

    except Exception as error:

        print(
            "Sunum JSON hatası:",
            error
        )

        log_error(
            error,
            "presentation_json"
        )

    return {
        "title": topic,

        "subtitle": (
            "K.A.R.V.I.S. tarafından "
            "hazırlanan eğitim sunumu"
        ),

        "slides": [
            {
                "title": "Giriş",

                "paragraph": (
                    f"{topic} konusu, temel "
                    "kavramları ve genel yapısı "
                    "açısından önemli bir konudur. "
                    "Bu sunumda konunun temel "
                    "özellikleri, önemi ve genel "
                    "çerçevesi ele alınacaktır. "
                    "Konuya ilişkin temel bilgilerin "
                    "öğrenilmesi, daha ayrıntılı "
                    "konuların anlaşılmasını "
                    "kolaylaştıracaktır."
                ),

                "bullets": [
                    "Temel kavramlar",
                    "Konunun önemi",
                    "Genel bakış"
                ],

                "note": (
                    "Derse giriş yaparken öğrencilerin "
                    "konu hakkındaki mevcut bilgilerini "
                    "kısaca öğreniniz."
                ),

                "visual_query": topic
            },

            {
                "title": "Temel Bilgiler",

                "paragraph": (
                    f"{topic} hakkında temel "
                    "bilgilerin öğrenilmesi, "
                    "konunun daha ayrıntılı "
                    "şekilde anlaşılmasını sağlar. "
                    "Temel kavramlar arasındaki "
                    "ilişkilerin incelenmesi, "
                    "konunun bütünsel olarak "
                    "değerlendirilmesine yardımcı olur. "
                    "Bu nedenle temel özelliklerin "
                    "sistematik biçimde ele alınması "
                    "önemlidir."
                ),

                "bullets": [
                    "Temel özellikler",
                    "Önemli kavramlar",
                    "Neden-sonuç ilişkileri"
                ],

                "note": (
                    "Önemli kavramları açıklarken "
                    "öğrencilerden günlük hayattan "
                    "örnekler vermelerini isteyiniz."
                ),

                "visual_query": topic
            },

            {
                "title": "Sonuç",

                "paragraph": (
                    f"{topic} konusunda öğrenilen "
                    "bilgiler birlikte değerlendirildiğinde, "
                    "konunun farklı unsurları arasında "
                    "bir bağlantı bulunduğu görülmektedir. "
                    "Temel bilgilerin tekrar edilmesi "
                    "ve önemli noktaların değerlendirilmesi, "
                    "öğrenilen bilgilerin daha kalıcı "
                    "hale gelmesine yardımcı olacaktır."
                ),

                "bullets": [
                    "Temel çıkarımlar",
                    "Konunun önemi",
                    "Genel değerlendirme"
                ],

                "note": (
                    "Ders sonunda öğrencilerden konuyu "
                    "kendi cümleleriyle özetlemelerini "
                    "isteyiniz."
                ),

                "visual_query": topic
            }
        ]
    }


# ============================================================
# GELİŞMİŞ GÖRSEL HTTP OTURUMU
# ============================================================

IMAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),

    "Accept": (
        "image/avif,image/webp,image/apng,"
        "image/svg+xml,image/jpeg,image/png,"
        "image/*,*/*;q=0.8"
    ),

    "Accept-Language": (
        "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
    ),

    "Connection": "keep-alive"
}


def create_image_session():

    session = requests.Session()

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.7,

        status_forcelist=[
            429,
            500,
            502,
            503,
            504
        ],

        allowed_methods=[
            "GET",
            "HEAD"
        ],

        raise_on_status=False
    )

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=10,
        pool_maxsize=20
    )

    session.mount(
        "http://",
        adapter
    )

    session.mount(
        "https://",
        adapter
    )

    session.headers.update(
        IMAGE_HEADERS
    )

    return session


IMAGE_SESSION = create_image_session()


# ============================================================
# GÖRSEL HEADER
# ============================================================

def get_image_headers(url):

    headers = dict(
        IMAGE_HEADERS
    )

    url_lower = str(
        url or ""
    ).lower()

    if "wikimedia.org" in url_lower:

        headers["Referer"] = (
            "https://commons.wikimedia.org/"
        )

    elif "wikipedia.org" in url_lower:

        headers["Referer"] = (
            "https://tr.wikipedia.org/"
        )

    elif "openverse.org" in url_lower:

        headers["Referer"] = (
            "https://openverse.org/"
        )

    elif "duckduckgo.com" in url_lower:

        headers["Referer"] = (
            "https://duckduckgo.com/"
        )

    return headers


# ============================================================
# URL TEMİZLEME
# ============================================================

def normalize_image_url(url):

    if not url:
        return None

    url = str(
        url
    ).strip()

    if not url:
        return None

    if url.startswith(
        "//"
    ):

        url = (
            "https:"
            + url
        )

    if not url.startswith(
        ("http://", "https://")
    ):

        return None

    return url


# ============================================================
# GÖRSELİ PİL İLE NORMALLEŞTİR
# ============================================================

def normalize_pil_image(image):

    from PIL import Image
    from PIL import ImageOps

    try:

        image = ImageOps.exif_transpose(
            image
        )

    except Exception:

        pass

    try:

        if getattr(
            image,
            "is_animated",
            False
        ):

            image.seek(0)

    except Exception:

        pass

    image.load()

    width, height = image.size

    if (
        width < 250
        or height < 150
    ):

        raise ValueError(
            f"Görsel çözünürlüğü düşük: "
            f"{width}x{height}"
        )

    # RGBA / LA / transparency
    if (
        image.mode in (
            "RGBA",
            "LA"
        )
        or "transparency" in image.info
    ):

        rgba = image.convert(
            "RGBA"
        )

        background = Image.new(
            "RGBA",
            rgba.size,
            "white"
        )

        background.alpha_composite(
            rgba
        )

        return background.convert(
            "RGB"
        )

    if image.mode != "RGB":

        return image.convert(
            "RGB"
        )

    return image


# ============================================================
# GÖRSEL İNDİRME
# ============================================================

def download_image(
    url,
    filename=None,
    retries=3
):

    url = normalize_image_url(
        url
    )

    if not url:

        print(
            "✗ Geçersiz görsel URL."
        )

        return None

    print("")
    print(
        "--------------------------------------"
    )
    print(
        "GÖRSEL İNDİRİLİYOR"
    )
    print(
        url
    )
    print(
        "--------------------------------------"
    )

    last_error = None

    max_bytes = (
        20 * 1024 * 1024
    )

    for attempt in range(
        1,
        retries + 1
    ):

        response = None

        try:

            print(
                f"Görsel deneme: "
                f"{attempt}/{retries}"
            )

            response = IMAGE_SESSION.get(
                url,
                headers=get_image_headers(
                    url
                ),
                timeout=(10, 35),
                allow_redirects=True,
                stream=True
            )

            print(
                "HTTP:",
                response.status_code
            )

            final_url = str(
                response.url
                or url
            )

            print(
                "Son URL:",
                final_url
            )

            if response.status_code != 200:

                print(
                    "✗ HTTP başarılı değil."
                )

                response.close()

                if attempt < retries:

                    time.sleep(
                        0.5 * attempt
                    )

                continue

            content_type = (
                response.headers
                .get(
                    "Content-Type",
                    ""
                )
                .lower()
            )

            print(
                "Content-Type:",
                content_type
            )

            content_length = (
                response.headers
                .get(
                    "Content-Length",
                    ""
                )
            )

            if content_length:

                try:

                    declared_size = int(
                        content_length
                    )

                    if declared_size > max_bytes:

                        print(
                            "✗ Görsel çok büyük."
                        )

                        response.close()

                        continue

                except Exception:

                    pass

            # ------------------------------------------------
            # VERİYİ PARÇA PARÇA AL
            # ------------------------------------------------

            chunks = []
            total_size = 0

            for chunk in response.iter_content(
                chunk_size=64 * 1024
            ):

                if not chunk:
                    continue

                total_size += len(
                    chunk
                )

                if total_size > max_bytes:

                    print(
                        "✗ Görsel 20 MB sınırını aştı."
                    )

                    chunks = []

                    break

                chunks.append(
                    chunk
                )

            content = b"".join(
                chunks
            )

            response.close()

            if not content:

                print(
                    "✗ Boş içerik."
                )

                continue

            if len(content) < 500:

                print(
                    "✗ İçerik çok küçük."
                )

                continue

            # ------------------------------------------------
            # CONTENT TYPE HTML İSE
            # ------------------------------------------------

            if (
                "text/html"
                in content_type
                or "application/json"
                in content_type
            ):

                print(
                    "✗ Sunucu görsel yerine "
                    "HTML/JSON gönderdi."
                )

                continue

            # ------------------------------------------------
            # PIL GERÇEK GÖRSEL KONTROLÜ
            # ------------------------------------------------

            try:

                from PIL import Image

                with Image.open(
                    BytesIO(content)
                ) as check_image:

                    print(
                        "Görsel formatı:",
                        check_image.format
                    )

                    print(
                        "Görsel boyutu:",
                        check_image.size
                    )

                    # Bozuk dosya kontrolü
                    check_image.verify()

                # verify sonrasında tekrar açılır.
                with Image.open(
                    BytesIO(content)
                ) as opened_image:

                    normalized_image = (
                        normalize_pil_image(
                            opened_image
                        )
                    )

            except Exception as error:

                print(
                    "✗ PIL görsel doğrulaması başarısız:"
                )

                print(
                    error
                )

                last_error = error

                continue

            # ------------------------------------------------
            # DOSYA ADI
            # ------------------------------------------------

            if filename:

                safe_filename = os.path.basename(
                    str(filename)
                )

                if not safe_filename.lower().endswith(
                    ".jpg"
                ):

                    safe_filename += ".jpg"

                destination = (
                    FILES_DIR
                    / safe_filename
                )

            else:

                destination = (
                    FILES_DIR
                    / (
                        "visual_"
                        + uuid.uuid4().hex
                        + ".jpg"
                    )
                )

            # ------------------------------------------------
            # JPEG KAYDET
            # ------------------------------------------------

            try:

                normalized_image.save(
                    destination,
                    "JPEG",
                    quality=92,
                    optimize=True,
                    progressive=True
                )

            except Exception as error:

                print(
                    "✗ JPEG kayıt hatası:",
                    error
                )

                last_error = error

                try:

                    if destination.exists():
                        destination.unlink()

                except Exception:
                    pass

                continue

            # ------------------------------------------------
            # DOSYA KONTROL
            # ------------------------------------------------

            if not destination.exists():

                print(
                    "✗ Dosya oluşmadı."
                )

                continue

            file_size = (
                destination.stat().st_size
            )

            if file_size < 1000:

                print(
                    "✗ Kaydedilen JPEG geçersiz."
                )

                try:

                    destination.unlink()

                except Exception:
                    pass

                continue

            print(
                "✓ GÖRSEL BAŞARIYLA KAYDEDİLDİ"
            )

            print(
                "Dosya:",
                destination
            )

            print(
                "Boyut:",
                file_size,
                "byte"
            )

            return destination

        except requests.exceptions.Timeout as error:

            print(
                "✗ Görsel zaman aşımı."
            )

            last_error = error

        except requests.exceptions.RequestException as error:

            print(
                "✗ Görsel bağlantı hatası:"
            )

            print(
                error
            )

            last_error = error

        except Exception as error:

            print(
                "✗ Görsel indirme hatası:"
            )

            print(
                error
            )

            last_error = error

        finally:

            try:

                if response is not None:
                    response.close()

            except Exception:
                pass

        if attempt < retries:

            time.sleep(
                0.7 * attempt
            )

    if last_error:

        print(
            "Son görsel hatası:",
            last_error
        )

    print(
        "✗ Bu URL kullanılamadı."
    )

    return None


# ============================================================
# WIKIMEDIA
# ============================================================

def download_wikimedia_visual(
    query
):

    try:

        if not query:
            return None

        print(
            "Wikimedia araması:",
            query
        )

        api_url = (
            "https://commons.wikimedia.org/"
            "w/api.php"
        )

        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": str(query),
            "gsrnamespace": 6,
            "gsrlimit": 25,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "iiurlwidth": 1800,
            "format": "json"
        }

        response = IMAGE_SESSION.get(
            api_url,
            params=params,
            headers={
                "User-Agent":
                    "KARVIS-KARAHAN-INC/26.2",
                "Accept":
                    "application/json"
            },
            timeout=20
        )

        print(
            "Wikimedia HTTP:",
            response.status_code
        )

        if response.status_code != 200:

            return None

        data = response.json()

        pages = (
            data
            .get("query", {})
            .get("pages", {})
        )

        page_items = list(
            pages.values()
        )

        print(
            "Wikimedia sonuç sayısı:",
            len(page_items)
        )

        tried_urls = set()

        for page in page_items:

            imageinfo = page.get(
                "imageinfo",
                []
            )

            if not imageinfo:
                continue

            info = imageinfo[0]

            mime = str(
                info.get(
                    "mime",
                    ""
                )
            ).lower()

            if not mime.startswith(
                "image/"
            ):

                continue

            # SVG / ikon / uygunsuz formatları
            # mümkün olduğunca ele.
            if mime in (
                "image/svg+xml",
                "image/x-icon"
            ):

                continue

            candidate_urls = [
                info.get("thumburl"),
                info.get("url")
            ]

            for image_url in candidate_urls:

                image_url = normalize_image_url(
                    image_url
                )

                if not image_url:
                    continue

                if image_url in tried_urls:
                    continue

                tried_urls.add(
                    image_url
                )

                filename = (
                    "visual_"
                    + uuid.uuid4().hex
                    + ".jpg"
                )

                image = download_image(
                    image_url,
                    filename,
                    retries=3
                )

                if image:

                    print(
                        "✓ WIKIMEDIA GÖRSELİ HAZIR"
                    )

                    return image

                print(
                    "Wikimedia URL başarısız."
                )

    except Exception as error:

        print(
            "Wikimedia hatası:",
            error
        )

        log_error(
            error,
            "wikimedia_visual"
        )

    return None


# ============================================================
# DUCKDUCKGO GÖRSEL ARAMA
# ============================================================

def get_duckduckgo_vqd(
    query
):

    try:

        homepage_url = (
            "https://duckduckgo.com/"
        )

        response = IMAGE_SESSION.get(
            homepage_url,
            params={
                "q": str(query),
                "iar": "images",
                "iax": "images",
                "ia": "images"
            },
            headers={
                **IMAGE_HEADERS,
                "Referer":
                    "https://duckduckgo.com/"
            },
            timeout=20
        )

        if response.status_code != 200:

            print(
                "DuckDuckGo ana sayfa HTTP:",
                response.status_code
            )

            return None

        html = response.text

        patterns = [
            r'vqd=["\']([^"\']+)["\']',
            r'vqd\s*=\s*["\']([^"\']+)["\']',
            r'vqd["\']?\s*:\s*["\']([^"\']+)["\']'
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                html,
                re.I
            )

            if match:

                token = match.group(1)

                if token:

                    return token

    except Exception as error:

        print(
            "DuckDuckGo VQD hatası:",
            error
        )

        log_error(
            error,
            "duckduckgo_vqd"
        )

    return None


def download_duckduckgo_visual(
    query
):

    try:

        if not query:
            return None

        print(
            "DuckDuckGo görsel araması:",
            query
        )

        vqd = get_duckduckgo_vqd(
            query
        )

        if not vqd:

            print(
                "✗ DuckDuckGo VQD bulunamadı."
            )

            return None

        api_url = (
            "https://duckduckgo.com/i.js"
        )

        params = {
            "q": str(query),
            "o": "json",
            "l": "us-en",
            "vqd": vqd,
            "f": ",,,,,",
            "p": "1"
        }

        response = IMAGE_SESSION.get(
            api_url,
            params=params,
            headers={
                **IMAGE_HEADERS,
                "Accept":
                    "application/json",
                "Referer":
                    "https://duckduckgo.com/"
            },
            timeout=20
        )

        print(
            "DuckDuckGo görsel HTTP:",
            response.status_code
        )

        if response.status_code != 200:

            return None

        data = response.json()

        results = data.get(
            "results",
            []
        )

        print(
            "DuckDuckGo görsel sonucu:",
            len(results)
        )

        tried_urls = set()

        # En fazla ilk 15 sonucu deniyoruz.
        for item in results[:15]:

            candidate_urls = [
                item.get("image"),
                item.get("thumbnail"),
                item.get("url")
            ]

            for image_url in candidate_urls:

                image_url = normalize_image_url(
                    image_url
                )

                if not image_url:
                    continue

                if image_url in tried_urls:
                    continue

                tried_urls.add(
                    image_url
                )

                filename = (
                    "visual_"
                    + uuid.uuid4().hex
                    + ".jpg"
                )

                image = download_image(
                    image_url,
                    filename,
                    retries=3
                )

                if image:

                    print(
                        "✓ DUCKDUCKGO GÖRSELİ HAZIR"
                    )

                    return image

        print(
            "✗ DuckDuckGo uygun görsel bulamadı."
        )

    except Exception as error:

        print(
            "DuckDuckGo görsel hatası:",
            error
        )

        log_error(
            error,
            "duckduckgo_visual"
        )

    return None


# ============================================================
# WIKIPEDIA
# ============================================================

def download_wikipedia_visual(
    query
):

    try:

        if not query:
            return None

        print(
            "Wikipedia araması:",
            query
        )

        api_url = (
            "https://tr.wikipedia.org/"
            "w/api.php"
        )

        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": str(query),
            "gsrnamespace": 0,
            "gsrlimit": 20,
            "prop": "pageimages",
            "piprop": "original|thumbnail",
            "pithumbsize": 1800,
            "format": "json"
        }

        response = IMAGE_SESSION.get(
            api_url,
            params=params,
            headers={
                "User-Agent":
                    "KARVIS-KARAHAN-INC/26.2",
                "Accept":
                    "application/json"
            },
            timeout=20
        )

        print(
            "Wikipedia HTTP:",
            response.status_code
        )

        if response.status_code != 200:

            return None

        data = response.json()

        pages = (
            data
            .get("query", {})
            .get("pages", {})
        )

        tried_urls = set()

        for page in pages.values():

            candidates = []

            original = page.get(
                "original"
            )

            thumbnail = page.get(
                "thumbnail"
            )

            if original:

                candidates.append(
                    original.get(
                        "source"
                    )
                )

            if thumbnail:

                candidates.append(
                    thumbnail.get(
                        "source"
                    )
                )

            for image_url in candidates:

                image_url = normalize_image_url(
                    image_url
                )

                if not image_url:
                    continue

                if image_url in tried_urls:
                    continue

                tried_urls.add(
                    image_url
                )

                filename = (
                    "visual_"
                    + uuid.uuid4().hex
                    + ".jpg"
                )

                image = download_image(
                    image_url,
                    filename,
                    retries=3
                )

                if image:

                    print(
                        "✓ WIKIPEDIA GÖRSELİ HAZIR"
                    )

                    return image

                print(
                    "Wikipedia URL başarısız."
                )

    except Exception as error:

        print(
            "Wikipedia görsel hatası:",
            error
        )

        log_error(
            error,
            "wikipedia_visual"
        )

    return None


# ============================================================
# OPENVERSE
# ============================================================

def download_openverse_visual(
    query
):

    try:

        if not query:
            return None

        print(
            "Openverse araması:",
            query
        )

        url = (
            "https://api.openverse.org/"
            "v1/images/"
        )

        response = IMAGE_SESSION.get(
            url,
            params={
                "q": str(query),
                "page_size": 30,
                "mature": "false"
            },
            headers={
                "User-Agent":
                    "KARVIS-KARAHAN-INC/26.2",
                "Accept":
                    "application/json"
            },
            timeout=20
        )

        print(
            "Openverse HTTP:",
            response.status_code
        )

        if response.status_code != 200:

            return None

        data = response.json()

        results = data.get(
            "results",
            []
        )

        print(
            "Openverse sonuç sayısı:",
            len(results)
        )

        tried_urls = set()

        for item in results:

            candidate_urls = [
                item.get("thumbnail"),
                item.get("image"),
                item.get("url")
            ]

            for image_url in candidate_urls:

                image_url = normalize_image_url(
                    image_url
                )

                if not image_url:
                    continue

                if image_url in tried_urls:
                    continue

                tried_urls.add(
                    image_url
                )

                filename = (
                    "visual_"
                    + uuid.uuid4().hex
                    + ".jpg"
                )

                image = download_image(
                    image_url,
                    filename,
                    retries=3
                )

                if image:

                    print(
                        "✓ OPENVERSE GÖRSELİ HAZIR"
                    )

                    return image

                print(
                    "Openverse URL başarısız."
                )

    except Exception as error:

        print(
            "Openverse hatası:",
            error
        )

        log_error(
            error,
            "openverse_visual"
        )

    return None


# ============================================================
# GÖRSEL SORGULARI
# ============================================================

def build_visual_queries(
    query
):

    query = str(
        query or ""
    ).strip()

    if not query:
        return []

    queries = []

    def add_query(value):

        value = str(
            value or ""
        ).strip()

        if (
            value
            and value not in queries
        ):

            queries.append(
                value
            )

    add_query(
        query
    )

    cleaned = re.sub(
        r"[^\w\sçğıöşüÇĞİÖŞÜ-]",
        " ",
        query,
        flags=re.UNICODE
    )

    cleaned = re.sub(
        r"\s+",
        " ",
        cleaned
    ).strip()

    add_query(
        cleaned
    )

    # Eğer AI zaten İngilizce query verdiyse
    # sorguyu gereksiz yere bozma.
    lower_cleaned = cleaned.lower()

    visual_words = [
        "photo",
        "photograph",
        "diagram",
        "map",
        "historical",
        "anatomy",
        "illustration",
        "educational"
    ]

    has_visual_word = any(
        word in lower_cleaned
        for word in visual_words
    )

    if has_visual_word:

        add_query(
            cleaned
        )

    else:

        add_query(
            cleaned + " photograph"
        )

        add_query(
            cleaned + " photo"
        )

        add_query(
            cleaned + " diagram"
        )

        add_query(
            cleaned + " map"
        )

        add_query(
            cleaned + " historical photograph"
        )

        add_query(
            cleaned + " educational"
        )

    return queries[:7]


# ============================================================
# ANA GÖRSEL SİSTEMİ
# ============================================================

def get_slide_image(
    query
):

    if not query:

        return None

    print("")
    print("======================================")
    print("GÖRSEL ARAMA BAŞLADI")
    print(
        "Sorgu:",
        query
    )
    print("======================================")

    queries = build_visual_queries(
        query
    )

    if not queries:

        print(
            "✗ Görsel sorgusu oluşturulamadı."
        )

        return None

    # Aynı URL'yi farklı kaynaklardan
    # tekrar tekrar denememek için.
    attempted_urls = set()

    # ========================================================
    # HER SORGUDA TÜM KAYNAKLAR
    # ========================================================
    #
    # Eski sistem:
    #
    # 7 sorgu x Wikimedia
    # sonra 7 sorgu x Wikipedia
    # sonra 7 sorgu x Openverse
    #
    # Yeni sistem:
    #
    # 1 sorgu -> Wikimedia
    # 1 sorgu -> DuckDuckGo
    # 1 sorgu -> Wikipedia
    # 1 sorgu -> Openverse
    # sonra diğer sorguya geç.
    #
    # Böylece uygun görsel çok daha erken bulunur.
    # ========================================================

    for search_query in queries:

        print("")
        print(
            "######################################"
        )

        print(
            "GÖRSEL SORGU:",
            search_query
        )

        print(
            "######################################"
        )

        # ----------------------------------------------------
        # WIKIMEDIA
        # ----------------------------------------------------

        print(
            "Kaynak 1/4: Wikimedia"
        )

        image = download_wikimedia_visual(
            search_query
        )

        if image:

            print(
                "✓ KAYNAK: WIKIMEDIA"
            )

            return image

        # ----------------------------------------------------
        # DUCKDUCKGO
        # ----------------------------------------------------

        print(
            "Kaynak 2/4: DuckDuckGo"
        )

        image = download_duckduckgo_visual(
            search_query
        )

        if image:

            print(
                "✓ KAYNAK: DUCKDUCKGO"
            )

            return image

        # ----------------------------------------------------
        # WIKIPEDIA
        # ----------------------------------------------------

        print(
            "Kaynak 3/4: Wikipedia"
        )

        image = download_wikipedia_visual(
            search_query
        )

        if image:

            print(
                "✓ KAYNAK: WIKIPEDIA"
            )

            return image

        # ----------------------------------------------------
        # OPENVERSE
        # ----------------------------------------------------

        print(
            "Kaynak 4/4: Openverse"
        )

        image = download_openverse_visual(
            search_query
        )

        if image:

            print(
                "✓ KAYNAK: OPENVERSE"
            )

            return image

        print(
            "Bu sorgudan uygun görsel çıkmadı."
        )

    # ========================================================
    # SON ÇARE
    # ========================================================

    print("")
    print(
        "✗ TÜM GÖRSEL KAYNAKLARI DENENDİ."
    )
    print(
        "✗ UYGUN GÖRSEL BULUNAMADI."
    )
    print("")

    return None


# ============================================================
# PDF METİN SARMA
# ============================================================

def draw_wrapped_text(
    pdf,
    text,
    x,
    y,
    width,
    font=REGULAR_FONT,
    size=18,
    leading=24,
    max_lines=None
):

    text = str(
        text or ""
    ).strip()

    if not text:
        return y

    pdf.setFont(
        font,
        size
    )

    words = text.split()

    line = ""

    lines = []

    for word in words:

        test = (
            line + " " + word
        ).strip()

        if pdf.stringWidth(
            test,
            font,
            size
        ) <= width:

            line = test

        else:

            if line:

                lines.append(
                    line
                )

            line = word

    if line:

        lines.append(
            line
        )

    if max_lines is not None:

        lines = lines[:max_lines]

    current_y = y

    for item in lines:

        pdf.drawString(
            x,
            current_y,
            item
        )

        current_y -= leading

    return current_y


# ============================================================
# YEDEK GÖRSEL
# ============================================================

def draw_fallback_visual(
    pdf,
    x,
    y,
    width,
    height,
    title
):

    pdf.roundRect(
        x,
        y,
        width,
        height,
        18,
        stroke=1,
        fill=0
    )

    pdf.setFont(
        BOLD_FONT,
        22
    )

    pdf.drawCentredString(
        x + width / 2,
        y + height / 2 + 15,
        "K.A.R.V.I.S."
    )

    pdf.setFont(
        REGULAR_FONT,
        13
    )

    pdf.drawCentredString(
        x + width / 2,
        y + height / 2 - 10,
        "Kavramsal Görsel"
    )

    pdf.setFont(
        REGULAR_FONT,
        9
    )

    words = str(
        title or ""
    ).split()

    line = ""

    lines = []

    for word in words:

        test = (
            line + " " + word
        ).strip()

        if len(test) <= 38:

            line = test

        else:

            if line:

                lines.append(
                    line
                )

            line = word

    if line:

        lines.append(
            line
        )

    yy = y + 45

    for item in lines[:3]:

        pdf.drawCentredString(
            x + width / 2,
            yy,
            item
        )

        yy -= 13


# ============================================================
# GÖRSELİ PDF'E ÇİZ
# ============================================================

def draw_image(
    pdf,
    image_path,
    x,
    y,
    width,
    height
):

    try:

        from PIL import Image

        image = Image.open(
            image_path
        )

        image_width, image_height = (
            image.size
        )

        if (
            image_width <= 0
            or image_height <= 0
        ):

            return False

        ratio = min(
            width / image_width,
            height / image_height
        )

        draw_width = (
            image_width * ratio
        )

        draw_height = (
            image_height * ratio
        )

        draw_x = (
            x
            + (width - draw_width) / 2
        )

        draw_y = (
            y
            + (height - draw_height) / 2
        )

        pdf.drawImage(
            ImageReader(
                image_path
            ),
            draw_x,
            draw_y,
            width=draw_width,
            height=draw_height,
            preserveAspectRatio=True,
            mask="auto"
        )

        return True

    except Exception as error:

        print(
            "PDF görsel çizim hatası:",
            error
        )

        return False


# ============================================================
# ÖĞRETMEN NOTU KUTUSU
# ============================================================

def draw_teacher_note(
    pdf,
    note,
    x,
    y,
    width,
    height
):

    note = str(
        note or ""
    ).strip()

    pdf.roundRect(
        x,
        y,
        width,
        height,
        8,
        stroke=1,
        fill=0
    )

    pdf.setFont(
        BOLD_FONT,
        9.5
    )

    pdf.drawString(
        x + 12,
        y + height - 17,
        "Öğretmen Notu"
    )

    text_x = (
        x + 105
    )

    text_y = (
        y + height - 17
    )

    text_width = (
        width - 120
    )

    draw_wrapped_text(
        pdf,
        note,
        text_x,
        text_y,
        text_width,
        font=REGULAR_FONT,
        size=8.7,
        leading=11,
        max_lines=4
    )


# ============================================================
# SUNUM PDF OLUŞTUR
# ============================================================

def create_presentation_pdf(
    outline,
    username="karahan"
):

    filename = (
        "KARVIS_Sunum_"
        + uuid.uuid4().hex
        + ".pdf"
    )

    pdf_path = (
        GENERATED_DIR / filename
    )

    page_width, page_height = (
        landscape(A4)
    )

    pdf = canvas.Canvas(
        str(pdf_path),
        pagesize=(
            page_width,
            page_height
        )
    )

    pdf.setTitle(
        str(
            outline.get(
                "title",
                "K.A.R.V.I.S. Sunum"
            )
        )
    )

    # ========================================================
    # KAPAK
    # ========================================================

    pdf.setFont(
        BOLD_FONT,
        30
    )

    pdf.drawCentredString(
        page_width / 2,
        page_height - 140,
        str(
            outline.get(
                "title",
                "K.A.R.V.I.S. Sunum"
            )
        )
    )

    pdf.setFont(
        REGULAR_FONT,
        17
    )

    pdf.drawCentredString(
        page_width / 2,
        page_height - 178,
        str(
            outline.get(
                "subtitle",
                "K.A.R.V.I.S. - KARAHAN INC."
            )
        )
    )

    cover_query = outline.get(
        "title",
        ""
    )

    print(
        "Kapak görseli aranıyor..."
    )

    cover_image = get_slide_image(
        cover_query
    )

    if cover_image:

        success = draw_image(
            pdf,
            cover_image,
            page_width / 2 - 200,
            110,
            400,
            190
        )

        if not success:

            draw_fallback_visual(
                pdf,
                page_width / 2 - 160,
                120,
                320,
                170,
                cover_query
            )

    else:

        draw_fallback_visual(
            pdf,
            page_width / 2 - 160,
            120,
            320,
            170,
            cover_query
        )

    pdf.setFont(
        REGULAR_FONT,
        10
    )

    pdf.drawCentredString(
        page_width / 2,
        55,
        "K.A.R.V.I.S. - KARAHAN INC."
    )

    pdf.showPage()

    # ========================================================
    # SLAYTLAR
    # ========================================================

    slides = outline.get(
        "slides",
        []
    )

    total_slides = len(
        slides
    )

    for index, slide in enumerate(
        slides,
        start=1
    ):

        title = slide.get(
            "title",
            "Slayt"
        )

        paragraph = slide.get(
            "paragraph",
            ""
        )

        bullets = slide.get(
            "bullets",
            []
        )

        note = slide.get(
            "note",
            ""
        )

        visual_query = slide.get(
            "visual_query",
            title
        )

        # ====================================================
        # BAŞLIK
        # ====================================================

        pdf.setFont(
            BOLD_FONT,
            20
        )

        pdf.drawString(
            55,
            page_height - 55,
            str(title)
        )

        # ====================================================
        # SOL İÇERİK
        # ====================================================

        left_x = 55
        left_width = 390

        text_y = (
            page_height - 90
        )

        pdf.setFont(
            BOLD_FONT,
            11
        )

        pdf.drawString(
            left_x,
            text_y,
            "Açıklama"
        )

        text_y -= 20

        text_y = draw_wrapped_text(
            pdf,
            paragraph,
            left_x,
            text_y,
            left_width,
            font=REGULAR_FONT,
            size=10.5,
            leading=15,
            max_lines=11
        )

        text_y -= 10

        pdf.setFont(
            BOLD_FONT,
            10.5
        )

        pdf.drawString(
            left_x,
            text_y,
            "Önemli Noktalar"
        )

        text_y -= 18

        for bullet in bullets[:4]:

            text_y = draw_wrapped_text(
                pdf,
                "• " + str(bullet),
                left_x,
                text_y,
                left_width,
                font=REGULAR_FONT,
                size=9.7,
                leading=13,
                max_lines=2
            )

            text_y -= 3

        # ====================================================
        # SAĞ GÖRSEL
        # ====================================================

        image_x = (
            page_width - 350
        )

        image_y = 170

        image_width = 300

        image_height = 220

        image_path = get_slide_image(
            visual_query
        )

        if image_path:

            success = draw_image(
                pdf,
                image_path,
                image_x,
                image_y,
                image_width,
                image_height
            )

            if not success:

                draw_fallback_visual(
                    pdf,
                    image_x,
                    image_y,
                    image_width,
                    image_height,
                    visual_query
                )

        else:

            draw_fallback_visual(
                pdf,
                image_x,
                image_y,
                image_width,
                image_height,
                visual_query
            )

        # ====================================================
        # ÖĞRETMEN NOTU
        # ====================================================

        draw_teacher_note(
            pdf,
            note,
            55,
            55,
            page_width - 110,
            65
        )

        # ====================================================
        # ALT BİLGİ
        # ====================================================

        pdf.setFont(
            REGULAR_FONT,
            7.5
        )

        pdf.drawString(
            55,
            32,
            "K.A.R.V.I.S. - KARAHAN INC."
        )

        pdf.drawRightString(
            page_width - 55,
            32,
            f"{index} / {total_slides}"
        )

        pdf.showPage()

    pdf.save()

    print("")
    print(
        "PDF başarıyla oluşturuldu:"
    )
    print(
        pdf_path
    )
    print("")

    return pdf_path


# ============================================================
# ANA SAYFA
# ============================================================

@app.get("/")
def home():

    index_file = (
        BASE_DIR / "index.html"
    )

    if index_file.exists():

        return FileResponse(
            str(index_file),
            media_type="text/html"
        )

    return {
        "success": True,
        "message": (
            "K.A.R.V.I.S. backend çalışıyor."
        ),
        "version": APP_VERSION
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    return {
        "success": True,
        "status": "online",
        "version": APP_VERSION,
        "time": datetime.now().isoformat(),

        "pdf_font": REGULAR_FONT,

        "font_exists": (
            REGULAR_FONT_FILE.exists()
            and BOLD_FONT_FILE.exists()
        ),

        "font_normal_size": (
            REGULAR_FONT_FILE.stat().st_size
            if REGULAR_FONT_FILE.exists()
            else 0
        ),

        "font_bold_size": (
            BOLD_FONT_FILE.stat().st_size
            if BOLD_FONT_FILE.exists()
            else 0
        ),

        "groq": bool(
            GROQ_API_KEY
        ),

        "openrouter": bool(
            OPENROUTER_API_KEY
        ),

        "visual_system": True,

        "visual_sources": [
            "Wikimedia",
            "DuckDuckGo",
            "Wikipedia",
            "Openverse"
        ],

        "advanced_image_download": True,

        "pdf_system": True
    }


# ============================================================
# VERSION
# ============================================================

@app.get("/version")
def version():

    return {
        "version": APP_VERSION,
        "name": (
            "K.A.R.V.I.S. - KARAHAN INC."
        )
    }


# ============================================================
# USERS
# ============================================================

@app.get("/users")
def users():

    return {
        "success": True,
        "users": [
            {
                "username": user["username"],
                "name": user["name"],
                "role": user["role"]
            }
            for user in USERS.values()
        ]
    }


# ============================================================
# PROFILE LOGIN
# ============================================================

@app.post("/profile-login")
def profile_login(
    request: LoginRequest
):

    username = (
        request.username
        .strip()
        .lower()
    )

    password = request.password

    user = USERS.get(
        username
    )

    if not user:

        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": (
                    "Kullanıcı bulunamadı."
                )
            }
        )

    if username == "karahan":

        return {
            "success": True,
            "user": user,
            "default_mode": "normal"
        }

    if user.get(
        "password"
    ) != password:

        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": "Şifre hatalı."
            }
        )

    if username == "ilknur":

        return {
            "success": True,
            "user": user,
            "default_mode": "lesson",
            "default_mode_name": (
                "🎓 Ders Asistanı"
            )
        }

    return {
        "success": True,
        "user": user,
        "default_mode": "normal"
    }


# ============================================================
# AKADEMİK MODLAR
# ============================================================

@app.get("/academic-modes")
def academic_modes():

    return {
        "success": True,
        "modes": ACADEMIC_MODES
    }


# ============================================================
# CHAT
# ============================================================

@app.post("/chat")
def chat(
    request: ChatRequest
):

    try:

        mode = get_user_mode(
            request.username,
            request.mode
        )

        answer = ask_ai(
            request.message,
            request.username,
            mode,
            request.history
        )

        return {
            "success": True,
            "answer": answer,
            "message": answer,
            "username": request.username,
            "mode": mode
        }

    except Exception as error:

        log_error(
            error,
            "/chat"
        )

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": (
                    "K.A.R.V.I.S. hata verdi."
                ),
                "error": str(error)
            }
        )


# ============================================================
# RESEARCH
# ============================================================

@app.post("/research")
def research(
    request: ResearchRequest
):

    try:

        results = research_topic(
            request.topic
        )

        if not results.get(
            "success"
        ):

            return results

        source_text = "\n".join(
            [
                (
                    f"{item['title']} - "
                    f"{item['url']}"
                )
                for item in results["results"]
            ]
        )

        analysis_prompt = f"""
Şu konu hakkında araştırma yap:

{request.topic}

Bulunan kaynaklar:

{source_text}

Türkçe, anlaşılır ve düzenli
bir araştırma özeti hazırla.

Kaynaklarda bulunmayan bilgileri
kesinmiş gibi yazma.
"""

        summary = ask_ai(
            analysis_prompt,
            request.username,
            "research"
        )

        return {
            "success": True,
            "topic": request.topic,
            "summary": summary,
            "results": results["results"]
        }

    except Exception as error:

        log_error(
            error,
            "/research"
        )

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": str(error)
            }
        )


# ============================================================
# PRESENTATION
# ============================================================

@app.post("/presentation")
def presentation(
    request: PresentationRequest
):

    try:

        topic = (
            request.topic
            or ""
        ).strip()

        if not topic:

            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": (
                        "Sunum konusu boş bırakılamaz."
                    )
                }
            )

        print("")
        print("======================================")
        print("SUNUM OLUŞTURULUYOR")
        print(
            "Konu:",
            topic
        )
        print(
            "Kullanıcı:",
            request.username
        )
        print("======================================")

        outline = (
            generate_presentation_outline(
                topic
            )
        )

        pdf_path = (
            create_presentation_pdf(
                outline,
                request.username
            )
        )

        filename = pdf_path.name

        file_url = (
            "/generated/"
            + filename
        )

        print(
            "Sunum tamamlandı:"
        )

        print(
            file_url
        )

        return {
            "success": True,

            "title": outline.get(
                "title",
                topic
            ),

            "slides": len(
                outline.get(
                    "slides",
                    []
                )
            ),

            "file_url": file_url,

            "download_url": file_url
        }

    except Exception as error:

        log_error(
            error,
            "/presentation"
        )

        print(
            "SUNUM HATASI:",
            error
        )

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": (
                    "Sunum oluşturulamadı."
                ),
                "error": str(error)
            }
        )


# ============================================================
# GENERATED PDF
# ============================================================

@app.get(
    "/generated/{filename}"
)
def generated_file(
    filename: str
):

    try:

        safe_name = os.path.basename(
            filename
        )

        if not safe_name.lower().endswith(
            ".pdf"
        ):

            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": (
                        "Geçersiz dosya türü."
                    )
                }
            )

        file_path = (
            GENERATED_DIR
            / safe_name
        )

        if not file_path.exists():

            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": (
                        "Dosya bulunamadı."
                    )
                }
            )

        return FileResponse(
            str(file_path),
            media_type="application/pdf",
            filename=safe_name
        )

    except Exception as error:

        log_error(
            error,
            "/generated"
        )

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": str(error)
            }
        )


# ============================================================
# MEMORY
# ============================================================

@app.get("/memory")
def get_memory():

    return {
        "success": True,
        "memory": MEMORY
    }


# ============================================================
# NEW CHAT
# ============================================================

@app.post("/new-chat")
def new_chat():

    return {
        "success": True,
        "message": (
            "Yeni sohbet başlatıldı."
        )
    }


# ============================================================
# ERRORS
# ============================================================

@app.get("/errors")
def get_errors():

    return {
        "success": True,
        "errors": ERRORS[-100:]
    }


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
def startup():

    print("")
    print("======================================")
    print(" K.A.R.V.I.S. - KARAHAN INC.")
    print(" Backend başlatılıyor...")
    print("======================================")

    print(
        "Versiyon:",
        APP_VERSION
    )

    print(
        "Sunucu: AKTİF"
    )

    print(
        "Groq:",
        "AKTİF"
        if GROQ_API_KEY
        else "YOK"
    )

    print(
        "OpenRouter:",
        "AKTİF"
        if OPENROUTER_API_KEY
        else "YOK"
    )

    print(
        "PDF Font:",
        REGULAR_FONT
    )

    print(
        "Font dosyaları:",
        "AKTİF"
        if (
            REGULAR_FONT_FILE.exists()
            and BOLD_FONT_FILE.exists()
        )
        else "BULUNAMADI"
    )

    print(
        "PDF klasörü:",
        GENERATED_DIR
    )

    print(
        "Görsel sistemi: AKTİF"
    )

    print(
        "Görsel kaynakları:"
        " Wikimedia + DuckDuckGo + Wikipedia + Openverse"
    )

    print(
        "Gelişmiş görsel indirme:"
        " AKTİF"
    )

    print(
        "Görsel retry sistemi:"
        " AKTİF"
    )

    print(
        "Görsel doğrulama:"
        " AKTİF"
    )

    print(
        "Karahan varsayılan profil: AKTİF"
    )

    print(
        "İlknur -> Ders Asistanı: AKTİF"
    )

    print("======================================")
    print(" K.A.R.V.I.S. HAZIR")
    print("======================================")
    print("")
