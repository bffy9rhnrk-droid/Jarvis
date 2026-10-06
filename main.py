import os
import re
import json
import uuid
import html
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

import requests

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from openai import OpenAI

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from PIL import Image
from io import BytesIO


# =========================================================
# UYGULAMA
# =========================================================

APP_VERSION = "22.0.0"

BASE_DIR = Path(__file__).resolve().parent

INDEX_FILE = BASE_DIR / "index.html"

MEMORY_FILE = BASE_DIR / "jarvis_memory.json"

ERROR_FILE = BASE_DIR / "jarvis_errors.json"

PRESENTATION_DIR = BASE_DIR / "generated_presentations"

PRESENTATION_DIR.mkdir(
    exist_ok=True
)


app = FastAPI(
    title="K.A.R.V.I.S.",
    version=APP_VERSION
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# =========================================================
# API ANAHTARLARI
# =========================================================

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY",
    ""
)

OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    ""
)


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


# =========================================================
# KULLANICILAR
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
        "name": "Sunum Asistanı",
        "icon": "🎞️"
    }

}


# =========================================================
# MODELLER
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


# =========================================================
# DOSYA SISTEMI
# =========================================================

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


# =========================================================
# MEMORY
# =========================================================

def load_memory():

    return load_json_file(
        MEMORY_FILE,
        {}
    )


def save_memory(memory):

    save_json_file(
        MEMORY_FILE,
        memory
    )


def get_user_memory(username):

    memory = load_memory()

    if username not in memory:

        memory[username] = []

    return memory


def add_memory(username, role, content):

    memory = load_memory()

    if username not in memory:

        memory[username] = []

    memory[username].append({

        "role": role,

        "content": content,

        "time": datetime.now().isoformat()

    })

    memory[username] = memory[username][-30:]

    save_memory(memory)


# =========================================================
# HATA SISTEMI
# =========================================================

def save_error(
    provider,
    error_type,
    message,
    detail=""
):

    errors = load_json_file(
        ERROR_FILE,
        []
    )

    errors.append({

        "provider": provider,

        "type": error_type,

        "message": str(message),

        "error": str(detail),

        "time":
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

    })

    errors = errors[-100:]

    save_json_file(
        ERROR_FILE,
        errors
    )


# =========================================================
# KULLANICI NORMALIZE
# =========================================================

def normalize_username(username):

    username = (
        username or "karahan"
    ).strip().lower()

    if username == "betül":
        username = "betul"

    return username


# =========================================================
# SISTEM PROMPT
# =========================================================

