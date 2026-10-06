import os
import re
import json
import uuid
import textwrap
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

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


# =========================================================
# KARVIS - KARAHAN INC.
# MAIN SERVER
# =========================================================

APP_VERSION = "23.0.0"

BASE_DIR = Path(__file__).resolve().parent
FILES_DIR = BASE_DIR / "files"
GENERATED_DIR = BASE_DIR / "generated"
MEMORY_FILE = BASE_DIR / "memory.json"
ERROR_FILE = BASE_DIR / "errors.json"
FONT_DIR = BASE_DIR / "fonts"

FILES_DIR.mkdir(exist_ok=True)
GENERATED_DIR.mkdir(exist_ok=True)
FONT_DIR.mkdir(exist_ok=True)


# =========================================================
# FONT
# Türkçe karakter destekli PDF fontu
# =========================================================

REGULAR_FONT_PATH = FONT_DIR / "DejaVuSans.ttf"
BOLD_FONT_PATH = FONT_DIR / "DejaVuSans-Bold.ttf"

REGULAR_FONT = "Helvetica"
BOLD_FONT = "Helvetica-Bold"

try:
    if REGULAR_FONT_PATH.exists():
        pdfmetrics.registerFont(
            TTFont("DejaVu", str(REGULAR_FONT_PATH))
        )
        REGULAR_FONT = "DejaVu"

    if BOLD_FONT_PATH.exists():
        pdfmetrics.registerFont(
            TTFont("DejaVu-Bold", str(BOLD_FONT_PATH))
        )
        BOLD_FONT = "DejaVu-Bold"

except Exception as font_error:
    print("Font yükleme hatası:", font_error)


# =========================================================
# APP
# =========================================================

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


# =========================================================
# AKADEMİK MODLAR
# =========================================================

ACADEMIC_MODES = {
    "research": {
        "name": "Araştırma Modu",
        "icon": "🔬"
    },

    "academic": {
        "name": "Akademik Mod",
        "icon": "📚"
    },

    "article": {
        "name": "Makale Asistanı",
        "icon": "📝"
    },

    "lesson": {
        "name": "Ders Asistanı",
        "icon": "🎓"
    },

    "quiz": {
        "name": "Sınav / Quiz",
        "icon": "🧪"
    },

    "presentation": {
        "name": "Sunum Hazırlama",
        "icon": "📊"
    }
}


# =========================================================
# ENV
# =========================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b"
]

OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openai/gpt-oss-20b:free"
)


# =========================================================
# MEMORY HELPERS
# =========================================================

def load_json_file(path: Path, default):
    try:
        if not path.exists():
            return default

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return default


def save_json_file(path: Path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )
    except Exception as error:
        print("JSON kayıt hatası:", error)


def get_memory():
    return load_json_file(MEMORY_FILE, {})


def save_memory(memory):
    save_json_file(MEMORY_FILE, memory)


def get_errors():
    return load_json_file(ERROR_FILE, [])


def save_error(error_text: str):
    errors = get_errors()

    errors.append({
        "time": datetime.now().isoformat(),
        "error": str(error_text)
    })

    errors = errors[-100:]

    save_json_file(ERROR_FILE, errors)


# =========================================================
# MODELS
# =========================================================

class ChatRequest(BaseModel):
    message: str
    username: str = "karahan"
    mode: str = "normal"


class LoginRequest(BaseModel):
    username: str
    password: str


class ResearchRequest(BaseModel):
    query: str
    username: str = "ilknur"


class PresentationRequest(BaseModel):
    topic: str
    username: str = "ilknur"
    slide_count: int = 10
    include_visuals: bool = True


# =========================================================
# USER
# =========================================================

def get_user(username: str):
    return USERS.get(
        username.lower(),
        USERS["karahan"]
    )


# =========================================================
# SYSTEM PROMPT
# =========================================================

