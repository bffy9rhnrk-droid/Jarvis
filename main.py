# ============================================================
# K.A.R.V.I.S. - KARAHAN INC.
# Professional AI Assistant Backend
# Presentation Engine v29.1.0
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

APP_VERSION = "29.1.0"

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

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY",
    ""
).strip()

OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    ""
).strip()


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
# FILES
# ============================================================

MEMORY_FILE = BASE_DIR / "memory.json"

ERROR_FILE = BASE_DIR / "errors.json"


memory_lock = threading.Lock()

error_lock = threading.Lock()

presentation_lock = threading.Lock()


PRESENTATION_JOBS = {}


# ============================================================
# JSON FUNCTIONS
# ============================================================

def read_json_file(
    path,
    default
):

    try:

        if not path.exists():
            return default

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception:

        return default


def write_json_file(
    path,
    data
):

    temp = path.with_suffix(
        ".tmp"
    )

    with open(
        temp,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

    temp.replace(path)


# ============================================================
# ERROR LOG
# ============================================================

def save_error(
    message,
    details=None
):

    try:

        with error_lock:

            data = read_json_file(
                ERROR_FILE,
                []
            )

            data.append({
                "time":
                    time.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                "error":
                    str(message),
                "details":
                    str(details or "")
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


class LoginRequest(BaseModel):

    username: str

    password: str = ""


# ============================================================
# KARVIS SYSTEM
# ============================================================

BASE_SYSTEM = """
Sen K.A.R.V.I.S. isimli profesyonel Türkçe
yapay zeka asistanısın.

HİTAP KURALI:

- Kullanıcıya gerektiğinde "Hocam" şeklinde hitap et.
- "Hocam 😄" gibi ifadeler kullanma.
- Gereksiz emoji kullanma.
- Aşırı samimi veya günlük ifadeler kullanma.
- "Bence şöyle yapalım hocam" gibi ifadelerden kaçın.
- Kurumsal, akademik ve profesyonel bir dil kullan.

GENEL CEVAP STANDARDI:

- Soruyu doğrudan cevapla.
- Gerekiyorsa başlık kullan.
- Gerekiyorsa açıklama kullan.
- Gerekiyorsa maddeler kullan.
- Gerekiyorsa sonuç bölümü ekle.
- Gereksiz tekrar yapma.
- Bilmediğin bilgiyi kesinmiş gibi sunma.
- Teknik konularda uygulanabilir ve açık adımlar ver.
- Türkçe karakterleri doğru kullan.
"""


# ============================================================
# MODE SYSTEM
# ============================================================

def get_mode_instruction(
    mode
):

    mode = (
        mode or "normal"
    ).lower().strip()


    # --------------------------------------------------------
    # ARAŞTIRMA
    # --------------------------------------------------------

    if mode in (
        "research",
        "araştırma",
        "arastirma"
    ):

        return """

ARAŞTIRMA MODU:

Cevabı mümkün olduğunda:

1. Yöntem
2. Bulgular
3. Kaynak / Dayanak
4. Değerlendirme

şeklinde düzenle.

Kaynak verilmediyse kaynak uydurma.

Güncel bilgi gerekiyorsa doğrulanması
gerektiğini belirt.

Kesin bilgi ile tahmini bilgiyi birbirinden ayır.
"""


    # --------------------------------------------------------
    # DERS
    # --------------------------------------------------------

    if mode in (
        "lesson",
        "ders",
        "academic",
        "akademik"
    ):

        return """

DERS MODU:

Öğretici fakat akademik bir dil kullan.

Konuyu:

- Tanım
- Açıklama
- Örnek
- Sonuç

mantığında anlat.

Öğrencinin konuyu gerçekten anlamasını hedefle.
"""


    # --------------------------------------------------------
    # QUIZ
    # --------------------------------------------------------

    if mode in (
        "quiz",
        "quiz_mode",
        "sınav",
        "sinav"
    ):

        return """

QUIZ MODU:

Kullanıcıya doğrudan doğru cevabı verme.

Öncelikle kullanıcının cevap vermesini sağla.

Yanlış cevap verilirse:

- Doğrudan cevabı söyleme.
- Kısa bir ipucu ver.
- Kullanıcının tekrar düşünmesini sağla.

Kullanıcı açıkça "cevabı göster"
veya "doğru cevap nedir" derse cevabı açıklayabilirsin.

Sınav formatına uygun davran.
"""


    # --------------------------------------------------------
    # SUNUM
    # --------------------------------------------------------

    if mode in (
        "presentation",
        "sunum"
    ):

        return """

SUNUM MODU:

Metinleri kısa ve okunabilir tut.

Slayt üzerinde uzun akademik makale
bulundurulmaz.

Başlıklar kısa olmalı.

Ana fikir açık olmalı.

Sunum sırasında okunabilecek
profesyonel metinler üret.
"""


    # --------------------------------------------------------
    # NORMAL
    # --------------------------------------------------------

    return """

NORMAL MOD:

Profesyonel, açık, düzenli
ve anlaşılır cevaplar üret.
"""


# ============================================================
# AI - GROQ
# ============================================================

def call_groq(
    prompt,
    model
):

    if not groq_client:

        return None


    try:

        response = (
            groq_client
            .chat
            .completions
            .create(
                model=model,

                messages=[
                    {
                        "role": "system",
                        "content":
                            BASE_SYSTEM
                    },
                    {
                        "role": "user",
                        "content":
                            prompt
                    }
                ],

                temperature=0.30,

                max_tokens=5000
            )
        )


        return (
            response
            .choices[0]
            .message
            .content
        )


    except Exception:

        save_error(
            "Groq error",
            traceback.format_exc()
        )

        return None


# ============================================================
# AI - OPENROUTER
# ============================================================

def call_openrouter(
    prompt,
    model
):

    if not openrouter_client:

        return None


    try:

        response = (
            openrouter_client
            .chat
            .completions
            .create(
                model=model,

                messages=[
                    {
                        "role": "system",
                        "content":
                            BASE_SYSTEM
                    },
                    {
                        "role": "user",
                        "content":
                            prompt
                    }
                ],

                temperature=0.30,

                max_tokens=5000
            )
        )


        return (
            response
            .choices[0]
            .message
            .content
        )


    except Exception:

        save_error(
            "OpenRouter error",
            traceback.format_exc()
        )

        return None


# ============================================================
# AI FALLBACK
# ============================================================

def ask_ai(
    prompt
):

    # Önce Groq

    for model in GROQ_MODELS:

        result = call_groq(
            prompt,
            model
        )

        if result:

            return result


    # Sonra OpenRouter

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

def extract_json(
    text
):

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

        return json.loads(
            text
        )

    except Exception:

        pass


    start = text.find(
        "{"
    )

    end = text.rfind(
        "}"
    )


    if (
        start >= 0
        and end > start
    ):

        try:

            return json.loads(
                text[
                    start:
                    end + 1
                ]
            )

        except Exception:

            pass


    return None


# ============================================================
# PRESENTATION
# 7 SLIDES - SABİT
# ============================================================

PRESENTATION_SLIDE_COUNT = 7


# ============================================================
# FALLBACK PRESENTATION
# ============================================================

def fallback_presentation(
    topic
):

    return {

        "title":
            topic,

        "subtitle":
            "Akademik Sunum",

        "cover_visual_query":
            f"{topic} academic professional",

        "slides": [

            {
                "title":
                    "Temel Kavramlar",

                "paragraph":
                    f"{topic} konusunun temel kavramları, kapsamı ve ana özellikleri açıklanmaktadır.",

                "visual_query":
                    f"{topic} basic concepts academic"
            },

            {
                "title":
                    "Tarihsel Gelişim",

                "paragraph":
                    f"{topic} ile ilgili gelişmelerin tarihsel süreci ve önemli dönüm noktaları ele alınmaktadır.",

                "visual_query":
                    f"{topic} history timeline academic"
            },

            {
                "title":
                    "Temel Unsurlar",

                "paragraph":
                    f"{topic} başlığını oluşturan temel unsurlar ve bu unsurlar arasındaki ilişkiler değerlendirilmektedir.",

                "visual_query":
                    f"{topic} key elements academic"
            },

            {
                "title":
                    "Toplumsal Etkiler",

                "paragraph":
                    f"{topic} konusunun bireyler, toplum ve kurumlar üzerindeki başlıca etkileri incelenmektedir.",

                "visual_query":
                    f"{topic} social impact academic"
            },

            {
                "title":
                    "Günümüzdeki Önemi",

                "paragraph":
                    f"{topic} günümüzde farklı alanlarda önemini korumakta ve yeni uygulamalarla gelişmektedir.",

                "visual_query":
                    f"{topic} modern application academic"
            }

        ],

        "conclusion": {

            "title":
                "Sonuç ve Değerlendirme",

            "paragraph":
                f"{topic} farklı boyutlarıyla değerlendirildiğinde, temel kavramların tarihsel gelişim ve güncel etkilerle birlikte ele alınması gerektiği görülmektedir.",

            "visual_query":
                f"{topic} conclusion academic"
        }
    }


# ============================================================
# CREATE PRESENTATION OUTLINE
# ============================================================

def create_presentation_outline(
    topic
):

    prompt = f"""

K.A.R.V.I.S. için profesyonel
bir üniversite sunumu hazırla.

KONU:

{topic}

TOPLAM SLAYT SAYISI:

7

YAPI:

1. Kapak
2. İçerik
3. İçerik
4. İçerik
5. İçerik
6. İçerik
7. Sonuç ve Değerlendirme

Yalnızca JSON döndür.

FORMAT:

{{
  "title": "Ana başlık",
  "subtitle": "Kısa akademik alt başlık",
  "cover_visual_query": "English image search query",

  "slides": [

    {{
      "title": "Kısa başlık",
      "paragraph": "Kısa akademik açıklama",
      "visual_query": "English image search query"
    }}

  ],

  "conclusion": {{

    "title":
      "Sonuç ve Değerlendirme",

    "paragraph":
      "Kısa akademik sonuç",

    "visual_query":
      "English image search query"

  }}

}}

KURALLAR:

- Tam olarak 5 içerik slaytı üret.
- Toplam 7 slayt olacak.
- Türkçe yaz.
- Başlıklar kısa olsun.
- Başlıklar birbirinin aynısı olmasın.
- Paragraflar yaklaşık 45-75 kelime olsun.
- Gereksiz uzun metin üretme.
- Sunumda okunabilir metin üret.
- Akademik ama anlaşılır dil kullan.
- Visual query alanları İngilizce olsun.
- Her visual query farklı olsun.
- Görsel sorguları konuyla doğrudan ilgili olsun.
- Sonuç slaytı gerçek bir değerlendirme içersin.
- JSON dışında hiçbir şey yazma.

"""


    result = ask_ai(
        prompt
    )


    data = extract_json(
        result
    )


    if not data:

        return fallback_presentation(
            topic
        )


    raw_slides = data.get(
        "slides",
        []
    )


    slides = []


    for slide in raw_slides:

        if not isinstance(
            slide,
            dict
        ):

            continue


        title = str(
            slide.get(
                "title",
                ""
            )
        ).strip()


        paragraph = str(
            slide.get(
                "paragraph",
                ""
            )
        ).strip()


        query = str(
            slide.get(
                "visual_query",
                ""
            )
        ).strip()


        if (
            title
            and paragraph
        ):

            slides.append({

                "title":
                    title[:120],

                "paragraph":
                    paragraph,

                "visual_query":
                    query
                    or
                    f"{topic} {title} academic"

            })


    if len(slides) < 5:

        return fallback_presentation(
            topic
        )


    slides = slides[:5]


    conclusion = data.get(
        "conclusion",
        {}
    )


    if not isinstance(
        conclusion,
        dict
    ):

        conclusion = {}


    conclusion_paragraph = str(
        conclusion.get(
            "paragraph",
            ""
        )
    ).strip()


    if not conclusion_paragraph:

        conclusion_paragraph = (
            f"{topic} açısından temel kavramların, "
            f"gelişim sürecinin ve güncel etkilerin "
            f"birlikte değerlendirilmesi önem taşımaktadır."
        )


    return {

        "title":
            str(
                data.get(
                    "title"
                )
                or topic
            ),

        "subtitle":
            str(
                data.get(
                    "subtitle"
                )
                or "Akademik Sunum"
            ),

        "cover_visual_query":
            str(
                data.get(
                    "cover_visual_query"
                )
                or
                f"{topic} academic professional"
            ),

        "slides":
            slides,

        "conclusion": {

            "title":
                str(
                    conclusion.get(
                        "title"
                    )
                    or
                    "Sonuç ve Değerlendirme"
                ),

            "paragraph":
                conclusion_paragraph,

            "visual_query":
                str(
                    conclusion.get(
                        "visual_query"
                    )
                    or
                    f"{topic} conclusion academic"
                )
        }
    }


# ============================================================
# IMAGE SEARCH
# ============================================================

IMAGE_HEADERS = {

    "User-Agent":
        "Mozilla/5.0 K.A.R.V.I.S./29.1 PresentationBot"

}


# ============================================================
# WIKIMEDIA
# ============================================================

def get_wikimedia_candidates(
    query
):

    try:

        response = requests.get(

            "https://commons.wikimedia.org/w/api.php",

            params={

                "action":
                    "query",

                "generator":
                    "search",

                "gsrsearch":
                    query,

                "gsrnamespace":
                    6,

                "gsrlimit":
                    20,

                "prop":
                    "imageinfo",

                "iiprop":
                    "url|mime|size",

                "iiurlwidth":
                    1600,

                "format":
                    "json"
            },

            headers=
                IMAGE_HEADERS,

            timeout=15
        )


        if response.status_code != 200:

            return []


        pages = (
            response
            .json()
            .get(
                "query",
                {}
            )
            .get(
                "pages",
                {}
            )
        )


        results = []


        for page in pages.values():

            info = (
                page
                .get(
                    "imageinfo"
                )
                or []
            )


            if not info:

                continue


            item = info[0]


            image_url = (
                item.get(
                    "thumburl"
                )
                or
                item.get(
                    "url"
                )
            )


            mime = item.get(
                "mime",
                ""
            )


            if (
                image_url
                and
                mime.startswith(
                    "image/"
                )
            ):

                results.append(
                    image_url
                )


        return results


    except Exception:

        return []


# ============================================================
# OPENVERSE
# ============================================================

def get_openverse_candidates(
    query
):

    try:

        response = requests.get(

            "https://api.openverse.org/v1/images/",

            params={

                "q":
                    query,

                "page_size":
                    20
            },

            headers=
                IMAGE_HEADERS,

            timeout=15
        )


        if response.status_code != 200:

            return []


        results = []


        for item in (
            response
            .json()
            .get(
                "results",
                []
            )
        ):

            image_url = (
                item.get(
                    "thumbnail"
                )
                or
                item.get(
                    "url"
                )
            )


            if image_url:

                results.append(
                    image_url
                )


        return results


    except Exception:

        return []


# ============================================================
# IMAGE HASH
# ============================================================

def image_hash(
    image
):

    try:

        small = (
            image
            .convert(
                "RGB"
            )
            .resize(
                (96, 96)
            )
        )


        return hashlib.sha256(
            small.tobytes()
        ).hexdigest()


    except Exception:

        return None


# ============================================================
# DOWNLOAD UNIQUE IMAGE
# ============================================================

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

            headers=
                IMAGE_HEADERS,

            timeout=20
        )


        if response.status_code != 200:

            return None


        content_type = (
            response
            .headers
            .get(
                "Content-Type",
                ""
            )
            .lower()
        )


        if not content_type.startswith(
            "image/"
        ):

            return None


        from io import BytesIO


        image = Image.open(
            BytesIO(
                response.content
            )
        )


        image.load()


        if (
            image.width < 300
            or
            image.height < 200
        ):

            return None


        digest = image_hash(
            image
        )


        if not digest:

            return None


        with lock:

            if (
                url in used_urls
                or
                digest in used_hashes
            ):

                return None


            used_urls.add(
                url
            )

            used_hashes.add(
                digest
            )


        return image.convert(
            "RGB"
        )


    except Exception:

        return None


# ============================================================
# IMAGE FALLBACK SEARCH
# ============================================================

def find_unique_image(
    queries,
    used_urls,
    used_hashes,
    lock
):

    candidates = []


    # Birden fazla sorgu sırayla denenir.
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


        if len(candidates) >= 40:

            break


    seen = set()


    for url in candidates:

        if url in seen:

            continue


        seen.add(
            url
        )


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
# BUILD FALLBACK QUERIES
# ============================================================

def build_image_queries(
    topic,
    title,
    primary
):

    return [

        primary,

        f"{topic} {title} academic",

        f"{topic} {title} education",

        f"{topic} {title} professional",

        f"{topic} documentary",

        f"{topic} university",

        f"{topic} research",

        f"{topic} historical"

    ]


# ============================================================
# FONT SYSTEM
# ============================================================

def find_font(
    bold=False
):

    if bold:

        candidates = [

            BASE_DIR /
            "fonts" /
            "DejaVuSans-Bold.ttf",

            Path(
                "/usr/share/fonts/truetype/"
                "dejavu/DejaVuSans-Bold.ttf"
            ),

            Path(
                "/usr/share/fonts/truetype/"
                "liberation2/"
                "LiberationSans-Bold.ttf"
            )

        ]

    else:

        candidates = [

            BASE_DIR /
            "fonts" /
            "DejaVuSans.ttf",

            Path(
                "/usr/share/fonts/truetype/"
                "dejavu/DejaVuSans.ttf"
            ),

            Path(
                "/usr/share/fonts/truetype/"
                "liberation2/"
                "LiberationSans-Regular.ttf"
            )

        ]


    for path in candidates:

        if path.exists():

            return str(
                path
            )


    return None


FONT_REGULAR = find_font(
    False
)

FONT_BOLD = find_font(
    True
)


def karvis_font(
    size,
    bold=False
):

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
# SLIDE SIZE
# ============================================================

SLIDE_WIDTH = 1600

SLIDE_HEIGHT = 900

PDF_WIDTH = 16 * inch

PDF_HEIGHT = 9 * inch


# ============================================================
# TEXT MEASUREMENT
# ============================================================

def text_width(
    draw,
    text,
    font
):

    try:

        return draw.textlength(
            text,
            font=font
        )

    except Exception:

        bbox = draw.textbbox(
            (0, 0),
            text,
            font=font
        )

        return (
            bbox[2]
            -
            bbox[0]
        )


def text_height(
    draw,
    text,
    font
):

    try:

        bbox = draw.textbbox(
            (0, 0),
            text,
            font=font
        )

        return (
            bbox[3]
            -
            bbox[1]
        )

    except Exception:

        return getattr(
            font,
            "size",
            20
        )


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_pixel_text(
    draw,
    text,
    font,
    max_width
):

    words = str(
        text or ""
    ).split()


    lines = []

    current = ""


    for word in words:

        candidate = (

            word

            if not current

            else

            current
            +
            " "
            +
            word

        )


        if (
            text_width(
                draw,
                candidate,
                font
            )
            <=
            max_width
        ):

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


# ============================================================
# DYNAMIC FONT FIT
# ============================================================

def fit_font_to_box(
    draw,
    text,
    max_width,
    max_height,
    start_size=28,
    min_size=15,
    bold=False,
    max_lines=None
):

    text = str(
        text or ""
    ).strip()


    for size in range(
        start_size,
        min_size - 1,
        -1
    ):

        font = karvis_font(
            size,
            bold
        )


        lines = wrap_pixel_text(

            draw,

            text,

            font,

            max_width

        )


        if (
            max_lines
            and
            len(lines) > max_lines
        ):

            continue


        line_height = max(

            text_height(
                draw,
                "Ag",
                font
            ),

            size

        )


        spacing = max(

            3,

            int(
                size * 0.25
            )

        )


        total_height = (

            len(lines)
            *
            line_height

            +

            max(
                0,
                len(lines) - 1
            )
            *
            spacing

        )


        if (
            total_height
            <=
            max_height
        ):

            return (
                font,
                lines,
                spacing
            )


    font = karvis_font(
        min_size,
        bold
    )


    lines = wrap_pixel_text(

        draw,

        text,

        font,

        max_width

    )


    if (
        max_lines
        and
        len(lines) > max_lines
    ):

        lines = lines[
            :max_lines
        ]


        if lines:

            last = lines[-1]


            while (

                text_width(
                    draw,
                    last + "…",
                    font
                )
                >
                max_width

                and
                last

            ):

                last = last[:-1]


            lines[-1] = (
                last.rstrip()
                +
                "…"
            )


    return (

        font,

        lines,

        max(
            3,
            int(
                min_size * 0.25
            )
        )

    )


# ============================================================
# DRAW FITTED TEXT
# ============================================================

def draw_fitted_text(
    draw,
    text,
    box,
    start_size,
    min_size,
    fill,
    bold=False,
    align="left",
    max_lines=None
):

    x, y, width, height = box


    font, lines, spacing = fit_font_to_box(

        draw,

        text,

        width,

        height,

        start_size=start_size,

        min_size=min_size,

        bold=bold,

        max_lines=max_lines

    )


    current_y = y


    for line in lines:

        line_w = text_width(

            draw,

            line,

            font

        )


        if align == "center":

            line_x = (
                x
                +
                (
                    width
                    -
                    line_w
                )
                /
                2
            )


        elif align == "right":

            line_x = (
                x
                +
                width
                -
                line_w
            )


        else:

            line_x = x


        draw.text(

            (
                line_x,
                current_y
            ),

            line,

            font=font,

            fill=fill

        )


        current_y += (

            text_height(
                draw,
                line,
                font
            )

            +

            spacing

        )


    return current_y


# ============================================================
# ROUNDED IMAGE
# ============================================================

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

        method=
            Image.Resampling.LANCZOS,

        centering=(
            0.5,
            0.5
        )

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

        (
            w,
            h
        )

    )


    mask = rounded_mask(

        (
            w,
            h
        ),

        radius

    )


    base.paste(

        image,

        (
            x,
            y
        ),

        mask

    )


# ============================================================
# COVER SLIDE
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

        (
            5,
            10,
            18
        )

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

            (
                2,
                7,
                13,
                165
            )

        )


        img = Image.alpha_composite(

            bg.convert(
                "RGBA"
            ),

            dark

        ).convert(
            "RGB"
        )


    draw = ImageDraw.Draw(
        img
    )


    # Üst çizgi

    draw.rectangle(

        (
            80,
            75,
            410,
            81
        ),

        fill=(
            0,
            229,
            255
        )

    )


    draw.text(

        (
            80,
            110
        ),

        "K.A.R.V.I.S.",

        font=
            karvis_font(
                26,
                True
            ),

        fill=(
            0,
            229,
            255
        )

    )


    draw.text(

        (
            80,
            148
        ),

        "KARAHAN INC.",

        font=
            karvis_font(
                17
            ),

        fill=(
            160,
            175,
            190
        )

    )


    # Dinamik başlık

    draw_fitted_text(

        draw,

        title,

        (
            80,
            275,
            1050,
            330
        ),

        start_size=72,

        min_size=38,

        fill=(
            245,
            250,
            255
        ),

        bold=True,

        max_lines=3

    )


    # Alt başlık

    draw_fitted_text(

        draw,

        subtitle,

        (
            85,
            640,
            950,
            75
        ),

        start_size=28,

        min_size=18,

        fill=(
            180,
            195,
            210
        ),

        max_lines=2

    )


    draw.text(

        (
            80,
            810
        ),

        "AKADEMİK SUNUM",

        font=
            karvis_font(
                18,
                True
            ),

        fill=(
            0,
            229,
            255
        )

    )


    draw.text(

        (
            80,
            845
        ),

        "K.A.R.V.I.S. • KARAHAN INC.",

        font=
            karvis_font(
                15
            ),

        fill=(
            110,
            125,
            140
        )

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

        (
            5,
            11,
            19
        )

    )


    draw = ImageDraw.Draw(
        img
    )


    # --------------------------------------------------------
    # TOP
    # --------------------------------------------------------

    draw.rectangle(

        (
            70,
            55,
            1530,
            58
        ),

        fill=(
            18,
            45,
            58
        )

    )


    draw.rectangle(

        (
            70,
            55,
            280,
            58
        ),

        fill=(
            0,
            229,
            255
        )

    )


    # --------------------------------------------------------
    # LOGO
    # --------------------------------------------------------

    draw.text(

        (
            70,
            82
        ),

        "K.A.R.V.I.S.",

        font=
            karvis_font(
                21,
                True
            ),

        fill=(
            0,
            229,
            255
        )

    )


    draw.text(

        (
            70,
            111
        ),

        "KARAHAN INC.",

        font=
            karvis_font(
                14
            ),

        fill=(
            110,
            130,
            145
        )

    )


    # --------------------------------------------------------
    # BAŞLIK
    # --------------------------------------------------------

    draw_fitted_text(

        draw,

        title,

        (
            70,
            165,
            700,
            105
        ),

        start_size=45,

        min_size=28,

        fill=(
            245,
            250,
            255
        ),

        bold=True,

        max_lines=2

    )


    # --------------------------------------------------------
    # SOL KUTU
    # --------------------------------------------------------

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

        fill=(
            10,
            20,
            30
        ),

        outline=(
            22,
            48,
            62
        ),

        width=2

    )


    draw.text(

        (
            105,
            335
        ),

        "AKADEMİK AÇIKLAMA",

        font=
            karvis_font(
                18,
                True
            ),

        fill=(
            0,
            229,
            255
        )

    )


    draw.rectangle(

        (
            105,
            372,
            190,
            376
        ),

        fill=(
            0,
            229,
            255
        )

    )


    # --------------------------------------------------------
    # PARAGRAF
    # --------------------------------------------------------

    draw_fitted_text(

        draw,

        paragraph,

        (
            105,
            415,
            625,
            335
        ),

        start_size=25,

        min_size=15,

        fill=(
            215,
            225,
            235
        ),

        max_lines=13

    )


    # --------------------------------------------------------
    # GÖRSEL KUTUSU
    # --------------------------------------------------------

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

        fill=(
            9,
            18,
            27
        ),

        outline=(
            25,
            51,
            65
        ),

        width=2

    )


    if image is not None:

        # Görsel kesin olarak kutu içine sığdırılır.
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

            font=
                karvis_font(
                    42,
                    True
                ),

            fill=(
                0,
                229,
                255
            )

        )


    # --------------------------------------------------------
    # FOOTER
    # --------------------------------------------------------

    draw.text(

        (
            70,
            842
        ),

        "K.A.R.V.I.S. • KARAHAN INC.",

        font=
            karvis_font(
                15
            ),

        fill=(
            90,
            110,
            125
        )

    )


    draw.text(

        (
            1430,
            842
        ),

        f"{slide_number:02d} / {total_slides:02d}",

        font=
            karvis_font(
                16,
                True
            ),

        fill=(
            0,
            229,
            255
        )

    )


    img.save(

        output_path,

        "PNG",

        optimize=True

    )