def build_system_prompt(
    username,
    mode="normal"
):

    user = USERS.get(
        username,
        USERS["karahan"]
    )

    personality = user["personality"]


    if personality == "teacher":

        prompt = """
Sen K.A.R.V.I.S.'sin.

İlknur Hocam'ın kişisel akademik asistanısın.

Hocam ile her zaman saygılı,
profesyonel, akademik ve yardımcı
bir üslupla konuş.

Gereksiz yere robotik konuşma.

Türkçeyi doğal kullan.

Bir akademik konuda emin olmadığın
bilgiyi kesin gerçek gibi sunma.

Güncel bilgi gerektiğinde araştırma
modunun sağladığı internet kaynaklarını
kullan.

Kaynaklardan elde edilen bilgileri
özetle ve anlaşılır şekilde sun.

Öğretmenin amacı öğrencilere ders
anlatmaksa içeriği öğrenci seviyesine
uygun hale getir.

Uzun cevap gerekiyorsa başlıklar,
maddeler ve tablolar kullan.
"""

    elif personality == "betul":

        prompt = """
Sen K.A.R.V.I.S.'sin.

Betül ile samimi ve eğlenceli konuş.

Gerektiğinde hafif şakalaşabilirsin.

Ancak bilgi verirken doğru ve faydalı ol.
"""

    elif personality == "sinem":

        prompt = """
Sen K.A.R.V.I.S.'sin.

Sinem ile sıcak, nazik ve sevecen konuş.

Gerektiğinde prenses şeklinde
hitap edebilirsin.

Bilgi verirken doğru ve faydalı ol.
"""

    else:

        prompt = """
Sen K.A.R.V.I.S.'sin.

Ana kullanıcın Karahan.

Kullanıcıya doğal, profesyonel,
yardımcı ve gerektiğinde samimi
bir Türkçe ile cevap ver.

Gereksiz şekilde robotik davranma.
"""


    mode_instructions = {

        "research": """
ARAŞTIRMA MODUNDASIN.

Güncel bilgi isteyen konularda
internet araştırma sonuçlarını
dikkate al.

Kaynakların güvenilirliğini
değerlendir.

Cevap sonunda mümkünse
"Kullanılan kaynaklar" bölümü oluştur.
""",

        "academic": """
AKADEMİK MODDASIN.

Akademik kavramları açıkla.

Neden-sonuç ilişkileri kur.

Gerekirse karşılaştırma tabloları,
kavramsal çerçeveler ve örnekler kullan.
""",

        "article": """
MAKALE ASİSTANI MODUNDASIN.

Akademik makale hazırlamaya yardımcı ol.

Başlık, özet, anahtar kelimeler,
giriş, yöntem, bulgular, tartışma
ve sonuç gibi bölümleri uygun
olduğunda kullan.

Uydurma kaynak üretme.
""",

        "lesson": """
DERS ASİSTANI MODUNDASIN.

Öğretmen için ders anlatımı hazırla.

Konu anlatımı,
ders planı,
öğrenme hedefleri,
örnekler,
etkinlikler,
soru-cevap ve değerlendirme
önerileri oluşturabilirsin.

Öğrenci seviyesine uygun anlat.
""",

        "quiz": """
SINAV / QUIZ MODUNDASIN.

Sorular hazırlayabilirsin.

Çoktan seçmeli,
doğru-yanlış,
boşluk doldurma,
eşleştirme ve açık uçlu
sorular oluşturabilirsin.

İstenirse cevap anahtarı ekle.
""",

        "presentation": """
SUNUM ASİSTANI MODUNDASIN.

Öğretmen için profesyonel eğitim
sunumu hazırlamaya yardımcı ol.

Sunumları öğrenci seviyesine göre
tasarla.

Slayt başına aşırı metin koyma.

Başlıkları kısa ve anlaşılır tut.

Görsel, harita, zaman çizelgesi,
şema, tablo veya infografik
kullanılabilecek yerleri belirt.

Sunumun öğretmenin sınıfta
kullanabileceği şekilde düzenli
olmasını sağla.
"""

    }


    if mode in mode_instructions:

        prompt += "\n" + mode_instructions[mode]


    return prompt


# =========================================================
# AI CEVABI
# =========================================================

def call_ai(
    system_prompt,
    user_message,
    temperature=0.4,
    max_tokens=5000
):

    providers = []


    if groq_client:

        providers.append({

            "name": "groq-120b",

            "client": groq_client,

            "model": "openai/gpt-oss-120b"

        })


        providers.append({

            "name": "groq-20b",

            "client": groq_client,

            "model": "openai/gpt-oss-20b"

        })


    if openrouter_client:

        providers.append({

            "name": "openrouter",

            "client": openrouter_client,

            "model":
                "openai/gpt-oss-20b:free"

        })


    if not providers:

        raise RuntimeError(
            "Yapay zeka API anahtarı bulunamadı."
        )


    last_error = None


    for provider in providers:

        try:

            response = provider["client"].chat.completions.create(

                model=provider["model"],

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

                temperature=temperature,

                max_tokens=max_tokens

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

                provider["name"],

                "AI_PROVIDER_ERROR",

                str(error),

                repr(error)

            )


    raise RuntimeError(
        str(last_error)
        if last_error
        else "AI sağlayıcıları cevap vermedi."
    )


# =========================================================
# INTERNET ARAŞTIRMA
# =========================================================

