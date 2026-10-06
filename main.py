import os
import io
import re
import json
import uuid
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from PIL import Image, ImageOps

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from pydantic import BaseModel

from openai import OpenAI

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# =========================================================
# KARVIS
# K.A.R.V.I.S. - KARAHAN INC.
# MAIN BACKEND
# =========================================================

APP_VERSION = "28.0.0"

BASE_DIR = Path(__file__).resolve().parent

FILES_DIR = BASE_DIR / "files"
GENERATED_DIR = BASE_DIR / "generated"

MEMORY_FILE = BASE_DIR / "memory.json"
ERROR_FILE = BASE_DIR / "errors.json"

FILES_DIR.mkdir(exist_ok=True)
GENERATED_DIR.mkdir(exist_ok=True)


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
    allow_headers=["*"],
)


# =========================================================
# API KEYS
# =========================================================

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY",
    ""
).strip()

OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    ""
).strip()


# =========================================================
# AI CLIENTS
# =========================================================

groq_client = None
openrouter_client = None


if GROQ_API_KEY:

    try:

        groq_client = OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )

    except Exception:

        groq_client = None


if OPENROUTER_API_KEY:

    try:

        openrouter_client = OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        )

    except Exception:

        openrouter_client = None


GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b"
]


OPENROUTER_MODELS = [
    "openai/gpt-oss-20b:free"
]


# =========================================================
# USERS
# =========================================================

USERS = {

    "karahan": {
        "name": "KARAHAN INC.",
        "password": "",
        "mode": "professional",
        "role": "owner"
    },

    "betul": {
        "name": "Betül",
        "password": "1234",
        "mode": "normal",
        "role": "user"
    },

    "sinem": {
        "name": "Sinem",
        "password": "3021",
        "mode": "normal",
        "role": "user"
    },

    "ilknur": {
        "name": "İlknur",
        "password": "1111",
        "mode": "lesson",
        "role": "teacher"
    }

}


# =========================================================
# ACADEMIC MODES
# =========================================================

ACADEMIC_MODES = {

    "research": "Araştırma",

    "academic": "Akademik",

    "article": "Makale",

    "lesson": "Ders",

    "quiz": "Quiz",

    "presentation": "Sunum"

}


# =========================================================
# MEMORY
# =========================================================

memory_lock = threading.Lock()


def load_json_file(
    path: Path,
    default
):

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


def save_json_file(
    path: Path,
    data
):

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

    except Exception:
        pass


def load_memory():

    return load_json_file(
        MEMORY_FILE,
        {}
    )


def save_memory(data):

    save_json_file(
        MEMORY_FILE,
        data
    )


def load_errors():

    return load_json_file(
        ERROR_FILE,
        []
    )


def save_error(
    message: str
):

    errors = load_errors()

    errors.append({

        "time": time.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

        "error": str(message)

    })

    errors = errors[-100:]

    save_json_file(
        ERROR_FILE,
        errors
    )


# =========================================================
# PRESENTATION JOB SYSTEM
# =========================================================

PRESENTATION_JOBS: Dict[
    str,
    Dict[str, Any]
] = {}

presentation_lock = threading.Lock()


def create_job():

    job_id = uuid.uuid4().hex

    with presentation_lock:

        PRESENTATION_JOBS[job_id] = {

            "job_id": job_id,

            "stage": "content",

            "message": "İçerik hazırlanıyor",

            "progress": 0,

            "total": 0,

            "completed": False,

            "success": False,

            "file_url": None,

            "error": None,

            "created_at": time.time()

        }

    return job_id


def update_job(
    job_id: str,
    stage: Optional[str] = None,
    message: Optional[str] = None,
    progress: Optional[int] = None,
    total: Optional[int] = None,
    completed: Optional[bool] = None,
    success: Optional[bool] = None,
    file_url: Optional[str] = None,
    error: Optional[str] = None
):

    with presentation_lock:

        job = PRESENTATION_JOBS.get(
            job_id
        )

        if not job:
            return

        if stage is not None:
            job["stage"] = stage

        if message is not None:
            job["message"] = message

        if progress is not None:
            job["progress"] = progress

        if total is not None:
            job["total"] = total

        if completed is not None:
            job["completed"] = completed

        if success is not None:
            job["success"] = success

        if file_url is not None:
            job["file_url"] = file_url

        if error is not None:
            job["error"] = error


# =========================================================
# MODELS
# =========================================================

class ChatRequest(BaseModel):

    message: str

    username: str = "karahan"

    mode: Optional[str] = None


class ResearchRequest(BaseModel):

    query: str

    username: str = "karahan"


class PresentationRequest(BaseModel):

    topic: str

    username: str = "karahan"

    slide_count: int = 7


class ProfileLoginRequest(BaseModel):

    username: str

    password: str = ""


class MemoryRequest(BaseModel):

    username: str = "karahan"

    key: str

    value: str


