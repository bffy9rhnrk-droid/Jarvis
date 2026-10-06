import os
import re
import json
import uuid
import textwrap
from pathlib import Path
from datetime import datetime
from io import BytesIO

import requests

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

APP_VERSION = "26.0.0"

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

    # İlknur Hocam'ın varsayılan modu
    # Ders Asistanı.
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

    # ========================================================
    # GROQ
    # ========================================================

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

    # ========================================================
    # OPENROUTER YEDEK
    # ========================================================

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

    # ========================================================
    # YEDEK SUNUM
    # ========================================================

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
# GÖRSEL İNDİRME
# ============================================================

def download_image(
    url,
    filename=None
):

    try:

        if not url:
            return None

        print("")
        print(
            "GÖRSEL İNDİRİLİYOR:"
        )
        print(url)

        response = requests.get(
            url,
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "Chrome/120 Safari/537.36"
            },
            timeout=25,
            allow_redirects=True
        )

        print(
            "Görsel HTTP:",
            response.status_code
        )

        if response.status_code != 200:

            return None

        if len(response.content) < 1000:

            return None

        try:

            from PIL import Image

            image = Image.open(
                BytesIO(
                    response.content
                )
            )

            print(
                "Görsel formatı:",
                image.format
            )

            print(
                "Görsel boyutu:",
                image.size
            )

            if image.mode != "RGB":

                if image.mode in (
                    "RGBA",
                    "LA"
                ):

                    background = Image.new(
                        "RGB",
                        image.size,
                        "white"
                    )

                    background.paste(
                        image,
                        mask=image.getchannel(
                            "A"
                        )
                        if "A" in image.getbands()
                        else None
                    )

                    image = background

                else:

                    image = image.convert(
                        "RGB"
                    )

            if filename:

                destination = (
                    FILES_DIR / filename
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

            image.save(
                destination,
                "JPEG",
                quality=90,
                optimize=True
            )

            print(
                "Görsel kaydedildi:",
                destination
            )

            return destination

        except Exception as error:

            print(
                "PIL görsel açma hatası:",
                error
            )

            return None

    except Exception as error:

        print(
            "Görsel indirme hatası:",
            error
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
            "gsrlimit": 15,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "iiurlwidth": 1400,
            "format": "json"
        }

        response = requests.get(
            api_url,
            params=params,
            headers={
                "User-Agent":
                    "KARVIS-KARAHAN-INC/26.0"
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

        for page in pages.values():

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

            if mime not in [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "image/bmp",
                "image/tiff"
            ]:

                continue

            image_url = (
                info.get("thumburl")
                or info.get("url")
            )

            if not image_url:
                continue

            filename = (
                "visual_"
                + uuid.uuid4().hex
                + ".jpg"
            )

            image = download_image(
                image_url,
                filename
            )

            if image:

                print(
                    "✓ WIKIMEDIA GÖRSELİ HAZIR"
                )

                return image

    except Exception as error:

        print(
            "Wikimedia hatası:",
            error
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
            "gsrlimit": 10,
            "prop": "pageimages",
            "piprop": "original|thumbnail",
            "pithumbsize": 1400,
            "format": "json"
        }

        response = requests.get(
            api_url,
            params=params,
            headers={
                "User-Agent":
                    "KARVIS-KARAHAN-INC/26.0"
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

        for page in pages.values():

            image_info = (
                page.get("original")
                or page.get("thumbnail")
            )

            if not image_info:
                continue

            image_url = image_info.get(
                "source"
            )

            if not image_url:
                continue

            filename = (
                "visual_"
                + uuid.uuid4().hex
                + ".jpg"
            )

            image = download_image(
                image_url,
                filename
            )

            if image:

                print(
                    "✓ WIKIPEDIA GÖRSELİ HAZIR"
                )

                return image

    except Exception as error:

        print(
            "Wikipedia görsel hatası:",
            error
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

        response = requests.get(
            url,
            params={
                "q": str(query),
                "page_size": 20,
                "mature": "false"
            },
            headers={
                "User-Agent":
                    "KARVIS-KARAHAN-INC/26.0"
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

        for item in results:

            image_url = (
                item.get("thumbnail")
                or item.get("url")
                or item.get("image")
            )

            if not image_url:
                continue

            filename = (
                "visual_"
                + uuid.uuid4().hex
                + ".jpg"
            )

            image = download_image(
                image_url,
                filename
            )

            if image:

                print(
                    "✓ OPENVERSE GÖRSELİ HAZIR"
                )

                return image

    except Exception as error:

        print(
            "Openverse hatası:",
            error
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

    if query not in queries:

        queries.append(query)

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

    if cleaned and cleaned not in queries:

        queries.append(cleaned)

    extra_queries = [
        cleaned + " photograph",
        cleaned + " photo",
        cleaned + " historical photograph",
        cleaned + " diagram",
        cleaned + " map"
    ]

    for item in extra_queries:

        item = item.strip()

        if item and item not in queries:

            queries.append(item)

    return queries[:6]


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

    # --------------------------------------------------------
    # WIKIMEDIA
    # --------------------------------------------------------

    for search_query in queries:

        image = download_wikimedia_visual(
            search_query
        )

        if image:

            print(
                "✓ KAYNAK: WIKIMEDIA"
            )

            return image

    # --------------------------------------------------------
    # WIKIPEDIA
    # --------------------------------------------------------

    for search_query in queries:

        image = download_wikipedia_visual(
            search_query
        )

        if image:

            print(
                "✓ KAYNAK: WIKIPEDIA"
            )

            return image

    # --------------------------------------------------------
    # OPENVERSE
    # --------------------------------------------------------

    for search_query in queries:

        image = download_openverse_visual(
            search_query
        )

        if image:

            print(
                "✓ KAYNAK: OPENVERSE"
            )

            return image

    print(
        "✗ UYGUN GÖRSEL BULUNAMADI."
    )

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

    # Kutu
    pdf.roundRect(
        x,
        y,
        width,
        height,
        8,
        stroke=1,
        fill=0
    )

    # Başlık
    pdf.setFont(
        BOLD_FONT,
        9.5
    )

    pdf.drawString(
        x + 12,
        y + height - 17,
        "Öğretmen Notu"
    )

    # Metin alanı
    text_x = (
        x + 105
    )

    text_y = (
        y + height - 17
    )

    text_width = (
        width - 120
    )

    # Metni otomatik satırlandır.
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
        # SOL İÇERİK ALANI
        # ====================================================

        left_x = 55

        left_width = 390

        text_y = (
            page_height - 90
        )

        # ----------------------------------------------------
        # AÇIKLAMA BAŞLIĞI
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # UZUN AÇIKLAMA
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # ÖNEMLİ NOKTALAR
        # ----------------------------------------------------

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
        #
        # Ayrı sabit kutu kullanılıyor.
        # Böylece metinler artık birbirinin
        # üzerine binmiyor.
        # ========================================================

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

    # Ana kullanıcı
    # şifresiz kullanılabilir.
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

    # İlknur Hocam için otomatik
    # Ders Asistanı.
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
        " Wikimedia + Wikipedia + Openverse"
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