def internet_search(
    query,
    limit=6
):

    try:

        url = (
            "https://html.duckduckgo.com/html/?q="
            + quote(query)
        )


        response = requests.get(

            url,

            headers={
                "User-Agent":
                    "Mozilla/5.0"
            },

            timeout=15
        )


        response.raise_for_status()


        from bs4 import BeautifulSoup

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )


        results = []


        for result in soup.select(
            ".result"
        )[:limit]:

            title_node = result.select_one(
                ".result__a"
            )

            snippet_node = result.select_one(
                ".result__snippet"
            )


            if not title_node:
                continue


            title = title_node.get_text(
                " ",
                strip=True
            )


            link = title_node.get(
                "href",
                ""
            )


            snippet = ""

            if snippet_node:

                snippet = snippet_node.get_text(
                    " ",
                    strip=True
                )


            if title:

                results.append({

                    "title": title,

                    "url": link,

                    "snippet": snippet

                })


        return results


    except Exception as error:

        save_error(

            "internet",

            "SEARCH_ERROR",

            str(error),

            repr(error)

        )

        return []


def build_research_context(
    query
):

    results =
        internet_search(
            query,
            8
        )


    if not results:

        return (
            "İnternet araştırmasında sonuç "
            "bulunamadı."
        ), []


    lines = [

        "İNTERNET ARAŞTIRMA SONUÇLARI:"

    ]


    for index, item in enumerate(
        results,
        1
    ):

        lines.append(

            f"{index}. {item['title']}\n"
            f"URL: {item['url']}\n"
            f"Özet: {item['snippet']}"

        )


    return "\n\n".join(lines), results


# =========================================================
# WIKIMEDIA GÖRSEL ARAŞTIRMA
# =========================================================

def search_wikimedia_image(
    query
):

    try:

        api_url = (
            "https://commons.wikimedia.org/w/api.php"
        )


        params = {

            "action": "query",

            "generator": "search",

            "gsrsearch": query,

            "gsrnamespace": 6,

            "gsrlimit": 5,

            "prop": "imageinfo",

            "iiprop": "url",

            "iiurlwidth": 1000,

            "format": "json"

        }


        response = requests.get(

            api_url,

            params=params,

            headers={
                "User-Agent":
                    "KARVIS-Educational-Assistant/1.0"
            },

            timeout=15

        )


        response.raise_for_status()


        data = response.json()


        pages = (
            data
            .get("query", {})
            .get("pages", {})
        )


        for page in pages.values():

            info = (
                page
                .get("imageinfo", [])
            )


            if not info:
                continue


            image_url = (
                info[0]
                .get("thumburl")
                or info[0].get("url")
            )


            if image_url:

                return image_url


    except Exception as error:

        save_error(

            "wikimedia",

            "IMAGE_SEARCH_ERROR",

            str(error),

            repr(error)

        )


    return None


def download_image(
    image_url
):

    if not image_url:
        return None


    try:

        response = requests.get(

            image_url,

            headers={
                "User-Agent":
                    "KARVIS-Educational-Assistant/1.0"
            },

            timeout=20
        )


        response.raise_for_status()


        image = Image.open(
            BytesIO(response.content)
        )


        if image.mode not in (
            "RGB",
            "RGBA"
        ):

            image = image.convert(
                "RGB"
            )


        return image


    except Exception as error:

        save_error(

            "wikimedia",

            "IMAGE_DOWNLOAD_ERROR",

            str(error),

            repr(error)

        )

        return None


# =========================================================
# JSON AYIKLAMA
# =========================================================

def extract_json(text):

    text = text.strip()


    text = re.sub(

        r"^```json\s*",

        "",

        text,

        flags=re.IGNORECASE

    )


    text = re.sub(

        r"^```\s*",

        "",

        text

    )


    text = re.sub(

        r"\s*```$",

        "",

        text

    )


    start = text.find("{")

    end = text.rfind("}")


    if start == -1 or end == -1:

        raise ValueError(
            "AI geçerli JSON üretmedi."
        )


    json_text =
        text[start:end + 1]


    return json.loads(
        json_text
    )


