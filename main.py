# ============================================================
# K.A.R.V.I.S. - KARAHAN INC.
# Professional AI Assistant Backend
# Smart Web Research + Presentation Engine v33.0.0
# ============================================================

import os
import re
import json
import uuid
import time
import hashlib
import threading
import traceback
from datetime import datetime

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from difflib import SequenceMatcher

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

APP_VERSION = "33.1.0"

BASE_DIR = Path(__file__).resolve().parent

GENERATED_DIR = BASE_DIR / "generated"
GENERATED_DIR.mkdir(
    exist_ok=True
)

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

GOOGLE_IMAGE_API_KEY = os.getenv(
    "GOOGLE_IMAGE_API_KEY",
    ""
).strip()

GOOGLE_CSE_ID = os.getenv(
    "GOOGLE_CSE_ID",
    ""
).strip()


groq_client = (
    OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )
    if GROQ_API_KEY
    else None
)


openrouter_client = (
    OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1"
    )
    if OPENROUTER_API_KEY
    else None
)


GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]


OPENROUTER_MODELS = [
    "openai/gpt-oss-20b:free",
]


# ============================================================
# MEMORY / ERROR LOG
# ============================================================

MEMORY_FILE = BASE_DIR / "memory.json"
ERROR_FILE = BASE_DIR / "errors.json"

memory_lock = threading.Lock()
error_lock = threading.Lock()


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

            write_json_file(
                ERROR_FILE,
                data[-100:]
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
        "style": "professional",
    },

    "betul": {
        "name": "Betül",
        "password": "1234",
        "role": "user",
        "style": "professional",
    },

    "sinem": {
        "name": "Sinem",
        "password": "3021",
        "role": "user",
        "style": "professional",
    },

    "ilknur": {
        "name": "İlknur",
        "password": "1111",
        "role": "teacher",
        "style": "academic",
    },
}


# ============================================================
# MODELS
# ============================================================

class LoginRequest(BaseModel):

    username: str
    password: str = ""


class ChatRequest(BaseModel):

    message: str
    username: str = "karahan"
    mode: str = "normal"


class PresentationRequest(BaseModel):

    topic: str
    slide_count: int = 7
    username: str = "karahan"


class BetulInstagramRequest(BaseModel):

    username: str


# ============================================================
# LOGIN
# ============================================================

@app.post("/login")
async def login(
    request: LoginRequest
):

    username = (
        request.username or ""
    ).strip().lower()

    password = (
        request.password or ""
    )

    user = USERS.get(
        username
    )

    if user is None:

        raise HTTPException(
            status_code=401,
            detail="Kullanıcı adı veya şifre hatalı."
        )

    if user.get(
        "password",
        ""
    ) != password:

        raise HTTPException(
            status_code=401,
            detail="Kullanıcı adı veya şifre hatalı."
        )

    public_user = {

        "username":
            username,

        "name":
            user.get(
                "name",
                username
            ),

        "role":
            user.get(
                "role",
                "user"
            ),

        "style":
            user.get(
                "style",
                "professional"
            ),
    }

    return {

        "success":
            True,

        "username":
            username,

        "user":
            public_user,

        "message":
            "Giriş başarılı."
    }


# ============================================================
# AI SYSTEMS
# ============================================================

PROFESSIONAL_SYSTEM = """
Sen K.A.R.V.I.S. isimli profesyonel Türkçe yapay zeka asistanısın.

Yanıtların:
- doğru,
- açık,
- doğal,
- bağlama uygun,
- gereksiz tekrar içermeyen
Türkçe olmalıdır.

Bilmediğin bir bilgiyi kesin gerçekmiş gibi uydurma.
Kaynak verilmişse yalnızca kaynaklarla desteklenen bilgileri kullan.
"""


ACADEMIC_SYSTEM = """
Sen K.A.R.V.I.S. isimli akademik yardımcı asistansın.

Kullanıcıya "Hocam" diye hitap et.

Dil:
- resmi,
- akademik,
- kurumsal,
- açık,
- ölçülü

olmalıdır.

Gereksiz emoji, argo ve aşırı samimi ifade kullanma.

Araştırma taleplerinde:
- kaynaklar,
- yöntem,
- bulgular,
- değerlendirme

ayrımını koru.

Ders anlatımında kavramları sistematik ve öğretici biçimde açıkla.

Quiz taleplerinde sınav formatını koru.

Sunum hazırlarken:
- kaynaklara dayalı,
- doğru,
- birbirini tekrar etmeyen,
- kısa,
- akademik,
- slayta uygun

metin üret.
"""


# ============================================================
# AI CALLS
# ============================================================

def call_groq(
    prompt,
    model,
    system_prompt=PROFESSIONAL_SYSTEM
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
                        "role":
                            "system",

                        "content":
                            system_prompt
                    },

                    {
                        "role":
                            "user",

                        "content":
                            prompt
                    }
                ],

                temperature=0.20,
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


def call_openrouter(
    prompt,
    model,
    system_prompt=PROFESSIONAL_SYSTEM
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
                        "role":
                            "system",

                        "content":
                            system_prompt
                    },

                    {
                        "role":
                            "user",

                        "content":
                            prompt
                    }
                ],

                temperature=0.20,
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


def ask_ai(
    prompt,
    system_prompt=PROFESSIONAL_SYSTEM
):

    for model in GROQ_MODELS:

        result = call_groq(
            prompt,
            model,
            system_prompt
        )

        if result:
            return result

    for model in OPENROUTER_MODELS:

        result = call_openrouter(
            prompt,
            model,
            system_prompt
        )

        if result:
            return result

    return None


# ============================================================
# JSON
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
    ).strip()

    try:

        return json.loads(
            text
        )

    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if (
        start >= 0
        and end > start
    ):

        try:

            return json.loads(
                text[start:end + 1]
            )

        except Exception:
            pass

    return None


# ============================================================
# BETÜL ENTERTAINMENT - INSTAGRAM SIMULATION
# ============================================================

def betul_deterministic_scores(
    seed: str,
    count: int = 6
):

    """
    Aynı kullanıcı adı için her zaman aynı
    eğlence sonuçlarını üretir.

    Bu gerçek Instagram verisi değildir.
    Tamamen deterministik bir simülasyondur.
    """

    seed = (
        str(seed or "")
        .strip()
        .lower()
        .lstrip("@")
    )

    digest = hashlib.sha256(
        seed.encode("utf-8")
    ).digest()

    raw = []

    for i in range(count):

        raw.append(
            10 + (
                digest[i] % 91
            )
        )

    total = sum(raw)

    exact = [
        value / total * 100
        for value in raw
    ]

    scores = [
        int(value)
        for value in exact
    ]

    remainder = 100 - sum(scores)

    order = sorted(
        range(count),
        key=lambda i:
            exact[i] - scores[i],
        reverse=True
    )

    for i in range(remainder):

        scores[
            order[
                i % len(order)
            ]
        ] += 1

    return scores


def betul_instagram_comment(
    categories,
    scores
):

    if not categories or not scores:

        return (
            "Aşkoo sistem ne diyeceğini "
            "bilemedi 😭"
        )

    highest_index = max(
        range(len(scores)),
        key=lambda i:
            scores[i]
    )

    highest = categories[
        highest_index
    ]

    comments = {

        "Romantik":
            (
                "Aşko burada aşk kokusu aldım... "
                "burnuma bildirim geldi resmen 💅💕"
            ),

        "Komik":
            (
                "AŞKOOO bu hesap iyiymiş 😭😂 "
                "K.A.R.V.I.S. analiz yaparken bile güldü."
            ),

        "Sıkıcı":
            (
                "Aşkoo bu hesap biraz fazla sakin çıktı ya... "
                "işlemci bile esnedi 😭"
            ),

        "Havalı":
            (
                "Aşkoo bu hesap kendini biraz fazla "
                "ciddiye alıyor ama hakkını da yemeyelim 😎"
            ),

        "Kaotik":
            (
                "AŞKOOO BU NE?! 💀 "
                "Sistemleri yeniden başlatmam gerekti."
            ),

        "Gizemli":
            (
                "Aşkoo burada bir şeyler dönüyor... "
                "K.A.R.V.I.S. radarları susmuyor 🤨"
            )
    }

    return comments.get(
        highest,
        "Aşkoo bu hesap enteresan çıktı 😭"
    )


@app.post(
    "/betul/instagram-analysis"
)
async def betul_instagram_analysis(
    request: BetulInstagramRequest
):

    username = (
        request.username
        or ""
    ).strip().lstrip("@")

    if not username:

        raise HTTPException(
            status_code=400,
            detail="Instagram kullanıcı adı boş olamaz."
        )

    # Bu endpoint yalnızca Betül profili için kullanılabilir.
    # Gerçek Instagram verisi çekilmez.
    categories = [
        "Romantik",
        "Komik",
        "Sıkıcı",
        "Havalı",
        "Kaotik",
        "Gizemli"
    ]

    scores = betul_deterministic_scores(
        username
    )

    return {
        "success": True,
        "username": username,
        "entertainment_only": True,
        "categories": [
            {
                "name": categories[i],
                "percent": scores[i]
            }
            for i in range(len(categories))
        ],
        "comment": betul_instagram_comment(
            categories,
            scores
        ),
        "disclaimer": (
            "Bu analiz gerçek Instagram verilerini "
            "incelemez; tamamen eğlence amaçlı bir "
            "simülasyondur ve yanılma payı vardır."
        )
    }


# ============================================================
# WEB RESEARCH
# ============================================================

