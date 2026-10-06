import os
import re
import json
import uuid
import textwrap
import urllib.request
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


# ============================================================
# KARVIS - KARAHAN INC.
# BACKEND
# ============================================================

APP_VERSION = "24.0.0"

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
    allow_headers=["*"],
)


app.mount(
    "/files",
    StaticFiles(directory=str(FILES_DIR)),
    name="files"
)


# ============================================================
# API ANAHTARLARI
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()


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
# FONT SİSTEMİ
# ============================================================

REGULAR_FONT = "Helvetica"
BOLD_FONT = "Helvetica-Bold"


def install_dejavu_fonts():

    regular = FONT_DIR / "DejaVuSans.ttf"
    bold = FONT_DIR / "DejaVuSans-Bold.ttf"

    # --------------------------------------------------------
    # 1. Proje klasöründe mevcutsa kullan
    # --------------------------------------------------------

    if regular.exists() and bold.exists():
        return regular, bold

    # --------------------------------------------------------
    # 2. Render Linux sisteminde ara
    # --------------------------------------------------------

    regular_paths = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/ttf-dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
    ]

    bold_paths = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/ttf-dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ]

    found_regular = None
    found_bold = None

    for path in regular_paths:
        if path.exists():
            found_regular = path
            break

    for path in bold_paths:
        if path.exists():
            found_bold = path
            break

    if found_regular and found_bold:

        try:
            import shutil

            shutil.copy2(found_regular, regular)
            shutil.copy2(found_bold, bold)

            print("DejaVu sistem fontu bulundu.")

            return regular, bold

        except Exception as error:
            print("Font kopyalama hatası:", error)

            return found_regular, found_bold

    # --------------------------------------------------------
    # 3. İnternetten indir
    # --------------------------------------------------------

    regular_urls = [
        "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf",
        "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/master/ttf/DejaVuSans.ttf"
    ]

    bold_urls = [
        "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans-Bold.ttf",
        "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/master/ttf/DejaVuSans-Bold.ttf"
    ]

    try:

        for url in regular_urls:

            try:
                print("DejaVuSans.ttf indiriliyor...")

                request = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "KARVIS/24.0"
                    }
                )

                with urllib.request.urlopen(
                    request,
                    timeout=20
                ) as response:

                    data = response.read()

                if len(data) > 10000:

                    regular.write_bytes(data)

                    break

            except Exception as error:
                print("Normal font URL başarısız:", error)

        for url in bold_urls:

            try:
                print("DejaVuSans-Bold.ttf indiriliyor...")

                request = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "KARVIS/24.0"
                    }
                )

                with urllib.request.urlopen(
                    request,
                    timeout=20
                ) as response:

                    data = response.read()

                if len(data) > 10000:

                    bold.write_bytes(data)

                    break

            except Exception as error:
                print("Bold font URL başarısız:", error)

    except Exception as error:

        print("Font indirme sistemi hatası:", error)

    if regular.exists() and bold.exists():

        return regular, bold

    return None, None


def setup_pdf_fonts():

    global REGULAR_FONT
    global BOLD_FONT

    regular_file, bold_file = install_dejavu_fonts()

    if regular_file and bold_file:

        try:

            pdfmetrics.registerFont(
                TTFont(
                    "KarahanDejaVu",
                    str(regular_file)
                )
            )

            pdfmetrics.registerFont(
                TTFont(
                    "KarahanDejaVu-Bold",
                    str(bold_file)
                )
            )

            REGULAR_FONT = "KarahanDejaVu"
            BOLD_FONT = "KarahanDejaVu-Bold"

            print("======================================")
            print("TÜRKÇE PDF FONTU: AKTİF")
            print("DejaVu Sans")
            print("Ç Ğ İ Ö Ş Ü ç ğ ı ö ş ü")
            print("======================================")

            return True

        except Exception as error:

            print("Font kayıt hatası:", error)

    print("======================================")
    print("UYARI: Türkçe PDF fontu yüklenemedi.")
    print("Helvetica kullanılacak.")
    print("======================================")

    return False


setup_pdf_fonts()


# ============================================================
# MEMORY
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

        print("JSON kayıt hatası:", error)


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

    except Exception as error:

        print("Groq client hatası:", error)


if OPENROUTER_API_KEY:

    try:

        openrouter_client = OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        )

    except Exception as error:

        print("OpenRouter client hatası:", error)


