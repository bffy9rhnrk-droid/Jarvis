import os
import json
import re
import uuid
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import OpenAI


BASE_DIR = Path(__file__).resolve().parent
MEMORY_FILE = BASE_DIR / "jarvis_memory.json"
ERROR_FILE = BASE_DIR / "jarvis_errors.json"
GENERATED_DIR = BASE_DIR / "generated"

GENERATED_DIR.mkdir(exist_ok=True)

APP_VERSION = "22.0.0"


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
    StaticFiles(directory=str(GENERATED_DIR)),
    name="files"
)


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


def load_json(path, default):
    try:
        if not path.exists():
            return default

        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    except Exception:
        return default


def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )
    except Exception:
        pass


def normalize_username(username):
    if not username:
        return "karahan"

    username = username.strip().lower()

    if username not in USERS:
        return "karahan"

    return username


def save_memory(username, role, content):
    memory = load_json(MEMORY_FILE, {})

    if username not in memory:
        memory[username] = []

    memory[username].append({
        "role": role,
        "content": content
    })

    memory[username] = memory[username][-30:]

    save_json(MEMORY_FILE, memory)


def get_memory(username):
    memory = load_json(MEMORY_FILE, {})
    return memory.get(username, [])


def save_error(message):
    errors = load_json(ERROR_FILE, [])

    errors.append({
        "message": str(message)
    })

    errors = errors[-100:]

    save_json(ERROR_FILE, errors)


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


def get_groq_client(model=None):
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        return None

    return OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1"
    )


def get_openrouter_client():
    api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key:
        return None

    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1"
    )


def build_system_prompt(username, mode="normal"):
    user = USERS.get(username, USERS["karahan"])

    base = """
Sen K.A.R.V.I.S. adlı kişisel yapay zeka asistanısın.

Kullanıcıya doğal, anlaşılır ve samimi Türkçe ile cevap ver.

Gereksiz yere robotik konuşma.
Cevapları kullanıcının sorusuna göre kısa veya detaylı ver.
Bilmediğin bir bilgiyi kesinmiş gibi uydurma.
"""

    if username == "karahan":
        base += """
Kullanıcı KARAHAN INC. ana kullanıcısıdır.
Ona gerektiğinde "efendim" diye hitap edebilirsin.
Profesyonel, yardımsever ve doğal ol.
"""

    elif username == "betul":
        base += """
Kullanıcı Betül'dür.
Samimi ve sıcak konuş.
Gerektiğinde hafif eğlenceli olabilirsin.
"""

    elif username == "sinem":
        base += """
Kullanıcı Sinem'dir.
Nazik, sıcak ve samimi konuş.
"""

    elif username == "ilknur":
        base += """
Kullanıcı İlknur Hocam'dır.
Ona "Hocam" şeklinde hitap et.
Profesyonel, akademik ve saygılı ol.
Bir öğretmenin kişisel akademik asistanı gibi davran.
Ders, araştırma, makale, sınav ve sunum çalışmalarında yardımcı ol.
"""

    if username == "ilknur":
        if mode == "research":
            base += """
Araştırma Modundasın.
Konu hakkında araştırma planı oluştur.
Kaynak türlerini belirt.
Güncel bilgi gerekiyorsa bunu açıkça belirt.
Kaynak uydurma.
"""

        elif mode == "academic":
            base += """
Akademik Moddasın.
Kavramları akademik düzeyde açıkla.
Tanım, yöntem, değerlendirme ve sonuç bölümleri kullanabilirsin.
"""

        elif mode == "article":
            base += """
Makale Asistanı modundasın.
Akademik makale hazırlamaya yardımcı ol.
Başlık, özet, anahtar kelimeler, giriş, yöntem, bulgular,
tartışma ve sonuç gibi bölümler oluştur.
"""

        elif mode == "lesson":
            base += """
Ders Asistanı modundasın.
Öğrencilerin anlayabileceği şekilde ders materyali hazırla.
Konu anlatımı, örnekler, önemli noktalar ve tekrar soruları kullan.
"""

        elif mode == "quiz":
            base += """
Sınav / Quiz modundasın.
Sorular oluştur.
Gerekirse çoktan seçmeli, doğru-yanlış veya açık uçlu sorular hazırla.
Cevap anahtarını ayrı ve anlaşılır şekilde ver.
"""

        elif mode == "presentation":
            base += """
Sunum Hazırlama modundasın.
Sunum içeriğini öğrencilerin anlayabileceği profesyonel bir yapıda hazırla.
Başlıkları kısa tut.
Her slaytta gereksiz uzun paragraflar kullanma.
"""

    return base