def build_system_prompt(
    username: str,
    mode: str = "normal"
):

    user = get_user(username)

    personality = user.get(
        "personality",
        "professional"
    )

    base_prompt = """
Sen K.A.R.V.I.S. isimli kişisel yapay zeka asistanısın.

Marka:
K.A.R.V.I.S.
KARAHAN INC.

Görevin:
Kullanıcıya doğal, anlaşılır, hızlı ve faydalı cevaplar vermek.

Kurallar:

- Türkçe konuş.
- Kullanıcı Türkçe yazıyorsa Türkçe cevap ver.
- Gereksiz yere kendini tekrar etme.
- Çok uzun cevaplar vermek yerine gerektiği kadar açık ol.
- Kullanıcı teknik bir şey soruyorsa doğrudan çözüm üret.
- Kod gerekiyorsa çalışabilir kod üret.
- Kullanıcıyı gereksiz yere korkutma.
- Bilmediğin bilgiyi kesinmiş gibi söyleme.
- Güncel bilgi gerektiğinde araştırma yapılmasını öner.
- Robotik ve mekanik konuşma.
- Profesyonel ama doğal bir üslup kullan.
"""

    if personality == "betul":
        base_prompt += """
Betül ile konuşurken sıcak, nazik ve samimi ol.
Gerektiğinde hafif esprili olabilirsin.
"""

    elif personality == "sinem":
        base_prompt += """
Sinem ile konuşurken samimi ve pozitif ol.
Gerektiğinde hafif eğlenceli bir üslup kullan.
"""

    elif personality == "teacher":
        base_prompt += """
Kullanıcı İlknur Hocam'dır.

Akademik konularda:
- Düzenli
- Kaynak odaklı
- Öğretici
- Açık
- Öğrencilerin anlayabileceği
bir dil kullan.

Ders içeriği hazırlanırken başlıkları ve maddeleri düzenli ver.
"""

    if personality == "teacher":

        mode_prompt = {
            "research": """
Araştırma Modu aktif.

Konuyu sistematik şekilde incele.
Önemli kavramları açıkla.
Gerekirse kaynak araştırması yapılabilecek arama terimleri üret.
""",

            "academic": """
Akademik Mod aktif.

Akademik terminoloji kullan.
Tanım, açıklama, değerlendirme ve sonuç yapısını koru.
""",

            "article": """
Makale Asistanı aktif.

Akademik makale yapısına uygun içerik üret.
Giriş, gelişme, değerlendirme ve sonuç bölümlerini gerektiğinde kullan.
""",

            "lesson": """
Ders Asistanı aktif.

Konuyu öğrenci seviyesine göre açıkla.
Örnekler kullan.
Öğretmenin derste doğrudan kullanabileceği içerikler oluştur.
""",

            "quiz": """
Sınav / Quiz Modu aktif.

Sorular üretirken açık ve ölçülebilir sorular oluştur.
Çoktan seçmeli, doğru-yanlış veya açık uçlu format kullanılabilir.
Cevap anahtarı istenirse ayrıca ver.
""",

            "presentation": """
Sunum Hazırlama Modu aktif.

Slayt başlıkları, kısa maddeler ve öğretmen notları oluştur.
Slaytların çok fazla metin içermemesine dikkat et.
Görsel önerileri oluştur.
"""
        }

        base_prompt += mode_prompt.get(
            mode,
            mode_prompt["lesson"]
        )

    return base_prompt


# =========================================================
# AI
# =========================================================

def ask_ai(
    messages: List[Dict[str, str]],
    temperature: float = 0.4,
    max_tokens: int = 2500
):

    last_error = None

    # -----------------------------------------------------
    # GROQ
    # -----------------------------------------------------

    if GROQ_API_KEY:

        try:
            client = OpenAI(
                api_key=GROQ_API_KEY,
                base_url=GROQ_BASE_URL
            )

            for model in GROQ_MODELS:

                try:
                    response = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )

                    content = response.choices[0].message.content

                    if content:
                        return content.strip()

                except Exception as error:
                    last_error = error
                    print(
                        "Groq model hatası:",
                        model,
                        error
                    )

        except Exception as error:
            last_error = error

    # -----------------------------------------------------
    # OPENROUTER
    # -----------------------------------------------------

    if OPENROUTER_API_KEY:

        try:
            client = OpenAI(
                api_key=OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1"
            )

            response = client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            content = response.choices[0].message.content

            if content:
                return content.strip()

        except Exception as error:
            last_error = error

    save_error(last_error or "AI sağlayıcısı bulunamadı.")

    return (
        "Şu anda yapay zeka bağlantısında bir sorun oluştu. "
        "Lütfen biraz sonra tekrar deneyin."
    )


