# ============================================================
# K.A.R.V.I.S. - KARAHAN INC.
# Professional AI Assistant Backend
# Presentation Engine v29.0.0
# ============================================================

import os
import re
import json
import uuid
import time
import hashlib
import threading
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from pydantic import BaseModel

from openai import OpenAI

from PIL import Image, ImageDraw, ImageFont, ImageOps

from reportlab.pdfgen import canvas
from reportlab.lib.units import inch


# ============================================================
# APP
# ============================================================

APP_VERSION = "29.0.0"

BASE_DIR = Path(__file__).resolve().parent

GENERATED_DIR = BASE_DIR / "generated"
GENERATED_DIR.mkdir(exist_ok=True)

INDEX_FILE = BASE_DIR / "index.html"


app = FastAPI(
    title="K.A.R.V.I.S. - KARAHAN INC.",
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
# API KEYS
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()


groq_client = None
openrouter_client = None


if GROQ_API_KEY:
    groq_client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )


if OPENROUTER_API_KEY:
    openrouter_client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1"
    )


# ============================================================
# MODELS
# ============================================================

GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]

OPENROUTER_MODELS = [
    "openai/gpt-oss-20b:free",
]


# ============================================================
# MEMORY
# ============================================================

MEMORY_FILE = BASE_DIR / "memory.json"
ERROR_FILE = BASE_DIR / "errors.json"

memory_lock = threading.Lock()
error_lock = threading.Lock()


def read_json_file(path, default):
    try:
        if not path.exists():
            return default

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return default


def write_json_file(path, data):
    temp = path.with_suffix(".tmp")

    with open(temp, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

    temp.replace(path)


def save_error(message, details=None):
    try:
        with error_lock:
            data = read_json_file(ERROR_FILE, [])

            data.append({
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "error": str(message),
                "details": str(details or "")
            })

            data = data[-100:]

            write_json_file(
                ERROR_FILE,
                data
            )

    except Exception:
        pass


# ============================================================
# USERS
# ============================================================

USERS = {
    "karahan": {
        "name": "KARAHAN INC.",
        "password": "",
        "role": "owner",
        "style": "professional"
    },

    "betul": {
        "name": "Betül",
        "password": "1234",
        "role": "user",
        "style": "professional"
    },

    "sinem": {
        "name": "Sinem",
        "password": "3021",
        "role": "user",
        "style": "professional"
    },

    "ilknur": {
        "name": "İlknur",
        "password": "1111",
        "role": "teacher",
        "style": "academic"
    }
}


# ============================================================
# REQUEST MODELS
# ============================================================

class ChatRequest(BaseModel):
    message: str
    username: str = "karahan"
    mode: str = "normal"


class PresentationRequest(BaseModel):
    topic: str
    slide_count: int = 7
    username: str = "karahan"


# ============================================================
# AI
# ============================================================

def call_groq(prompt, model):
    if not groq_client:
        return None

    try:
        response = groq_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sen K.A.R.V.I.S. isimli profesyonel Türkçe "
                        "yapay zeka asistanısın. "
                        "Bilgileri açık, doğru ve doğal Türkçe ile ver."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.35,
            max_tokens=5000
        )

        return response.choices[0].message.content

    except Exception as e:
        save_error("Groq error", traceback.format_exc())
        return None


def call_openrouter(prompt, model):
    if not openrouter_client:
        return None

    try:
        response = openrouter_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sen K.A.R.V.I.S. isimli profesyonel Türkçe "
                        "yapay zeka asistanısın."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.35,
            max_tokens=5000
        )

        return response.choices[0].message.content

    except Exception:
        save_error(
            "OpenRouter error",
            traceback.format_exc()
        )
        return None


def ask_ai(prompt):
    for model in GROQ_MODELS:

        result = call_groq(
            prompt,
            model
        )

        if result:
            return result

    for model in OPENROUTER_MODELS:

        result = call_openrouter(
            prompt,
            model
        )

        if result:
            return result

    return None


# ============================================================
# JSON EXTRACTION
# ============================================================

def extract_json(text):
    if not text:
        return None

    text = text.strip()

    text = re.sub(
        r"^```json",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"^```",
        "",
        text
    )

    text = re.sub(
        r"```$",
        "",
        text
    )

    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:

        try:
            return json.loads(
                text[start:end + 1]
            )
        except Exception:
            pass

    return None


# ============================================================
# PRESENTATION FALLBACK
# ============================================================