def ask_ai(username, user_message, mode="normal", extra_context=""):
    clients = []

    groq = get_groq_client()

    if groq:
        clients.append((
            groq,
            "openai/gpt-oss-120b"
        ))

        clients.append((
            groq,
            "openai/gpt-oss-20b"
        ))

    openrouter = get_openrouter_client()

    if openrouter:
        clients.append((
            openrouter,
            "openai/gpt-oss-120b:free"
        ))

    if not clients:
        raise Exception(
            "API anahtarı bulunamadı. GROQ_API_KEY veya OPENROUTER_API_KEY ekleyin."
        )

    memory = get_memory(username)

    messages = [
        {
            "role": "system",
            "content": build_system_prompt(username, mode)
        }
    ]

    if extra_context:
        messages.append({
            "role": "system",
            "content": extra_context
        })

    for item in memory[-12:]:
        messages.append({
            "role": item.get("role", "user"),
            "content": item.get("content", "")
        })

    messages.append({
        "role": "user",
        "content": user_message
    })

    last_error = None

    for client, model in clients:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=4000
            )

            answer = response.choices[0].message.content

            if answer:
                return answer.strip()

        except Exception as error:
            last_error = error
            save_error(error)

    raise Exception(str(last_error))


def internet_search(query, limit=5):
    encoded = urllib.parse.quote(query)

    url = (
        "https://html.duckduckgo.com/html/?q="
        + encoded
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=12
        ) as response:
            html = response.read().decode(
                "utf-8",
                errors="ignore"
            )

        results = []

        pattern = re.compile(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL
        )

        matches = pattern.findall(html)

        for link, title in matches[:limit]:
            clean_title = re.sub(
                r"<.*?>",
                "",
                title
            ).strip()

            results.append({
                "title": clean_title,
                "url": link
            })

        return results

    except Exception as error:
        save_error(error)
        return []


def build_research_context(query):
    results = internet_search(query, 6)

    if not results:
        return ""

    lines = [
        "Araştırma sırasında bulunan web sonuçları:"
    ]

    for item in results:
        lines.append(
            "- " + item["title"] + " | " + item["url"]
        )

    return "\n".join(lines)


def clean_json_text(text):
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?",
            "",
            text,
            flags=re.IGNORECASE
        )

        text = re.sub(
            r"```$",
            "",
            text
        )

    return text.strip()


def generate_presentation_outline(
    topic,
    username,
    slide_count
):
    prompt = f"""
Aşağıdaki konu hakkında profesyonel bir eğitim sunumu hazırla.

KONU:
{topic}

SLAYT SAYISI:
{slide_count}

Hedef kitle:
Öğrenciler.

Çıktıyı SADECE geçerli JSON olarak ver.

JSON yapısı tam olarak şöyle olsun:

{{
  "title": "Sunum başlığı",
  "subtitle": "Alt başlık",
  "audience": "Hedef kitle",
  "slides": [
    {{
      "title": "Slayt başlığı",
      "bullets": [
        "Kısa bilgi",
        "Kısa bilgi",
        "Kısa bilgi"
      ],
      "visual_type": "diagram",
      "visual_text": "Görselde gösterilecek kısa ifade",
      "speaker_notes": "Öğretmen için konuşmacı notu"
    }}
  ]
}}

Kurallar:
- Slayt başlıkları kısa olsun.
- Öğrencilerin anlayabileceği dil kullan.
- Her slaytta 2 ile 5 arasında madde olsun.
- Gereksiz uzun paragraflar kullanma.
- Tarih, sayı veya bilimsel bilgi uydurma.
- Görsel türleri şu değerlerden biri olabilir:
  diagram
  timeline
  comparison
  process
  facts
  quote
  concept
"""

    answer = ask_ai(
        username,
        prompt,
        "presentation"
    )

    cleaned = clean_json_text(answer)

    try:
        return json.loads(cleaned)

    except Exception:
        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start >= 0 and end > start:
            return json.loads(
                cleaned[start:end + 1]
            )

        raise Exception(
            "Sunum içeriği JSON olarak oluşturulamadı."
        )