# =========================================================
# INTERNET SEARCH
# =========================================================

def internet_search(query: str, limit: int = 6):

    try:

        url = "https://html.duckduckgo.com/html/"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 "
                "(iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            )
        }

        response = requests.get(
            url,
            params={"q": query},
            headers=headers,
            timeout=15
        )

        response.raise_for_status()

        html = response.text

        results = []

        pattern = re.compile(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.I | re.S
        )

        matches = pattern.findall(html)

        for href, title in matches[:limit]:

            title = re.sub(
                r"<.*?>",
                "",
                title
            )

            title = title.strip()

            results.append({
                "title": title,
                "url": href
            })

        return results

    except Exception as error:

        save_error(
            "Internet search hatası: "
            + str(error)
        )

        return []


# =========================================================
# RESEARCH CONTEXT
# =========================================================

def build_research_context(query: str):

    results = internet_search(
        query,
        limit=8
    )

    if not results:
        return "Araştırma sonucu bulunamadı."

    lines = [
        "İnternetten bulunan araştırma sonuçları:"
    ]

    for index, item in enumerate(
        results,
        start=1
    ):

        lines.append(
            f"{index}. "
            f"{item['title']} - "
            f"{item['url']}"
        )

    return "\n".join(lines)


# =========================================================
# PRESENTATION OUTLINE
# =========================================================

def generate_presentation_outline(
    topic: str,
    slide_count: int
):

    slide_count = max(
        4,
        min(slide_count, 30)
    )

    prompt = f"""
Bir öğretmenin öğrencilerine sunabileceği profesyonel
bir eğitim sunumu hazırla.

KONU:
{topic}

SLAYT SAYISI:
{slide_count}

Sadece geçerli JSON döndür.

JSON yapısı:

{{
  "title": "Sunum başlığı",
  "subtitle": "Kısa alt başlık",
  "slides": [
    {{
      "title": "Slayt başlığı",
      "bullets": [
        "Kısa madde 1",
        "Kısa madde 2",
        "Kısa madde 3"
      ],
      "visual_query": "Görsel araması için kısa ifade",
      "visual_type": "photo",
      "teacher_note": "Öğretmenin sunum sırasında kullanabileceği kısa not"
    }}
  ]
}}

KURALLAR:

- Türkçe karakterleri kesinlikle doğru kullan.
- Her slaytta 3 ila 5 kısa madde olsun.
- Maddeler çok uzun olmasın.
- Öğrenci seviyesinde anlaşılır olsun.
- Gereksiz tekrar yapma.
- Her slayt için mutlaka görsel önerisi üret.
- visual_query gerçek internette aranabilecek kısa bir ifade olsun.
- Mümkünse gerçek fotoğraf öner.
- Fotoğraf bulunamayabilecek konularda diyagram, şema,
  harita veya kavramsal görsel öner.
- Öğretmen notu kısa ve kullanışlı olsun.
- İlk slayt giriş niteliğinde olsun.
- Son slayt sonuç veya değerlendirme niteliğinde olsun.
"""

    messages = [
        {
            "role": "system",
            "content": """
Sen profesyonel eğitim sunumu hazırlayan
bir akademik sunum asistanısın.

Yalnızca geçerli JSON üret.
JSON dışında hiçbir şey yazma.
"""
        },
        {
            "role": "user",
            "content": prompt
        }
    ]

    raw = ask_ai(
        messages,
        temperature=0.25,
        max_tokens=7000
    )

    # -----------------------------------------------------
    # JSON temizleme
    # -----------------------------------------------------

    raw = raw.strip()

    if raw.startswith("```"):
        raw = re.sub(
            r"^```(?:json)?",
            "",
            raw,
            flags=re.I
        )

        raw = re.sub(
            r"```$",
            "",
            raw
        )

    raw = raw.strip()

    try:
        data = json.loads(raw)

        if "slides" not in data:
            raise ValueError(
                "Sunum JSON'unda slides bulunamadı."
            )

        return data

    except Exception as error:

        save_error(
            "Sunum JSON hatası: "
            + str(error)
        )

        # -------------------------------------------------
        # AI JSON üretemezse güvenli fallback
        # -------------------------------------------------

        return {
            "title": topic,
            "subtitle": "K.A.R.V.I.S. - KARAHAN INC.",
            "slides": [
                {
                    "title": "Giriş",
                    "bullets": [
                        f"{topic} kavramının temel özellikleri",
                        "Konunun temel amacı ve kapsamı",
                        "Konunun günlük ve mesleki önemi"
                    ],
                    "visual_query": topic,
                    "visual_type": "photo",
                    "teacher_note": (
                        "Konunun temel çerçevesini "
                        "öğrencilere açıklayın."
                    )
                },
                {
                    "title": "Temel Kavramlar",
                    "bullets": [
                        "Temel kavramların açıklanması",
                        "Konuyla ilişkili önemli unsurlar",
                        "Uygulamadaki karşılıkları"
                    ],
                    "visual_query": topic,
                    "visual_type": "diagram",
                    "teacher_note": (
                        "Temel kavramları örneklerle açıklayın."
                    )
                },
                {
                    "title": "Sonuç",
                    "bullets": [
                        "Konunun genel değerlendirmesi",
                        "Önemli noktaların tekrar edilmesi",
                        "Güvenli ve doğru uygulamanın önemi"
                    ],
                    "visual_query": topic,
                    "visual_type": "photo",
                    "teacher_note": (
                        "Sunumun ana mesajını vurgulayın."
                    )
                }
            ]
        }