# =========================================================
# USER HELPERS
# =========================================================

def get_user(
    username: str
):

    username = (
        username
        or "karahan"
    ).lower().strip()

    return USERS.get(
        username,
        USERS["karahan"]
    )


def get_user_mode(
    username: str,
    mode: Optional[str] = None
):

    user = get_user(username)

    if user["role"] == "teacher":

        if not mode or mode == "normal":

            return "lesson"

    if mode:
        return mode

    return user.get(
        "mode",
        "professional"
    )


# =========================================================
# AI
# =========================================================

SYSTEM_PROMPT = """

Sen K.A.R.V.I.S. adlı kişisel yapay zeka asistanısın.

Tam adın:

K.A.R.V.I.S. - KARAHAN INC.

Kullanıcıyla doğal Türkçe konuş.

Kurallar:

- Gereksiz yere "efendim" kelimesini her cümlede kullanma.
- Kullanıcı sana nasıl konuşuyorsa ona uygun cevap ver.
- Kısa soruya kısa cevap ver.
- Teknik soruda teknik ama anlaşılır cevap ver.
- Kod isterse doğrudan çalışabilir kod üret.
- Bilmediğin bilgiyi uydurma.
- Güncel bilgi gerektiğinde araştırma özelliğinin kullanılmasını öner.
- Profesyonel, sakin ve yardımcı ol.
- Kullanıcıya Murat diye hitap etmek zorunda değilsin.
- Kendini ChatGPT olarak tanıtma.
- K.A.R.V.I.S. olarak davran.

"""


def ask_single_ai(
    client,
    model: str,
    messages: List[
        Dict[str, str]
    ],
    temperature: float = 0.4
):

    response = client.chat.completions.create(

        model=model,

        messages=messages,

        temperature=temperature,

        max_tokens=4000,

        timeout=35

    )

    return (
        response
        .choices[0]
        .message
        .content
        .strip()
    )


def ask_ai(
    message: str,
    username: str = "karahan",
    mode: Optional[str] = None,
    extra_context: str = ""
):

    selected_mode = get_user_mode(
        username,
        mode
    )

    memory = load_memory()

    user_memory = memory.get(
        username,
        {}
    )

    memory_text = ""

    if user_memory:

        memory_text = (
            "\nKullanıcı hafızası:\n"
        )

        for key, value in user_memory.items():

            memory_text += (
                f"- {key}: {value}\n"
            )


    mode_instruction = ""


    if selected_mode == "lesson":

        mode_instruction = """

Ders modundasın.

Konuyu öğretmen gibi açıkla.

Gerekli olduğunda örnekler ve
açıklayıcı maddeler kullan.

"""


    elif selected_mode == "academic":

        mode_instruction = """

Akademik moddasın.

Bilgileri akademik Türkçe ile,
düzenli ve mümkün olduğunca
kanıta dayalı şekilde hazırla.

"""


    elif selected_mode == "article":

        mode_instruction = """

Makale modundasın.

Başlıklar ve akademik anlatım kullan.

"""


    elif selected_mode == "quiz":

        mode_instruction = """

Quiz modundasın.

Kullanıcıya konu hakkında soru sor
veya istenen quiz formatını oluştur.

"""


    elif selected_mode == "research":

        mode_instruction = """

Araştırma modundasın.

Bilgileri mümkün olduğunca
doğrulanabilir şekilde sun.

"""


    messages = [

        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },

        {
            "role": "system",
            "content": mode_instruction
        }

    ]


    if memory_text:

        messages.append({

            "role": "system",

            "content": memory_text

        })


    if extra_context:

        messages.append({

            "role": "system",

            "content": extra_context

        })


    messages.append({

        "role": "user",

        "content": message

    })


    errors = []


    if groq_client:

        for model in GROQ_MODELS:

            try:

                result = ask_single_ai(

                    groq_client,

                    model,

                    messages

                )

                if result:
                    return result

            except Exception as e:

                errors.append(
                    f"Groq {model}: {e}"
                )


    if openrouter_client:

        for model in OPENROUTER_MODELS:

            try:

                result = ask_single_ai(

                    openrouter_client,

                    model,

                    messages

                )

                if result:
                    return result

            except Exception as e:

                errors.append(
                    f"OpenRouter {model}: {e}"
                )


    if errors:

        save_error(
            "\n".join(errors)
        )


    return (

        "Şu anda yapay zeka servislerine "
        "bağlanamıyorum. API anahtarlarını "
        "veya Render ortam değişkenlerini "
        "kontrol et."

    )


# =========================================================
# SEARCH
# =========================================================

SEARCH_HEADERS = {

    "User-Agent":
        "Mozilla/5.0 "
        "(iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Safari/604.1"

}