# =========================================================
# SUNUM İÇERİĞİ
# =========================================================

def generate_presentation_content(
    topic,
    research_context="",
    slide_count=12,
    student_level="genel"
):

    system_prompt = """

Sen profesyonel bir eğitim sunumu
tasarımcısısın.

Bir öğretmenin sınıfta kullanacağı
sunumun içeriğini hazırlıyorsun.

Çıktıyı SADECE geçerli JSON olarak ver.

JSON formatı:

{
  "title": "...",
  "subtitle": "...",
  "audience": "...",
  "slides": [
    {
      "title": "...",
      "body": ["...", "..."],
      "visual": "...",
      "visual_type": "image"
    }
  ]
}

Kurallar:

- İstenen slayt sayısına mümkün olduğunca uy.
- İlk slayt kapak olsun.
- Son slayt özet veya değerlendirme olsun.
- Slayt başına 3-5 kısa madde kullan.
- Uzun paragraf kullanma.
- Öğrencinin anlayabileceği bir dil kullan.
- Önemli tarihleri ve kavramları öne çıkar.
- Görsel kullanılabilecek her slayt için
  visual alanına İngilizce kısa bir arama
  ifadesi yaz.
- Uygun yerlerde harita, belge, zaman çizelgesi,
  bilimsel şema veya infografik öner.
- Yanlış bilgi üretme.
- Verilen araştırma sonuçlarını dikkate al.
"""


    user_prompt = f"""

KONU:
{topic}

ÖĞRENCİ SEVİYESİ:
{student_level}

SLAYT SAYISI:
{slide_count}

ARAŞTIRMA:
{research_context}

Profesyonel, eğitim amaçlı,
görsellerle desteklenebilecek
bir sunum oluştur.
"""


    answer = call_ai(

        system_prompt,

        user_prompt,

        temperature=0.25,

        max_tokens=9000

    )


    data = extract_json(
        answer
    )


    if not isinstance(
        data.get("slides"),
        list
    ):

        raise ValueError(
            "Sunum slaytları bulunamadı."
        )


    return data


# =========================================================
# PDF YARDIMCILARI
# =========================================================

PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)


def draw_wrapped_text(
    pdf,
    text,
    x,
    y,
    max_width,
    font="Helvetica",
    size=17,
    leading=23,
    color=colors.white
):

    pdf.setFont(
        font,
        size
    )

    pdf.setFillColor(
        color
    )


    words = str(text).split()

    line = ""


    for word in words:

        test_line = (
            line + " " + word
        ).strip()


        if pdf.stringWidth(
            test_line,
            font,
            size
        ) <= max_width:

            line = test_line

        else:

            pdf.drawString(
                x,
                y,
                line
            )

            y -= leading

            line = word


    if line:

        pdf.drawString(
            x,
            y,
            line
        )

        y -= leading


    return y


def draw_image_cover(
    pdf,
    image,
    x,
    y,
    width,
    height
):

    try:

        image_width, image_height = image.size


        scale = max(

            width / image_width,

            height / image_height

        )


        new_width =
            image_width * scale

        new_height =
            image_height * scale


        image = image.resize(

            (
                int(new_width),
                int(new_height)
            )
        )


        left =
            (new_width - width) / 2

        bottom =
            (new_height - height) / 2


        crop =
            image.crop(

                (
                    int(left),
                    int(bottom),
                    int(left + width),
                    int(bottom + height)
                )

            )


        buffer =
            BytesIO()

        crop.save(
            buffer,
            format="JPEG",
            quality=88
        )

        buffer.seek(0)


        pdf.drawImage(

            ImageReader(buffer),

            x,
            y,

            width=width,

            height=height,

            preserveAspectRatio=False,

            mask="auto"

        )


    except Exception:

        pdf.setFillColor(
            colors.HexColor("#0d2529")
        )

        pdf.rect(
            x,
            y,
            width,
            height,
            fill=1,
            stroke=0
        )