def download_wikimedia_visual(query):
    try:
        api_url = (
            "https://commons.wikimedia.org/w/api.php?"
            + urllib.parse.urlencode({
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrnamespace": 6,
                "gsrlimit": 3,
                "prop": "imageinfo",
                "iiprop": "url|mime",
                "iiurlwidth": 1000,
                "format": "json",
                "origin": "*"
            })
        )

        request = urllib.request.Request(
            api_url,
            headers={
                "User-Agent": "KARVIS Academic Assistant"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=12
        ) as response:
            data = json.loads(
                response.read().decode(
                    "utf-8",
                    errors="ignore"
                )
            )

        pages = data.get("query", {}).get(
            "pages",
            {}
        )

        for page in pages.values():
            imageinfo = page.get(
                "imageinfo",
                []
            )

            if not imageinfo:
                continue

            info = imageinfo[0]
            image_url = info.get("thumburl")

            if not image_url:
                image_url = info.get("url")

            if not image_url:
                continue

            image_request = urllib.request.Request(
                image_url,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )

            with urllib.request.urlopen(
                image_request,
                timeout=15
            ) as image_response:
                image_data = image_response.read()

            if len(image_data) < 1000:
                continue

            return image_data

    except Exception as error:
        save_error(error)

    return None


def create_presentation_pdf(
    topic,
    outline,
    include_visuals=True
):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Image,
        Table,
        TableStyle,
        PageBreak
    )
    from reportlab.lib.units import cm
    from reportlab.lib.utils import ImageReader
    from io import BytesIO

    filename = (
        "karvis_sunum_"
        + uuid.uuid4().hex[:10]
        + ".pdf"
    )

    filepath = GENERATED_DIR / filename

    page_width, page_height = landscape(A4)

    document = SimpleDocTemplate(
        str(filepath),
        pagesize=landscape(A4),
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "PresentationTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=28,
        leading=34,
        alignment=TA_CENTER,
        spaceAfter=18
    )

    subtitle_style = ParagraphStyle(
        "PresentationSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=16,
        leading=22,
        alignment=TA_CENTER,
        spaceAfter=15
    )

    slide_title_style = ParagraphStyle(
        "SlideTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=23,
        leading=28,
        alignment=TA_LEFT,
        spaceAfter=16
    )

    bullet_style = ParagraphStyle(
        "Bullet",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=15,
        leading=22,
        spaceAfter=10
    )

    note_style = ParagraphStyle(
        "Notes",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14
    )

    story = []

    title = outline.get(
        "title",
        topic
    )

    subtitle = outline.get(
        "subtitle",
        "K.A.R.V.I.S. Akademik Sunum"
    )

    story.append(
        Spacer(1, 2.5 * cm)
    )

    story.append(
        Paragraph(
            title,
            title_style
        )
    )

    story.append(
        Paragraph(
            subtitle,
            subtitle_style
        )
    )

    story.append(
        Spacer(1, 1 * cm)
    )

    story.append(
        Paragraph(
            "Hazırlayan: K.A.R.V.I.S. - KARAHAN INC.",
            subtitle_style
        )
    )

    story.append(PageBreak())

    slides = outline.get("slides", [])

    for index, slide in enumerate(slides):
        slide_title = slide.get(
            "title",
            "Konu"
        )

        bullets = slide.get(
            "bullets",
            []
        )

        visual_type = slide.get(
            "visual_type",
            "concept"
        )

        story.append(
            Paragraph(
                slide_title,
                slide_title_style
            )
        )

        content = []

        for bullet in bullets:
            content.append(
                Paragraph(
                    "• " + str(bullet),
                    bullet_style
                )
            )

        visual_data = None

        if include_visuals:
            visual_data = download_wikimedia_visual(
                topic + " " + slide_title
            )

        if visual_data:
            try:
                image = Image(
                    ImageReader(
                        BytesIO(visual_data)
                    )
                )

                image.drawHeight = 7.5 * cm
                image.drawWidth = 11 * cm

                table_data = [[
                    content,
                    image
                ]]

                table = Table(
                    table_data,
                    colWidths=[
                        14 * cm,
                        11 * cm
                    ]
                )

                table.setStyle(
                    TableStyle([
                        (
                            "VALIGN",
                            (0, 0),
                            (-1, -1),
                            "TOP"
                        ),
                        (
                            "LEFTPADDING",
                            (0, 0),
                            (-1, -1),
                            8
                        ),
                        (
                            "RIGHTPADDING",
                            (0, 0),
                            (-1, -1),
                            8
                        ),
                        (
                            "TOPPADDING",
                            (0, 0),
                            (-1, -1),
                            8
                        ),
                        (
                            "BOTTOMPADDING",
                            (0, 0),
                            (-1, -1),
                            8
                        )
                    ])
                )

                story.append(table)

            except Exception:
                for item in content:
                    story.append(item)

        else:
            for item in content:
                story.append(item)

            visual_label = {
                "diagram": "Şema / Kavram Haritası",
                "timeline": "Zaman Çizelgesi",
                "comparison": "Karşılaştırma",
                "process": "Süreç Şeması",
                "facts": "Önemli Bilgiler",
                "quote": "Önemli Nokta",
                "concept": "Kavramsal Görsel"
            }.get(
                visual_type,
                "Kavramsal Görsel"
            )

            visual_text = slide.get(
                "visual_text",
                ""
            )

            visual_table = Table(
                [[
                    visual_label,
                    visual_text
                ]],
                colWidths=[
                    6 * cm,
                    17 * cm
                ]
            )

            visual_table.setStyle(
                TableStyle([
                    (
                        "BOX",
                        (0, 0),
                        (-1, -1),
                        1,
                        colors.grey
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "MIDDLE"
                    ),
                    (
                        "FONTNAME",
                        (0, 0),
                        (0, 0),
                        "Helvetica-Bold"
                    ),
                    (
                        "FONTNAME",
                        (1, 0),
                        (1, 0),
                        "Helvetica"
                    ),
                    (
                        "FONTSIZE",
                        (0, 0),
                        (-1, -1),
                        12
                    ),
                    (
                        "PADDING",
                        (0, 0),
                        (-1, -1),
                        10
                    )
                ])
            )

            story.append(
                Spacer(1, 0.5 * cm)
            )

            story.append(visual_table)

        notes = slide.get(
            "speaker_notes",
            ""
        )

        if notes:
            story.append(
                Spacer(1, 0.4 * cm)
            )

            story.append(
                Paragraph(
                    "Öğretmen Notu: " + notes,
                    note_style
                )
            )

        story.append(
            Spacer(1, 0.5 * cm)
        )

        story.append(
            Paragraph(
                f"{index + 1} / {len(slides)}",
                note_style
            )
        )

        if index < len(slides) - 1:
            story.append(PageBreak())

    document.build(story)

    return filename