def web_search(
    query: str,
    limit: int = 6
):

    try:

        url = (
            "https://html.duckduckgo.com/html/"
        )

        response = requests.get(

            url,

            params={
                "q": query
            },

            headers=SEARCH_HEADERS,

            timeout=8

        )

        response.raise_for_status()

        html = response.text

        results = []

        pattern = re.compile(

            r'class="result__a"'
            r'[^>]*href="([^"]+)"'
            r'[^>]*>(.*?)</a>',

            re.I | re.S

        )


        for match in pattern.finditer(html):

            link = match.group(1)

            title = re.sub(

                r"<.*?>",
                "",
                match.group(2)

            )

            title = (

                title
                .replace("&amp;", "&")
                .replace("&quot;", '"')
                .strip()

            )


            if link and title:

                results.append({

                    "title": title,

                    "url": link

                })


            if len(results) >= limit:
                break


        return results


    except Exception as e:

        save_error(
            f"Search error: {e}"
        )

        return []


# =========================================================
# JSON CLEANING
# =========================================================

def clean_json_text(
    text: str
):

    text = text.strip()


    if text.startswith("```"):

        text = re.sub(

            r"^```(?:json)?",

            "",

            text,

            flags=re.I

        )

        text = re.sub(

            r"```$",

            "",

            text

        )


    return text.strip()


# =========================================================
# PRESENTATION OUTLINE
# =========================================================

def create_presentation_outline(
    topic: str,
    slide_count: int,
    username: str
):

    slide_count = max(
        5,
        min(slide_count, 10)
    )


    prompt = f"""

"{topic}" konusu hakkında
{slide_count} slaytlık profesyonel,
üniversite düzeyinde akademik bir sunum hazırla.

ÇIKTIYI SADECE GEÇERLİ JSON OLARAK VER.

Başka hiçbir açıklama yazma.

JSON FORMATIN:

{{
  "title": "Sunumun ana başlığı",
  "slides": [
    {{
      "title": "Benzersiz slayt başlığı",
      "paragraph": "Akademik açıklayıcı paragraf",
      "visual_query": "Unique English visual search query"
    }}
  ]
}}

ÇOK ÖNEMLİ KURALLAR:

1. Tam olarak {slide_count} slayt oluştur.

2. Her slaytta SADECE:
   - title
   - paragraph
   - visual_query
   alanları bulunmalı.

3. Her slaytın başlığı birbirinden farklı olmalı.

4. Her slaytın paragrafı birbirinden farklı olmalı.

5. Aynı bilgiyi farklı kelimelerle tekrar etme.

6. Her paragraf akademik Türkçe ile yazılmalı.

7. Her paragraf yaklaşık 100-150 kelime
   uzunluğunda olmalı.

8. Paragraf, doğrudan ilgili başlığı
   açıklamalı ve konu hakkında anlamlı
   akademik bilgi vermeli.

9. Madde işareti kullanma.

10. Paragrafı liste haline getirme.

11. Slaytlar mantıklı bir akademik sıra
    içerisinde ilerlemeli.

12. İlk slayt konuya giriş sağlayabilir.

13. Sonraki slaytlar farklı alt konuları
    ele almalı.

14. Son slayt konunun genel değerlendirmesini
    veya sonucunu içerebilir.

15. visual_query İNGİLİZCE olmalı.

16. Her visual_query diğerlerinden tamamen
    farklı olmalı.

17. visual_query doğrudan o slaytın
    başlığını ve içeriğini desteklemeli.

18. Genel ve alakasız sorgular kullanma.

19. Örneğin konu yapay zekâ ise her slayt
    için sadece "artificial intelligence"
    yazma.

20. Bunun yerine:

    artificial intelligence healthcare diagnosis

    artificial intelligence personalized education

    artificial intelligence autonomous vehicles

    artificial intelligence cybersecurity

    gibi slayta özel sorgular oluştur.

21. Görsel sorgular gerçek fotoğraf,
    tarihi fotoğraf, bilimsel görsel,
    harita, diyagram, teknoloji görseli
    veya infografik gibi aranabilir
    ifadeler içermeli.

22. Başlıkları kısa ve akademik tut.

23. Paragraflar üniversite sunumunda
    kullanılabilecek nitelikte olmalı.

24. Uydurma kaynak, istatistik veya
    doğrulanmamış kesin bilgi verme.

"""


    result = ask_ai(

        prompt,

        username,

        mode="academic"

    )


    try:

        data = json.loads(

            clean_json_text(result)

        )


        if (

            isinstance(data, dict)

            and isinstance(
                data.get("slides"),
                list
            )

        ):

            slides = data["slides"]


            cleaned_slides = []


            for slide in slides:

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


                visual_query = str(
                    slide.get(
                        "visual_query",
                        ""
                    )
                ).strip()


                if not title:
                    continue


                if not paragraph:
                    continue


                if not visual_query:

                    visual_query = (
                        f"{title} "
                        f"educational academic visual"
                    )


                cleaned_slides.append({

                    "title": title,

                    "paragraph": paragraph,

                    "visual_query":
                        visual_query

                })


            cleaned_slides = ensure_unique_slides(
                cleaned_slides,
                topic
            )


            if len(cleaned_slides) >= slide_count:

                cleaned_slides = (
                    cleaned_slides[:slide_count]
                )

                return {

                    "title":
                        str(
                            data.get(
                                "title",
                                topic
                            )
                        ),

                    "slides":
                        cleaned_slides

                }


    except Exception as e:

        save_error(
            f"Presentation JSON error: {e}"
        )


    return create_fallback_outline(

        topic,

        slide_count

    )