def fallback_presentation(topic, slide_count):
    content_count = max(
        3,
        slide_count - 2
    )

    templates = [
        (
            "Temel Kavramlar",
            f"{topic} konusunun temel kavramları ve kapsamı ele alınmaktadır."
        ),
        (
            "Tarihsel Gelişim",
            f"{topic} ile ilgili düşüncelerin ve uygulamaların tarihsel gelişimi incelenmektedir."
        ),
        (
            "Temel Unsurlar",
            f"{topic} başlığını oluşturan temel unsurlar ve bunların birbirleriyle ilişkileri açıklanmaktadır."
        ),
        (
            "Toplumsal Etkiler",
            f"{topic} konusunun birey, toplum ve kurumlar üzerindeki etkileri değerlendirilmektedir."
        ),
        (
            "Günümüzdeki Önemi",
            f"{topic} günümüzde farklı alanlarda önemini korumakta ve yeni uygulamalarla gelişmektedir."
        ),
        (
            "Değerlendirme",
            f"{topic} açısından mevcut yaklaşımların güçlü ve sınırlı yönleri birlikte değerlendirilmektedir."
        )
    ]

    slides = []

    for i in range(content_count):

        title, paragraph = templates[
            i % len(templates)
        ]

        slides.append({
            "title": title,
            "paragraph": paragraph,
            "visual_query": (
                f"{topic} {title} "
                f"academic educational"
            )
        })

    return {
        "title": topic,
        "subtitle": "Akademik Sunum",
        "cover_visual_query": (
            f"{topic} academic professional"
        ),
        "slides": slides,
        "conclusion": {
            "title": "Sonuç ve Değerlendirme",
            "paragraph": (
                f"{topic} farklı boyutlarıyla "
                f"değerlendirildiğinde, konunun temel "
                f"kavramlarının ve toplumsal etkilerinin "
                f"birlikte ele alınması gerektiği görülmektedir."
            ),
            "visual_query": (
                f"{topic} conclusion academic"
            )
        }
    }


def create_presentation_outline(topic, slide_count):
    content_count = max(
        3,
        slide_count - 2
    )

    prompt = f"""
K.A.R.V.I.S. için profesyonel bir üniversite sunumu hazırla.

KONU:
{topic}

TOPLAM SLAYT SAYISI:
{slide_count}

ÖNEMLİ:
Toplam slayt sayısı tam olarak {slide_count} olmalı.

Yapı:

1. Kapak
2. {content_count} adet içerik slaytı
3. Sonuç ve Değerlendirme

Yalnızca JSON döndür.

Format:

{{
  "title": "Ana başlık",
  "subtitle": "Kısa akademik alt başlık",
  "cover_visual_query": "English image search query",
  "slides": [
    {{
      "title": "Kısa başlık",
      "paragraph": "Akademik açıklama",
      "visual_query": "Unique English visual search query"
    }}
  ],
  "conclusion": {{
    "title": "Sonuç ve Değerlendirme",
    "paragraph": "Akademik sonuç",
    "visual_query": "Unique English visual search query"
  }}
}}

Kurallar:

- Türkçe yaz.
- Her slayt farklı bir konuyu anlatsın.
- Başlıklar birbirinin aynısı olmasın.
- Paragraflar birbirinin aynısı olmasın.
- Her paragraf yaklaşık 80-130 kelime olsun.
- Akademik ama anlaşılır dil kullan.
- Gereksiz madde işareti kullanma.
- Visual query alanları İngilizce olsun.
- Her visual query farklı olsun.
- Görseller konuyla doğrudan ilgili olsun.
- Sonuç slaytı gerçekten konuyu değerlendirsin.
- JSON dışında hiçbir şey yazma.
"""

    result = ask_ai(prompt)

    data = extract_json(result)

    if not data:
        return fallback_presentation(
            topic,
            slide_count
        )

    slides = data.get("slides", [])

    clean_slides = []

    for slide in slides:

        if not isinstance(slide, dict):
            continue

        title = str(
            slide.get("title", "")
        ).strip()

        paragraph = str(
            slide.get("paragraph", "")
        ).strip()

        query = str(
            slide.get("visual_query", "")
        ).strip()

        if not title:
            continue

        if not paragraph:
            continue

        if not query:
            query = (
                f"{topic} {title} academic"
            )

        clean_slides.append({
            "title": title,
            "paragraph": paragraph,
            "visual_query": query
        })

    if len(clean_slides) < content_count:
        return fallback_presentation(
            topic,
            slide_count
        )

    clean_slides = clean_slides[
        :content_count
    ]

    conclusion = data.get(
        "conclusion",
        {}
    )

    if not isinstance(conclusion, dict):
        conclusion = {}

    return {
        "title": str(
            data.get("title") or topic
        ),
        "subtitle": str(
            data.get("subtitle") or "Akademik Sunum"
        ),
        "cover_visual_query": str(
            data.get(
                "cover_visual_query",
                f"{topic} academic"
            )
        ),
        "slides": clean_slides,
        "conclusion": {
            "title": str(
                conclusion.get(
                    "title",
                    "Sonuç ve Değerlendirme"
                )
            ),
            "paragraph": str(
                conclusion.get(
                    "paragraph",
                    ""
                )
            ),
            "visual_query": str(
                conclusion.get(
                    "visual_query",
                    f"{topic} conclusion academic"
                )
            )
        }
    }