# ============================================================
# MODELLER
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
    username: str = "karahan"
    mode: str = "presentation"


# ============================================================
# SYSTEM PROMPT
# ============================================================

def build_system_prompt(username="karahan", mode="normal"):

    user = USERS.get(
        username,
        USERS["karahan"]
    )

    personality = user.get(
        "personality",
        "professional"
    )

    prompt = """
Sen K.A.R.V.I.S. - KARAHAN INC. isimli gelişmiş kişisel yapay zeka asistanısın.

Kullanıcıya doğal, akıcı ve profesyonel Türkçe ile cevap ver.

Gereksiz yere kendini tekrar etme.

Kullanıcı kısa soru sorarsa gereksiz uzun cevap verme.

Kullanıcı detay isterse ayrıntılı anlat.

Bilmediğin bilgiyi kesinmiş gibi uydurma.

Teknik konularda uygulanabilir ve doğrudan çözüm üret.

Kod istendiğinde çalışabilir kod üret.

Türkçe karakterleri doğru kullan.

Kullanıcıya her mesajda "Murat" diye hitap etme.

Kendini ChatGPT olarak tanıtma.

Sen K.A.R.V.I.S.'sin.
"""

    if personality == "professional":

        prompt += """
Ana kullanıcı için profesyonel, doğrudan ve yardımcı ol.
"""

    elif personality == "betul":

        prompt += """
Betül ile konuşurken samimi, nazik ve sıcak bir dil kullan.
"""

    elif personality == "sinem":

        prompt += """
Sinem ile konuşurken samimi ve doğal bir dil kullan.
"""

    elif personality == "teacher":

        prompt += """
İlknur Hocam için akademik, öğretici ve düzenli bir dil kullan.
Ders anlatırken konuyu öğrencinin anlayabileceği şekilde yapılandır.
"""

    if mode == "research":

        prompt += """
Araştırma modundasın.
Konuyu başlıklar halinde incele.
Güncel bilgi gerekiyorsa internet araştırması yapılması gerektiğini belirt.
"""

    elif mode == "academic":

        prompt += """
Akademik moddasın.
Kavramsal doğruluk, kaynak mantığı ve akademik terminolojiye önem ver.
"""

    elif mode == "article":

        prompt += """
Makale asistanı modundasın.
Giriş, gelişme, sonuç ve gerektiğinde kaynakça yapısını kullan.
"""

    elif mode == "lesson":

        prompt += """
Ders asistanı modundasın.
Konuyu öğretmen anlatımı şeklinde düzenle.
Örnekler ve öğrencinin anlayacağı açıklamalar ekle.
"""

    elif mode == "quiz":

        prompt += """
Sınav modundasın.
Soruları açık ve ölçülebilir hazırla.
İstenirse cevap anahtarı oluştur.
"""

    elif mode == "presentation":

        prompt += """
Sunum hazırlama modundasın.
Bilgileri slaytlara uygun kısa ve anlaşılır şekilde yapılandır.
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

        role = item.get("role")

        content = item.get("content")

        if role in ["user", "assistant"] and content:

            messages.append({
                "role": role,
                "content": str(content)
            })

    messages.append({
        "role": "user",
        "content": message
    })

    # --------------------------------------------------------
    # GROQ
    # --------------------------------------------------------

    if groq_client:

        for model in GROQ_MODELS:

            try:

                response = groq_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=3000
                )

                answer = response.choices[0].message.content

                if answer:

                    return answer.strip()

            except Exception as error:

                print(
                    "Groq model hatası:",
                    model,
                    error
                )

    # --------------------------------------------------------
    # OPENROUTER
    # --------------------------------------------------------

    if openrouter_client:

        try:

            response = openrouter_client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=3000
            )

            answer = response.choices[0].message.content

            if answer:

                return answer.strip()

        except Exception as error:

            print(
                "OpenRouter hatası:",
                error
            )

    return (
        "Şu anda yapay zeka servislerine bağlanamıyorum. "
        "API anahtarlarını veya Render ortam değişkenlerini kontrol et."
    )


# ============================================================
# DUCKDUCKGO ARAŞTIRMA
# ============================================================

def internet_search(query, limit=5):

    try:

        url = "https://html.duckduckgo.com/html/"

        response = requests.post(
            url,
            data={
                "q": query
            },
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=15
        )

        if response.status_code != 200:
            return []

        html = response.text

        results = []

        pattern = re.compile(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.S
        )

        for match in pattern.finditer(html):

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
            "message": "Araştırma sonucu bulunamadı.",
            "results": []
        }

    return {
        "success": True,
        "results": results
    }


# ============================================================
# SUNUM JSON ÜRET
# ============================================================

def generate_presentation_outline(topic):

    prompt = f"""