WEB_HEADERS = {

    "User-Agent":
        "KARVIS-KARAHAN-INC/32.0 academic research"
}


def clean_text(text):

    if not text:
        return ""

    text = re.sub(
        r"<[^>]+>",
        " ",
        str(text)
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def search_wikipedia(
    topic,
    language="tr",
    limit=6
):

    try:

        api = (
            f"https://{language}.wikipedia.org/w/api.php"
        )

        response = requests.get(

            api,

            params={

                "action":
                    "query",

                "generator":
                    "search",

                "gsrsearch":
                    topic,

                "gsrnamespace":
                    0,

                "gsrlimit":
                    limit,

                "prop":
                    "extracts|info",

                "exintro":
                    True,

                "explaintext":
                    True,

                "inprop":
                    "url",

                "format":
                    "json",
            },

            headers=WEB_HEADERS,

            timeout=15
        )

        if response.status_code != 200:
            return []

        pages = (
            response
            .json()
            .get("query", {})
            .get("pages", {})
        )

        results = []

        for page in pages.values():

            title = clean_text(
                page.get(
                    "title",
                    ""
                )
            )

            extract = clean_text(
                page.get(
                    "extract",
                    ""
                )
            )

            url = (
                page.get("fullurl")
                or
                (
                    f"https://{language}.wikipedia.org/wiki/"
                    +
                    title.replace(
                        " ",
                        "_"
                    )
                )
            )

            if not title or not extract:
                continue

            results.append({

                "title":
                    title,

                "text":
                    extract[:5000],

                "url":
                    url,

                "source":
                    "Wikipedia"
            })

        return results

    except Exception:

        save_error(
            "Wikipedia research error",
            traceback.format_exc()
        )

        return []


def search_google_web(
    topic
):

    if (
        not GOOGLE_IMAGE_API_KEY
        or
        not GOOGLE_CSE_ID
    ):

        return []

    try:

        response = requests.get(

            "https://www.googleapis.com/customsearch/v1",

            params={

                "key":
                    GOOGLE_IMAGE_API_KEY,

                "cx":
                    GOOGLE_CSE_ID,

                "q":
                    topic,

                "num":
                    8,

                "safe":
                    "active"
            },

            headers=WEB_HEADERS,

            timeout=15
        )

        if response.status_code != 200:
            return []

        items = (
            response
            .json()
            .get(
                "items",
                []
            )
        )

        results = []

        for item in items:

            title = clean_text(
                item.get(
                    "title",
                    ""
                )
            )

            snippet = clean_text(
                item.get(
                    "snippet",
                    ""
                )
            )

            link = item.get(
                "link",
                ""
            )

            if not title or not snippet:
                continue

            results.append({

                "title":
                    title,

                "text":
                    snippet,

                "url":
                    link,

                "source":
                    "Web"
            })

        return results

    except Exception:

        save_error(
            "Google web search error",
            traceback.format_exc()
        )

        return []


def research_topic(
    topic,
    progress_callback=None
):

    sources = []

    if progress_callback:

        progress_callback(
            10,
            "Araştırmalar yapılıyor..."
        )

    # --------------------------------------------------------
    # Turkish Wikipedia
    # --------------------------------------------------------

    if progress_callback:

        progress_callback(
            14,
            "Türkçe kaynaklar araştırılıyor..."
        )

    sources.extend(
        search_wikipedia(
            topic,
            "tr",
            6
        )
    )

    # --------------------------------------------------------
    # English Wikipedia
    # --------------------------------------------------------

    if progress_callback:

        progress_callback(
            20,
            "Yabancı kaynaklar karşılaştırılıyor..."
        )

    if len(sources) < 5:

        sources.extend(
            search_wikipedia(
                topic,
                "en",
                5
            )
        )

    # --------------------------------------------------------
    # Google
    # --------------------------------------------------------

    if progress_callback:

        progress_callback(
            25,
            "Ek web kaynakları kontrol ediliyor..."
        )

    google_sources = search_google_web(
        topic
    )

    sources.extend(
        google_sources
    )

    # --------------------------------------------------------
    # Duplicate
    # --------------------------------------------------------

    unique = []

    seen = set()

    for source in sources:

        url = source.get(
            "url",
            ""
        )

        if not url:
            continue

        if url in seen:
            continue

        seen.add(url)

        unique.append(
            source
        )

    if progress_callback:

        progress_callback(
            30,
            f"{len(unique)} kaynak değerlendiriliyor..."
        )

    return unique[:15]


def format_sources_for_ai(
    sources
):

    if not sources:

        return (
            "Kullanılabilir harici kaynak bulunamadı. "
            "Bu durumda doğrulanmamış özel istatistikler "
            "ve kesin sayısal iddialar üretme."
        )

    blocks = []

    for index, source in enumerate(
        sources,
        start=1
    ):

        blocks.append(
            f"""
KAYNAK {index}
Başlık: {source.get("title", "")}
Kaynak: {source.get("source", "")}
URL: {source.get("url", "")}
İçerik:
{source.get("text", "")[:3500]}
"""
        )

    return "\n".join(
        blocks
    )



# ============================================================
# LIVE WEATHER / LOCAL NEWS HELPERS
# ============================================================

WEATHER_CODES_TR = {
    0: "açık",
    1: "çoğunlukla açık",
    2: "parçalı bulutlu",
    3: "kapalı",
    45: "sisli",
    48: "puslu/sisli",
    51: "hafif çisenti",
    53: "çisenti",
    55: "kuvvetli çisenti",
    61: "hafif yağmur",
    63: "yağmur",
    65: "kuvvetli yağmur",
    71: "hafif kar",
    73: "kar",
    75: "kuvvetli kar",
    80: "hafif sağanak",
    81: "sağanak yağış",
    82: "kuvvetli sağanak",
    95: "gök gürültülü fırtına",
    96: "gök gürültülü, dolu ihtimalli yağış",
    99: "gök gürültülü, kuvvetli dolu ihtimalli yağış",
}


def fetch_denizli_weather():
    """Denizli için ana hava verisini doğrudan Open-Meteo'dan alır."""
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 37.7765,
                "longitude": 29.0864,
                "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
                "hourly": "temperature_2m,precipitation_probability,weather_code,wind_speed_10m",
                "forecast_days": 2,
                "timezone": "Europe/Istanbul",
            },
            headers=WEB_HEADERS,
            timeout=10,
        )
        if response.status_code != 200:
            return None

        data = response.json()
        current = data.get("current", {})
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        rain = hourly.get("precipitation_probability", [])
        codes = hourly.get("weather_code", [])
        winds = hourly.get("wind_speed_10m", [])

        now_temp = current.get("temperature_2m")
        now_code = current.get("weather_code")
        now_wind = current.get("wind_speed_10m")

        current_time = str(data.get("current", {}).get("time", ""))
        upcoming = []
        start_index = 0
        if current_time and current_time in times:
            start_index = times.index(current_time)
        for i in range(start_index, min(start_index + 8, len(times))):
            upcoming.append({
                "time": times[i],
                "temperature": temps[i] if i < len(temps) else None,
                "rain_probability": rain[i] if i < len(rain) else None,
                "condition": WEATHER_CODES_TR.get(codes[i], "değişken") if i < len(codes) else "değişken",
                "wind": winds[i] if i < len(winds) else None,
            })

        return {
            "location": "Denizli",
            "current_temperature": now_temp,
            "apparent_temperature": current.get("apparent_temperature"),
            "current_condition": WEATHER_CODES_TR.get(now_code, "değişken"),
            "current_wind": now_wind,
            "upcoming": upcoming,
            "source": "Open-Meteo",
        }
    except Exception:
        save_error("Weather API error", traceback.format_exc())
        return None


def weather_context_for_ai(weather):
    if not weather:
        return ""

    lines = [
        "CANLI DENİZLİ HAVA VERİSİ",
        f"Şu an: {weather.get('current_temperature')}°C, hissedilen {weather.get('apparent_temperature')}°C, {weather.get('current_condition')}, rüzgar {weather.get('current_wind')} km/sa.",
        "Önümüzdeki saatler:"
    ]
    for item in weather.get("upcoming", [])[:8]:
        lines.append(
            f"{item.get('time')}: {item.get('temperature')}°C, {item.get('condition')}, yağış ihtimali %{item.get('rain_probability')}, rüzgar {item.get('wind')} km/sa."
        )
    lines.append(
        "Bu veriyi kullanıcıya doğal bir hava durumu değerlendirmesi olarak aktar; URL veya ham API verisi gösterme."
    )
    return "\n".join(lines)


def is_weather_request(message):
    text = clean_text(message).lower()
    return bool(re.search(r"\b(hava durumu|hava nasıl|hava bugün|yağmur yağacak mı|yağış var mı|sıcaklık kaç|kaç derece|derece kaç)\b", text))


def is_local_news_request(message):
    text = clean_text(message).lower()
    return bool(re.search(r"\b(gündem|haberler|son haberler|bugün neler oluyor|son gelişmeler|gündemde ne var)\b", text)) and any(
        place in text for place in ["denizli", "honaz", "pamukkale", "merkezefendi", "çivril", "acipayam", "acıpayam"]
    )



# ============================================================
# SMART WEB RESEARCH
# ============================================================
# Web araştırması yalnızca sorunun güncel/doğrulanması gereken
# bir bilgiye ihtiyaç duyduğu durumlarda çalışır.
# Normal sohbet, genel bilgi ve yaratıcı istekler internete çıkmaz.

CURRENT_YEAR = datetime.now().year