# =========================================================
# SLIDE UNIQUENESS
# =========================================================

def normalize_text(
    text: str
):

    text = str(text).lower()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    text = re.sub(
        r"[^\w\s]",
        "",
        text,
        flags=re.UNICODE
    )

    return text.strip()


def ensure_unique_slides(
    slides: List[Dict[str, Any]],
    topic: str
):

    unique_slides = []

    used_titles = set()
    used_paragraphs = set()
    used_queries = set()


    for slide in slides:

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


        visual_query = str(
            slide.get(
                "visual_query",
                ""
            )
        ).strip()


        title_key = normalize_text(
            title
        )

        paragraph_key = normalize_text(
            paragraph
        )

        query_key = normalize_text(
            visual_query
        )


        if not title:
            continue


        if title_key in used_titles:
            continue


        if paragraph_key in used_paragraphs:
            continue


        if query_key in used_queries:

            visual_query = (
                f"{title} "
                f"{topic} academic visual"
            )

            query_key = normalize_text(
                visual_query
            )


        used_titles.add(
            title_key
        )

        used_paragraphs.add(
            paragraph_key
        )

        used_queries.add(
            query_key
        )


        unique_slides.append({

            "title": title,

            "paragraph": paragraph,

            "visual_query":
                visual_query

        })


    return unique_slides


# =========================================================
# FALLBACK PRESENTATION
# =========================================================

def create_fallback_outline(
    topic: str,
    slide_count: int
):

    default_sections = [

        (
            "Konuya Genel Bakış",
            "overview"
        ),

        (
            "Temel Kavramlar",
            "fundamental concepts"
        ),

        (
            "Tarihsel Gelişim",
            "historical development"
        ),

        (
            "Temel Unsurlar",
            "key components"
        ),

        (
            "Etkiler ve Sonuçlar",
            "effects and consequences"
        ),

        (
            "Günümüzdeki Uygulamalar",
            "modern applications"
        ),

        (
            "Geleceğe Yönelik Değerlendirme",
            "future perspectives"
        ),

        (
            "Genel Sonuç",
            "conclusion"
        ),

        (
            "Değerlendirme",
            "academic evaluation"
        ),

        (
            "Sonuç ve Öneriler",
            "conclusion and recommendations"
        )

    ]


    slides = []


    for index in range(
        slide_count
    ):

        section = default_sections[
            index
            % len(default_sections)
        ]


        title = section[0]

        query_part = section[1]


        paragraph = (

            f"{topic} konusu, {query_part} "
            f"açısından değerlendirildiğinde "
            f"çok boyutlu bir yapıya sahip olan "
            f"önemli bir inceleme alanı olarak "
            f"karşımıza çıkmaktadır. Bu bağlamda "
            f"konunun temel özelliklerinin, ortaya "
            f"çıkış koşullarının ve toplumsal ya da "
            f"bilimsel sonuçlarının birlikte ele "
            f"alınması gerekmektedir. Akademik "
            f"incelemelerde yalnızca mevcut durumun "
            f"tanımlanması yeterli olmayıp, konuyu "
            f"şekillendiren temel unsurlar arasındaki "
            f"ilişkilerin de değerlendirilmesi önem "
            f"taşımaktadır. Bu yaklaşım, {topic} "
            f"konusunun daha sistematik biçimde "
            f"anlaşılmasına ve farklı boyutlarının "
            f"bir bütün içerisinde değerlendirilmesine "
            f"olanak sağlamaktadır."

        )


        visual_query = (

            f"{topic} "
            f"{query_part} "
            f"academic educational visual"

        )


        slides.append({

            "title": title,

            "paragraph": paragraph,

            "visual_query":
                visual_query

        })


    return {

        "title": topic,

        "slides": slides

    }


# =========================================================
# IMAGE SYSTEM
# =========================================================

IMAGE_HEADERS = {

    "User-Agent":
        "KARVIS/28.0 "
        "(presentation image retrieval)"

}