def create_presentation_pdf(
    presentation,
    topic
):

    filename = (
        "KARVIS_"
        + re.sub(
            r"[^a-zA-Z0-9_-]",
            "_",
            topic
        )[:35]
        + "_"
        + uuid.uuid4().hex[:8]
        + ".pdf"
    )


    path =
        PRESENTATION_DIR / filename


    pdf = canvas.Canvas(

        str(path),

        pagesize=landscape(A4)

    )


    pdf.setTitle(
        presentation.get(
            "title",
            topic
        )
    )


    slides =
        presentation.get(
            "slides",
            []
        )


    for index, slide in enumerate(
        slides
    ):

        # -----------------------------------------
        # ARKA PLAN
        # -----------------------------------------

        pdf.setFillColor(
            colors.HexColor("#061216")
        )

        pdf.rect(

            0,
            0,
            PAGE_WIDTH,
            PAGE_HEIGHT,

            fill=1,
            stroke=0
        )


        # -----------------------------------------
        # ÜST ÇİZGİ
        # -----------------------------------------

        pdf.setStrokeColor(
            colors.HexColor("#00d9e8")
        )

        pdf.setLineWidth(1)

        pdf.line(

            38,
            PAGE_HEIGHT - 38,

            PAGE_WIDTH - 38,
            PAGE_HEIGHT - 38

        )


        # -----------------------------------------
        # KAPAK
        # -----------------------------------------

        if index == 0:

            image_query = (
                presentation
                .get("title", topic)
            )


            image_url =
                search_wikimedia_image(
                    image_query
                )


            image =
                download_image(
                    image_url
                )


            if image:

                draw_image_cover(

                    pdf,

                    image,

                    PAGE_WIDTH * 0.56,

                    0,

                    PAGE_WIDTH * 0.44,

                    PAGE_HEIGHT

                )


                pdf.setFillColor(
                    colors.Color(
                        0,
                        0,
                        0,
                        alpha=0.35
                    )
                )

                pdf.rect(

                    PAGE_WIDTH * 0.56,

                    0,

                    PAGE_WIDTH * 0.44,

                    PAGE_HEIGHT,

                    fill=1,

                    stroke=0

                )


            pdf.setFillColor(
                colors.HexColor("#00f0ff")
            )

            pdf.setFont(
                "Helvetica-Bold",
                12
            )

            pdf.drawString(

                55,

                PAGE_HEIGHT - 100,

                "K.A.R.V.I.S. ACADEMIC"

            )


            title =
                presentation.get(
                    "title",
                    topic
                )


            y =
                PAGE_HEIGHT - 190


            y = draw_wrapped_text(

                pdf,

                title,

                55,

                y,

                PAGE_WIDTH * 0.44,

                font="Helvetica-Bold",

                size=31,

                leading=38,

                color=colors.white

            )


            subtitle =
                presentation.get(
                    "subtitle",
                    ""
                )


            draw_wrapped_text(

                pdf,

                subtitle,

                55,

                y - 12,

                PAGE_WIDTH * 0.40,

                font="Helvetica",

                size=16,

                leading=23,

                color=colors.HexColor("#9ccdd2")

            )


        else:

            # -------------------------------------
            # NORMAL SLAYT
            # -------------------------------------

            title =
                slide.get(
                    "title",
                    "Konu"
                )


            body =
                slide.get(
                    "body",
                    []
                )


            visual_query =
                slide.get(
                    "visual",
                    ""
                )


            # Sol içerik

            pdf.setFillColor(
                colors.HexColor("#00e6f2")
            )

            pdf.setFont(
                "Helvetica-Bold",
                24
            )

            pdf.drawString(

                48,

                PAGE_HEIGHT - 82,

                title[:80]

            )


            pdf.setStrokeColor(
                colors.HexColor("#15383e")
            )

            pdf.line(

                48,

                PAGE_HEIGHT - 102,

                PAGE_WIDTH * 0.60,

                PAGE_HEIGHT - 102

            )


            y =
                PAGE_HEIGHT - 145


            for bullet in body[:6]:

                pdf.setFillColor(
                    colors.HexColor("#00e6f2")
                )

                pdf.circle(

                    58,

                    y + 4,

                    3,

                    fill=1,

                    stroke=0

                )


                y = draw_wrapped_text(

                    pdf,

                    bullet,

                    72,

                    y,

                    PAGE_WIDTH * 0.47,

                    font="Helvetica",

                    size=15,

                    leading=22,

                    color=colors.HexColor("#e8f8fa")

                )

                y -= 8


            # Sağ görsel

            image = None


            if visual_query:

                image_url =
                    search_wikimedia_image(
                        visual_query
                    )


                image =
                    download_image(
                        image_url
                    )


            image_x =
                PAGE_WIDTH * 0.64


            image_y = 90


            image_width =
                PAGE_WIDTH * 0.30


            image_height =
                PAGE_HEIGHT - 155


            if image:

                draw_image_cover(

                    pdf,

                    image,

                    image_x,

                    image_y,

                    image_width,

                    image_height

                )

            else:

                # Görsel bulunamazsa
                # profesyonel bilgi paneli

                pdf.setFillColor(
                    colors.HexColor("#0a2025")
                )

                pdf.roundRect(

                    image_x,

                    image_y,

                    image_width,

                    image_height,

                    12,

                    fill=1,

                    stroke=0

                )


                pdf.setFillColor(
                    colors.HexColor("#6cabb1")
                )

                pdf.setFont(
                    "Helvetica",
                    12
                )

                pdf.drawCentredString(

                    image_x +
                    image_width / 2,

                    image_y +
                    image_height / 2,

                    "GÖRSEL / ŞEMA"

                )


            # Sayfa numarası

            pdf.setFillColor(
                colors.HexColor("#577b80")
            )

            pdf.setFont(
                "Helvetica",
                9
            )

            pdf.drawRightString(

                PAGE_WIDTH - 42,

                30,

                f"{index + 1} / {len(slides)}"

            )


        pdf.showPage()


    pdf.save()


    return filename