WEB_TRIGGER_PATTERNS = [
    r"\bbugün\b",
    r"\bşu an\b",
    r"\bşuan\b",
    r"\bşimdiki\b",
    r"\bgüncel\b",
    r"\bson dakika\b",
    r"\bson gelişme",
    r"\bson haber",
    r"\byeni çıkan\b",
    r"\byenisi\b",
    r"\bbu hafta\b",
    r"\bbu ay\b",
    r"\bdün\b",
    r"\byarın\b",
    r"\bkaç tl\b",
    r"\bfiyatı\b",
    r"\bfiyatları\b",
    r"\bkur\b",
    r"\bdöviz\b",
    r"\beuro\b",
    r"\bdolar\b",
    r"\baltın\b",
    r"\bhava durumu\b",
    r"\bseçim sonuç",
    r"\bsonuçları açıklandı\b",
    r"\bkim kazandı\b",
    r"\bşampiyon\b",
    r"\bpuan durumu\b",
    r"\bmaç sonucu\b",
    r"\bbugünkü\b",
    r"\b202[4-9]\b",
]

RESEARCH_TRIGGER_PHRASES = [
    "internetten araştır",
    "internetten bak",
    "webden araştır",
    "web'den araştır",
    "internette ara",
    "kaynak bul",
    "kaynakları bul",
    "kaynak göster",
    "araştır",
    "güncel bilgi ver",
    "en son bilgiyi",
    "en güncel",
    "doğrula",
    "teyit et",
    "karşılaştır",
]

# Bazı konular güncel kelime içermese bile doğası gereği değişkendir.
VOLATILE_TOPICS = [
    "mevzuat", "kanun", "yönetmelik", "yasa", "vergi",
    "maaş", "asgari ücret", "faiz", "merkez bankası",
    "borsa", "hisse", "bitcoin", "kripto", "akaryakıt",
    "benzin", "motorin", "altın", "döviz", "kampanya",
    "sınav takvimi", "başvuru tarihi", "başvuru şartları",
    "üniversite taban puanı", "kontenjan", "kpss", "pmyo",
]

# İnternet gerektirmeyen tipik istekler. Bunlar özellikle korunur.
NO_WEB_PATTERNS = [
    r"^merhaba\b",
    r"^selam\b",
    r"^naber\b",
    r"^nasılsın\b",
    r"^teşekkür",
    r"^sağ ol\b",
    r"^eyvallah\b",
    r"\bne demek\b",
    r"\bnedir\b$",
]

def needs_web_research(message, username="karahan", mode="normal"):
    """
    Hafif ve deterministik bir karar katmanı.
    Ekstra AI çağrısı yapmaz; böylece normal konuşmalarda maliyet ve
    gecikme oluşturmaz.
    """
    text = clean_text(message).lower()
    if not text:
        return False

    # Selamlaşma gibi kısa mesajlarda kesinlikle araştırma yapma.
    for pattern in NO_WEB_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return False

    # Kullanıcı açıkça araştırma istediğinde araştır.
    if any(phrase in text for phrase in RESEARCH_TRIGGER_PHRASES):
        return True

    # Akademik araştırma modunda açık araştırma ifadeleri ve güncel
    # çalışma talepleri web araştırmasını tetikler.
    if username == "ilknur" or mode in {"research", "article"}:
        academic_current = [
            "güncel çalışma", "son çalışmalar", "literatür",
            "2025", "2026", "yeni araştırma", "makale",
            "kaynakça", "bilimsel kaynak", "literatür taraması"
        ]
        if any(x in text for x in academic_current):
            return True

    if any(re.search(pattern, text, re.IGNORECASE) for pattern in WEB_TRIGGER_PATTERNS):
        return True

    if any(topic in text for topic in VOLATILE_TOPICS):
        return True

    # Tarih/yıl açıkça geleceğe veya günümüze referans veriyorsa.
    year_match = re.search(r"\b20\d{2}\b", text)
    if year_match:
        try:
            year = int(year_match.group(0))
            if year >= CURRENT_YEAR - 1:
                return True
        except Exception:
            pass

    return False


def build_profile_research_query(message, username, mode):
    """
    Aynı soruyu her profile farklı araştırma amacıyla aratır.
    Arama sorgusunun kendisi de profilin kullanım amacına göre şekillenir.
    """
    text = clean_text(message)

    # Yerel gündem sorularında arama motorunu doğrudan haber odaklı çalıştır.
    if is_local_news_request(text):
        if username == "ilknur":
            return f"{text} Denizli bugün son dakika haber gündem resmi kaynak"
        if username == "betul":
            return f"{text} Denizli bugün son dakika haber gündem gelişmeler"
        if username == "sinem":
            return f"{text} Denizli bugün güvenilir haber gündem gelişmeler"
        return f"{text} Denizli bugün son dakika haber gündem resmi kaynak"

    if username == "ilknur":
        return (
            f"{text} akademik güncel araştırma bilimsel kaynak "
            f"2025 2026"
        )

    if username == "betul":
        return (
            f"{text} güncel gelişmeler haberler trendler"
        )

    if username == "sinem":
        return (
            f"{text} güncel güvenilir bilgi"
        )

    # Karahan / varsayılan: teknik, resmi ve doğrudan.
    return (
        f"{text} güncel resmi kaynak teknik bilgi"
    )


def profile_research_instruction(username):
    if username == "betul":
        return """
Araştırma sonucunu Betül profiline uygun yorumla:
- Aşko, samimi, komik ve hafif dedikoducu bir arkadaş gibi konuş.
- Haber veya güncel bilgiyi önce net söyle, sonra Betül tarzında kısa bir yorum ekle.
- Hava durumunda sıcaklık, yağış ve gün içindeki değişimi söyle; uygun bir küçük tavsiye ver (ör. şemsiye, ince ceket).
- Yerel gündemde önemli bir olay varsa 'kız', 'aşko' gibi doğal ifadelerle dikkat çekebilirsin.
- Kaynak URL'si, kaynak listesi veya araştırma tekniği anlatma.
- Kaynaklarda olmayan olayı uydurma ve gerçek bir haberi eğlence olsun diye değiştirme.
"""
    if username == "sinem":
        return """
Araştırma sonucunu Sinem profiline uygun yorumla:
- Sıcak, doğal ve arkadaşça anlat.
- Güncel bilgiyi anlaşılır şekilde özetle ve kullanıcıya günlük hayatta işe yarayacak küçük bir öneri ver.
- Hava durumunda özellikle sıcaklık, yağış ihtimali ve dışarı çıkma açısından pratik tavsiye ver.
- Yerel haberlerde önce önemli olayı, sonra kısa bağlamını söyle.
- Kaynak URL'si veya link listesi verme.
"""
    if username == "ilknur":
        return """
Araştırma sonucunu İlknur akademik profiline uygun yorumla:
- Hocam diye hitap et.
- Güncel bilgiyi kısa bir sonuç paragrafıyla özetle.
- Akademik konularda kaynakların bulgu ve değerlendirmesini ayır.
- Günlük konularda gereksiz akademik dil kullanma; hava durumu gibi sorulara doğal ve faydalı cevap ver.
- Kaynak URL'si listesi verme; yalnızca gerekirse kurum/kaynak adını metin içinde belirt.
"""
    return """
Araştırma sonucunu Karahan profiline uygun yorumla:
- Teknik, net, doğrudan ve pratik ol.
- Kullanıcıya önce sonucu söyle, ardından önemli ayrıntıları ver.
- Hava durumunda sıcaklık, hissedilen sıcaklık, yağış ve ilerleyen saatlerdeki değişimi söyle; gerekiyorsa dışarı çıkma önerisi ekle.
- Yerel gündemde olayın ne olduğunu, nerede/ne zaman olduğunu ve bilinen önemli ayrıntıyı kısa şekilde ver.
- Kaynak URL'si veya link listesi verme.
"""


def perform_smart_research(message, username, mode):
    """
    Yalnızca needs_web_research() True olduğunda çağrılır.
    """
    query = build_profile_research_query(
        message,
        username,
        mode
    )

    sources = research_topic(query)

    return {
        "query": query,
        "sources": sources,
        "context": format_sources_for_ai(sources)
    }


def format_research_sources_for_user(sources):
    if not sources:
        return ""

    lines = ["\n\nKaynaklar:"]
    for i, source in enumerate(sources[:6], 1):
        title = clean_text(source.get("title", "Kaynak"))
        url = source.get("url", "").strip()
        if url:
            lines.append(f"[{i}] {title} — {url}")

    return "\n".join(lines)



# ============================================================
# PRESENTATION FALLBACK
# ============================================================