def download_image(
    url: str,
    output_path: Path
):

    try:

        response = requests.get(

            url,

            headers=IMAGE_HEADERS,

            timeout=(3, 8),

            stream=True

        )


        if response.status_code != 200:

            return False


        content_length = response.headers.get(
            "content-length"
        )


        if content_length:

            try:

                if int(
                    content_length
                ) > 12_000_000:

                    return False

            except Exception:

                pass


        data = bytearray()


        for chunk in response.iter_content(
            chunk_size=32768
        ):

            if not chunk:
                continue


            data.extend(chunk)


            if len(data) > 12_000_000:

                return False


        if len(data) < 1000:

            return False


        image = Image.open(
            io.BytesIO(data)
        )


        image.verify()


        image = Image.open(
            io.BytesIO(data)
        )


        if (

            image.width < 250

            or image.height < 150

        ):

            return False


        image = ImageOps.exif_transpose(
            image
        ).convert("RGB")


        image.thumbnail(

            (1600, 1000),

            Image.Resampling.LANCZOS

        )


        image.save(

            output_path,

            "JPEG",

            quality=88,

            optimize=True

        )


        return True


    except Exception:

        return False


# =========================================================
# WIKIMEDIA CANDIDATES
# =========================================================

def get_wikimedia_candidates(
    query: str
):

    try:

        response = requests.get(

            "https://commons.wikimedia.org/w/api.php",

            params={

                "action": "query",

                "generator": "search",

                "gsrsearch": query,

                "gsrnamespace": 6,

                "gsrlimit": 12,

                "prop": "imageinfo",

                "iiprop": "url",

                "iiurlwidth": 1600,

                "format": "json"

            },

            headers=IMAGE_HEADERS,

            timeout=7

        )


        if response.status_code != 200:

            return []


        data = response.json()


        pages = (

            data
            .get("query", {})
            .get("pages", {})
        )


        candidates = []


        for page in pages.values():

            info = page.get(
                "imageinfo",
                []
            )


            if not info:
                continue


            item = info[0]


            url = (

                item.get("thumburl")

                or item.get("url")

            )


            if not url:
                continue


            candidates.append(url)


        return candidates


    except Exception as e:

        save_error(
            f"Wikimedia error: {e}"
        )

        return []


# =========================================================
# OPENVERSE CANDIDATES
# =========================================================

def get_openverse_candidates(
    query: str
):

    try:

        response = requests.get(

            "https://api.openverse.org/v1/images/",

            params={

                "q": query,

                "page_size": 12

            },

            headers=IMAGE_HEADERS,

            timeout=7

        )


        if response.status_code != 200:

            return []


        data = response.json()


        candidates = []


        for item in data.get(
            "results",
            []
        ):

            url = (

                item.get("thumbnail")

                or item.get("url")

            )


            if url:

                candidates.append(url)


        return candidates


    except Exception as e:

        save_error(
            f"Openverse error: {e}"
        )

        return []


# =========================================================
# VISUAL QUERY BUILDER
# =========================================================

def build_visual_queries(
    slide: Dict[str, Any]
):

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


    visual_query = str(
        slide.get(
            "visual_query",
            ""
        )
    ).strip()


    queries = []


    if visual_query:

        queries.append(
            visual_query
        )


    if title:

        queries.append(

            f"{title} "
            f"educational academic photograph"

        )


    if title:

        queries.append(

            f"{title} "
            f"scientific diagram"

        )


    if title:

        queries.append(

            f"{title} "
            f"historical photograph"

        )


    if paragraph:

        words = paragraph.split()

        keyword_part = " ".join(
            words[:12]
        )

        queries.append(

            f"{keyword_part} "
            f"educational visual"

        )


    unique = []

    seen = set()


    for item in queries:

        item = item.strip()

        key = normalize_text(
            item
        )


        if (
            item
            and key not in seen
        ):

            unique.append(item)

            seen.add(key)


    return unique[:6]


# =========================================================
# UNIQUE IMAGE SELECTION
# =========================================================

def get_unique_visual(
    slide: Dict[str, Any],
    output_path: Path,
    used_urls: set,
    used_lock: threading.Lock
):

    queries = build_visual_queries(
        slide
    )


    # -----------------------------------------------------
    # WIKIMEDIA
    # -----------------------------------------------------

    for query in queries:

        candidates = (
            get_wikimedia_candidates(
                query
            )
        )


        for url in candidates:

            with used_lock:

                if url in used_urls:

                    continue

                used_urls.add(url)


            if download_image(
                url,
                output_path
            ):

                return True


            with used_lock:

                used_urls.discard(
                    url
                )


    # -----------------------------------------------------
    # OPENVERSE
    # -----------------------------------------------------

    for query in queries:

        candidates = (
            get_openverse_candidates(
                query
            )
        )


        for url in candidates:

            with used_lock:

                if url in used_urls:

                    continue

                used_urls.add(url)


            if download_image(
                url,
                output_path
            ):

                return True


            with used_lock:

                used_urls.discard(
                    url
                )


    return False


# =========================================================
# CREATE SLIDE VISUALS
# =========================================================