# =========================================================
# SUNUM ÜRET
# =========================================================

def create_presentation(
    topic,
    slide_count=12,
    student_level="genel"
):

    research_context, research_results = (
        build_research_context(
            topic
        )
    )


    presentation = (
        generate_presentation_content(

            topic,

            research_context,

            slide_count,

            student_level

        )
    )


    filename =
        create_presentation_pdf(

            presentation,

            topic

        )


    return {

        "filename": filename,

        "url":
            "/presentation/"
            + filename,

        "title":
            presentation.get(
                "title",
                topic
            ),

        "slide_count":
            len(
                presentation.get(
                    "slides",
                    []
                )
            ),

        "sources":
            research_results

    }


# =========================================================
# SUNUM KOMUTU ALGILAMA
# =========================================================

def looks_like_presentation_request(
    message
):

    text =
        message.lower()


    keywords = [

        "sunum hazırla",

        "sunum hazırlar mısın",

        "sunum oluştur",

        "sunum yap",

        "pdf sunum",

        "pdf hazırla",

        "slayt hazırla",

        "slayt oluştur",

        "sunum hazırlayabilir misin"

    ]


    return any(
        keyword in text
        for keyword in keywords
    )


def extract_slide_count(
    message,
    default=12
):

    patterns = [

        r"(\d+)\s*slayt",

        r"(\d+)\s*sayfalık",

        r"(\d+)\s*sayfa",

        r"(\d+)\s*slaytlık"

    ]


    for pattern in patterns:

        match = re.search(
            pattern,
            message.lower()
        )


        if match:

            number =
                int(
                    match.group(1)
                )


            return max(
                5,
                min(
                    number,
                    30
                )
            )


    return default