# ============================================================
# CONCLUSION SLIDE
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

        (
            5,
            11,
            19
        )

    )


    draw = ImageDraw.Draw(
        img
    )


    # Üst çizgiler

    draw.rectangle(

        (
            70,
            55,
            1530,
            58
        ),

        fill=(
            18,
            45,
            58
        )

    )


    draw.rectangle(

        (
            70,
            55,
            520,
            58
        ),

        fill=(
            0,
            229,
            255
        )

    )


    draw.text(

        (
            70,
            90
        ),

        "K.A.R.V.I.S.",

        font=
            karvis_font(
                22,
                True
            ),

        fill=(
            0,
            229,
            255
        )

    )


    draw.text(

        (
            70,
            120
        ),

        "KARAHAN INC.",

        font=
            karvis_font(
                14
            ),

        fill=(
            110,
            130,
            145
        )

    )


    # Sonuç başlığı

    draw_fitted_text(

        draw,

        title,

        (
            70,
            205,
            750,
            90
        ),

        start_size=54,

        min_size=32,

        fill=(
            245,
            250,
            255
        ),

        bold=True,

        max_lines=2

    )


    # Sonuç kutusu

    draw.rounded_rectangle(

        (
            70,
            310,
            820,
            750
        ),

        radius=30,

        fill=(
            10,
            20,
            30
        ),

        outline=(
            22,
            48,
            62
        ),

        width=2

    )


    draw.text(

        (
            110,
            350
        ),

        "SONUÇ VE DEĞERLENDİRME",

        font=
            karvis_font(
                19,
                True
            ),

        fill=(
            0,
            229,
            255
        )

    )


    draw_fitted_text(

        draw,

        paragraph,

        (
            110,
            405,
            650,
            280
        ),

        start_size=27,

        min_size=16,

        fill=(
            220,
            230,
            238
        ),

        max_lines=11

    )


    # Sonuç görseli

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

            (
                880,
                185,
                1500,
                750
            ),

            radius=35,

            fill=(
                8,
                22,
                31
            ),

            outline=(
                0,
                229,
                255
            ),

            width=2

        )


        draw.text(

            (
                1050,
                430
            ),

            "K.A.R.V.I.S.",

            font=
                karvis_font(
                    42,
                    True
                ),

            fill=(
                0,
                229,
                255
            )

        )


    # Footer

    draw.text(

        (
            70,
            835
        ),

        "K.A.R.V.I.S. • KARAHAN INC.",

        font=
            karvis_font(
                15
            ),

        fill=(
            90,
            110,
            125
        )

    )


    draw.text(

        (
            1430,
            835
        ),

        f"{total_slides:02d} / {total_slides:02d}",

        font=
            karvis_font(
                16,
                True
            ),

        fill=(
            0,
            229,
            255
        )

    )


    img.save(

        output_path,

        "PNG",

        optimize=True

    )