# ============================================================
# IMAGE SEARCH
# ============================================================

IMAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "KARVIS/29.0 "
        "PresentationBot"
    )
}


def get_wikimedia_candidates(query):
    try:

        url = (
            "https://commons.wikimedia.org/w/api.php"
        )

        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,
            "gsrlimit": 15,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "iiurlwidth": 1400,
            "format": "json"
        }

        r = requests.get(
            url,
            params=params,
            headers=IMAGE_HEADERS,
            timeout=15
        )

        if r.status_code != 200:
            return []

        data = r.json()

        pages = (
            data.get("query", {})
            .get("pages", {})
        )

        results = []

        for page in pages.values():

            info = (
                page.get("imageinfo") or []
            )

            if not info:
                continue

            item = info[0]

            image_url = item.get(
                "thumburl"
            ) or item.get("url")

            mime = item.get(
                "mime",
                ""
            )

            if not image_url:
                continue

            if not mime.startswith("image/"):
                continue

            results.append(image_url)

        return results

    except Exception:
        return []


def get_openverse_candidates(query):
    try:

        url = (
            "https://api.openverse.org/v1/images/"
        )

        params = {
            "q": query,
            "page_size": 15
        }

        r = requests.get(
            url,
            params=params,
            headers=IMAGE_HEADERS,
            timeout=15
        )

        if r.status_code != 200:
            return []

        data = r.json()

        results = []

        for item in data.get(
            "results",
            []
        ):

            image_url = (
                item.get("thumbnail")
                or item.get("url")
            )

            if image_url:
                results.append(
                    image_url
                )

        return results

    except Exception:
        return []


def image_hash(image):
    try:

        small = image.convert(
            "RGB"
        ).resize(
            (96, 96)
        )

        raw = small.tobytes()

        return hashlib.sha256(
            raw
        ).hexdigest()

    except Exception:
        return None


def download_image_unique(
    url,
    used_urls,
    used_hashes,
    lock
):
    try:

        with lock:

            if url in used_urls:
                return None

        response = requests.get(
            url,
            headers=IMAGE_HEADERS,
            timeout=20
        )

        if response.status_code != 200:
            return None

        content_type = response.headers.get(
            "Content-Type",
            ""
        ).lower()

        if not content_type.startswith(
            "image/"
        ):
            return None

        from io import BytesIO

        image = Image.open(
            BytesIO(response.content)
        )

        image.load()

        if image.width < 300 or image.height < 200:
            return None

        h = image_hash(image)

        if not h:
            return None

        with lock:

            if (
                url in used_urls
                or h in used_hashes
            ):
                return None

            used_urls.add(url)
            used_hashes.add(h)

        return image.convert("RGB")

    except Exception:
        return None


def find_unique_image(
    queries,
    used_urls,
    used_hashes,
    lock
):
    candidates = []

    for query in queries:

        candidates.extend(
            get_wikimedia_candidates(
                query
            )
        )

        candidates.extend(
            get_openverse_candidates(
                query
            )
        )

        if len(candidates) >= 20:
            break

    unique_candidates = []

    seen = set()

    for url in candidates:

        if url in seen:
            continue

        seen.add(url)

        unique_candidates.append(url)

    for url in unique_candidates:

        image = download_image_unique(
            url,
            used_urls,
            used_hashes,
            lock
        )

        if image is not None:
            return image

    return None


# ============================================================
# FONT SYSTEM
# ============================================================