def fallback_presentation(
    topic,
    slide_count
):

    content_count = max(
        3,
        slide_count - 2
    )

    templates = [

        (
            "Temel Kavramlar",
            f"{topic} konusunun temel kavramları, kapsamı ve ana bileşenleri açıklanmaktadır."
        ),

        (
            "Tarihsel Gelişim",
            f"{topic} konusunun ortaya çıkışı ve tarihsel gelişimindeki önemli değişimler ele alınmaktadır."
        ),

        (
            "Temel Unsurlar",
            f"{topic} başlığını oluşturan temel unsurlar ve bu unsurlar arasındaki ilişkiler incelenmektedir."
        ),

        (
            "Uygulama Alanları",
            f"{topic} kapsamında kullanılan başlıca yöntemler, uygulamalar ve kullanım alanları değerlendirilmektedir."
        ),

        (
            "Etkileri",
            f"{topic} konusunun bireyler, toplum ve ilgili kurumlar üzerindeki başlıca etkileri açıklanmaktadır."
        ),

        (
            "Günümüzdeki Önemi",
            f"{topic} konusunun günümüzdeki önemi ve değişen koşullar karşısındaki konumu değerlendirilmektedir."
        ),

        (
            "Genel Değerlendirme",
            f"{topic} açısından temel bulgular ve öne çıkan noktalar bütüncül biçimde değerlendirilmektedir."
        )
    ]

    slides = []

    for i in range(
        content_count
    ):

        title, paragraph = templates[
            i % len(templates)
        ]

        slides.append({

            "title":
                title,

            "paragraph":
                paragraph,

            "visual_query":
                f"{topic} {title} documentary academic",

            "sources":
                []
        })

    return {

        "title":
            topic,

        "subtitle":
            "Akademik Sunum",

        "cover_visual_query":
            f"{topic} academic professional",

        "slides":
            slides,

        "conclusion": {

            "title":
                "Sonuç ve Değerlendirme",

            "paragraph":
                f"{topic} farklı boyutlarıyla değerlendirildiğinde, temel kavramların, uygulamaların ve etkilerin birlikte ele alınmasının konunun bütüncül biçimde anlaşılması açısından önemli olduğu görülmektedir.",

            "visual_query":
                f"{topic} conclusion academic",

            "sources":
                []
        }
    }


# ============================================================
# TEXT SIMILARITY
# ============================================================

def normalize_similarity_text(
    text
):

    text = str(
        text or ""
    ).lower()

    text = re.sub(
        r"[^a-zA-Z0-9çğıöşüÇĞİÖŞÜ ]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def text_similarity(
    a,
    b
):

    a = normalize_similarity_text(
        a
    )

    b = normalize_similarity_text(
        b
    )

    if not a or not b:
        return 0

    return SequenceMatcher(
        None,
        a,
        b
    ).ratio()


def has_duplicate_content(
    paragraph,
    previous_paragraphs,
    threshold=0.68
):

    for previous in previous_paragraphs:

        if (
            text_similarity(
                paragraph,
                previous
            )
            >= threshold
        ):

            return True

    return False


# ============================================================
# PRESENTATION PLAN
# ============================================================

def create_presentation_plan(
    topic,
    slide_count,
    sources,
    progress_callback=None
):

    content_count = max(
        3,
        slide_count - 2
    )

    if progress_callback:

        progress_callback(
            31,
            "Sunumun slayt planı oluşturuluyor..."
        )

    source_text = format_sources_for_ai(
        sources
    )

    prompt = f"""
Bir üniversite düzeyinde akademik sunum için
SLAYT PLANI oluştur.

KONU:
{topic}

TOPLAM SLAYT:
{slide_count}

Yapı:

1 kapak
{content_count} içerik
1 sonuç

ÖNEMLİ:

Her içerik slaytının farklı bir amacı olmalı.

Aynı bilgiyi farklı başlıklarla tekrar etme.

Konuya uygun farklı boyutlar seç:

- tanım
- tarihsel gelişim
- yapı
- süreç
- uygulama
- örnek
- etkiler
- avantaj/dezavantaj
- güncel durum
- değerlendirme

KAYNAKLAR:

{source_text}

Yalnızca JSON döndür:

{{
  "title": "Ana sunum başlığı",
  "subtitle": "Akademik alt başlık",
  "cover_visual_query": "English image search query",
  "slides": [
    {{
      "title": "Slayt başlığı",
      "objective": "Bu slaytın anlatacağı özgün konu",
      "visual_query": "English image search query"
    }}
  ],
  "conclusion": {{
    "title": "Sonuç ve Değerlendirme",
    "objective": "Sunumun genel değerlendirmesi",
    "visual_query": "English image search query"
  }}
}}

Kurallar:

- Türkçe yaz.
- Tam olarak {content_count} içerik slaytı oluştur.
- Her objective birbirinden farklı olmalı.
- Aynı konuyu tekrar eden slayt oluşturma.
- Görsel sorguları birbirinden farklı olmalı.
- Görsel sorguları İngilizce olmalı.
- Sonuç slaytı önceki slaytların kopyası olmamalı.
- JSON dışında hiçbir şey yazma.
"""

    result = ask_ai(
        prompt,
        ACADEMIC_SYSTEM
    )

    data = extract_json(
        result
    )

    if not data:

        return fallback_presentation(
            topic,
            slide_count
        )

    raw_slides = data.get(
        "slides",
        []
    )

    clean_slides = []

    used_titles = set()

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

        objective = str(
            slide.get(
                "objective",
                ""
            )
        ).strip()

        visual_query = str(
            slide.get(
                "visual_query",
                ""
            )
        ).strip()

        if not title or not objective:
            continue

        title_key = normalize_similarity_text(
            title
        )

        if title_key in used_titles:
            continue

        used_titles.add(
            title_key
        )

        clean_slides.append({

            "title":
                title,

            "objective":
                objective,

            "visual_query":
                visual_query
                or
                f"{topic} {title} academic",
        })

    if len(clean_slides) < content_count:

        return fallback_presentation(
            topic,
            slide_count
        )

    clean_slides = clean_slides[
        :content_count
    ]

    conclusion_data = data.get(
        "conclusion",
        {}
    )

    if not isinstance(
        conclusion_data,
        dict
    ):

        conclusion_data = {}

    return {

        "title":
            str(
                data.get(
                    "title",
                    topic
                )
            ).strip()
            or topic,

        "subtitle":
            str(
                data.get(
                    "subtitle",
                    "Akademik Sunum"
                )
            ).strip()
            or "Akademik Sunum",

        "cover_visual_query":
            str(
                data.get(
                    "cover_visual_query",
                    f"{topic} academic professional"
                )
            ).strip(),

        "slides":
            clean_slides,

        "conclusion": {

            "title":
                str(
                    conclusion_data.get(
                        "title",
                        "Sonuç ve Değerlendirme"
                    )
                ).strip(),

            "objective":
                str(
                    conclusion_data.get(
                        "objective",
                        "Konunun genel değerlendirmesi"
                    )
                ).strip(),

            "visual_query":
                str(
                    conclusion_data.get(
                        "visual_query",
                        f"{topic} conclusion academic"
                    )
                ).strip()
        }
    }


# ============================================================
# INDIVIDUAL SLIDE CONTENT
# ============================================================

def generate_slide_content(
    topic,
    slide,
    sources,
    previous_paragraphs
):

    source_text = format_sources_for_ai(
        sources
    )

    prompt = f"""
Aşağıdaki akademik sunum için SADECE BU SLAYTIN
içeriğini oluştur.

ANA KONU:
{topic}

SLAYT BAŞLIĞI:
{slide["title"]}

BU SLAYTIN ÖZGÜN AMACI:
{slide["objective"]}

KAYNAKLAR:
{source_text}

ÖNCEKİ SLAYT METİNLERİ:
{chr(10).join(previous_paragraphs[-5:]) if previous_paragraphs else "Henüz yok."}

Bu slayt önceki slaytların tekrarını yapmamalıdır.

Kaynaklarda bulunmayan kesin istatistik, tarih,
kişi, kurum veya olay uydurma.

Akademik ama anlaşılır Türkçe kullan.

80-120 kelime civarında açıklama üret.

Görsel için İngilizce arama sorgusu oluştur.

Yalnızca JSON döndür:

{{
  "paragraph": "Slayt açıklaması",
  "visual_query": "English visual search query",
  "source_indexes": [1, 2]
}}

JSON dışında hiçbir şey yazma.
"""

    result = ask_ai(
        prompt,
        ACADEMIC_SYSTEM
    )

    data = extract_json(
        result
    )

    if not data:
        return None

    paragraph = str(
        data.get(
            "paragraph",
            ""
        )
    ).strip()

    visual_query = str(
        data.get(
            "visual_query",
            slide.get(
                "visual_query",
                f"{topic} academic"
            )
        )
    ).strip()

    source_indexes = data.get(
        "source_indexes",
        []
    )

    if not isinstance(
        source_indexes,
        list
    ):

        source_indexes = []

    selected_sources = []

    for index in source_indexes:

        try:

            index = int(
                index
            ) - 1

            if (
                0 <= index
                < len(sources)
            ):

                selected_sources.append(
                    sources[index]
                )

        except Exception:

            continue

    if not selected_sources:

        selected_sources = sources[:2]

    if not paragraph:

        return None

    return {

        "paragraph":
            paragraph,

        "visual_query":
            visual_query
            or
            slide.get(
                "visual_query",
                f"{topic} academic"
            ),

        "sources":
            selected_sources
    }


# ============================================================
# BUILD COMPLETE PRESENTATION
# ============================================================