@app.get("/")
async def root():
    index_file = BASE_DIR / "index.html"

    if not index_file.exists():
        return {
            "message": "K.A.R.V.I.S. backend aktif."
        }

    return FileResponse(
        str(index_file)
    )


@app.get("/health")
async def health():
    return {
        "status": "online",
        "version": APP_VERSION,
        "app": "K.A.R.V.I.S.",
        "academic_system": True,
        "presentation_system": True
    }


@app.get("/version")
async def version():
    return {
        "version": APP_VERSION,
        "academic_teacher": True,
        "web_research": True,
        "presentation_pdf": True
    }


@app.get("/users")
async def users():
    return [
        {
            "username": item["username"],
            "name": item["name"],
            "role": item["role"]
        }
        for item in USERS.values()
    ]


@app.post("/profile-login")
async def profile_login(data: LoginRequest):
    username = normalize_username(
        data.username
    )

    user = USERS.get(username)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Kullanıcı bulunamadı."
        )

    if user["password"] is not None:
        if data.password != user["password"]:
            raise HTTPException(
                status_code=401,
                detail="Şifre yanlış."
            )

    return {
        "ok": True,
        "username": username,
        "name": user["name"],
        "role": user["role"],
        "teacher_mode": username == "ilknur",
        "default_mode": (
            "lesson"
            if username == "ilknur"
            else "normal"
        ),
        "academic_modes": ACADEMIC_MODES
    }