def find_font(bold=False):

    if bold:

        candidates = [
            BASE_DIR / "fonts" / "DejaVuSans-Bold.ttf",
            Path(
                "/usr/share/fonts/truetype/dejavu/"
                "DejaVuSans-Bold.ttf"
            ),
            Path(
                "/usr/share/fonts/truetype/liberation2/"
                "LiberationSans-Bold.ttf"
            )
        ]

    else:

        candidates = [
            BASE_DIR / "fonts" / "DejaVuSans.ttf",
            Path(
                "/usr/share/fonts/truetype/dejavu/"
                "DejaVuSans.ttf"
            ),
            Path(
                "/usr/share/fonts/truetype/liberation2/"
                "LiberationSans-Regular.ttf"
            )
        ]

    for path in candidates:

        if path.exists():
            return str(path)

    return None


FONT_REGULAR = find_font(False)
FONT_BOLD = find_font(True)


def karvis_font(size, bold=False):

    path = (
        FONT_BOLD
        if bold
        else FONT_REGULAR
    )

    try:

        if path:
            return ImageFont.truetype(
                path,
                size
            )

    except Exception:
        pass

    return ImageFont.load_default()


# ============================================================
# SLIDE DESIGN
# ============================================================

SLIDE_WIDTH = 1600
SLIDE_HEIGHT = 900

PDF_WIDTH = 16 * inch
PDF_HEIGHT = 9 * inch


def wrap_pixel_text(
    draw,
    text,
    font,
    max_width
):
    words = str(text or "").split()

    lines = []

    current = ""

    for word in words:

        candidate = (
            word
            if not current
            else current + " " + word
        )

        try:
            width = draw.textlength(
                candidate,
                font=font
            )

        except Exception:

            width = len(candidate) * 12

        if width <= max_width:

            current = candidate

        else:

            if current:
                lines.append(
                    current
                )

            current = word

    if current:
        lines.append(
            current
        )

    return lines


def draw_wrapped(
    draw,
    text,
    xy,
    font,
    fill,
    max_width,
    line_spacing=10
):
    x, y = xy

    lines = wrap_pixel_text(
        draw,
        text,
        font,
        max_width
    )

    try:
        line_height = (
            font.size +
            line_spacing
        )

    except Exception:
        line_height = 35

    for line in lines:

        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill
        )

        y += line_height

    return y


def rounded_mask(
    size,
    radius
):
    mask = Image.new(
        "L",
        size,
        0
    )

    draw = ImageDraw.Draw(
        mask
    )

    draw.rounded_rectangle(
        (
            0,
            0,
            size[0],
            size[1]
        ),
        radius=radius,
        fill=255
    )

    return mask


def prepare_image(
    image,
    size
):
    image = image.convert(
        "RGB"
    )

    return ImageOps.fit(
        image,
        size,
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5)
    )


def paste_round_image(
    base,
    image,
    box,
    radius=30
):
    x, y, w, h = box

    image = prepare_image(
        image,
        (w, h)
    )

    mask = rounded_mask(
        (w, h),
        radius
    )

    base.paste(
        image,
        (x, y),
        mask
    )


# ============================================================
# COVER
# ============================================================

def create_cover_slide(
    title,
    subtitle,
    image,
    output_path
):

    img = Image.new(
        "RGB",
        (
            SLIDE_WIDTH,
            SLIDE_HEIGHT
        ),
        (5, 10, 18)
    )

    if image is not None:

        bg = prepare_image(
            image,
            (
                SLIDE_WIDTH,
                SLIDE_HEIGHT
            )
        )

        dark = Image.new(
            "RGBA",
            bg.size,
            (2, 7, 13, 165)
        )

        bg = Image.alpha_composite(
            bg.convert("RGBA"),
            dark
        ).convert("RGB")

        img = bg

    draw = ImageDraw.Draw(img)

    draw.rectangle(
        (80, 75, 410, 81),
        fill=(0, 229, 255)
    )

    draw.text(
        (80, 110),
        "K.A.R.V.I.S.",
        font=karvis_font(
            26,
            True
        ),
        fill=(0, 229, 255)
    )

    draw.text(
        (80, 148),
        "KARAHAN INC.",
        font=karvis_font(
            17
        ),
        fill=(160, 175, 190)
    )

    title_font = karvis_font(
        72,
        True
    )

    y = 290

    lines = wrap_pixel_text(
        draw,
        title,
        title_font,
        1050
    )

    for line in lines[:3]:

        draw.text(
            (80, y),
            line,
            font=title_font,
            fill=(245, 250, 255)
        )

        y += 88

    draw.text(
        (85, y + 20),
        subtitle,
        font=karvis_font(
            28
        ),
        fill=(180, 195, 210)
    )

    draw.text(
        (80, 810),
        "AKADEMİK SUNUM",
        font=karvis_font(
            18,
            True
        ),
        fill=(0, 229, 255)
    )

    draw.text(
        (80, 845),
        "K.A.R.V.I.S. • KARAHAN INC.",
        font=karvis_font(
            15
        ),
        fill=(110, 125, 140)
    )

    img.save(
        output_path,
        "PNG",
        optimize=True
    )