# =========================================================
# WIKIMEDIA IMAGE SEARCH
# =========================================================

def download_wikimedia_visual(
    query: str,
    output_path: Path
):

    try:

        if not query:
            return None

        api_url = (
            "https://commons.wikimedia.org/w/api.php"
        )

        headers = {
            "User-Agent": (
                "KARVIS-Karahan-Inc/1.0 "
                "(educational presentation generator)"
            }
        }

        # Türkçe arama başarısız olursa İngilizce
        # kelimelerle ikinci arama yapılabilmesi için
        # ilk aramayı doğrudan kullanıyoruz.

        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,
            "gsrlimit": 20,
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": 1400,
            "format": "json"
        }

        response = requests.get(
            api_url,
            params=params,
            headers=headers,
            timeout=20
        )

        response.raise_for_status()

        data = response.json()

        pages = (
            data
            .get("query", {})
            .get("pages", {})
        )

        if not pages:
            return None

        for page in pages.values():

            image_info = page.get(
                "imageinfo",
                []
            )

            if not image_info:
                continue

            info = image_info[0]

            image_url = (
                info.get("thumburl")
                or info.get("url")
            )

            if not image_url:
                continue

            try:

                image_response = requests.get(
                    image_url,
                    headers=headers,
                    timeout=25
                )

                image_response.raise_for_status()

                content_type = (
                    image_response
                    .headers
                    .get(
                        "content-type",
                        ""
                    )
                    .lower()
                )

                if not content_type.startswith(
                    "image/"
                ):
                    continue

                content = image_response.content

                if len(content) < 5000:
                    continue

                output_path.parent.mkdir(
                    parents=True,
                    exist_ok=True
                )

                with open(
                    output_path,
                    "wb"
                ) as image_file:

                    image_file.write(content)

                if output_path.exists():

                    if output_path.stat().st_size >= 5000:
                        return output_path

            except Exception as image_error:

                print(
                    "Tekil görsel indirme hatası:",
                    image_error
                )

                continue

        return None

    except Exception as error:

        print(
            "Wikimedia görsel hatası:",
            error
        )

        save_error(
            "Wikimedia görsel hatası: "
            + str(error)
        )

        return None


# =========================================================
# GENERIC IMAGE SEARCH
# Wikimedia bulunamazsa Openverse denenir
# =========================================================

