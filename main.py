import os
import re
import json
import uuid
import textwrap
from pathlib import Path
from datetime import datetime

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


# =========================================================
# KARVIS - KARAHAN INC.
# =========================================================

APP_VERSION = "23.2.0"

BASE_DIR = Path(__file__).resolve().parent

FILES_DIR = BASE_DIR / "files"
GENERATED_DIR = BASE_DIR / "generated"
FONT_DIR = BASE_DIR / "fonts"

MEMORY_FILE = BASE_DIR / "memory.json"
ERROR_FILE = BASE_DIR / "errors.json"

FILES_DIR.mkdir(exist_ok=True)
GENERATED_DIR.mkdir(exist_ok=True)
FONT_DIR.mkdir(exist_ok=True)


# =========================================================
# PDF FONT
# =========================================================

REGULAR_FONT = "Helvetica"
BOLD_FONT = "Helvetica-Bold"

REGULAR_FONT_FILE = FONT_DIR / "DejaVuSans.ttf"
BOLD_FONT_FILE = FONT_DIR / "DejaVuSans-Bold.ttf"

try:

    if REGULAR_FONT_FILE.exists():

        pdfmetrics.registerFont(
            TTFont(
                "DejaVu",
                str(REGULAR_FONT_FILE)
            )
        )

        REGULAR_FONT = "DejaVu"

    if BOLD_FONT_FILE.exists():

        pdfmetrics.registerFont(
            TTFont(
                "DejaVu-Bold",
                str(BOLD_FONT_FILE)
            )
        )

        BOLD_FONT = "DejaVu-Bold"

except Exception as error:

    print(
        "Font yükleme hatası:",
        error
    )


# =========================================================
# FASTAPI
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
    StaticFiles(
        directory=str(FILES_DIR)
    ),
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
# ACADEMIC MODES
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
# API SETTINGS
# =========================================================

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY",
    ""
)

OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    ""
)

GROQ_BASE_URL = (
    "https://api.groq.com/openai/v1"
)

GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b"
]

OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openai/gpt-oss-20b:free"
)


# =========================================================
# JSON HELPERS
# =========================================================

def load_json(path, default):

    try:

        if not path.exists():
            return default

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    except Exception as error:

        print(
            "JSON okuma hatası:",
            error
        )

        return default


def save_json(path, data):

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


def get_memory():

    return load_json(
        MEMORY_FILE,
        {}
    )


def save_memory(data):

    save_json(
        MEMORY_FILE,
        data
    )


def get_errors():

    return load_json(
        ERROR_FILE,
        []
    )


def save_error(message):

    errors = get_errors()

    errors.append({
        "time": datetime.now().isoformat(),
        "error": str(message)
    })

    errors = errors[-100:]

    save_json(
        ERROR_FILE,
        errors
    )


# =========================================================
# REQUEST MODELS
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

def get_user(username):

    username = (
        username
        .lower()
        .strip()
    )

    return USERS.get(
        username,
        USERS["karahan"]
    )


# =========================================================
# SYSTEM PROMPT
# =========================================================