def extract_student_level(
    message
):

    patterns = [

        r"(\d+)\.\s*sınıf",

        r"(\d+)\s*sınıf",

        r"üniversite",

        r"lisans",

        r"lise",

        r"ortaokul",

        r"ilkokul"

    ]


    for pattern in patterns:

        match = re.search(
            pattern,
            message.lower()
        )


        if match:

            return match.group(0)


    return "genel"


# =========================================================
# CHAT
# =========================================================

@app.post("/chat")
def chat(request: ChatRequest):

    username =
        normalize_username(
            request.username
        )


    if username not in USERS:

        username = "karahan"


    mode =
        request.mode or "normal"


    if (
        username == "ilknur"
        and mode == "normal"
    ):

        mode = "lesson"


    message =
        request.message.strip()


    if not message:

        raise HTTPException(
            status_code=400,
            detail="Mesaj boş olamaz."
        )


    # -----------------------------------------
    # SUNUM
    # -----------------------------------------

    if (
        username == "ilknur"
        and (
            mode == "presentation"
            or looks_like_presentation_request(
                message
            )
        )
    ):

        try:

            slide_count =
                extract_slide_count(
                    message
                )


            student_level =
                extract_student_level(
                    message
                )


            presentation =
                create_presentation(

                    message,

                    slide_count,

                    student_level

                )


            answer = (

                "Elbette Hocam. Profesyonel "
                "sunumunuzu hazırladım.\n\n"

                f"📚 {presentation['title']}\n"

                f"🎞️ {presentation['slide_count']} slayt\n"

                f"🎓 Seviye: {student_level}\n\n"

                "Sunum görseller, başlıklar ve "
                "öğrenci seviyesine uygun içerikle "
                "hazırlandı.\n\n"

                "📄 PDF dosyası hazır."

            )


            add_memory(
                username,
                "user",
                message
            )


            add_memory(
                username,
                "assistant",
                answer
            )


            return {

                "answer": answer,

                "presentation": True,

                "file_url":
                    presentation["url"],

                "file_name":
                    presentation["filename"]

            }


        except Exception as error:

            save_error(

                "presentation",

                "PRESENTATION_ERROR",

                str(error),

                repr(error)

            )


            raise HTTPException(

                status_code=500,

                detail={
                    "type":
                        "PRESENTATION_ERROR",

                    "message":
                        "Sunum PDF'i oluşturulurken "
                        "bir hata oluştu.",

                    "error":
                        str(error)

                }

            )


    # -----------------------------------------
    # ARAŞTIRMA
    # -----------------------------------------

    research_context = ""

    research_results = []


    if (
        username == "ilknur"
        and mode == "research"
    ):

        research_context, research_results = (
            build_research_context(
                message
            )
        )


    system_prompt =
        build_system_prompt(
            username,
            mode
        )


    if research_context:

        user_message = f"""

Kullanıcının sorusu:

{message}

İnternet araştırması:

{research_context}

Bu araştırma sonuçlarını
değerlendirerek cevap ver.

Araştırmada kesin olmayan bilgileri
kesin gerçek olarak sunma.

Cevabın sonunda önemli kaynakları
belirt.
"""

    else:

        user_message =
            message


    try:

        answer =
            call_ai(

                system_prompt,

                user_message

            )


    except Exception as error:

        raise HTTPException(

            status_code=500,

            detail={
                "type": "AI_ERROR",

                "message":
                    "K.A.R.V.I.S. şu anda "
                    "cevap oluşturamadı.",

                "error":
                    str(error)
            }

        )


    add_memory(
        username,
        "user",
        message
    )


    add_memory(
        username,
        "assistant",
        answer
    )


    return {

        "answer": answer,

        "research":
            bool(research_results),

        "sources":
            research_results

    }


# =========================================================
# RESEARCH ENDPOINT
# =========================================================

@app.post("/research")
def research(
    request: ResearchRequest
):

    username =
        normalize_username(
            request.username
        )


    context, results =
        build_research_context(
            request.query
        )


    return {

        "query":
            request.query,

        "results":
            results,

        "context":
            context

    }