def download_openverse_visual(
    query: str,
    output_path: Path
):

    try:

        url = "https://api.openverse.org/v1/images/"

        params = {
            "q": query,
            "page_size": 10
        }

        headers = {
            "User-Agent": (
                "KARVIS-Karahan-Inc/1.0"
            )
        }

        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=20
        )

        response.raise_for_status()

        data = response.json()

        results = data.get(
            "results",
            []
        )

        for item in results:

            image_url = (
                item.get("thumbnail")
                or item.get("url")
            )

            if not image_url:
                continue

            try:

                image_response = requests.get(
                    image_url,
                    headers=headers,
                    timeout=20
                )

                image_response.raise_for_status()

                content_type = (
                    image_response
                    .headers
                    .get(
                        "content-type",
                        ""
                    )
                    .lower()
                )

                if not content_type.startswith(
                    "image/"
                ):
                    continue

                content = image_response.content

                if len(content) < 5000:
                    continue

                output_path.parent.mkdir(
                    parents=True,
                    exist_ok=True
                )

                with open(
                    output_path,
                    "wb"
                ) as f:

                    f.write(content)

                if (
                    output_path.exists()
                    and output_path.stat().st_size >= 5000
                ):
                    return output_path

            except Exception:
                continue

        return None

    except Exception as error:

        print(
            "Openverse görsel hatası:",
            error
        )

        return None


# =========================================================
# IMAGE DOWNLOAD WITH FALLBACK
# =========================================================

def get_slide_image(
    visual_query: str,
    slide_number: int
):

    if not visual_query:
        return None

    safe_name = re.sub(
        r"[^a-zA-Z0-9ğüşöçıİĞÜŞÖÇ]+",
        "_",
        visual_query
    )

    safe_name = safe_name[:50]

    output_path = (
        GENERATED_DIR
        / f"slide_{slide_number}_{safe_name}.jpg"
    )

    # Önce Wikimedia
    result = download_wikimedia_visual(
        visual_query,
        output_path
    )

    if result:
        return result

    # Sonra Openverse
    result = download_openverse_visual(
        visual_query,
        output_path
    )

    if result:
        return result

    return None


# =========================================================
# PDF HELPERS
# =========================================================

def draw_wrapped_text(
    c,
    text,
    x,
    y,
    max_width,
    font_name,
    font_size,
    leading=None
):

    if leading is None:
        leading = font_size + 5

    c.setFont(
        font_name,
        font_size
    )

    # Yaklaşık karakter hesabı
    chars_per_line = max(
        20,
        int(max_width / (font_size * 0.52))
    )

    lines = []

    paragraphs = str(text).split("\n")

    for paragraph in paragraphs:

        if not paragraph:
            lines.append("")
            continue

        wrapped = textwrap.wrap(
            paragraph,
            width=chars_per_line,
            break_long_words=False,
            break_on_hyphens=False
        )

        lines.extend(wrapped)

    for line in lines:

        c.drawString(
            x,
            y,
            line
        )

        y -= leading

    return y


def draw_bullet_list(
    c,
    bullets,
    x,
    y,
    max_width,
    font_name,
    font_size=14
):

    for bullet in bullets:

        c.setFont(
            font_name,
            font_size
        )

        c.drawString(
            x,
            y,
            "•"
        )

        y = draw_wrapped_text(
            c,
            str(bullet),
            x + 20,
            y,
            max_width - 20,
            font_name,
            font_size,
            leading=font_size + 7
        )

        y -= 8

    return y


def draw_fallback_visual(
    c,
    x,
    y,
    width,
    height,
    title
):

    # Çerçeve
    c.rect(
        x,
        y,
        width,
        height
    )

    # Başlık
    c.setFont(
        BOLD_FONT,
        16
    )

    c.drawCentredString(
        x + width / 2,
        y + height - 30,
        "Kavramsal Görsel"
    )

    # Basit profesyonel şema
    box_width = width * 0.65
    box_height = 55

    box_x = (
        x + (width - box_width) / 2
    )

    center_y = (
        y + height / 2
    )

    c.rect(
        box_x,
        center_y - box_height / 2,
        box_width,
        box_height
    )

    c.setFont(
        REGULAR_FONT,
        12
    )

    short_title = str(title)

    if len(short_title) > 45:
        short_title = (
            short_title[:42]
            + "..."
        )

    c.drawCentredString(
        x + width / 2,
        center_y - 5,
        short_title
    )

    # Alt açıklama
    c.setFont(
        REGULAR_FONT,
        10
    )

    c.drawCentredString(
        x + width / 2,
        y + 25,
        "K.A.R.V.I.S. Akademik Sunum"
    )