def create_slide_visuals(
    slides: List[Dict[str, Any]],
    job_id: str,
    presentation_id: str
):

    total = len(slides)


    visual_dir = (
        GENERATED_DIR
        / presentation_id
    )


    visual_dir.mkdir(
        parents=True,
        exist_ok=True
    )


    results = {}


    update_job(

        job_id,

        stage="visuals",

        message="Görseller aranıyor",

        progress=0,

        total=total

    )


    # Kullanılmış görsel URL'lerini
    # bütün sunum boyunca takip ediyoruz.
    used_urls = set()

    used_lock = threading.Lock()


    def worker(
        index: int
    ):

        output = (

            visual_dir
            / f"slide_{index + 1}.jpg"

        )


        success = get_unique_visual(

            slides[index],

            output,

            used_urls,

            used_lock

        )


        return (

            index,

            str(output)
            if success
            else None

        )


    with ThreadPoolExecutor(
        max_workers=3
    ) as executor:

        futures = [

            executor.submit(
                worker,
                i
            )

            for i in range(total)

        ]


        completed = 0


        for future in as_completed(
            futures
        ):

            try:

                index, path = (
                    future.result()
                )

                results[index] = path

            except Exception as e:

                save_error(
                    f"Visual worker error: {e}"
                )


            completed += 1


            update_job(

                job_id,

                stage="visuals",

                message="Görseller aranıyor",

                progress=completed,

                total=total

            )


    return results


# =========================================================
# PDF FONTS
# =========================================================

FONT_REGULAR = (
    BASE_DIR
    / "fonts"
    / "DejaVuSans.ttf"
)

FONT_BOLD = (
    BASE_DIR
    / "fonts"
    / "DejaVuSans-Bold.ttf"
)


if FONT_REGULAR.exists():

    try:

        pdfmetrics.registerFont(

            TTFont(
                "DejaVu",
                str(FONT_REGULAR)
            )

        )

    except Exception:
        pass


if FONT_BOLD.exists():

    try:

        pdfmetrics.registerFont(

            TTFont(
                "DejaVu-Bold",
                str(FONT_BOLD)
            )

        )

    except Exception:
        pass


def pdf_font():

    if FONT_REGULAR.exists():

        return "DejaVu"

    return "Helvetica"


def pdf_bold_font():

    if FONT_BOLD.exists():

        return "DejaVu-Bold"

    return "Helvetica-Bold"


# =========================================================
# TEXT WRAPPING
# =========================================================

def wrap_text(
    text: str,
    max_chars: int
):

    words = str(text).split()

    lines = []

    current = ""


    for word in words:

        candidate = (

            word

            if not current

            else current
            + " "
            + word

        )


        if len(candidate) <= max_chars:

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


def draw_wrapped_text(
    pdf,
    text,
    x,
    y,
    max_width,
    font_size=12,
    leading=17,
    bold=False
):

    font = (

        pdf_bold_font()

        if bold

        else pdf_font()

    )


    pdf.setFont(
        font,
        font_size
    )


    words = str(text).split()

    line = ""

    lines = []


    for word in words:

        test = (

            word

            if not line

            else line
            + " "
            + word

        )


        if pdf.stringWidth(

            test,

            font,

            font_size

        ) <= max_width:

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


    for item in lines:

        pdf.drawString(
            x,
            y,
            item
        )

        y -= leading


    return y


# =========================================================
# IMAGE DRAWING
# =========================================================

def draw_slide_image(
    pdf,
    image_path,
    x,
    y,
    width,
    height
):

    try:

        if not image_path:

            return False


        path = Path(
            image_path
        )


        if not path.exists():

            return False


        image = Image.open(
            path
        )


        image = ImageOps.exif_transpose(
            image
        )


        image.thumbnail(

            (
                int(width * 4),
                int(height * 4)
            ),

            Image.Resampling.LANCZOS

        )


        buffer = io.BytesIO()


        image.convert(
            "RGB"
        ).save(

            buffer,

            "JPEG",

            quality=88

        )


        buffer.seek(0)


        pdf.drawImage(

            ImageReader(buffer),

            x,

            y,

            width=width,

            height=height,

            preserveAspectRatio=True,

            anchor="c",

            mask="auto"

        )


        return True


    except Exception:

        return False


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

        pdf_bold_font(),

        12

    )


    pdf.drawCentredString(

        x + width / 2,

        y + height / 2,

        "K.A.R.V.I.S."

    )


    pdf.setFont(

        pdf_font(),

        8

    )


    pdf.drawCentredString(

        x + width / 2,

        y + height / 2 - 18,

        title[:60]

    )


# =========================================================
# PDF
# =========================================================