# ============================================================
# CONTENT SLIDE
# ============================================================

def create_content_slide(
    slide_number,
    total_slides,
    title,
    paragraph,
    image,
    output_path
):

    img = Image.new(
        "RGB",
        (
            SLIDE_WIDTH,
            SLIDE_HEIGHT
        ),
        (5, 11, 19)
    )

    draw = ImageDraw.Draw(img)

    # Top line

    draw.rectangle(
        (70, 55, 1530, 58),
        fill=(18, 45, 58)
    )

    draw.rectangle(
        (70, 55, 280, 58),
        fill=(0, 229, 255)
    )

    # Logo

    draw.text(
        (70, 82),
        "K.A.R.V.I.S.",
        font=karvis_font(
            21,
            True
        ),
        fill=(0, 229, 255)
    )

    draw.text(
        (70, 111),
        "KARAHAN INC.",
        font=karvis_font(
            14
        ),
        fill=(110, 130, 145)
    )

    # Title

    title_font = karvis_font(
        45,
        True
    )

    title_lines = wrap_pixel_text(
        draw,
        title,
        title_font,
        850
    )

    y_title = 165

    for line in title_lines[:2]:

        draw.text(
            (70, y_title),
            line,
            font=title_font,
            fill=(245, 250, 255)
        )

        y_title += 56

    # Left card

    left_x = 70
    left_y = 300
    left_w = 700
    left_h = 500

    draw.rounded_rectangle(
        (
            left_x,
            left_y,
            left_x + left_w,
            left_y + left_h
        ),
        radius=28,
        fill=(10, 20, 30),
        outline=(22, 48, 62),
        width=2
    )

    draw.text(
        (105, 335),
        "AKADEMİK AÇIKLAMA",
        font=karvis_font(
            18,
            True
        ),
        fill=(0, 229, 255)
    )

    draw.rectangle(
        (105, 372, 190, 376),
        fill=(0, 229, 255)
    )

    draw_wrapped(
        draw,
        paragraph,
        (105, 415),
        karvis_font(
            25
        ),
        (215, 225, 235),
        625,
        12
    )

    # Image

    image_x = 825
    image_y = 165
    image_w = 705
    image_h = 635

    draw.rounded_rectangle(
        (
            image_x,
            image_y,
            image_x + image_w,
            image_y + image_h
        ),
        radius=32,
        fill=(9, 18, 27),
        outline=(25, 51, 65),
        width=2
    )

    if image is not None:

        paste_round_image(
            img,
            image,
            (
                image_x + 10,
                image_y + 10,
                image_w - 20,
                image_h - 20
            ),
            25
        )

    else:

        draw.text(
            (
                image_x + 220,
                image_y + 280
            ),
            "K.A.R.V.I.S.",
            font=karvis_font(
                42,
                True
            ),
            fill=(0, 229, 255)
        )

    # Footer

    draw.text(
        (70, 842),
        "K.A.R.V.I.S. • KARAHAN INC.",
        font=karvis_font(
            15
        ),
        fill=(90, 110, 125)
    )

    draw.text(
        (1430, 842),
        f"{slide_number:02d} / {total_slides:02d}",
        font=karvis_font(
            16,
            True
        ),
        fill=(0, 229, 255)
    )

    img.save(
        output_path,
        "PNG",
        optimize=True
    )


# ============================================================
# CONCLUSION
# ============================================================