def draw_image_contain(
    c,
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

        if image_width <= 0 or image_height <= 0:
            return False

        scale = min(
            width / image_width,
            height / image_height
        )

        draw_width = (
            image_width * scale
        )

        draw_height = (
            image_height * scale
        )

        draw_x = (
            x
            + (width - draw_width) / 2
        )

        draw_y = (
            y
            + (height - draw_height) / 2
        )

        c.drawImage(
            ImageReader(image_path),
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
            "PDF görsel yerleştirme hatası:",
            error
        )

        return False


# =========================================================
# PRESENTATION PDF
# =========================================================

def create_presentation_pdf(
    presentation: Dict[str, Any],
    topic: str,
    include_visuals: bool = True
):

    slides = presentation.get(
        "slides",
        []
    )

    if not slides:
        raise ValueError(
            "Sunum slaytları oluşturulamadı."
        )

    title = presentation.get(
        "title",
        topic
    )

    subtitle = presentation.get(
        "subtitle",
        "K.A.R.V.I.S. - KARAHAN INC."
    )

    file_id = uuid.uuid4().hex[:12]

    pdf_path = (
        GENERATED_DIR
        / f"sunum_{file_id}.pdf"
    )

    page_width, page_height = landscape(A4)

    c = canvas.Canvas(
        str(pdf_path),
        pagesize=(
            page_width,
            page_height
        )
    )

    # =====================================================
    # KAPAK
    # =====================================================

    c.setTitle(
        str(title)
    )

    c.setAuthor(
        "K.A.R.V.I.S. - KARAHAN INC."
    )

    c.setFont(
        BOLD_FONT,
        32
    )

    c.drawCentredString(
        page_width / 2,
        page_height * 0.62,
        str(title)
    )

    c.setFont(
        REGULAR_FONT,
        17
    )

    c.drawCentredString(
        page_width / 2,
        page_height * 0.52,
        str(subtitle)
    )

    c.setFont(
        REGULAR_FONT,
        11
    )

    c.drawCentredString(
        page_width / 2,
        55,
        "K.A.R.V.I.S. - KARAHAN INC."
    )

    c.showPage()

    # =====================================================
    # SLAYTLAR
    # =====================================================

    for index, slide in enumerate(
        slides,
        start=1
    ):

        slide_title = slide.get(
            "title",
            f"Slayt {index}"
        )

        bullets = slide.get(
            "bullets",
            []
        )

        teacher_note = slide.get(
            "teacher_note",
            ""
        )

        visual_query = slide.get(
            "visual_query",
            ""
        )

        # -------------------------------------------------
        # Görsel
        # -------------------------------------------------

        image_path = None

        if include_visuals:

            try:

                image_path = get_slide_image(
                    visual_query,
                    index
                )

            except Exception as error:

                print(
                    "Görsel hazırlanamadı:",
                    error
                )

                image_path = None

        # -------------------------------------------------
        # Başlık
        # -------------------------------------------------

        c.setFont(
            BOLD_FONT,
            24
        )

        c.drawString(
            45,
            page_height - 55,
            str(slide_title)
        )

        # -------------------------------------------------
        # Sol içerik alanı
        # -------------------------------------------------

        content_x = 50
        content_y = page_height - 100

        if image_path:

            content_width = (
                page_width * 0.48
            )

            image_x = (
                page_width * 0.54
            )

            image_y = 125

            image_width = (
                page_width * 0.40
            )

            image_height = (
                page_height * 0.60
            )

        else:

            content_width = (
                page_width - 100
            )

            image_x = (
                page_width * 0.55
            )

            image_y = 145

            image_width = (
                page_width * 0.36
            )

            image_height = (
                page_height * 0.55
            )

        # -------------------------------------------------
        # Maddeler
        # -------------------------------------------------

        c.setFont(
            REGULAR_FONT,
            15
        )

        draw_bullet_list(
            c,
            bullets,
            content_x,
            content_y,
            content_width,
            REGULAR_FONT,
            15
        )

        # -------------------------------------------------
        # Görsel
        # -------------------------------------------------

        if image_path:

            success = draw_image_contain(
                c,
                image_path,
                image_x,
                image_y,
                image_width,
                image_height
            )

            if not success:

                draw_fallback_visual(
                    c,
                    image_x,
                    image_y,
                    image_width,
                    image_height,
                    visual_query or slide_title
                )

        else:

            draw_fallback_visual(
                c,
                image_x,
                image_y,
                image_width,
                image_height,
                visual_query or slide_title
            )

        # -------------------------------------------------
        # Öğretmen Notu
        # -------------------------------------------------

        if teacher_note:

            note_x = 50
            note_y = 65

            note_width = (
                page_width - 100
            )

            c.setFont(
                BOLD_FONT,
                10
            )

            c.drawString(
                note_x,
                note_y + 22,
                "Öğretmen Notu:"
            )

            draw_wrapped_text(
                c,
                teacher_note,
                note_x + 85,
                note_y + 22,
                note_width - 85,
                REGULAR_FONT,
                9,
                leading=11
            )

        # -------------------------------------------------
        # Alt bilgi
        # -------------------------------------------------

        c.setFont(
            REGULAR_FONT,
            8
        )

        c.drawRightString(
            page_width - 40,
            25,
            f"{index} / {len(slides)}"
        )

        c.drawString(
            40,
            25,
            "K.A.R.V.I.S. - KARAHAN INC."
        )

        c.showPage()

    # =====================================================
    # KAPAT
    # =====================================================

    c.save()

    return pdf_path


# =========================================================
# ROUTES
# =========================================================

@app.get("/")
def home():

    index_file = BASE_DIR / "index.html"

    if index_file.exists():

        return FileResponse(
            str(index_file)
        )

    return {
        "app": "K.A.R.V.I.S.",
        "company": "KARAHAN INC.",
        "version": APP_VERSION
    }


@app.get("/health")
def health():

    return {
        "status": "online",
        "app": "K.A.R.V.I.S.",
        "version": APP_VERSION
    }


@app.get("/version")
def version():

    return {
        "version": APP_VERSION
    }


@app.get("/users")
def users():

    result = []

    for username, user in USERS.items():

        result.append({
            "username": username,
            "name": user["name"],
            "role": user["role"]
        })

    return result


# =========================================================
# LOGIN
# =========================================================

@app.post("/profile-login")
def profile_login(request: LoginRequest):

    username = request.username.lower().strip()

    user = USERS.get(username)

    if not user:

        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": "Kullanıcı bulunamadı."
            }
        )

    password = user.get(
        "password"
    )

    # Ana kullanıcı şifresiz
    if password is None:

        return {
            "success": True,
            "user": {
                "username": username,
                "name": user["name"],
                "role": user["role"],
                "personality": user["personality"]
            }
        }

    if request.password != password:

        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": "Şifre hatalı."
            }
        )

    return {
        "success": True,
        "user": {
            "username": username,
            "name": user["name"],
            "role": user["role"],
            "personality": user["personality"]
        }
    }