def create_presentation_pdf(
    outline,
    visual_paths,
    output_path,
    job_id
):

    slides = outline.get(
        "slides",
        []
    )


    total = len(slides)


    update_job(

        job_id,

        stage="pdf",

        message="PDF oluşturuluyor",

        progress=0,

        total=total

    )


    pdf = canvas.Canvas(

        str(output_path),

        pagesize=A4

    )


    width, height = A4


    # =====================================================
    # KAPAK
    # =====================================================

    pdf.setFont(

        pdf_bold_font(),

        28

    )


    title = outline.get(

        "title",

        "K.A.R.V.I.S. Sunumu"

    )


    title_lines = wrap_text(

        title,

        35

    )


    y = height / 2 + 40


    for line in title_lines:

        pdf.drawCentredString(

            width / 2,

            y,

            line

        )

        y -= 38


    pdf.setFont(

        pdf_font(),

        12

    )


    pdf.drawCentredString(

        width / 2,

        y - 15,

        "K.A.R.V.I.S. - KARAHAN INC."

    )


    pdf.showPage()


    # =====================================================
    # SLAYTLAR
    # =====================================================

    for index, slide in enumerate(
        slides
    ):

        title = str(

            slide.get(

                "title",

                f"Slayt {index + 1}"

            )

        )


        paragraph = str(

            slide.get(

                "paragraph",

                ""

            )

        )


        # -------------------------------------------------
        # BAŞLIK
        # -------------------------------------------------

        pdf.setFont(

            pdf_bold_font(),

            21

        )


        pdf.drawString(

            45,

            height - 55,

            title

        )


        # -------------------------------------------------
        # GÖRSEL
        # -------------------------------------------------

        image_path = (
            visual_paths.get(index)
        )


        image_x = 45

        image_y = height - 360

        image_w = width - 90

        image_h = 245


        if not draw_slide_image(

            pdf,

            image_path,

            image_x,

            image_y,

            image_w,

            image_h

        ):

            draw_fallback_visual(

                pdf,

                image_x,

                image_y,

                image_w,

                image_h,

                title

            )


        # -------------------------------------------------
        # AKADEMİK PARAGRAF
        # -------------------------------------------------

        text_y = height - 390


        text_y = draw_wrapped_text(

            pdf,

            paragraph,

            45,

            text_y,

            width - 90,

            font_size=10.5,

            leading=15

        )


        # -------------------------------------------------
        # FOOTER
        # -------------------------------------------------

        pdf.setFont(

            pdf_font(),

            7

        )


        pdf.drawRightString(

            width - 35,

            25,

            f"{index + 1} / {total}"

        )


        pdf.drawString(

            35,

            25,

            "K.A.R.V.I.S. - KARAHAN INC."

        )


        pdf.showPage()


        update_job(

            job_id,

            stage="pdf",

            message="PDF oluşturuluyor",

            progress=index + 1,

            total=total

        )


    pdf.save()


# =========================================================
# PRESENTATION WORKER
# =========================================================