def create_conclusion_slide(
    total_slides,
    title,
    paragraph,
    image,
    output_path
):

    img = Image.new(
        "RGB",
        (
            SLIDE_WIDTH,
            SLIDE_HEIGHT
        ),
        (5, 11, 19)
    )

    draw = ImageDraw.Draw(img)

    draw.rectangle(
        (70, 55, 1530, 58),
        fill=(18, 45, 58)
    )

    draw.rectangle(
        (70, 55, 520, 58),
        fill=(0, 229, 255)
    )

    draw.text(
        (70, 90),
        "K.A.R.V.I.S.",
        font=karvis_font(
            22,
            True
        ),
        fill=(0, 229, 255)
    )

    draw.text(
        (70, 120),
        "KARAHAN INC.",
        font=karvis_font(
            14
        ),
        fill=(110, 130, 145)
    )

    draw.text(
        (70, 205),
        title,
        font=karvis_font(
            54,
            True
        ),
        fill=(245, 250, 255)
    )

    draw.rounded_rectangle(
        (70, 310, 820, 750),
        radius=30,
        fill=(10, 20, 30),
        outline=(22, 48, 62),
        width=2
    )

    draw.text(
        (110, 350),
        "SONUÇ VE DEĞERLENDİRME",
        font=karvis_font(
            19,
            True
        ),
        fill=(0, 229, 255)
    )

    draw_wrapped(
        draw,
        paragraph,
        (110, 405),
        karvis_font(
            27
        ),
        (220, 230, 238),
        650,
        13
    )

    if image is not None:

        paste_round_image(
            img,
            image,
            (
                880,
                185,
                620,
                565
            ),
            35
        )

    else:

        draw.rounded_rectangle(
            (880, 185, 1500, 750),
            radius=35,
            fill=(8, 22, 31),
            outline=(0, 229, 255),
            width=2
        )

        draw.text(
            (1050, 430),
            "K.A.R.V.I.S.",
            font=karvis_font(
                42,
                True
            ),
            fill=(0, 229, 255)
        )

    draw.text(
        (70, 835),
        "K.A.R.V.I.S. • KARAHAN INC.",
        font=karvis_font(
            15
        ),
        fill=(90, 110, 125)
    )

    draw.text(
        (1430, 835),
        f"{total_slides:02d} / {total_slides:02d}",
        font=karvis_font(
            16,
            True
        ),
        fill=(0, 229, 255)
    )

    img.save(
        output_path,
        "PNG",
        optimize=True
    )


# ============================================================
# PDF CREATION
# ============================================================

def create_presentation_pdf(
    presentation_id,
    outline,
    images
):

    title = outline["title"]

    subtitle = outline.get(
        "subtitle",
        "Akademik Sunum"
    )

    slides = outline["slides"]

    conclusion = outline[
        "conclusion"
    ]

    total_slides = (
        len(slides) + 2
    )

    presentation_dir = (
        GENERATED_DIR /
        f"presentation_{presentation_id}"
    )

    slides_dir = (
        presentation_dir /
        "slides"
    )

    slides_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    slide_paths = []

    # Cover

    cover_path = (
        slides_dir /
        "slide_01.png"
    )

    create_cover_slide(
        title,
        subtitle,
        images.get("cover"),
        str(cover_path)
    )

    slide_paths.append(
        cover_path
    )

    # Content

    for index, slide in enumerate(
        slides,
        start=2
    ):

        slide_path = (
            slides_dir /
            f"slide_{index:02d}.png"
        )

        create_content_slide(
            slide_number=index,
            total_slides=total_slides,
            title=slide["title"],
            paragraph=slide["paragraph"],
            image=images.get(
                f"slide_{index}"
            ),
            output_path=str(
                slide_path
            )
        )

        slide_paths.append(
            slide_path
        )

    # Conclusion

    conclusion_path = (
        slides_dir /
        f"slide_{total_slides:02d}.png"
    )

    create_conclusion_slide(
        total_slides=total_slides,
        title=conclusion[
            "title"
        ],
        paragraph=conclusion[
            "paragraph"
        ],
        image=images.get(
            "conclusion"
        ),
        output_path=str(
            conclusion_path
        )
    )

    slide_paths.append(
        conclusion_path
    )

    # PDF

    pdf_filename = (
        f"karvis_sunum_{presentation_id}.pdf"
    )

    pdf_path = (
        GENERATED_DIR /
        pdf_filename
    )

    pdf = canvas.Canvas(
        str(pdf_path),
        pagesize=(
            PDF_WIDTH,
            PDF_HEIGHT
        )
    )

    for path in slide_paths:

        pdf.drawImage(
            str(path),
            0,
            0,
            width=PDF_WIDTH,
            height=PDF_HEIGHT,
            preserveAspectRatio=False,
            mask="auto"
        )

        pdf.showPage()

    pdf.save()

    return pdf_filename