Aşağıdaki konu için profesyonel bir eğitim sunumu hazırla:

KONU:
{topic}

Sadece geçerli JSON döndür.

Format:

{{
  "title": "Sunum başlığı",
  "subtitle": "Kısa açıklama",
  "slides": [
    {{
      "title": "Slayt başlığı",
      "bullets": [
        "Madde 1",
        "Madde 2",
        "Madde 3"
      ],
      "note": "Öğretmen notu",
      "visual_query": "Görsel arama kelimeleri"
    }}
  ]
}}

5 ile 8 arasında slayt oluştur.

Bilgiler doğru ve öğretici olsun.

Türkçe karakterleri doğru kullan.
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

        if "slides" in data:

            return data

    except Exception as error:

        print(
            "Sunum JSON ayrıştırma hatası:",
            error
        )

    return {
        "title": topic,
        "subtitle": "K.A.R.V.I.S. tarafından hazırlanan sunum",
        "slides": [
            {
                "title": "Giriş",
                "bullets": [
                    topic,
                    "Temel kavramlar",
                    "Genel bakış"
                ],
                "note": "Konuya giriş yapınız.",
                "visual_query": topic
            },
            {
                "title": "Temel Bilgiler",
                "bullets": [
                    "Temel özellikler",
                    "Önemli noktalar",
                    "Uygulama alanları"
                ],
                "note": "Önemli kavramları açıklayınız.",
                "visual_query": topic
            },
            {
                "title": "Sonuç",
                "bullets": [
                    "Konunun önemi",
                    "Temel çıkarımlar",
                    "Genel değerlendirme"
                ],
                "note": "Öğrencilerle kısa değerlendirme yapınız.",
                "visual_query": topic
            }
        ]
    }


# ============================================================
# GÖRSEL İNDİRME
# ============================================================

def clean_filename(text):

    text = re.sub(
        r"[^a-zA-Z0-9çÇğĞıİöÖşŞüÜ_-]+",
        "_",
        text
    )

    return text[:80]


def download_image(url, filename):

    try:

        destination = FILES_DIR / filename

        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=20
        )

        if response.status_code != 200:
            return None

        content_type = response.headers.get(
            "content-type",
            ""
        ).lower()

        if (
            "image" not in content_type
            and not url.lower().endswith(
                (".jpg", ".jpeg", ".png", ".webp")
            )
        ):
            return None

        if len(response.content) < 1000:
            return None

        destination.write_bytes(
            response.content
        )

        return destination

    except Exception as error:

        print(
            "Görsel indirme hatası:",
            error
        )

        return None


# ============================================================
# WIKIMEDIA GÖRSEL
# ============================================================

def download_wikimedia_visual(query):

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
            "format": "json"
        }

        response = requests.get(
            api_url,
            params=params,
            headers={
                "User-Agent": "KARVIS/24.0"
            },
            timeout=15
        )

        if response.status_code != 200:
            return None

        data = response.json()

        pages = (
            data.get("query", {})
            .get("pages", {})
        )

        for page in pages.values():

            imageinfo = page.get(
                "imageinfo",
                []
            )

            if not imageinfo:
                continue

            url = imageinfo[0].get("url")

            if not url:
                continue

            extension = ".jpg"

            lower_url = url.lower()

            if ".png" in lower_url:
                extension = ".png"

            elif ".webp" in lower_url:
                extension = ".webp"

            filename = (
                "visual_"
                + uuid.uuid4().hex
                + extension
            )

            result = download_image(
                url,
                filename
            )

            if result:
                return result

    except Exception as error:

        print(
            "Wikimedia hatası:",
            error
        )

    return None


# ============================================================
# OPENVERSE GÖRSEL
# ============================================================