@app.get("/academic-modes")
async def academic_modes():
    return ACADEMIC_MODES


@app.post("/chat")
async def chat(data: ChatRequest):
    username = normalize_username(
        data.username
    )

    message = data.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Mesaj boş olamaz."
        )

    mode = data.mode or "normal"

    if username != "ilknur":
        mode = "normal"

    context = ""

    if username == "ilknur" and mode == "research":
        context = build_research_context(
            message
        )

    try:
        save_memory(
            username,
            "user",
            message
        )

        answer = ask_ai(
            username,
            message,
            mode,
            context
        )

        save_memory(
            username,
            "assistant",
            answer
        )

        return {
            "ok": True,
            "answer": answer,
            "username": username,
            "mode": mode
        }

    except Exception as error:
        save_error(error)

        raise HTTPException(
            status_code=500,
            detail="Yapay zeka yanıt oluşturamadı."
        )


@app.post("/research")
async def research(data: ResearchRequest):
    username = normalize_username(
        data.username
    )

    if username != "ilknur":
        raise HTTPException(
            status_code=403,
            detail="Bu özellik yalnızca öğretmen hesabında kullanılabilir."
        )

    context = build_research_context(
        data.query
    )

    answer = ask_ai(
        username,
        data.query,
        "research",
        context
    )

    return {
        "ok": True,
        "answer": answer,
        "sources": internet_search(
            data.query,
            6
        )
    }


@app.post("/presentation")
async def presentation(data: PresentationRequest):
    username = normalize_username(
        data.username
    )

    if username != "ilknur":
        raise HTTPException(
            status_code=403,
            detail="Sunum hazırlama yalnızca öğretmen hesabında kullanılabilir."
        )

    topic = data.topic.strip()

    if not topic:
        raise HTTPException(
            status_code=400,
            detail="Sunum konusu boş olamaz."
        )

    slide_count = max(
        5,
        min(
            data.slide_count,
            20
        )
    )

    try:
        outline = generate_presentation_outline(
            topic,
            username,
            slide_count
        )

        filename = create_presentation_pdf(
            topic,
            outline,
            data.include_visuals
        )

        return {
            "ok": True,
            "filename": filename,
            "file_url": "/files/" + filename,
            "title": outline.get(
                "title",
                topic
            ),
            "slides": len(
                outline.get(
                    "slides",
                    []
                )
            )
        }

    except Exception as error:
        save_error(error)

        raise HTTPException(
            status_code=500,
            detail="Sunum PDF'i oluşturulamadı: "
            + str(error)
        )


@app.get("/memory")
async def memory(username: str = "karahan"):
    username = normalize_username(
        username
    )

    return {
        "username": username,
        "memory": get_memory(username)
    }


@app.delete("/memory")
async def delete_memory(username: str = "karahan"):
    username = normalize_username(
        username
    )

    memory = load_json(
        MEMORY_FILE,
        {}
    )

    memory[username] = []

    save_json(
        MEMORY_FILE,
        memory
    )

    return {
        "ok": True
    }


@app.post("/new-chat")
async def new_chat(username: str = "karahan"):
    username = normalize_username(
        username
    )

    memory = load_json(
        MEMORY_FILE,
        {}
    )

    memory[username] = []

    save_json(
        MEMORY_FILE,
        memory
    )

    return {
        "ok": True
    }


@app.get("/errors")
async def errors():
    return {
        "errors": load_json(
            ERROR_FILE,
            []
        )
    }


@app.delete("/errors")
async def delete_errors():
    save_json(
        ERROR_FILE,
        []
    )

    return {
        "ok": True
    }