# ============================================================
# PRESENTATION JOB SYSTEM
# ============================================================

PRESENTATION_JOBS = {}

presentation_lock = threading.Lock()


def create_job():
    job_id = uuid.uuid4().hex

    with presentation_lock:

        PRESENTATION_JOBS[job_id] = {
            "id": job_id,
            "status": "queued",
            "progress": 0,
            "message": "Sunum hazırlanıyor...",
            "file": None,
            "download_url": None,
            "error": None
        }

    return job_id


def update_job(
    job_id,
    **kwargs
):
    with presentation_lock:

        if job_id in PRESENTATION_JOBS:
            PRESENTATION_JOBS[
                job_id
            ].update(kwargs)


def presentation_worker(
    job_id,
    topic,
    slide_count
):

    try:

        update_job(
            job_id,
            status="working",
            progress=5,
            message="Sunum planı oluşturuluyor..."
        )

        outline = create_presentation_outline(
            topic,
            slide_count
        )

        slides = outline[
            "slides"
        ]

        update_job(
            job_id,
            progress=20,
            message="Görseller aranıyor..."
        )

        used_urls = set()
        used_hashes = set()

        lock = threading.Lock()

        image_tasks = {}

        image_tasks[
            "cover"
        ] = [
            outline.get(
                "cover_visual_query",
                topic
            )
        ]

        for index, slide in enumerate(
            slides,
            start=2
        ):

            image_tasks[
                f"slide_{index}"
            ] = [
                slide.get(
                    "visual_query",
                    f"{topic} academic"
                )
            ]

        image_tasks[
            "conclusion"
        ] = [
            outline[
                "conclusion"
            ].get(
                "visual_query",
                f"{topic} conclusion"
            )
        ]

        images = {}

        total_tasks = len(
            image_tasks
        )

        completed = 0

        with ThreadPoolExecutor(
            max_workers=4
        ) as executor:

            futures = {}

            for key, queries in image_tasks.items():

                future = executor.submit(
                    find_unique_image,
                    queries,
                    used_urls,
                    used_hashes,
                    lock
                )

                futures[
                    future
                ] = key

            for future in as_completed(
                futures
            ):

                key = futures[
                    future
                ]

                try:

                    images[
                        key
                    ] = future.result()

                except Exception:

                    images[
                        key
                    ] = None

                completed += 1

                progress = (
                    20 +
                    int(
                        completed /
                        total_tasks *
                        45
                    )
                )

                update_job(
                    job_id,
                    progress=progress,
                    message=(
                        f"Görseller hazırlanıyor "
                        f"({completed}/{total_tasks})..."
                    )
                )

        update_job(
            job_id,
            progress=70,
            message="Profesyonel slaytlar oluşturuluyor..."
        )

        pdf_filename = create_presentation_pdf(
            presentation_id=job_id,
            outline=outline,
            images=images
        )

        update_job(
            job_id,
            status="completed",
            progress=100,
            message="Sunum hazırlandı.",
            file=pdf_filename,
            download_url=(
                f"/generated/{pdf_filename}"
            )
        )

    except Exception as e:

        save_error(
            "Presentation worker error",
            traceback.format_exc()
        )

        update_job(
            job_id,
            status="error",
            progress=0,
            message="Sunum oluşturulamadı.",
            error=str(e)
        )


# ============================================================
# ROUTES
# ============================================================

@app.get("/")
async def home():

    if not INDEX_FILE.exists():

        return JSONResponse({
            "app": "K.A.R.V.I.S.",
            "version": APP_VERSION,
            "status": "online"
        })

    return FileResponse(
        INDEX_FILE
    )


@app.get("/health")
async def health():

    return {
        "status": "online",
        "app": "K.A.R.V.I.S.",
        "version": APP_VERSION,
        "groq": bool(GROQ_API_KEY),
        "openrouter": bool(
            OPENROUTER_API_KEY
        )
    }


# ============================================================
# CHAT
# ============================================================