def presentation_worker(
    job_id: str,
    topic: str,
    username: str,
    slide_count: int
):

    try:

        presentation_id = (
            uuid.uuid4().hex
        )


        # =================================================
        # İÇERİK
        # =================================================

        update_job(

            job_id,

            stage="content",

            message="Akademik içerik hazırlanıyor",

            progress=0,

            total=slide_count

        )


        outline = create_presentation_outline(

            topic,

            slide_count,

            username

        )


        slides = outline.get(

            "slides",

            []

        )


        if not slides:

            raise Exception(

                "Sunum içeriği oluşturulamadı."

            )


        # =================================================
        # GÖRSELLER
        # =================================================

        visual_paths = create_slide_visuals(

            slides,

            job_id,

            presentation_id

        )


        # =================================================
        # PDF
        # =================================================

        filename = (

            f"karvis_sunum_"
            f"{presentation_id}.pdf"

        )


        output_path = (

            GENERATED_DIR
            / filename

        )


        create_presentation_pdf(

            outline,

            visual_paths,

            output_path,

            job_id

        )


        file_url = (

            f"/generated/{filename}"

        )


        update_job(

            job_id,

            stage="completed",

            message="Sunum hazır",

            progress=len(slides),

            total=len(slides),

            completed=True,

            success=True,

            file_url=file_url

        )


    except Exception as e:

        save_error(

            f"Presentation "
            f"{job_id}: {e}"

        )


        update_job(

            job_id,

            stage="error",

            message="Sunum oluşturulamadı",

            completed=True,

            success=False,

            error=str(e)

        )


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():

    index_file = (
        BASE_DIR
        / "index.html"
    )


    if index_file.exists():

        return FileResponse(
            index_file
        )


    return {

        "app": "K.A.R.V.I.S.",

        "company": "KARAHAN INC.",

        "version": APP_VERSION,

        "status": "online"

    }


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health():

    return {

        "status": "ok",

        "app": "K.A.R.V.I.S.",

        "version": APP_VERSION,

        "groq":
            bool(groq_client),

        "openrouter":
            bool(openrouter_client)

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

    return {

        username: {

            "name": data["name"],

            "role": data["role"],

            "mode": data["mode"]

        }

        for username, data
        in USERS.items()

    }


# =========================================================
# PROFILE LOGIN
# =========================================================

@app.post("/profile-login")
def profile_login(
    request: ProfileLoginRequest
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

        raise HTTPException(

            status_code=404,

            detail="Kullanıcı bulunamadı."

        )


    if user["password"] != request.password:

        raise HTTPException(

            status_code=401,

            detail="Şifre hatalı."

        )


    return {

        "success": True,

        "username": username,

        "name": user["name"],

        "role": user["role"],

        "mode": user["mode"]

    }


# =========================================================
# ACADEMIC MODES
# =========================================================

@app.get("/academic-modes")
def academic_modes():

    return {

        "modes":
            ACADEMIC_MODES

    }


# =========================================================
# CHAT
# =========================================================

@app.post("/chat")
def chat(
    request: ChatRequest
):

    if not request.message.strip():

        return {

            "success": False,

            "reply":
                "Mesaj boş olamaz."

        }


    try:

        reply = ask_ai(

            request.message,

            request.username,

            request.mode

        )


        return {

            "success": True,

            "reply": reply,

            "mode": get_user_mode(

                request.username,

                request.mode

            )

        }


    except Exception as e:

        save_error(

            f"Chat error: {e}"

        )


        return {

            "success": False,

            "reply":
                "Bir hata oluştu.",

            "error":
                str(e)

        }


# =========================================================
# RESEARCH
# =========================================================

@app.post("/research")
def research(
    request: ResearchRequest
):

    if not request.query.strip():

        return {

            "success": False,

            "error":
                "Arama sorgusu boş."

        }


    results = web_search(

        request.query,

        limit=6

    )


    context = ""


    for item in results:

        context += (

            f"Başlık: "
            f"{item['title']}\n"

            f"URL: "
            f"{item['url']}\n\n"

        )


    prompt = f"""

Kullanıcı şu konuda araştırma istiyor:

{request.query}

İnternetten bulunan sonuçlar:

{context}

Bu bilgileri kullanarak Türkçe,
anlaşılır ve düzenli bir araştırma
özeti hazırla.

Kaynakları ayrıca listele.

"""


    answer = ask_ai(

        prompt,

        request.username,

        mode="research"

    )


    return {

        "success": True,

        "answer": answer,

        "results": results

    }


# =========================================================
# PRESENTATION START
# =========================================================

@app.post("/presentation")
def presentation(

    request: PresentationRequest,

    background_tasks: BackgroundTasks

):

    topic = request.topic.strip()


    if not topic:

        raise HTTPException(

            status_code=400,

            detail="Sunum konusu boş olamaz."

        )


    slide_count = max(

        5,

        min(

            int(
                request.slide_count
                or 7
            ),

            10

        )

    )


    job_id = create_job()


    background_tasks.add_task(

        presentation_worker,

        job_id,

        topic,

        request.username,

        slide_count

    )


    return {

        "success": True,

        "job_id": job_id,

        "message":
            "Sunum hazırlanmaya başladı."

    }


# =========================================================
# PRESENTATION STATUS
# =========================================================

@app.get(
    "/presentation-status/{job_id}"
)
def presentation_status(
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
                    "Sunum işi bulunamadı."

            )


        return dict(job)


# =========================================================
# GENERATED FILES
# =========================================================

@app.get(
    "/generated/{filename}"
)
def generated_file(
    filename: str
):

    safe_name = Path(
        filename
    ).name


    file_path = (

        GENERATED_DIR
        / safe_name

    )


    if not file_path.exists():

        raise HTTPException(

            status_code=404,

            detail="Dosya bulunamadı."

        )


    return FileResponse(

        file_path,

        media_type="application/pdf",

        filename=safe_name

    )


# =========================================================
# MEMORY
# =========================================================

@app.get("/memory")
def get_memory(
    username: str = "karahan"
):

    memory = load_memory()


    return {

        "success": True,

        "username": username,

        "memory": memory.get(

            username,

            {}

        )

    }


@app.post("/memory")
def add_memory(
    request: MemoryRequest
):

    with memory_lock:

        memory = load_memory()


        if request.username not in memory:

            memory[
                request.username
            ] = {}


        memory[
            request.username
        ][
            request.key
        ] = request.value


        save_memory(
            memory
        )


    return {

        "success": True,

        "memory":
            memory[
                request.username
            ]

    }


# =========================================================
# NEW CHAT
# =========================================================

@app.post("/new-chat")
def new_chat(
    username: str = "karahan"
):

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
            load_errors()

    }


# =========================================================
# STARTUP
# =========================================================

@app.on_event("startup")
def startup_event():

    print("=" * 60)

    print(
        "K.A.R.V.I.S. - KARAHAN INC."
    )

    print(
        f"Version: {APP_VERSION}"
    )

    print(
        "Server starting..."
    )

    print(

        "Groq: "
        + (
            "CONNECTED"
            if groq_client
            else "NOT CONFIGURED"
        )

    )

    print(

        "OpenRouter: "
        + (
            "CONNECTED"
            if openrouter_client
            else "NOT CONFIGURED"
        )

    )

    print("=" * 60)