def download_openverse_visual(query):

    try:

        url = "https://api.openverse.org/v1/images/"

        response = requests.get(
            url,
            params={
                "q": query,
                "page_size": 5
            },
            headers={
                "User-Agent": "KARVIS/24.0"
            },
            timeout=15
        )

        if response.status_code != 200:
            return None

        data = response.json()

        for item in data.get(
            "results",
            []
        ):

            image_url = (
                item.get("thumbnail")
                or item.get("url")
            )

            if not image_url:
                continue

            filename = (
                "visual_"
                + uuid.uuid4().hex
                + ".jpg"
            )

            result = download_image(
                image_url,
                filename
            )

            if result:
                return result

    except Exception as error:

        print(
            "Openverse hatası:",
            error
        )

    return None


# ============================================================
# GÖRSEL BUL
# ============================================================

def get_slide_image(query):

    if not query:
        return None

    print(
        "Görsel aranıyor:",
        query
    )

    image = download_wikimedia_visual(
        query
    )

    if image:
        print(
            "Wikimedia görseli bulundu."
        )

        return image

    image = download_openverse_visual(
        query
    )

    if image:
        print(
            "Openverse görseli bulundu."
        )

        return image

    print(
        "Uygun görsel bulunamadı."
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
    leading=24
):

    pdf.setFont(
        font,
        size
    )

    words = str(text).split()

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
                lines.append(line)

            line = word

    if line:
        lines.append(line)

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
# PDF MADDELER
# ============================================================

def draw_bullets(
    pdf,
    bullets,
    x,
    y,
    width
):

    current_y = y

    for bullet in bullets:

        text = str(bullet)

        current_y = draw_wrapped_text(
            pdf,
            "• " + text,
            x,
            current_y,
            width,
            font=REGULAR_FONT,
            size=17,
            leading=24
        )

        current_y -= 8

    return current_y


# ============================================================
# FALLBACK GÖRSEL
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
        10
    )

    wrapped = textwrap.wrap(
        str(title),
        width=35
    )

    yy = y + 50

    for line in wrapped[:3]:

        pdf.drawCentredString(
            x + width / 2,
            yy,
            line
        )

        yy -= 14