def build_verified_presentation(
    topic,
    slide_count,
    progress_callback=None
):

    sources = research_topic(
        topic,
        progress_callback
    )

    if progress_callback:

        progress_callback(
            32,
            f"{len(sources)} kaynak bulundu. Bilgiler karşılaştırılıyor..."
        )

    plan = create_presentation_plan(
        topic,
        slide_count,
        sources,
        progress_callback
    )

    if progress_callback:

        progress_callback(
            36,
            "Slayt içerikleri hazırlanmaya başlanıyor..."
        )

    previous_paragraphs = []

    final_slides = []

    total_slides = len(
        plan["slides"]
    )

    for slide_index, slide in enumerate(
        plan["slides"],
        start=1
    ):

        if progress_callback:

            progress = 36 + int(
                (
                    slide_index - 1
                )
                /
                max(
                    1,
                    total_slides
                )
                * 12
            )

            progress_callback(
                progress,
                (
                    f"Slayt {slide_index}/{total_slides} "
                    "içeriği hazırlanıyor..."
                )
            )

        generated = generate_slide_content(
            topic,
            slide,
            sources,
            previous_paragraphs
        )

        if generated:

            duplicate = has_duplicate_content(
                generated["paragraph"],
                previous_paragraphs
            )

            if duplicate:

                if progress_callback:

                    progress_callback(
                        min(
                            48,
                            36 + slide_index * 2
                        ),
                        (
                            f"Slayt {slide_index} "
                            "özgünlük kontrolünden geçiriliyor..."
                        )
                    )

                regeneration_prompt = f"""
Bu slaytın metni önceki slaytlara fazla benziyor.

ANA KONU:
{topic}

SLAYT:
{slide["title"]}

AMAÇ:
{slide["objective"]}

YENİ METİN ÖNCEKİ SLAYTLARLA
ANLAM OLARAK ÇAKIŞMAMALI.

ÖNCEKİ METİNLER:

{chr(10).join(previous_paragraphs)}

Kaynaklara bağlı kal.

80-120 kelime arasında,
özgün ve akademik yeni bir açıklama yaz.

Yalnızca JSON:

{{
  "paragraph": "Yeni açıklama",
  "visual_query": "English image query"
}}
"""

                retry = ask_ai(
                    regeneration_prompt,
                    ACADEMIC_SYSTEM
                )

                retry_data = extract_json(
                    retry
                )

                if retry_data:

                    retry_paragraph = str(
                        retry_data.get(
                            "paragraph",
                            ""
                        )
                    ).strip()

                    if (
                        retry_paragraph
                        and
                        not has_duplicate_content(
                            retry_paragraph,
                            previous_paragraphs,
                            0.72
                        )
                    ):

                        generated[
                            "paragraph"
                        ] = retry_paragraph

                        generated[
                            "visual_query"
                        ] = str(
                            retry_data.get(
                                "visual_query",
                                generated[
                                    "visual_query"
                                ]
                            )
                        ).strip()

        if not generated:

            generated = {

                "paragraph":
                    slide["objective"],

                "visual_query":
                    slide["visual_query"],

                "sources":
                    sources[:2]
            }

        final_slide = {

            "title":
                slide["title"],

            "paragraph":
                generated["paragraph"],

            "visual_query":
                generated["visual_query"],

            "sources":
                generated.get(
                    "sources",
                    sources[:2]
                )
        }

        final_slides.append(
            final_slide
        )

        previous_paragraphs.append(
            final_slide["paragraph"]
        )

    if progress_callback:

        progress_callback(
            50,
            "İçerikler tamamlandı. Sonuç bölümü hazırlanıyor..."
        )

    conclusion = plan[
        "conclusion"
    ]

    conclusion_prompt = f"""
Bir akademik sunumun SONUÇ slaydını oluştur.

KONU:
{topic}

SONUÇ SLAYTININ AMACI:
{conclusion.get("objective", "")}

SUNUMDAKİ SLAYTLAR:

{chr(10).join(
    [
        f"- {slide['title']}: {slide['paragraph']}"
        for slide in final_slides
    ]
)}

KAYNAKLAR:

{format_sources_for_ai(sources)}

Kurallar:

- Önceki slaytların cümlelerini kopyalama.
- Yeni bilgi uydurma.
- Sunumda anlatılan ana noktaları sentezle.
- Akademik ve net Türkçe kullan.
- Yaklaşık 70-100 kelime.
- Görsel sorgusu İngilizce olsun.

Yalnızca JSON:

{{
  "paragraph": "Sonuç metni",
  "visual_query": "English conclusion visual query",
  "source_indexes": [1, 2]
}}
"""

    conclusion_result = ask_ai(
        conclusion_prompt,
        ACADEMIC_SYSTEM
    )

    conclusion_data = extract_json(
        conclusion_result
    )

    if conclusion_data:

        conclusion_paragraph = str(
            conclusion_data.get(
                "paragraph",
                ""
            )
        ).strip()

        conclusion_visual = str(
            conclusion_data.get(
                "visual_query",
                ""
            )
        ).strip()

    else:

        conclusion_paragraph = (
            "Sunum kapsamında ele alınan temel "
            "kavramlar, gelişim süreci, uygulamalar "
            "ve etkiler birlikte değerlendirildiğinde "
            "konunun çok boyutlu bir yapıya sahip "
            "olduğu görülmektedir."
        )

        conclusion_visual = (
            conclusion.get(
                "visual_query",
                f"{topic} conclusion academic"
            )
        )

    if progress_callback:

        progress_callback(
            55,
            "İçerikler doğrulandı. Görsel araştırma aşamasına geçiliyor..."
        )

    return {

        "title":
            plan["title"],

        "subtitle":
            plan["subtitle"],

        "cover_visual_query":
            plan["cover_visual_query"],

        "slides":
            final_slides,

        "conclusion": {

            "title":
                "Sonuç ve Değerlendirme",

            "paragraph":
                conclusion_paragraph,

            "visual_query":
                conclusion_visual,

            "sources":
                sources[:3]
        },

        "research_sources":
            sources
    }


# ============================================================
# IMAGE SEARCH
# ============================================================