# =========================================================
# ACADEMIC MODLAR
# =========================================================

@app.get("/academic-modes")
def academic_modes():

    return {

        "default":
            "lesson",

        "modes":
            ACADEMIC_MODES

    }


# =========================================================
# USERS
# =========================================================

@app.get("/users")
def users():

    return {

        "users": [

            {
                "username":
                    user["username"],

                "name":
                    user["name"],

                "role":
                    user["role"]

            }

            for user in USERS.values()

        ]

    }


# =========================================================
# LOGIN
# =========================================================

@app.post("/profile-login")
def profile_login(
    request: LoginRequest
):

    username =
        normalize_username(
            request.username
        )


    if username not in USERS:

        raise HTTPException(

            status_code=401,

            detail="Kullanıcı bulunamadı."

        )


    user =
        USERS[username]


    if user["password"] is not None:

        if request.password != user["password"]:

            raise HTTPException(

                status_code=401,

                detail="Şifre yanlış."

            )


    return {

        "success": True,

        "username":
            username,

        "name":
            user["name"],

        "role":
            user["role"],

        "teacher_mode":
            username == "ilknur",

        "default_mode":
            "lesson"
            if username == "ilknur"
            else "normal",

        "academic_modes":
            ACADEMIC_MODES

    }


# =========================================================
# MEMORY
# =========================================================

@app.get("/memory")
def memory(
    username: str = "karahan"
):

    username =
        normalize_username(
            username
        )


    return {

        "username":
            username,

        "memory":
            get_user_memory(
                username
            )

    }


@app.delete("/memory")
def delete_memory(
    username: str = "karahan"
):

    username =
        normalize_username(
            username
        )


    memory =
        load_memory()


    memory[username] = []


    save_memory(
        memory
    )


    return {
        "success": True
    }


# =========================================================
# NEW CHAT
# =========================================================

@app.post("/new-chat")
def new_chat(
    username: str = "karahan"
):

    username =
        normalize_username(
            username
        )


    memory =
        load_memory()


    memory[username] = []


    save_memory(
        memory
    )


    return {
        "success": True
    }


# =========================================================
# ERRORS
# =========================================================

@app.get("/errors")
def errors():

    return {

        "errors":
            load_json_file(
                ERROR_FILE,
                []
            )

    }


@app.delete("/errors")
def delete_errors():

    save_json_file(
        ERROR_FILE,
        []
    )


    return {
        "success": True
    }


# =========================================================
# PRESENTATION FILE
# =========================================================

@app.get("/presentation/{filename}")
def presentation_file(
    filename: str
):

    safe_name =
        Path(filename).name


    file_path =
        PRESENTATION_DIR / safe_name


    if not file_path.exists():

        raise HTTPException(
            status_code=404,
            detail="PDF bulunamadı."
        )


    return FileResponse(

        path=str(file_path),

        media_type="application/pdf",

        filename=safe_name

    )


# =========================================================
# ANA SAYFA
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
# ICON
# =========================================================

@app.get("/icon.png")
def icon():

    icon_file =
        BASE_DIR / "icon.png"


    if not icon_file.exists():

        raise HTTPException(
            status_code=404,
            detail="icon.png bulunamadı."
        )


    return FileResponse(
        str(icon_file),
        media_type="image/png"
    )


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health():

    return {

        "status":
            "online",

        "version":
            APP_VERSION,

        "groq":
            bool(groq_client),

        "openrouter":
            bool(openrouter_client),

        "web_research":
            True,

        "academic_system":
            True,

        "presentation_pdf":
            True,

        "teacher_profile":
            True

    }


# =========================================================
# VERSION
# =========================================================

@app.get("/version")
def version():

    return {

        "version":
            APP_VERSION,

        "name":
            "K.A.R.V.I.S.",

        "company":
            "KARAHAN INC.",

        "web_research":
            True,

        "academic_teacher":
            True,

        "presentation_pdf":
            True,

        "visual_presentations":
            True

    }