@app.post("/chat")
async def chat(request: ChatRequest):

    message = (
        request.message or ""
    ).strip()

    if not message:

        return {
            "response": "Nasıl yardımcı olabilirim efendim?"
        }

    username = (
        request.username
        or "karahan"
    )

    mode = (
        request.mode
        or "normal"
    )

    system_instruction = f"""
Sen K.A.R.V.I.S. isimli kişisel
yapay zeka asistanısın.

Kullanıcı:
{username}

Mod:
{mode}

Yanıtların:
- Türkçe
- doğal
- profesyonel
- anlaşılır
- gereksiz uzun olmayan
- yardımcı

olmalıdır.
"""

    result = ask_ai(
        system_instruction +
        "\n\nKullanıcı mesajı:\n" +
        message
    )

    if not result:

        result = (
            "Şu anda yapay zeka servislerine "
            "bağlanamıyorum. API anahtarlarını "
            "kontrol etmen gerekiyor."
        )

    return {
        "response": result,
        "message": result
    }


# ============================================================
# PRESENTATION
# ============================================================

@app.post("/presentation")
async def create_presentation(
    request: PresentationRequest,
    background_tasks: BackgroundTasks
):

    topic = (
        request.topic or ""
    ).strip()

    if not topic:

        raise HTTPException(
            status_code=400,
            detail="Sunum konusu boş olamaz."
        )

    slide_count = max(
        5,
        min(
            int(request.slide_count),
            12
        )
    )

    job_id = create_job()

    background_tasks.add_task(
        presentation_worker,
        job_id,
        topic,
        slide_count
    )

    return {
        "success": True,
        "job_id": job_id,
        "status": "queued",
        "message": "Sunum oluşturuluyor..."
    }


@app.get(
    "/presentation-status/{job_id}"
)
async def presentation_status(
    job_id: str
):

    with presentation_lock:

        job = PRESENTATION_JOBS.get(
            job_id
        )

        if not job:

            raise HTTPException(
                status_code=404,
                detail="Sunum bulunamadı."
            )

        return dict(job)


# ============================================================
# GENERATED FILES
# ============================================================

@app.get(
    "/generated/{filename}"
)
async def generated_file(
    filename: str
):

    # Path traversal koruması

    safe_name = Path(
        filename
    ).name

    file_path = (
        GENERATED_DIR /
        safe_name
    )

    if not file_path.exists():

        raise HTTPException(
            status_code=404,
            detail="Dosya bulunamadı."
        )

    if not file_path.is_file():

        raise HTTPException(
            status_code=404,
            detail="Dosya bulunamadı."
        )

    # PDF ise indirme davranışı

    if safe_name.lower().endswith(
        ".pdf"
    ):

        return FileResponse(
            path=file_path,
            media_type="application/pdf",
            filename=safe_name,
            headers={
                "Content-Disposition":
                    f'attachment; filename="{safe_name}"'
            }
        )

    return FileResponse(
        path=file_path
    )


# ============================================================
# MEMORY
# ============================================================

@app.get("/memory")
async def get_memory():

    with memory_lock:

        return {
            "memory": read_json_file(
                MEMORY_FILE,
                []
            )
        }


@app.post("/memory")
async def add_memory(data: dict):

    text = str(
        data.get(
            "text",
            ""
        )
    ).strip()

    if not text:

        return {
            "success": False
        }

    with memory_lock:

        memories = read_json_file(
            MEMORY_FILE,
            []
        )

        memories.append({
            "id": uuid.uuid4().hex,
            "text": text,
            "created_at":
                time.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
        })

        memories = memories[-200:]

        write_json_file(
            MEMORY_FILE,
            memories
        )

    return {
        "success": True,
        "memory": memories
    }


# ============================================================
# NEW CHAT
# ============================================================

@app.post("/new-chat")
async def new_chat():

    return {
        "success": True,
        "message": "Yeni sohbet başlatıldı."
    }


# ============================================================
# ERRORS
# ============================================================

@app.get("/errors")
async def errors():

    return {
        "errors": read_json_file(
            ERROR_FILE,
            []
        )
    }


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
async def startup():

    GENERATED_DIR.mkdir(
        exist_ok=True
    )

    print("=" * 60)
    print("K.A.R.V.I.S. - KARAHAN INC.")
    print(f"Version: {APP_VERSION}")
    print("Backend: ONLINE")
    print(
        "Groq:",
        "ACTIVE"
        if GROQ_API_KEY
        else "NOT CONFIGURED"
    )
    print(
        "OpenRouter:",
        "ACTIVE"
        if OPENROUTER_API_KEY
        else "NOT CONFIGURED"
    )
    print("Presentation Engine: 16:9")
    print("PDF Download: ENABLED")
    print("=" * 60)


# ============================================================
# LOCAL RUN
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                "8000"
            )
        ),
        reload=False
    )