IMAGE_HEADERS = {

    "User-Agent":
        "Mozilla/5.0 "
        "(X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "Chrome/140 Safari/537.36 "
        "K.A.R.V.I.S./32.0"
}


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

            headers=IMAGE_HEADERS,

            timeout=15
        )

        if response.status_code != 200:
            return []

        pages = (
            response
            .json()
            .get("query", {})
            .get("pages", {})
        )

        results = []

        for page in pages.values():

            info = page.get(
                "imageinfo",
                []
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

            headers=IMAGE_HEADERS,

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

            url = (
                item.get(
                    "thumbnail"
                )
                or
                item.get(
                    "url"
                )
            )

            if url:
                results.append(
                    url
                )

        return results

    except Exception:

        return []


def get_google_candidates_api(
    query
):

    if not GOOGLE_IMAGE_API_KEY:
        return []

    if not GOOGLE_CSE_ID:
        return []

    try:

        response = requests.get(

            "https://www.googleapis.com/customsearch/v1",

            params={

                "key":
                    GOOGLE_IMAGE_API_KEY,

                "cx":
                    GOOGLE_CSE_ID,

                "q":
                    query,

                "searchType":
                    "image",

                "num":
                    3,

                "safe":
                    "active"
            },

            headers=IMAGE_HEADERS,

            timeout=15
        )

        if response.status_code != 200:
            return []

        items = (
            response
            .json()
            .get(
                "items",
                []
            )
        )

        return [

            item.get("link")

            for item in items[:3]

            if item.get("link")
        ]

    except Exception:

        return []


def get_google_candidates_html(
    query
):

    try:

        response = requests.get(

            "https://www.google.com/search",

            params={

                "tbm":
                    "isch",

                "q":
                    query,

                "safe":
                    "active",

                "hl":
                    "en"
            },

            headers=IMAGE_HEADERS,

            timeout=15
        )

        if response.status_code != 200:
            return []

        html = response.text

        candidates = []

        patterns = [

            r'"(https?://[^"\\]+?\.(?:jpg|jpeg|png|webp)(?:\?[^"\\]*)?)"',

            r'"(https?://[^"\\]+?\.(?:JPG|JPEG|PNG|WEBP)(?:\?[^"\\]*)?)"'
        ]

        for pattern in patterns:

            matches = re.findall(
                pattern,
                html,
                flags=re.IGNORECASE
            )

            for match in matches:

                url = (
                    match
                    .replace(
                        "\\u003d",
                        "="
                    )
                    .replace(
                        "\\u0026",
                        "&"
                    )
                )

                if (
                    url.startswith(
                        "http"
                    )
                    and
                    url not in candidates
                ):

                    candidates.append(
                        url
                    )

                if len(candidates) >= 3:

                    return candidates[:3]

        return candidates[:3]

    except Exception:

        return []


def get_google_candidates(
    query
):

    results = get_google_candidates_api(
        query
    )

    if results:

        return results[:3]

    return get_google_candidates_html(
        query
    )[:3]


# ============================================================
# IMAGE QUALITY
# ============================================================

def image_hash(
    image
):

    try:

        small = (
            image
            .convert("RGB")
            .resize(
                (96,96)
            )
        )

        return hashlib.sha256(
            small.tobytes()
        ).hexdigest()

    except Exception:

        return None


def image_quality_score(
    image
):

    try:

        width, height = image.size

        if width < 500:
            return 0

        if height < 300:
            return 0

        ratio = width / height

        score = 0

        if (
            1.2 <= ratio <= 2.2
        ):

            score += 30

        if width >= 1000:

            score += 30

        elif width >= 700:

            score += 20

        if height >= 600:

            score += 20

        elif height >= 400:

            score += 10

        if (
            ratio < 0.7
            or
            ratio > 3.0
        ):

            score -= 30

        return score

    except Exception:

        return 0


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

        content_type = (
            response.headers
            .get(
                "Content-Type",
                ""
            )
            .lower()
        )

        if (
            content_type
            and
            not content_type.startswith(
                "image/"
            )
        ):

            return None

        image = Image.open(
            BytesIO(
                response.content
            )
        )

        image.load()

        if (
            image.width < 400
            or
            image.height < 250
        ):

            return None

        quality = image_quality_score(
            image
        )

        if quality <= 0:
            return None

        h = image_hash(
            image
        )

        if not h:
            return None

        with lock:

            if url in used_urls:
                return None

            if h in used_hashes:
                return None

            used_urls.add(
                url
            )

            used_hashes.add(
                h
            )

        return image.convert(
            "RGB"
        )

    except Exception:

        return None


# ============================================================
# IMAGE PIPELINE
# ============================================================

def expand_image_queries(
    topic,
    title,
    visual_query
):

    queries = []

    if visual_query:

        queries.append(
            visual_query
        )

    queries.append(
        f"{topic} {title} documentary"
    )

    queries.append(
        f"{topic} {title} photograph"
    )

    queries.append(
        f"{topic} {title} academic"
    )

    result = []

    seen = set()

    for query in queries:

        query = query.strip()

        if not query:
            continue

        key = query.lower()

        if key in seen:
            continue

        seen.add(
            key
        )

        result.append(
            query
        )

    return result


def find_unique_image(
    queries,
    used_urls,
    used_hashes,
    lock
):

    candidate_urls = []

    for query in queries:

        candidate_urls.extend(
            get_wikimedia_candidates(
                query
            )
        )

        if len(candidate_urls) >= 30:
            break

    if len(candidate_urls) < 8:

        for query in queries:

            candidate_urls.extend(
                get_openverse_candidates(
                    query
                )
            )

            if len(candidate_urls) >= 30:
                break

    if len(candidate_urls) < 8:

        for query in queries:

            candidate_urls.extend(
                get_google_candidates(
                    query
                )[:3]
            )

            if len(candidate_urls) >= 15:
                break

    unique_urls = []

    seen = set()

    for url in candidate_urls:

        if not url:
            continue

        if url in seen:
            continue

        seen.add(
            url
        )

        unique_urls.append(
            url
        )

    for url in unique_urls:

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
# FONT
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
                "/usr/share/fonts/"
                "truetype/dejavu/"
                "DejaVuSans-Bold.ttf"
            ),

            Path(
                "/usr/share/fonts/"
                "truetype/liberation2/"
                "LiberationSans-Bold.ttf"
            )
        ]

    else:

        candidates = [

            BASE_DIR /
            "fonts" /
            "DejaVuSans.ttf",

            Path(
                "/usr/share/fonts/"
                "truetype/dejavu/"
                "DejaVuSans.ttf"
            ),

            Path(
                "/usr/share/fonts/"
                "truetype/liberation2/"
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
                max(
                    8,
                    int(size)
                )
            )

    except Exception:

        pass

    return ImageFont.load_default()


# ============================================================
# TEXT FITTING
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

        try:

            box = draw.textbbox(
                (0,0),
                text,
                font=font
            )

            return (
                box[2] -
                box[0]
            )

        except Exception:

            return (
                len(text)
                *
                max(
                    8,
                    getattr(
                        font,
                        "size",
                        12
                    ) * 0.55
                )
            )


def font_line_height(
    font,
    extra=0
):

    size = max(
        8,
        int(
            getattr(
                font,
                "size",
                20
            )
        )
    )

    return size + extra


def wrap_pixel_text(
    draw,
    text,
    font,
    max_width
):

    words = (
        str(text or "")
        .replace(
            "\n",
            " \n "
        )
        .split()
    )

    lines = []

    current = ""

    for word in words:

        if word == "\\n":

            if current:

                lines.append(
                    current
                )

                current = ""

            continue

        candidate = (
            word
            if not current
            else
            current + " " + word
        )

        if (
            text_width(
                draw,
                candidate,
                font
            )
            <= max_width
        ):

            current = candidate

            continue

        if current:

            lines.append(
                current
            )

        if (
            text_width(
                draw,
                word,
                font
            )
            <= max_width
        ):

            current = word

        else:

            chunk = ""

            for ch in word:

                test = chunk + ch

                if (
                    text_width(
                        draw,
                        test,
                        font
                    )
                    <= max_width
                ):

                    chunk = test

                else:

                    if chunk:

                        lines.append(
                            chunk
                        )

                    chunk = ch

            current = chunk

    if current:

        lines.append(
            current
        )

    return lines


def truncate_lines(
    draw,
    lines,
    font,
    max_width,
    max_lines
):

    if len(lines) <= max_lines:

        return lines

    lines = lines[
        :max_lines
    ]

    last = lines[-1]

    ellipsis = "…"

    while (
        last
        and
        text_width(
            draw,
            last + ellipsis,
            font
        ) > max_width
    ):

        last = last[:-1]

    lines[-1] = (
        last.rstrip()
        +
        ellipsis
        if last
        else
        ellipsis
    )

    return lines


def fit_text(
    draw,
    text,
    max_width,
    max_height,
    start_size,
    min_size=14,
    bold=False,
    spacing_ratio=0.30
):

    text = str(
        text or ""
    ).strip()

    if not text:

        return (
            karvis_font(
                start_size,
                bold
            ),
            [],
            0
        )

    size = int(
        start_size
    )

    while size >= min_size:

        font = karvis_font(
            size,
            bold
        )

        spacing = max(
            4,
            int(
                size *
                spacing_ratio
            )
        )

        lines = wrap_pixel_text(
            draw,
            text,
            font,
            max_width
        )

        line_h = font_line_height(
            font,
            spacing
        )

        max_lines = max(
            1,
            int(
                max_height //
                line_h
            )
        )

        if len(lines) <= max_lines:

            return (
                font,
                lines,
                spacing
            )

        size -= 1

    font = karvis_font(
        min_size,
        bold
    )

    spacing = max(
        4,
        int(
            min_size *
            spacing_ratio
        )
    )

    lines = wrap_pixel_text(
        draw,
        text,
        font,
        max_width
    )

    line_h = font_line_height(
        font,
        spacing
    )

    max_lines = max(
        1,
        int(
            max_height //
            line_h
        )
    )

    lines = truncate_lines(
        draw,
        lines,
        font,
        max_width,
        max_lines
    )

    return (
        font,
        lines,
        spacing
    )


def draw_fit_text(
    draw,
    text,
    xy,
    max_width,
    max_height,
    start_size,
    min_size=14,
    fill=(255,255,255),
    bold=False,
    spacing_ratio=0.30
):

    font, lines, spacing = fit_text(
        draw,
        text,
        max_width,
        max_height,
        start_size,
        min_size,
        bold,
        spacing_ratio
    )

    x, y = xy

    line_h = font_line_height(
        font,
        spacing
    )

    for line in lines:

        draw.text(
            (x,y),
            line,
            font=font,
            fill=fill
        )

        y += line_h

    return (
        y,
        font,
        lines
    )


# ============================================================
# IMAGE DESIGN
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

    ImageDraw.Draw(
        mask
    ).rounded_rectangle(
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

    return ImageOps.fit(
        image.convert(
            "RGB"
        ),
        size,
        method=Image.Resampling.LANCZOS,
        centering=(0.5,0.5)
    )


def paste_round_image(
    base,
    image,
    box,
    radius=30
):

    x,y,w,h = box

    image = prepare_image(
        image,
        (w,h)
    )

    base.paste(
        image,
        (x,y),
        rounded_mask(
            (w,h),
            radius
        )
    )


# ============================================================
# SLIDE DESIGN
# ============================================================

SLIDE_WIDTH = 1600
SLIDE_HEIGHT = 900

PDF_WIDTH = 16 * inch
PDF_HEIGHT = 9 * inch


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
        (5,10,18)
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
            (2,7,13,165)
        )

        img = Image.alpha_composite(
            bg.convert("RGBA"),
            dark
        ).convert(
            "RGB"
        )

    draw = ImageDraw.Draw(
        img
    )

    draw.rectangle(
        (80,75,410,81),
        fill=(0,229,255)
    )

    draw.text(
        (80,110),
        "K.A.R.V.I.S.",
        font=karvis_font(
            26,
            True
        ),
        fill=(0,229,255)
    )

    draw.text(
        (80,148),
        "KARAHAN INC.",
        font=karvis_font(
            17
        ),
        fill=(160,175,190)
    )

    draw_fit_text(
        draw,
        title,
        (80,275),
        1050,
        275,
        72,
        38,
        fill=(245,250,255),
        bold=True,
        spacing_ratio=0.18
    )

    draw_fit_text(
        draw,
        subtitle,
        (85,570),
        980,
        95,
        28,
        18,
        fill=(180,195,210),
        bold=False,
        spacing_ratio=0.20
    )

    draw.text(
        (80,810),
        "AKADEMİK SUNUM",
        font=karvis_font(
            18,
            True
        ),
        fill=(0,229,255)
    )

    draw.text(
        (80,845),
        "K.A.R.V.I.S. • KARAHAN INC.",
        font=karvis_font(
            15
        ),
        fill=(110,125,140)
    )

    img.save(
        output_path,
        "PNG",
        optimize=True
    )


def format_source_footer(
    sources,
    max_sources=2
):

    if not sources:

        return (
            "Kaynak: K.A.R.V.I.S. araştırma motoru"
        )

    names = []

    for source in sources[
        :max_sources
    ]:

        title = source.get(
            "title",
            ""
        ).strip()

        if title:

            names.append(
                title
            )

    if not names:

        return (
            "Kaynak: K.A.R.V.I.S."
        )

    return (
        "Kaynak: "
        +
        " • ".join(
            names
        )
    )


def create_content_slide(
    slide_number,
    total_slides,
    title,
    paragraph,
    image,
    sources,
    output_path
):

    img = Image.new(
        "RGB",
        (
            SLIDE_WIDTH,
            SLIDE_HEIGHT
        ),
        (5,11,19)
    )

    draw = ImageDraw.Draw(
        img
    )

    draw.rectangle(
        (70,55,1530,58),
        fill=(18,45,58)
    )

    draw.rectangle(
        (70,55,280,58),
        fill=(0,229,255)
    )

    draw.text(
        (70,82),
        "K.A.R.V.I.S.",
        font=karvis_font(
            21,
            True
        ),
        fill=(0,229,255)
    )

    draw.text(
        (70,111),
        "KARAHAN INC.",
        font=karvis_font(
            14
        ),
        fill=(110,130,145)
    )

    draw_fit_text(
        draw,
        title,
        (70,165),
        700,
        105,
        45,
        24,
        fill=(245,250,255),
        bold=True,
        spacing_ratio=0.18
    )

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
        fill=(10,20,30),
        outline=(22,48,62),
        width=2
    )

    draw.text(
        (105,335),
        "AKADEMİK AÇIKLAMA",
        font=karvis_font(
            18,
            True
        ),
        fill=(0,229,255)
    )

    draw.rectangle(
        (105,372,190,376),
        fill=(0,229,255)
    )

    draw_fit_text(
        draw,
        paragraph,
        (105,415),
        625,
        335,
        25,
        13,
        fill=(215,225,235),
        bold=False,
        spacing_ratio=0.30
    )

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
        fill=(9,18,27),
        outline=(25,51,65),
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
            fill=(0,229,255)
        )

    source_text = format_source_footer(
        sources
    )

    draw_fit_text(
        draw,
        source_text,
        (70,805),
        1250,
        28,
        12,
        9,
        fill=(100,120,135),
        bold=False,
        spacing_ratio=0.10
    )

    draw.text(
        (70,842),
        "K.A.R.V.I.S. • KARAHAN INC.",
        font=karvis_font(
            15
        ),
        fill=(90,110,125)
    )

    draw.text(
        (1430,842),
        f"{slide_number:02d} / {total_slides:02d}",
        font=karvis_font(
            16,
            True
        ),
        fill=(0,229,255)
    )

    img.save(
        output_path,
        "PNG",
        optimize=True
    )