def build_system_prompt(
    username,
    mode
):

    user = get_user(
        username
    )

    personality = user.get(
        "personality",
        "professional"
    )

    prompt = """
Sen K.A.R.V.I.S. isimli kişisel yapay zeka asistanısın.

Marka:
K.A.R.V.I.S.
KARAHAN INC.

Türkçe konuş.

Cevapların:
- doğal
- anlaşılır
- profesyonel
- yardımcı
- gereksiz tekrar içermeyen

olmalı.

Bilmediğin bilgileri kesinmiş gibi söyleme.

Kod istenirse çalışabilir kod üret.
"""

    if personality == "betul":

        prompt += """
Betül ile konuşurken sıcak ve samimi ol.
"""

    elif personality == "sinem":

        prompt += """
Sinem ile konuşurken samimi ve pozitif ol.
"""

    elif personality == "teacher":

        prompt += """
Kullanıcı İlknur Hocam'dır.

Akademik konularda:

- düzenli
- öğretici
- açık
- kaynak odaklı
- öğrenci seviyesinde anlaşılır

ol.
"""

        if mode == "research":

            prompt += """
Araştırma Modu aktif.
Konuyu sistematik olarak incele.
"""

        elif mode == "academic":

            prompt += """
Akademik Mod aktif.
Akademik terminoloji kullan.
"""

        elif mode == "article":

            prompt += """
Makale Asistanı aktif.
Makale düzenine uygun içerik üret.
"""

        elif mode == "lesson":

            prompt += """
Ders Asistanı aktif.
Konuyu öğrencilerin anlayacağı şekilde açıkla.
"""

        elif mode == "quiz":

            prompt += """
Sınav / Quiz Modu aktif.
Açık ve ölçülebilir sorular üret.
"""

        elif mode == "presentation":

            prompt += """
Sunum Hazırlama Modu aktif.
Kısa slayt maddeleri ve görsel önerileri üret.
"""

    return prompt


# =========================================================
# AI
# =========================================================