# ============================================================
# GÖRSEL PDF'E ÇİZ
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

        if image_width <= 0 or image_height <= 0:
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
            x + (width - draw_width) / 2
        )

        draw_y = (
            y + (height - draw_height) / 2
        )

        pdf.drawImage(
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
            "PDF görsel çizim hatası:",
            error
        )

        return False


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

    page_width, page_height = landscape(A4)

    pdf = canvas.Canvas(
        str(pdf_path),
        pagesize=(
            page_width,
            page_height
        )
    )

    # ========================================================
    # KAPAK
    # ========================================================

    pdf.setTitle(
        str(
            outline.get(
                "title",
                "K.A.R.V.I.S. Sunum"
            )
        )
    )

    pdf.setFont(
        BOLD_FONT,
        30
    )

    pdf.drawCentredString(
        page_width / 2,
        page_height - 150,
        str(
            outline.get(
                "title",
                "K.A.R.V.I.S. Sunum"
            )
        )
    )

    pdf.setFont(
        REGULAR_FONT,
        18
    )

    pdf.drawCentredString(
        page_width / 2,
        page_height - 190,
        str(
            outline.get(
                "subtitle",
                "K.A.R.V.I.S. - KARAHAN INC."
            )
        )
    )

    # Kapakta basit görsel
    draw_fallback_visual(
        pdf,
        page_width / 2 - 160,
        120,
        320,
        170,
        outline.get(
            "title",
            ""
        )
    )

    pdf.setFont(
        REGULAR_FONT,
        11
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

    for index, slide in enumerate(
        slides,
        start=1
    ):

        title = slide.get(
            "title",
            "Slayt"
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

        # ----------------------------------------------------
        # BAŞLIK
        # ----------------------------------------------------

        pdf.setFont(
            BOLD_FONT,
            25
        )

        pdf.drawString(
            55,
            page_height - 65,
            str(title)
        )

        # ----------------------------------------------------
        # METİN ALANI
        # ----------------------------------------------------

        text_width = (
            page_width * 0.48
        )

        draw_bullets(
            pdf,
            bullets,
            60,
            page_height - 115,
            text_width
        )

        # ----------------------------------------------------
        # GÖRSEL
        # ----------------------------------------------------

        image_path = get_slide_image(
            visual_query
        )

        image_x = (
            page_width * 0.55
        )

        image_y = 150

        image_width = 300

        image_height = 220

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

        # ----------------------------------------------------
        # ÖĞRETMEN NOTU
        # ----------------------------------------------------

        if note:

            pdf.setFont(
                BOLD_FONT,
                11
            )

            pdf.drawString(
                60,
                95,
                "Öğretmen Notu:"
            )

            draw_wrapped_text(
                pdf,
                note,
                145,
                95,
                page_width - 200,
                font=REGULAR_FONT,
                size=10,
                leading=13
            )

        # ----------------------------------------------------
        # ALT BİLGİ
        # ----------------------------------------------------

        pdf.setFont(
            REGULAR_FONT,
            9
        )

        pdf.drawString(
            55,
            35,
            "K.A.R.V.I.S. - KARAHAN INC."
        )

        pdf.drawRightString(
            page_width - 55,
            35,
            f"{index} / {len(slides)}"
        )

        pdf.showPage()

    pdf.save()

    return pdf_path


# ============================================================
# ANA SAYFA
# ============================================================

@app.get("/")
def home():

    index_file = BASE_DIR / "index.html"

    if index_file.exists():

        return FileResponse(
            str(index_file),
            media_type="text/html"
        )

    return {
        "success": True,
        "message": "K.A.R.V.I.S. backend çalışıyor.",
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
        "groq": bool(GROQ_API_KEY),
        "openrouter": bool(OPENROUTER_API_KEY)
    }


# ============================================================
# VERSION
# ============================================================

@app.get("/version")
def version():

    return {
        "version": APP_VERSION,
        "name": "K.A.R.V.I.S. - KARAHAN INC."
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
def profile_login(request: LoginRequest):

    username = (
        request.username
        .strip()
        .lower()
    )

    password = request.password

    user = USERS.get(username)

    if not user:

        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": "Kullanıcı bulunamadı."
            }
        )

    # Ana kullanıcı
    if username == "karahan":

        return {
            "success": True,
            "user": user
        }

    if user.get("password") != password:

        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": "Şifre hatalı."
            }
        )

    return {
        "success": True,
        "user": user
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
def chat(request: ChatRequest):

    try:

        answer = ask_ai(
            request.message,
            request.username,
            request.mode,
            request.history
        )

        return {
            "success": True,
            "answer": answer,
            "message": answer,
            "username": request.username,
            "mode": request.mode
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
                "message": "K.A.R.V.I.S. hata verdi.",
                "error": str(error)
            }
        )


# ============================================================
# RESEARCH
# ============================================================

@app.post("/research")
def research(request: ResearchRequest):

    try:

        results = research_topic(
            request.topic
        )

        if not results.get("success"):

            return results

        source_text = "\n".join(
            [
                f"{item['title']} - {item['url']}"
                for item in results["results"]
            ]
        )

        analysis_prompt = f"""
Şu konu hakkında araştırma yap:

{request.topic}

Bulunan kaynaklar:

{source_text}

Türkçe, anlaşılır ve düzenli bir araştırma özeti hazırla.
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

        if not request.topic.strip():

            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "Sunum konusu boş bırakılamaz."
                }
            )

        print(
            "Sunum hazırlanıyor:",
            request.topic
        )

        outline = generate_presentation_outline(
            request.topic
        )

        pdf_path = create_presentation_pdf(
            outline,
            request.username
        )

        filename = pdf_path.name

        file_url = (
            "/generated/"
            + filename
        )

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
                "message": "Sunum oluşturulamadı.",
                "error": str(error)
            }
        )


# ============================================================
# GENERATED PDF DOSYALARI
# ============================================================

@app.get("/generated/{filename}")
def generated_file(filename: str):

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
                    "message": "Geçersiz dosya türü."
                }
            )

        file_path = (
            GENERATED_DIR / safe_name
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
        "message": "Yeni sohbet başlatıldı."
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
        "AKTİF" if GROQ_API_KEY else "YOK"
    )

    print(
        "OpenRouter:",
        "AKTİF" if OPENROUTER_API_KEY else "YOK"
    )

    print(
        "PDF Font:",
        REGULAR_FONT
    )

    print(
        "PDF klasörü:",
        GENERATED_DIR
    )

    print(
        "Görsel sistemi: AKTİF"
    )

    print("======================================")
    print(" K.A.R.V.I.S. HAZIR")
    print("======================================")
    print("")