# =========================================================
# ACADEMIC MODES
# =========================================================

@app.get("/academic-modes")
def academic_modes():

    return {
        "modes": ACADEMIC_MODES
    }


# =========================================================
# CHAT
# =========================================================

@app.post("/chat")
def chat(request: ChatRequest):

    username = request.username.lower()

    user = get_user(username)

    mode = request.mode or "normal"

    memory = get_memory()

    user_memory = memory.get(
        username,
        []
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

    # Son hafıza kayıtları
    for item in user_memory[-10:]:

        messages.append({
            "role": item.get(
                "role",
                "user"
            ),
            "content": item.get(
                "content",
                ""
            )
        })

    messages.append({
        "role": "user",
        "content": request.message
    })

    answer = ask_ai(
        messages,
        temperature=0.45,
        max_tokens=3000
    )

    # Hafızaya kaydet
    if username not in memory:
        memory[username] = []

    memory[username].append({
        "role": "user",
        "content": request.message,
        "time": datetime.now().isoformat()
    })

    memory[username].append({
        "role": "assistant",
        "content": answer,
        "time": datetime.now().isoformat()
    })

    # Son 100 mesajı tut
    memory[username] = memory[username][-100:]

    save_memory(memory)

    return {
        "success": True,
        "answer": answer,
        "username": username,
        "mode": mode
    }


# =========================================================
# RESEARCH
# =========================================================

@app.post("/research")
def research(request: ResearchRequest):

    context = build_research_context(
        request.query
    )

    system_prompt = build_system_prompt(
        request.username,
        "research"
    )

    messages = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": (
                f"Araştırma konusu:\n"
                f"{request.query}\n\n"
                f"{context}\n\n"
                "Bu bilgileri kullanarak "
                "düzenli ve anlaşılır bir araştırma özeti hazırla."
            )
        }
    ]

    answer = ask_ai(
        messages,
        temperature=0.25,
        max_tokens=5000
    )

    return {
        "success": True,
        "query": request.query,
        "answer": answer,
        "sources": internet_search(
            request.query,
            limit=8
        )
    }