def ask_ai(
    messages,
    temperature=0.4,
    max_tokens=2500
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

                    response = (
                        client
                        .chat
                        .completions
                        .create(
                            model=model,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens
                        )
                    )

                    answer = (
                        response
                        .choices[0]
                        .message
                        .content
                    )

                    if answer:

                        return answer.strip()

                except Exception as error:

                    last_error = error

                    print(
                        "Groq hata:",
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
                base_url=(
                    "https://openrouter.ai/api/v1"
                )
            )

            response = (
                client
                .chat
                .completions
                .create(
                    model=OPENROUTER_MODEL,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            )

            answer = (
                response
                .choices[0]
                .message
                .content
            )

            if answer:

                return answer.strip()

        except Exception as error:

            last_error = error


    save_error(
        last_error
        or
        "AI bağlantısı bulunamadı."
    )

    return (
        "Şu anda yapay zeka bağlantısında "
        "bir sorun oluştu. Lütfen tekrar deneyin."
    )


# =========================================================
# INTERNET SEARCH
# =========================================================

def internet_search(
    query,
    limit=8
):

    try:

        url = (
            "https://html.duckduckgo.com/html/"
        )

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
            params={
                "q": query
            },
            headers=headers,
            timeout=15
        )

        response.raise_for_status()

        pattern = re.compile(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.I | re.S
        )

        matches = pattern.findall(
            response.text
        )

        results = []

        for href, title in matches[:limit]:

            clean_title = re.sub(
                r"<.*?>",
                "",
                title
            )

            results.append({

                "title": clean_title.strip(),

                "url": href

            })

        return results

    except Exception as error:

        save_error(
            "Arama hatası: "
            + str(error)
        )

        return []


# =========================================================
# RESEARCH
# =========================================================

def build_research_context(query):

    results = internet_search(
        query,
        8
    )

    if not results:

        return (
            "Araştırma sonucu bulunamadı."
        )

    lines = [
        "İnternet araştırma sonuçları:"
    ]

    for index, result in enumerate(
        results,
        1
    ):

        lines.append(
            f"{index}. "
            f"{result['title']} - "
            f"{result['url']}"
        )

    return "\n".join(
        lines
    )


# =========================================================
# PRESENTATION OUTLINE
# =========================================================

def generate_presentation_outline(
    topic,
    slide_count
):

    slide_count = max(
        4,
        min(
            int(slide_count),
            30
        )
    )

    prompt = f"""
Profesyonel bir eğitim sunumu hazırla.

Konu:
{topic}

Slayt sayısı:
{slide_count}

SADECE JSON döndür.

Format:

{{
  "title": "Sunum başlığı",
  "subtitle": "Alt başlık",
  "slides": [
    {{
      "title": "Slayt başlığı",
      "bullets": [
        "Kısa madde",
        "Kısa madde",
        "Kısa madde"
      ],
      "visual_query": "Gerçek görsel arama ifadesi",
      "teacher_note": "Öğretmen notu"
    }}
  ]
}}

Kurallar:

- Türkçe karakterleri doğru kullan.
- Her slaytta 3-5 madde olsun.
- Maddeler kısa olsun.
- Her slaytta visual_query mutlaka olsun.
- visual_query internette aranabilecek gerçek bir ifade olsun.
- Öncelikle gerçek fotoğraf öner.
- Fotoğraf bulunamazsa diyagram veya şema öner.
- Son slayt sonuç/değerlendirme olsun.
- Öğretmen notları kısa olsun.
"""

    messages = [

        {
            "role": "system",
            "content": (
                "Sen profesyonel akademik "
                "sunum hazırlayan bir asistansın. "
                "Yalnızca geçerli JSON döndür."
            )
        },

        {
            "role": "user",
            "content": prompt
        }

    ]

    raw = ask_ai(
        messages,
        temperature=0.2,
        max_tokens=7000
    )

    raw = raw.strip()

    if raw.startswith("```"):

        raw = re.sub(
            r"^```json",
            "",
            raw,
            flags=re.I
        )

        raw = re.sub(
            r"^```",
            "",
            raw
        )

        raw = re.sub(
            r"```$",
            "",
            raw
        )

    raw = raw.strip()

    try:

        data = json.loads(
            raw
        )

        if not isinstance(
            data.get("slides"),
            list
        ):

            raise ValueError(
                "slides listesi bulunamadı."
            )

        return data

    except Exception as error:

        save_error(
            "Sunum JSON hatası: "
            + str(error)
        )

        return {

            "title": topic,

            "subtitle": (
                "K.A.R.V.I.S. - KARAHAN INC."
            ),

            "slides": [

                {
                    "title": "Giriş",

                    "bullets": [
                        topic + " nedir?",
                        "Temel özellikleri",
                        "Konunun önemi"
                    ],

                    "visual_query": topic,

                    "teacher_note": (
                        "Konunun temel tanımını açıklayın."
                    )
                },

                {
                    "title": "Temel Kavramlar",

                    "bullets": [
                        "Temel kavramlar",
                        "Önemli unsurlar",
                        "Uygulama alanları"
                    ],

                    "visual_query": topic,

                    "teacher_note": (
                        "Temel kavramları örneklerle açıklayın."
                    )
                },

                {
                    "title": "Sonuç",

                    "bullets": [
                        "Ana noktaların özeti",
                        "Konunun önemi",
                        "Genel değerlendirme"
                    ],

                    "visual_query": topic,

                    "teacher_note": (
                        "Sunumun ana mesajını vurgulayın."
                    )
                }

            ]
        }


# =========================================================
# WIKIMEDIA IMAGE
# =========================================================

def download_wikimedia_visual(
    query,
    output_path
):

    try:

        api_url = (
            "https://commons.wikimedia.org/w/api.php"
        )

        headers = {
            "User-Agent": (
                "KARVIS-Karahan-Inc/1.0"
            )
        }

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
                or
                info.get("url")
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
                ) as file:

                    file.write(
                        content
                    )

                return output_path

            except Exception:

                continue

        return None

    except Exception as error:

        print(
            "Wikimedia hatası:",
            error
        )

        return None


# =========================================================
# OPENVERSE IMAGE
# =========================================================