# ============================================================
# PDF
# ============================================================

def create_presentation_pdf(
    presentation_id,
    outline,
    images
):

    title = outline[
        "title"
    ]


    subtitle = outline.get(

        "subtitle",

        "Akademik Sunum"

    )


    slides = outline[
        "slides"
    ]


    conclusion = outline[
        "conclusion"
    ]


    total_slides = (
        len(slides)
        +
        2
    )


    presentation_dir = (

        GENERATED_DIR
        /
        f"presentation_{presentation_id}"

    )


    slides_dir = (

        presentation_dir
        /
        "slides"

    )


    slides_dir.mkdir(

        parents=True,

        exist_ok=True

    )


    slide_paths = []


    # --------------------------------------------------------
    # 1 - COVER
    # --------------------------------------------------------

    cover_path = (

        slides_dir
        /
        "slide_01.png"

    )


    create_cover_slide(

        title,

        subtitle,

        images.get(
            "cover"
        ),

        str(
            cover_path
        )

    )


    slide_paths.append(
        cover_path
    )


    # --------------------------------------------------------
    # 2-6 CONTENT
    # --------------------------------------------------------

    for index, slide in enumerate(

        slides,

        start=2

    ):

        slide_path = (

            slides_dir
            /
            f"slide_{index:02d}.png"

        )


        create_content_slide(

            slide_number=index,

            total_slides=total_slides,

            title=slide[
                "title"
            ],

            paragraph=slide[
                "paragraph"
            ],

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


    # --------------------------------------------------------
    # 7 - CONCLUSION
    # --------------------------------------------------------

    conclusion_path = (

        slides_dir
        /
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


    # --------------------------------------------------------
    # PDF
    # --------------------------------------------------------

    pdf_filename = (

        f"karvis_sunum_{presentation_id}.pdf"

    )


    pdf_path = (

        GENERATED_DIR
        /
        pdf_filename

    )


    pdf = canvas.Canvas(

        str(
            pdf_path
        ),

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
# PRESENTATION JOB
# ============================================================

def create_job():

    job_id = uuid.uuid4().hex


    with presentation_lock:

        PRESENTATION_JOBS[
            job_id
        ] = {

            "id":
                job_id,

            "status":
                "queued",

            "progress":
                0,

            "message":
                "Sunum hazırlanıyor...",

            "file":
                None,

            "download_url":
                None,

            "error":
                None
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
            ].update(
                kwargs
            )


# ============================================================
# PRESENTATION WORKER
# ============================================================

def presentation_worker(
    job_id,
    topic
):

    try:

        # ----------------------------------------------------
        # OUTLINE
        # ----------------------------------------------------

        update_job(

            job_id,

            status="working",

            progress=5,

            message=
                "Sunum planı oluşturuluyor..."

        )


        outline = create_presentation_outline(
            topic
        )


        slides = outline[
            "slides"
        ]


        # ----------------------------------------------------
        # IMAGE SEARCH
        # ----------------------------------------------------

        update_job(

            job_id,

            progress=20,

            message=
                "Görseller aranıyor..."

        )


        used_urls = set()

        used_hashes = set()

        lock = threading.Lock()


        image_tasks = {}


        # Cover

        image_tasks[
            "cover"
        ] = build_image_queries(

            topic,

            "cover",

            outline.get(

                "cover_visual_query",

                topic

            )

        )


        # Content

        for index, slide in enumerate(

            slides,

            start=2

        ):

            image_tasks[
                f"slide_{index}"
            ] = build_image_queries(

                topic,

                slide[
                    "title"
                ],

                slide.get(

                    "visual_query",

                    ""

                )

            )


        # Conclusion

        image_tasks[
            "conclusion"
        ] = build_image_queries(

            topic,

            "conclusion",

            outline[
                "conclusion"
            ].get(

                "visual_query",

                ""

            )

        )


        images = {}


        total_tasks = len(
            image_tasks
        )


        completed = 0


        with ThreadPoolExecutor(

            max_workers=4

        ) as executor:


            futures = {}


            for key, queries in (
                image_tasks.items()
            ):

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

                    20
                    +
                    int(
                        completed
                        /
                        total_tasks
                        *
                        45
                    )

                )


                update_job(

                    job_id,

                    progress=progress,

                    message=(

                        "Görseller hazırlanıyor "
                        f"({completed}/{total_tasks})..."

                    )

                )


        # ----------------------------------------------------
        # CREATE PDF
        # ----------------------------------------------------

        update_job(

            job_id,

            progress=70,

            message=
                "Profesyonel slaytlar oluşturuluyor..."

        )


        pdf_filename = create_presentation_pdf(

            presentation_id=
                job_id,

            outline=
                outline,

            images=
                images

        )


        # ----------------------------------------------------
        # COMPLETED
        # ----------------------------------------------------

        update_job(

            job_id,

            status="completed",

            progress=100,

            message=
                "Sunum hazırlandı.",

            file=
                pdf_filename,

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

            message=
                "Sunum oluşturulamadı.",

            error=
                str(e)

        )


# ============================================================
# HOME
# ============================================================

@app.get("/")
async def home():

    if not INDEX_FILE.exists():

        return JSONResponse({

            "app":
                "K.A.R.V.I.S.",

            "version":
                APP_VERSION,

            "status":
                "online"

        })


    return FileResponse(
        INDEX_FILE
    )


# ============================================================
# HEALTH
# ============================================================

@app.get(
    "/health"
)
async def health():

    return {

        "status":
            "online",

        "app":
            "K.A.R.V.I.S.",

        "version":
            APP_VERSION,

        "groq":
            bool(
                GROQ_API_KEY
            ),

        "openrouter":
            bool(
                OPENROUTER_API_KEY
            ),

        "presentation_slides":
            7,

        "pdf_download":
            True,

        "dynamic_text_fit":
            True,

        "image_fallback":
            True

    }


# ============================================================
# LOGIN
# ============================================================

@app.post(
    "/login"
)
async def login(
    request: LoginRequest
):

    username = (
        request.username
        or ""
    ).strip().lower()


    user = USERS.get(
        username
    )


    if not user:

        raise HTTPException(

            status_code=401,

            detail=
                "Kullanıcı adı veya şifre hatalı."

        )


    if user[
        "password"
    ] != request.password:

        raise HTTPException(

            status_code=401,

            detail=
                "Kullanıcı adı veya şifre hatalı."

        )


    return {

        "success":
            True,

        "username":
            username,

        "name":
            user[
                "name"
            ],

        "role":
            user[
                "role"
            ],

        "style":
            user[
                "style"
            ]

    }


# ============================================================
# CHAT
# ============================================================

@app.post(
    "/chat"
)
async def chat(
    request: ChatRequest
):

    message = (
        request.message
        or ""
    ).strip()


    if not message:

        return {

            "response":
                "Nasıl yardımcı olabilirim Hocam?"

        }


    username = (
        request.username
        or "karahan"
    ).strip()


    mode = (
        request.mode
        or "normal"
    ).strip()


    user = USERS.get(

        username.lower(),

        {

            "name":
                username,

            "role":
                "user",

            "style":
                "professional"

        }

    )


    prompt = f"""

{BASE_SYSTEM}

KULLANICI:

{user.get("name", username)}

ROL:

{user.get("role", "user")}

MOD:

{mode}

{get_mode_instruction(mode)}

KULLANICI MESAJI:

{message}

"""


    result = ask_ai(
        prompt
    )


    if not result:

        result = (

            "Şu anda yapay zeka servislerine "
            "bağlanılamıyor. API anahtarlarını "
            "ve servis durumunu kontrol edin Hocam."

        )


    return {

        "response":
            result,

        "message":
            result,

        "mode":
            mode

    }


# ============================================================
# PRESENTATION
# ============================================================

@app.post(
    "/presentation"
)
async def create_presentation(

    request:
        PresentationRequest,

    background_tasks:
        BackgroundTasks

):

    topic = (
        request.topic
        or ""
    ).strip()


    if not topic:

        raise HTTPException(

            status_code=400,

            detail=
                "Sunum konusu boş olamaz."

        )


    # 7 slayt sistemi sabittir.

    slide_count = (
        PRESENTATION_SLIDE_COUNT
    )


    job_id = create_job()


    background_tasks.add_task(

        presentation_worker,

        job_id,

        topic

    )


    return {

        "success":
            True,

        "job_id":
            job_id,

        "status":
            "queued",

        "slide_count":
            slide_count,

        "message":
            "7 slaytlık sunum oluşturuluyor..."

    }


# ============================================================
# PRESENTATION STATUS
# ============================================================

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

                detail=
                    "Sunum bulunamadı."

            )


        return dict(
            job
        )


# ============================================================
# GENERATED FILES
# ============================================================

@app.get(
    "/generated/{filename}"
)
async def generated_file(
    filename: str
):

    # Path traversal koruması.

    safe_name = Path(
        filename
    ).name


    file_path = (
        GENERATED_DIR
        /
        safe_name
    )


    if (
        not file_path.exists()
        or
        not file_path.is_file()
    ):

        raise HTTPException(

            status_code=404,

            detail=
                "Dosya bulunamadı."

        )


    # PDF indirme davranışı korunur.

    if safe_name.lower().endswith(
        ".pdf"
    ):

        return FileResponse(

            path=
                file_path,

            media_type=
                "application/pdf",

            filename=
                safe_name,

            headers={

                "Content-Disposition":
                    f'attachment; filename="{safe_name}"'

            }

        )


    return FileResponse(
        file_path
    )


# ============================================================
# USER MEMORY
# ============================================================

def user_memory_path(
    username
):

    safe_username = re.sub(

        r"[^a-zA-Z0-9_-]",

        "_",

        str(
            username
            or "karahan"
        )

    ).lower()


    return (

        BASE_DIR
        /
        f"memory_{safe_username}.json"

    )


@app.get(
    "/memory"
)
async def get_memory(
    username: str = "karahan"
):

    path = user_memory_path(
        username
    )


    with memory_lock:

        return {

            "username":
                username,

            "memory":
                read_json_file(
                    path,
                    []
                )

        }


@app.post(
    "/memory"
)
async def add_memory(
    data: dict
):

    username = str(

        data.get(

            "username",

            "karahan"

        )

    ).strip()


    text = str(

        data.get(

            "text",

            ""

        )

    ).strip()


    if not text:

        return {

            "success":
                False

        }


    path = user_memory_path(
        username
    )


    with memory_lock:

        memories = read_json_file(

            path,

            []

        )


        memories.append({

            "id":
                uuid.uuid4().hex,

            "text":
                text,

            "created_at":
                time.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

        })


        memories = memories[-200:]


        write_json_file(

            path,

            memories

        )


    return {

        "success":
            True,

        "username":
            username,

        "memory":
            memories

    }


# ============================================================
# NEW CHAT
# ============================================================

@app.post(
    "/new-chat"
)
async def new_chat():

    return {

        "success":
            True,

        "message":
            "Yeni sohbet başlatıldı."

    }


# ============================================================
# ERRORS
# ============================================================

@app.get(
    "/errors"
)
async def errors():

    return {

        "errors":
            read_json_file(

                ERROR_FILE,

                []

            )

    }


# ============================================================
# STARTUP
# ============================================================

@app.on_event(
    "startup"
)
async def startup():

    GENERATED_DIR.mkdir(
        exist_ok=True
    )


    print(
        "=" * 60
    )

    print(
        "K.A.R.V.I.S. - KARAHAN INC."
    )

    print(
        f"Version: {APP_VERSION}"
    )

    print(
        "Backend: ONLINE"
    )

    print(

        "Groq:",

        "ACTIVE"
        if GROQ_API_KEY
        else
        "NOT CONFIGURED"

    )

    print(

        "OpenRouter:",

        "ACTIVE"
        if OPENROUTER_API_KEY
        else
        "NOT CONFIGURED"

    )

    print(
        "Presentation Engine: 16:9"
    )

    print(
        "Presentation System: 7 SLIDES"
    )

    print(
        "PDF Download: ENABLED"
    )

    print(
        "Dynamic Text Fit: ENABLED"
    )

    print(
        "Image Fallback Search: ENABLED"
    )

    print(
        "Professional Response Mode: ENABLED"
    )

    print(
        "=" * 60
    )


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