# =========================================================
# PRESENTATION
# =========================================================

@app.post("/presentation")
def presentation(
    request: PresentationRequest
):

    try:

        slide_count = max(
            4,
            min(
                int(request.slide_count),
                30
            )
        )

        outline = generate_presentation_outline(
            request.topic,
            slide_count
        )

        pdf_path = create_presentation_pdf(
            outline,
            request.topic,
            request.include_visuals
        )

        filename = pdf_path.name

        return {
            "success": True,
            "title": outline.get(
                "title",
                request.topic
            ),
            "slides": len(
                outline.get(
                    "slides",
                    []
                )
            ),
            "pdf": f"/files/../generated/{filename}",
            "download_url": f"/generated/{filename}"
        }

    except Exception as error:

        save_error(
            "Sunum oluşturma hatası: "
            + str(error)
        )

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": (
                    "Sunum oluşturulurken "
                    "bir hata oluştu."
                ),
                "error": str(error)
            }
        )


# =========================================================
# GENERATED FILES
# =========================================================

@app.get("/generated/{filename}")
def generated_file(filename: str):

    safe_filename = os.path.basename(
        filename
    )

    file_path = (
        GENERATED_DIR
        / safe_filename
    )

    if not file_path.exists():

        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": "Dosya bulunamadı."
            }
        )

    return FileResponse(
        str(file_path),
        media_type="application/pdf",
        filename=safe_filename
    )


# =========================================================
# MEMORY
# =========================================================

@app.get("/memory")
def memory(username: str = "karahan"):

    data = get_memory()

    return {
        "username": username,
        "memory": data.get(
            username,
            []
        )
    }


@app.delete("/memory")
def delete_memory(
    username: str = "karahan"
):

    data = get_memory()

    if username in data:
        del data[username]

    save_memory(data)

    return {
        "success": True,
        "message": "Hafıza temizlendi."
    }


# =========================================================
# NEW CHAT
# =========================================================

@app.post("/new-chat")
def new_chat(
    username: str = "karahan"
):

    data = get_memory()

    data[username] = []

    save_memory(data)

    return {
        "success": True,
        "message": "Yeni sohbet başlatıldı."
    }


# =========================================================
# ERRORS
# =========================================================

@app.get("/errors")
def errors():

    return {
        "errors": get_errors()
    }


@app.delete("/errors")
def delete_errors():

    save_json_file(
        ERROR_FILE,
        []
    )

    return {
        "success": True,
        "message": "Hata kayıtları temizlendi."
    }


# =========================================================
# STARTUP INFO
# =========================================================

@app.on_event("startup")
def startup_event():

    print("=" * 60)
    print("K.A.R.V.I.S. - KARAHAN INC.")
    print("Version:", APP_VERSION)
    print("Server hazır.")
    print("=" * 60)

    if REGULAR_FONT == "DejaVu":
        print(
            "Türkçe PDF fontu: AKTIF"
        )
    else:
        print(
            "UYARI: DejaVuSans bulunamadı."
        )

    if GROQ_API_KEY:
        print(
            "Groq API: AKTIF"
        )
    else:
        print(
            "Groq API: KAPALI"
        )

    if OPENROUTER_API_KEY:
        print(
            "OpenRouter fallback: AKTIF"
        )
    else:
        print(
            "OpenRouter fallback: KAPALI"
        )