def download_openverse_visual(
    query,
    output_path
):

    try:

        url = (
            "https://api.openverse.org/v1/images/"
        )

        response = requests.get(
            url,
            params={
                "q": query,
                "page_size": 10
            },
            headers={
                "User-Agent":
                    "KARVIS-Karahan-Inc/1.0"
            },
            timeout=20
        )

        response.raise_for_status()

        results = (
            response
            .json()
            .get(
                "results",
                []
            )
        )

        for item in results:

            image_url = (
                item.get("thumbnail")
                or
                item.get("url")
            )

            if not image_url:
                continue

            try:

                image_response = requests.get(
                    image_url,
                    timeout=20,
                    headers={
                        "User-Agent":
                            "KARVIS-Karahan-Inc/1.0"
                    }
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
                ) as file:

                    file.write(
                        content
                    )

                return output_path

            except Exception:

                continue

        return None

    except Exception as error:

        print(
            "Openverse hatası:",
            error
        )

        return None


# =========================================================
# GET IMAGE
# =========================================================

def get_slide_image(
    query,
    slide_number
):

    if not query:
        return None

    filename = (
        "slide_"
        + str(slide_number)
        + "_"
        + uuid.uuid4().hex[:8]
        + ".jpg"
    )

    output_path = (
        GENERATED_DIR
        / filename
    )

    image = download_wikimedia_visual(
        query,
        output_path
    )

    if image:
        return image

    image = download_openverse_visual(
        query,
        output_path
    )

    if image:
        return image

    return None


# =========================================================
# PDF TEXT
# =========================================================