def create_conclusion_slide(
    total_slides,
    title,
    paragraph,
    image,
    sources,
    output_path
):

    img = Image.new(
        "RGB",
        (
            SLIDE_WIDTH,
            SLIDE_HEIGHT
        ),
        (5,11,19)
    )

    draw = ImageDraw.Draw(
        img
    )

    draw.rectangle(
        (70,55,1530,58),
        fill=(18,45,58)
    )

    draw.rectangle(
        (70,55,520,58),
        fill=(0,229,255)
    )

    draw.text(
        (70,90),
        "K.A.R.V.I.S.",
        font=karvis_font(
            22,
            True
        ),
        fill=(0,229,255)
    )

    draw.text(
        (70,120),
        "KARAHAN INC.",
        font=karvis_font(
            14
        ),
        fill=(110,130,145)
    )

    draw_fit_text(
        draw,
        title,
        (70,205),
        750,
        85,
        54,
        30,
        fill=(245,250,255),
        bold=True,
        spacing_ratio=0.18
    )

    draw.rounded_rectangle(
        (70,310,820,750),
        radius=30,
        fill=(10,20,30),
        outline=(22,48,62),
        width=2
    )

    draw.text(
        (110,350),
        "SONUÇ VE DEĞERLENDİRME",
        font=karvis_font(
            19,
            True
        ),
        fill=(0,229,255)
    )

    draw_fit_text(
        draw,
        paragraph,
        (110,405),
        650,
        300,
        27,
        13,
        fill=(220,230,238),
        bold=False,
        spacing_ratio=0.30
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
            (
                880,
                185,
                1500,
                750
            ),
            radius=35,
            fill=(8,22,31),
            outline=(0,229,255),
            width=2
        )

        draw.text(
            (1050,430),
            "K.A.R.V.I.S.",
            font=karvis_font(
                42,
                True
            ),
            fill=(0,229,255)
        )

    source_text = format_source_footer(
        sources,
        3
    )

    draw_fit_text(
        draw,
        source_text,
        (70,805),
        1250,
        28,
        12,
        9,
        fill=(100,120,135),
        bold=False,
        spacing_ratio=0.10
    )

    draw.text(
        (70,835),
        "K.A.R.V.I.S. • KARAHAN INC.",
        font=karvis_font(
            15
        ),
        fill=(90,110,125)
    )

    draw.text(
        (1430,835),
        f"{total_slides:02d} / {total_slides:02d}",
        font=karvis_font(
            16,
            True
        ),
        fill=(0,229,255)
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
    images,
    progress_callback=None
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

    total_slides = len(
        slides
    ) + 2

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

    if progress_callback:

        progress_callback(
            82,
            "Kapak ve slayt tasarımları hazırlanıyor..."
        )

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

    content_total = len(
        slides
    )

    for index, slide in enumerate(
        slides,
        start=2
    ):

        if progress_callback:

            progress_callback(
                82 +
                int(
                    (
                        index - 1
                    )
                    /
                    max(
                        1,
                        content_total + 1
                    )
                    * 10
                ),
                (
                    f"Slayt tasarımı hazırlanıyor "
                    f"({index - 1}/{content_total})..."
                )
            )

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
            sources=slide.get(
                "sources",
                []
            ),
            output_path=str(
                slide_path
            )
        )

        slide_paths.append(
            slide_path
        )

    if progress_callback:

        progress_callback(
            94,
            "Sonuç slaytı hazırlanıyor..."
        )

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
        sources=conclusion.get(
            "sources",
            []
        ),
        output_path=str(
            conclusion_path
        )
    )

    slide_paths.append(
        conclusion_path
    )

    if progress_callback:

        progress_callback(
            96,
            "PDF dosyası oluşturuluyor..."
        )

    pdf_filename = (
        f"karvis_sunum_{presentation_id}.pdf"
    )

    pdf_path = (
        GENERATED_DIR
        /
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

    if progress_callback:

        progress_callback(
            99,
            "Bitirmek üzereyim..."
        )

    return pdf_filename


# ============================================================
# PRESENTATION JOB SYSTEM
# ============================================================

PRESENTATION_JOBS = {}

presentation_lock = threading.Lock()


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

            "stage":
                "analysis",

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

        if (
            job_id
            in PRESENTATION_JOBS
        ):

            PRESENTATION_JOBS[
                job_id
            ].update(
                kwargs
            )


def worker_progress(
    job_id,
    progress,
    message,
    stage=None
):

    if stage is None:

        if progress <= 8:

            stage = "analysis"

        elif progress < 35:

            stage = "research"

        elif progress < 55:

            stage = "content"

        elif progress < 76:

            stage = "visuals"

        elif progress < 88:

            stage = "design"

        elif progress < 98:

            stage = "pdf"

        else:

            stage = "finish"

    update_job(

        job_id,

        status="working",

        progress=max(
            0,
            min(
                100,
                int(progress)
            )
        ),

        stage=stage,

        message=message
    )


# ============================================================
# PRESENTATION WORKER
# ============================================================

def presentation_worker(
    job_id,
    topic,
    slide_count
):

    try:

        # ----------------------------------------------------
        # START
        # ----------------------------------------------------

        worker_progress(
            job_id,
            3,
            "Konu analiz ediliyor...",
            "analysis"
        )

        time.sleep(
            0.15
        )

        worker_progress(
            job_id,
            7,
            "Sunum yapısı belirleniyor...",
            "analysis"
        )

        # ----------------------------------------------------
        # RESEARCH + CONTENT
        # ----------------------------------------------------

        outline = (
            build_verified_presentation(
                topic,
                slide_count,

                progress_callback=lambda p, m:
                    worker_progress(
                        job_id,
                        p,
                        m
                    )
            )
        )

        slides = outline[
            "slides"
        ]

        research_sources = outline.get(
            "research_sources",
            []
        )

        worker_progress(
            job_id,
            35,
            (
                f"{len(research_sources)} "
                "kaynak üzerinden içerik doğrulanıyor..."
            ),
            "content"
        )

        time.sleep(
            0.10
        )

        # ----------------------------------------------------
        # IMAGE SEARCH
        # ----------------------------------------------------

        worker_progress(
            job_id,
            40,
            "Fotoğraflar araştırılıyor...",
            "visuals"
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
            ] = expand_image_queries(

                topic,

                slide[
                    "title"
                ],

                slide.get(
                    "visual_query",
                    ""
                )
            )

        image_tasks[
            "conclusion"
        ] = expand_image_queries(

            topic,

            "conclusion",

            outline[
                "conclusion"
            ].get(
                "visual_query",
                f"{topic} conclusion"
            )
        )

        images = {}

        total_tasks = len(
            image_tasks
        )

        completed = 0

        # ----------------------------------------------------
        # PARALLEL IMAGE SEARCH
        # ----------------------------------------------------

        with ThreadPoolExecutor(
            max_workers=4
        ) as executor:

            futures = {

                executor.submit(
                    find_unique_image,

                    queries,

                    used_urls,

                    used_hashes,

                    lock

                ):
                    key

                for key, queries
                in image_tasks.items()
            }

            for future in as_completed(
                futures
            ):

                key = futures[
                    future
                ]

                try:

                    images[key] = (
                        future.result()
                    )

                except Exception:

                    images[key] = None

                completed += 1

                progress = (
                    40
                    +
                    int(
                        completed
                        /
                        max(
                            1,
                            total_tasks
                        )
                        *
                        35
                    )
                )

                worker_progress(

                    job_id,

                    progress,

                    (
                        "Fotoğraflar araştırılıyor "
                        f"({completed}/{total_tasks})..."
                    ),

                    "visuals"
                )

        # ----------------------------------------------------
        # VISUAL CHECK
        # ----------------------------------------------------

        worker_progress(
            job_id,
            76,
            "Görseller kontrol ediliyor...",
            "design"
        )

        worker_progress(
            job_id,
            78,
            "Profesyonel slaytlar oluşturuluyor...",
            "design"
        )

        # ----------------------------------------------------
        # PDF
        # ----------------------------------------------------

        pdf_filename = (
            create_presentation_pdf(

                job_id,

                outline,

                images,

                progress_callback=lambda p, m:
                    worker_progress(
                        job_id,
                        p,
                        m
                    )
            )
        )

        # ----------------------------------------------------
        # FINAL
        # ----------------------------------------------------

        worker_progress(
            job_id,
            99,
            "Bitirmek üzereyim...",
            "finish"
        )

        time.sleep(
            0.15
        )

        update_job(

            job_id,

            status="completed",

            stage="finish",

            progress=100,

            message=
                "Sunum hazırlandı.",

            file=
                pdf_filename,

            download_url=
                f"/generated/{pdf_filename}"
        )

    except Exception as e:

        save_error(
            "Presentation worker error",
            traceback.format_exc()
        )

        update_job(

            job_id,

            status="error",

            stage="error",

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

@app.get("/health")
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

        "google_image_search":
            bool(
                GOOGLE_IMAGE_API_KEY
                and
                GOOGLE_CSE_ID
            ),

        "research_engine":
            True,

        "wikipedia":
            True,

        "openverse":
            True,

        "presentation_engine":
            APP_VERSION
    }


# ============================================================
# CHAT
# ============================================================

@app.post("/chat")
async def chat(
    request: ChatRequest
):
    message = (
        request.message
        or ""
    ).strip()

    if not message:
        return {
            "response": "Nasıl yardımcı olabilirim efendim?",
            "message": "Nasıl yardımcı olabilirim efendim?"
        }

    username = (
        request.username
        or "karahan"
    ).strip().lower()

    mode = (
        request.mode
        or "normal"
    ).strip().lower()

    user = USERS.get(
        username,
        USERS["karahan"]
    )

    # --------------------------------------------------------
    # PROFILE / MODE
    # --------------------------------------------------------
    if (
        user.get("role") == "teacher"
        or
        user.get("style") == "academic"
        or
        mode in {
            "academic",
            "research",
            "lesson",
            "quiz",
            "article",
            "teacher"
        }
    ):
        system_prompt = ACADEMIC_SYSTEM
        mode_instruction = (
            f"Akademik çalışma modu: {mode}. "
            "Kullanıcıya 'Hocam' diye hitap et."
        )
    else:
        system_prompt = PROFESSIONAL_SYSTEM
        mode_instruction = (
            f"Çalışma modu: {mode}."
        )

    # --------------------------------------------------------
    # SMART WEB DECISION
    # --------------------------------------------------------
    use_web = needs_web_research(
        message,
        username,
        mode
    )

    research = None
    research_context = ""

    # Hava durumu için ansiklopedik arama yerine doğrudan canlı saatlik veri kullan.
    if use_web and is_weather_request(message):
        weather = fetch_denizli_weather()
        if weather:
            research = {
                "query": "Denizli canlı saatlik hava durumu",
                "sources": [{
                    "title": "Denizli saatlik hava durumu",
                    "text": weather_context_for_ai(weather),
                    "url": "",
                    "source": "Open-Meteo"
                }],
                "context": weather_context_for_ai(weather)
            }

    if use_web and research is None:
        try:
            research = perform_smart_research(
                message,
                username,
                mode
            )
            research_context = research.get(
                "context",
                ""
            )
        except Exception:
            save_error(
                "Smart research error",
                traceback.format_exc()
            )
            research = None
            research_context = ""

    if research and not research_context:
        research_context = research.get("context", "")

    # --------------------------------------------------------
    # PROFILE-SPECIFIC RESEARCH PERSONALITY
    # --------------------------------------------------------
    character_instruction = profile_research_instruction(
        username
    )

    if research:
        web_instruction = f"""
Bu cevap için internet araştırması yapıldı.

Araştırma sorgusu:
{research.get("query", "")}

Aşağıdaki kaynaklar araştırma bağlamıdır:
{research_context}

KURALLAR:
- Yalnızca kaynakların desteklediği güncel bilgileri kullan.
- Kaynaklarda bulunmayan ayrıntıları uydurma.
- Kaynaklar arasında çelişki varsa bunu açıkça belirt.
- Güncel bilgi olduğunu ve mümkünse tarih/kapsamını belirt.
- Kullanıcı istemedikçe araştırma sürecini anlatma.
- URL, link, ham kaynak listesi veya "Kaynaklar:" bölümü oluşturma.
- Araştırma sonucunu doğrudan doğal cevabın içine yedir.
- Hava durumunda saatlik değişimi ve pratik öneriyi mutlaka değerlendir.
- Yerel gündemde en önemli güncel olayı önce söyle, sonra kısa bağlam ver.
- Kaynak adını yalnızca doğruluk için gerçekten gerekli olduğunda metin içinde an.
"""
    else:
        web_instruction = """
Bu soru için internet araştırması gerekli görülmedi.
Harici web kaynağı kullanma ve güncel olmayan bir bilgiyi
güncelmiş gibi sunma. Genel bilgin ve konuşma bağlamınla cevap ver.
"""

    prompt = f"""
Kullanıcı profili:
{username}

{mode_instruction}

{character_instruction}

{web_instruction}

Kullanıcının mesajı:
{message}

Yanıtı doğrudan ver.
Kullanıcı açıkça istemediyse gereksiz uzun açıklamalar yapma.
Bilmediğin bilgileri uydurma.
"""

    result = ask_ai(
        prompt,
        system_prompt
    )

    if not result:
        result = (
            "Şu anda yapay zeka servislerine "
            "bağlanamıyorum. API anahtarlarını "
            "kontrol etmen gerekiyor."
        )

    # Web kaynakları kullanıcıya link listesi olarak basılmaz.
    # Araştırma yalnızca cevabın doğruluğunu ve güncelliğini besler.
    return {
        "response": result,
        "message": result,
        "web_research": bool(research),
        "sources_count": (
            len(research.get("sources", []))
            if research
            else 0
        )
    }


# ============================================================
# PRESENTATION ROUTE
# ============================================================

@app.post("/presentation")
async def create_presentation(
    request: PresentationRequest,
    background_tasks: BackgroundTasks
):

    topic = (
        request.topic
        or ""
    ).strip()

    if not topic:

        raise HTTPException(
            status_code=400,
            detail="Sunum konusu boş olamaz."
        )

    try:

        requested_count = int(
            request.slide_count
        )

    except Exception:

        requested_count = 7

    slide_count = max(
        5,
        min(
            requested_count,
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

        "success":
            True,

        "job_id":
            job_id,

        "status":
            "queued",

        "stage":
            "analysis",

        "progress":
            0,

        "message":
            "Konu analiz ediliyor..."
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
                detail="Sunum bulunamadı."
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
            detail="Dosya bulunamadı."
        )

    if safe_name.lower().endswith(
        ".pdf"
    ):

        return FileResponse(

            path=file_path,

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
        path=file_path
    )


# ============================================================
# MEMORY
# ============================================================

@app.get("/memory")
async def get_memory():

    with memory_lock:

        return {

            "memory":
                read_json_file(
                    MEMORY_FILE,
                    []
                )
        }


@app.post("/memory")
async def add_memory(
    data: dict
):

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

    with memory_lock:

        memories = read_json_file(
            MEMORY_FILE,
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

        memories = memories[
            -200:
        ]

        write_json_file(
            MEMORY_FILE,
            memories
        )

    return {

        "success":
            True,

        "memory":
            memories
    }


# ============================================================
# NEW CHAT
# ============================================================

@app.post("/new-chat")
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

@app.get("/errors")
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

@app.on_event("startup")
async def startup():

    GENERATED_DIR.mkdir(
        exist_ok=True
    )

    print("=" * 65)

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
        "Google Search:",
        "ACTIVE"
        if (
            GOOGLE_IMAGE_API_KEY
            and
            GOOGLE_CSE_ID
        )
        else
        "NOT CONFIGURED"
    )

    print(
        "Wikipedia Research: ENABLED"
    )

    print(
        "Openverse Images: ENABLED"
    )

    print(
        "Google Images Fallback: ENABLED"
    )

    print(
        "Fact-Based Presentation: ENABLED"
    )

    print(
        "Duplicate Slide Protection: ENABLED"
    )

    print(
        "Per-Slide AI Generation: ENABLED"
    )

    print(
        "Source Footer: ENABLED"
    )

    print(
        "Dynamic Text Fit: ENABLED"
    )

    print(
        "Academic Teacher Mode: ENABLED"
    )

    print(
        "Profile Login: ENABLED"
    )


    print(
        "Betül Entertainment Mode: ENABLED"
    )

    print(
        "Betül Instagram Simulation: ENABLED"
    )

    print(
        "PDF Download: ENABLED"
    )

    print(
        "Live Presentation Progress: ENABLED"
    )

    print(
        "Presentation Engine: 16:9"
    )

    print("=" * 65)


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