def draw_wrapped_text(
    pdf,
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

    pdf.setFont(
        font_name,
        font_size
    )

    chars_per_line = max(
        20,
        int(
            max_width /
            (font_size * 0.52)
        )
    )

    lines = []

    for paragraph in str(text).split("\n"):

        if not paragraph:

            lines.append("")

            continue

        wrapped = textwrap.wrap(
            paragraph,
            width=chars_per_line,
            break_long_words=False,
            break_on_hyphens=False
        )

        lines.extend(
            wrapped
        )

    for line in lines:

        pdf.drawString(
            x,
            y,
            line
        )

        y -= leading

    return y


# =========================================================
# PDF BULLETS
# =========================================================

def draw_bullets(
    pdf,
    bullets,
    x,
    y,
    width
):

    for bullet in bullets:

        pdf.setFont(
            REGULAR_FONT,
            15
        )

        pdf.drawString(
            x,
            y,
            "•"
        )

        y = draw_wrapped_text(
            pdf,
            bullet,
            x + 20,
            y,
            width - 20,
            REGULAR_FONT,
            15,
            22
        )

        y -= 8

    return y


# =========================================================
# FALLBACK VISUAL
# =========================================================

def draw_fallback_visual(
    pdf,
    x,
    y,
    width,
    height,
    title
):

    pdf.rect(
        x,
        y,
        width,
        height
    )

    pdf.setFont(
        BOLD_FONT,
        16
    )

    pdf.drawCentredString(
        x + width / 2,
        y + height - 35,
        "Kavramsal Görsel"
    )

    box_width = width * 0.70

    box_height = 60

    box_x = (
        x
        + (width - box_width) / 2
    )

    box_y = (
        y
        + height / 2
        - box_height / 2
    )

    pdf.rect(
        box_x,
        box_y,
        box_width,
        box_height
    )

    short_title = str(title)

    if len(short_title) > 45:

        short_title = (
            short_title[:42]
            + "..."
        )

    pdf.setFont(
        REGULAR_FONT,
        12
    )

    pdf.drawCentredString(
        x + width / 2,
        box_y + 25,
        short_title
    )

    pdf.setFont(
        REGULAR_FONT,
        9
    )

    pdf.drawCentredString(
        x + width / 2,
        y + 20,
        "K.A.R.V.I.S. - KARAHAN INC."
    )


# =========================================================
# PDF IMAGE
# =========================================================

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

        if image_width <= 0:
            return False

        if image_height <= 0:
            return False

        scale = min(
            width / image_width,
            height / image_height
        )

        final_width = (
            image_width * scale
        )

        final_height = (
            image_height * scale
        )

        final_x = (
            x
            + (width - final_width) / 2
        )

        final_y = (
            y
            + (height - final_height) / 2
        )

        pdf.drawImage(
            ImageReader(image_path),
            final_x,
            final_y,
            width=final_width,
            height=final_height,
            preserveAspectRatio=True,
            mask="auto"
        )

        return True

    except Exception as error:

        print(
            "PDF görsel hatası:",
            error
        )

        return False


# =========================================================
# CREATE PDF
# =========================================================

def create_presentation_pdf(
    presentation,
    topic,
    include_visuals=True
):

    slides = presentation.get(
        "slides",
        []
    )

    if not slides:

        raise ValueError(
            "Sunum slaytı oluşturulamadı."
        )

    title = presentation.get(
        "title",
        topic
    )

    subtitle = presentation.get(
        "subtitle",
        "K.A.R.V.I.S. - KARAHAN INC."
    )

    filename = (
        "sunum_"
        + uuid.uuid4().hex[:12]
        + ".pdf"
    )

    pdf_path = (
        GENERATED_DIR
        / filename
    )

    page_width, page_height = landscape(A4)

    pdf = canvas.Canvas(
        str(pdf_path),
        pagesize=(
            page_width,
            page_height
        )
    )

    pdf.setTitle(
        str(title)
    )

    pdf.setAuthor(
        "K.A.R.V.I.S. - KARAHAN INC."
    )

    # -----------------------------------------------------
    # KAPAK
    # -----------------------------------------------------

    pdf.setFont(
        BOLD_FONT,
        32
    )

    pdf.drawCentredString(
        page_width / 2,
        page_height * 0.62,
        str(title)
    )

    pdf.setFont(
        REGULAR_FONT,
        17
    )

    pdf.drawCentredString(
        page_width / 2,
        page_height * 0.52,
        str(subtitle)
    )

    pdf.setFont(
        REGULAR_FONT,
        10
    )

    pdf.drawCentredString(
        page_width / 2,
        45,
        "K.A.R.V.I.S. - KARAHAN INC."
    )

    pdf.showPage()

    # -----------------------------------------------------
    # SLAYTLAR
    # -----------------------------------------------------

    total_slides = len(
        slides
    )

    for number, slide in enumerate(
        slides,
        1
    ):

        slide_title = slide.get(
            "title",
            "Slayt"
        )

        bullets = slide.get(
            "bullets",
            []
        )

        visual_query = slide.get(
            "visual_query",
            slide_title
        )

        teacher_note = slide.get(
            "teacher_note",
            ""
        )

        image_path = None

        if include_visuals:

            image_path = get_slide_image(
                visual_query,
                number
            )

        # -------------------------------------------------
        # BAŞLIK
        # -------------------------------------------------

        pdf.setFont(
            BOLD_FONT,
            25
        )

        pdf.drawString(
            45,
            page_height - 55,
            str(slide_title)
        )

        # -------------------------------------------------
        # İÇERİK
        # -------------------------------------------------

        content_x = 50

        content_y = (
            page_height - 105
        )

        if image_path:

            content_width = (
                page_width * 0.46
            )

        else:

            content_width = (
                page_width * 0.50
            )

        draw_bullets(
            pdf,
            bullets,
            content_x,
            content_y,
            content_width
        )

        # -------------------------------------------------
        # GÖRSEL
        # -------------------------------------------------

        visual_x = (
            page_width * 0.54
        )

        visual_y = 125

        visual_width = (
            page_width * 0.40
        )

        visual_height = (
            page_height * 0.58
        )

        if image_path:

            success = draw_image(
                pdf,
                image_path,
                visual_x,
                visual_y,
                visual_width,
                visual_height
            )

            if not success:

                draw_fallback_visual(
                    pdf,
                    visual_x,
                    visual_y,
                    visual_width,
                    visual_height,
                    visual_query
                )

        else:

            draw_fallback_visual(
                pdf,
                visual_x,
                visual_y,
                visual_width,
                visual_height,
                visual_query
            )

        # -------------------------------------------------
        # ÖĞRETMEN NOTU
        # -------------------------------------------------

        if teacher_note:

            pdf.setFont(
                BOLD_FONT,
                10
            )

            pdf.drawString(
                45,
                68,
                "Öğretmen Notu:"
            )

            draw_wrapped_text(
                pdf,
                teacher_note,
                125,
                68,
                page_width - 170,
                REGULAR_FONT,
                9,
                11
            )

        # -------------------------------------------------
        # ALT BİLGİ
        # -------------------------------------------------

        pdf.setFont(
            REGULAR_FONT,
            8
        )

        pdf.drawString(
            45,
            25,
            "K.A.R.V.I.S. - KARAHAN INC."
        )

        pdf.drawRightString(
            page_width - 45,
            25,
            f"{number} / {total_slides}"
        )

        pdf.showPage()

    pdf.save()

    # PDF gerçekten oluşmuş mu?
    if not pdf_path.exists():

        raise FileNotFoundError(
            "PDF dosyası oluşturulamadı."
        )

    if pdf_path.stat().st_size < 1000:

        raise ValueError(
            "PDF dosyası boş veya bozuk."
        )

    return pdf_path


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():

    index_file = (
        BASE_DIR
        / "index.html"
    )

    if index_file.exists():

        return FileResponse(
            str(index_file)
        )

    return {

        "app": "K.A.R.V.I.S.",

        "company": "KARAHAN INC.",

        "version": APP_VERSION
    }


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health():

    return {

        "status": "online",

        "app": "K.A.R.V.I.S.",

        "version": APP_VERSION
    }


# =========================================================
# VERSION
# =========================================================

@app.get("/version")
def version():

    return {
        "version": APP_VERSION
    }


# =========================================================
# USERS
# =========================================================

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
def profile_login(
    request: LoginRequest
):

    username = (
        request.username
        .lower()
        .strip()
    )

    user = USERS.get(
        username
    )

    if not user:

        return JSONResponse(

            status_code=401,

            content={

                "success": False,

                "message":
                    "Kullanıcı bulunamadı."
            }
        )

    password = user.get(
        "password"
    )

    if password is not None:

        if request.password != password:

            return JSONResponse(

                status_code=401,

                content={

                    "success": False,

                    "message":
                        "Şifre hatalı."
                }
            )

    return {

        "success": True,

        "user": {

            "username": username,

            "name": user["name"],

            "role": user["role"],

            "personality":
                user["personality"]
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
def chat(
    request: ChatRequest
):

    username = (
        request.username
        .lower()
        .strip()
    )

    mode = (
        request.mode
        or
        "normal"
    )

    memory = get_memory()

    user_memory = memory.get(
        username,
        []
    )

    messages = [

        {
            "role": "system",

            "content":
                build_system_prompt(
                    username,
                    mode
                )
        }

    ]

    for item in user_memory[-10:]:

        messages.append({

            "role":
                item.get(
                    "role",
                    "user"
                ),

            "content":
                item.get(
                    "content",
                    ""
                )
        })

    messages.append({

        "role": "user",

        "content":
            request.message
    })

    answer = ask_ai(

        messages,

        temperature=0.45,

        max_tokens=3000
    )

    if username not in memory:

        memory[username] = []

    memory[username].append({

        "role": "user",

        "content":
            request.message,

        "time":
            datetime.now().isoformat()
    })

    memory[username].append({

        "role": "assistant",

        "content":
            answer,

        "time":
            datetime.now().isoformat()
    })

    memory[username] = (
        memory[username][-100:]
    )

    save_memory(
        memory
    )

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
def research(
    request: ResearchRequest
):

    context = build_research_context(
        request.query
    )

    messages = [

        {
            "role": "system",

            "content":
                build_system_prompt(
                    request.username,
                    "research"
                )
        },

        {
            "role": "user",

            "content": (
                "Araştırma konusu:\n"
                + request.query
                + "\n\n"
                + context
                + "\n\n"
                + "Bu bilgilerle düzenli bir "
                  "araştırma özeti hazırla."
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

        "query":
            request.query,

        "answer":
            answer,

        "sources":
            internet_search(
                request.query,
                8
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

        if not request.topic.strip():

            return JSONResponse(

                status_code=400,

                content={

                    "success": False,

                    "message":
                        "Sunum konusu boş bırakılamaz."
                }
            )

        slides_count = max(

            4,

            min(
                int(
                    request.slide_count
                ),
                30
            )
        )

        outline = (
            generate_presentation_outline(

                request.topic,

                slides_count
            )
        )

        pdf_path = (
            create_presentation_pdf(

                outline,

                request.topic,

                request.include_visuals
            )
        )

        filename = pdf_path.name

        # =================================================
        # ÖNEMLİ:
        # FRONTEND data.file_url BEKLİYOR
        # =================================================

        file_url = (
            "/generated/"
            + filename
        )

        return {

            "success": True,

            "title":
                outline.get(
                    "title",
                    request.topic
                ),

            "slides":
                len(
                    outline.get(
                        "slides",
                        []
                    )
                ),

            "file_url":
                file_url,

            # Geriye dönük uyumluluk
            "download_url":
                file_url
        }

    except Exception as error:

        print(
            "SUNUM HATASI:",
            error
        )

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
                    "bir hata oluştu: "
                    + str(error)
                )
            }
        )


# =========================================================
# GENERATED PDF
# =========================================================

@app.get("/generated/{filename}")
def generated_file(
    filename: str
):

    safe_name = os.path.basename(
        filename
    )

    # Sadece PDF dosyalarına izin ver
    if not safe_name.lower().endswith(
        ".pdf"
    ):

        return JSONResponse(

            status_code=400,

            content={

                "success": False,

                "message":
                    "Geçersiz dosya türü."
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

                "message":
                    "Dosya bulunamadı."
            }
        )

    return FileResponse(

        str(file_path),

        media_type="application/pdf",

        filename=safe_name
    )


# =========================================================
# MEMORY
# =========================================================

@app.get("/memory")
def memory(
    username: str = "karahan"
):

    data = get_memory()

    return {

        "username":
            username,

        "memory":
            data.get(
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

    save_memory(
        data
    )

    return {

        "success": True,

        "message":
            "Hafıza temizlendi."
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

    save_memory(
        data
    )

    return {

        "success": True,

        "message":
            "Yeni sohbet başlatıldı."
    }


# =========================================================
# ERRORS
# =========================================================

@app.get("/errors")
def errors():

    return {

        "errors":
            get_errors()
    }


@app.delete("/errors")
def delete_errors():

    save_json(
        ERROR_FILE,
        []
    )

    return {

        "success": True,

        "message":
            "Hata kayıtları temizlendi."
    }


# =========================================================
# STARTUP
# =========================================================

@app.on_event("startup")
def startup():

    print("=" * 55)

    print(
        "K.A.R.V.I.S. - KARAHAN INC."
    )

    print(
        "Version:",
        APP_VERSION
    )

    print(
        "Server hazır."
    )

    print("=" * 55)

    if REGULAR_FONT == "DejaVu":

        print(
            "Türkçe PDF fontu: AKTİF"
        )

    else:

        print(
            "UYARI: DejaVuSans.ttf bulunamadı."
        )

    if GROQ_API_KEY:

        print(
            "Groq API: AKTİF"
        )

    else:

        print(
            "Groq API: KAPALI"
        )

    if OPENROUTER_API_KEY:

        print(
            "OpenRouter fallback: AKTİF"
        )

    else:

        print(
            "OpenRouter fallback: KAPALI"
        )

    print(
        "PDF klasörü:",
        str(GENERATED_DIR)
    )

    print("=" * 55)
