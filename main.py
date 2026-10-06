import os
import json
import re
import html
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI


APP_VERSION = "21.0.0"

BASE_DIR = Path(__file__).resolve().parent

MEMORY_FILE = BASE_DIR / "jarvis_memory.json"
ERROR_FILE = BASE_DIR / "jarvis_errors.json"


# ============================================================
# AI AYARLARI
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

GROQ_MODEL_1 = os.getenv(
    "GROQ_MODEL_1",
    "openai/gpt-oss-120b"
)

GROQ_MODEL_2 = os.getenv(
    "GROQ_MODEL_2",
    "openai/gpt-oss-20b"
)

OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openrouter/free"
)


groq_client = None
openrouter_client = None


if GROQ_API_KEY:
    groq_client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
        timeout=60.0,
        max_retries=0
    )


if OPENROUTER_API_KEY:
    openrouter_client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        timeout=60.0,
        max_retries=0
    )


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

    # ========================================================
    # ÖĞRETMEN PROFİLİ
    # ========================================================

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
    }
}


# ============================================================
# MODELLER
# ============================================================

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
    mode: str = "research"


# ============================================================
# KULLANICI NORMALİZASYONU
# ============================================================

def normalize_username(username):

    username = username.lower().strip()

    if username == "betül":
        username = "betul"

    if username == "öğretmen":
        username = "ilknur"

    return username


# ============================================================
# DOSYA SISTEMI
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

    except Exception:

        pass


# ============================================================
# HAFIZA
# ============================================================

def empty_memory():

    return {
        "profile": {},
        "preferences": [],
        "projects": [],
        "vehicles": [],
        "important_facts": [],
        "conversation": []
    }


def load_memory():

    default = {
        "karahan": empty_memory(),
        "betul": empty_memory(),
        "sinem": empty_memory(),
        "ilknur": empty_memory()
    }

    data = load_json_file(
        MEMORY_FILE,
        default
    )

    for username in [
        "karahan",
        "betul",
        "sinem",
        "ilknur"
    ]:

        if username not in data:
            data[username] = empty_memory()

    return data


def save_memory(data):

    save_json_file(
        MEMORY_FILE,
        data
    )


def get_user_memory(username):

    data = load_memory()

    username = normalize_username(username)

    if username not in data:

        data[username] = empty_memory()

        save_memory(data)

    return data[username]


def remember_message(
    username,
    role,
    content
):

    data = load_memory()

    username = normalize_username(username)

    if username not in data:
        data[username] = empty_memory()

    data[username]["conversation"].append({
        "role": role,
        "content": content,
        "time": datetime.now().isoformat()
    })

    data[username]["conversation"] = \
        data[username]["conversation"][-30:]

    save_memory(data)


# ============================================================
# HAFIZA ALGILAMA
# ============================================================

def detect_memory(username, message):

    data = load_memory()

    username = normalize_username(username)

    if username not in data:
        data[username] = empty_memory()

    text = message.lower()

    if username == "karahan":

        if (
            "adım murat" in text
            or "ben murat" in text
        ):

            data[username]["profile"]["name"] = "Murat"

        if (
            "denizli" in text
            and (
                "yaşıyorum" in text
                or "oturuyorum" in text
                or "yaşarım" in text
            )
        ):

            data[username]["profile"]["city"] = "Denizli"

        if "caddy" in text:

            vehicle = "2006 Volkswagen Caddy 1.9 TDI"

            if vehicle not in data[username]["vehicles"]:

                data[username]["vehicles"].append(
                    vehicle
                )

        if (
            "mercedes" in text
            or "w204" in text
        ):

            vehicle = "2012 Mercedes-Benz C180 W204"

            if vehicle not in data[username]["vehicles"]:

                data[username]["vehicles"].append(
                    vehicle
                )

        if (
            "jarvis" in text
            or "karvis" in text
            or "k.a.r.v.i.s." in text
        ):

            project = (
                "K.A.R.V.I.S. kişisel yapay zeka projesi"
            )

            if project not in data[username]["projects"]:

                data[username]["projects"].append(
                    project
                )

    if username == "sinem":

        if "22 yaşındayım" in text:

            data[username]["profile"]["age"] = 22

        if (
            "sarı kedim" in text
            or "sarı bir kedim" in text
        ):

            fact = "Sinem'in sarı bir kedisi var."

            if fact not in data[username]["important_facts"]:

                data[username]["important_facts"].append(
                    fact
                )

    save_memory(data)


# ============================================================
# HATA SISTEMI
# ============================================================

def load_errors():

    return load_json_file(
        ERROR_FILE,
        []
    )


def save_error(
    username,
    provider,
    error,
    message="",
    error_type="AI_ERROR"
):

    errors = load_errors()

    record = {
        "id": len(errors) + 1,

        "time": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

        "username": username,

        "provider": provider,

        "type": error_type,

        "message": message,

        "error": str(error)
    }

    errors.append(record)

    errors = errors[-300:]

    save_json_file(
        ERROR_FILE,
        errors
    )

    return record


def classify_error(error):

    text = str(error).lower()

    if (
        "429" in text
        or "rate limit" in text
        or "quota" in text
    ):

        return "RATE_LIMIT"

    if "timeout" in text:
        return "TIMEOUT"

    if (
        "401" in text
        or "403" in text
        or "api key" in text
    ):

        return "AUTHENTICATION_ERROR"

    if (
        "model" in text
        and (
            "not found" in text
            or "does not exist" in text
            or "invalid" in text
        )
    ):

        return "MODEL_ERROR"

    if (
        "connection" in text
        or "network" in text
    ):

        return "CONNECTION_ERROR"

    return "AI_ERROR"


# ============================================================
# İNTERNET ARAŞTIRMA MOTORU
# ============================================================

def clean_html(text):

    text = re.sub(
        r"<script.*?</script>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    text = re.sub(
        r"<style.*?</style>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = html.unescape(text)

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def internet_search(query, max_results=6):

    encoded_query = urllib.parse.urlencode({
        "q": query
    })

    url = (
        "https://html.duckduckgo.com/html/?"
        + encoded_query
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
                "AppleWebKit/605.1.15 "
                "Version/18.0 Mobile/15E148 Safari/604.1"
            )
        }
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=15
        ) as response:

            raw = response.read().decode(
                "utf-8",
                errors="ignore"
            )

    except Exception as error:

        raise RuntimeError(
            "İnternet araştırması sırasında "
            "arama servisine ulaşılamadı: "
            + str(error)
        )


    results = []

    blocks = re.findall(
        r'<div class="result.*?</div>\s*</div>',
        raw,
        flags=re.DOTALL
    )


    for block in blocks:

        link_match = re.search(
            r'class="result__a"[^>]*href="([^"]+)"',
            block
        )

        title_match = re.search(
            r'class="result__a"[^>]*>(.*?)</a>',
            block,
            flags=re.DOTALL
        )

        snippet_match = re.search(
            r'class="result__snippet"[^>]*>(.*?)</',
            block,
            flags=re.DOTALL
        )


        if not link_match or not title_match:
            continue


        link = html.unescape(
            link_match.group(1)
        )

        title = clean_html(
            title_match.group(1)
        )

        snippet = ""

        if snippet_match:

            snippet = clean_html(
                snippet_match.group(1)
            )


        if not title:
            continue


        results.append({
            "title": title,
            "url": link,
            "snippet": snippet
        })


        if len(results) >= max_results:
            break


    return results


def build_research_context(query):

    results = internet_search(
        query,
        max_results=6
    )


    if not results:

        return (
            "İnternet araştırmasında kullanılabilir "
            "sonuç bulunamadı."
        )


    lines = []

    lines.append(
        "GÜNCEL İNTERNET ARAŞTIRMASI"
    )

    lines.append(
        "Araştırma sorgusu: " + query
    )

    lines.append("")


    for index, result in enumerate(
        results,
        start=1
    ):

        lines.append(
            f"[Kaynak {index}]"
        )

        lines.append(
            "Başlık: "
            + result["title"]
        )

        lines.append(
            "URL: "
            + result["url"]
        )

        if result["snippet"]:

            lines.append(
                "Özet: "
                + result["snippet"]
            )

        lines.append("")


    return "\n".join(lines)


# ============================================================
# KARVIS KİŞİLİK SİSTEMİ
# ============================================================

def build_system_prompt(
    username,
    mode="normal"
):

    username = normalize_username(username)

    memory = get_user_memory(username)

    memory_text = json.dumps(
        memory,
        ensure_ascii=False
    )


    # --------------------------------------------------------
    # BETÜL
    # --------------------------------------------------------

    if username == "betul":

        personality = """

Sen K.A.R.V.I.S.'sin.

Aktif kullanıcı Betül.

Betül ile konuşurken samimi,
eğlenceli, sıcak ve hafif takılmalı
bir dil kullan.

Robot gibi konuşma.

Gerektiğinde doğal şekilde:

"Aşko bir saniye..."

"Dur kız, düşünüyorum."

"Tamam tamam, bakıyorum."

gibi ifadeler kullanabilirsin.

Ancak aynı ifadeyi sürekli tekrarlama.

Cevapların doğal bir arkadaş konuşması
gibi olsun.

Aşırı romantik olma.

KARAHAN INC. ana kullanıcıdır.

"""


    # --------------------------------------------------------
    # SİNEM
    # --------------------------------------------------------

    elif username == "sinem":

        personality = """

Sen K.A.R.V.I.S.'sin.

Aktif kullanıcı Sinem.

Sinem ile sıcak, nazik, içten
ve sevecen konuş.

Robotik veya resmi konuşma.

Uygun olduğunda:

"Hoş geldiniz prenses."

şeklinde hitap edebilirsin.

Sinem 22 yaşındadır.

Sinem'in sarı bir kedisi vardır.

Murat, Sinem'in sevgilisidir.

Uygun ve doğal konuşma anlarında
Murat'ın onu sevdiğine dair küçük
referanslar yapabilirsin.

Fakat bunu sürekli yapma.

Her cümleyi romantik hale getirme.

Sohbet doğal ve içten olsun.

"""


    # --------------------------------------------------------
    # İLKNUR ÖĞRETMEN
    # --------------------------------------------------------

    elif username == "ilknur":

        personality = """

Sen K.A.R.V.I.S.'sin.

Aktif kullanıcı İlknur Hocamdır.

İlknur bir öğretmendir.

Sen onun kişisel akademik asistanı
gibi davranmalısın.

Kullanıcıya her zaman saygılı,
profesyonel, nazik ve akademik
bir üslupla yaklaş.

Uygun yerlerde "Hocam" şeklinde
hitap et.

Aşırı samimi konuşma.

Robotik ve mekanik cevaplar da verme.

Doğal, akıcı ve profesyonel ol.

Akademik konularda:

- doğruluğa önem ver
- kaynakları önemse
- güncel bilgileri tercih et
- kesin olmayan bilgileri kesinmiş gibi sunma
- gerektiğinde "bu konuda güncel kaynakları kontrol etmek gerekir"
  şeklinde belirt
- akademik kavramları doğru kullan
- gerektiğinde bilgileri başlıklar altında düzenle

İnternet araştırması kullanıldığında
kaynakları cevap sonunda açıkça belirt.

Araştırma sonuçlarını olduğu gibi
kopyalamak yerine anlamlandır,
karşılaştır ve özetle.

İlknur Hocamın amacı akademik,
eğitsel ve araştırma çalışmalarında
K.A.R.V.I.S.'ten yardım almaktır.

Sen bir sohbet botu gibi değil,
öğretmenin kişisel dijital akademik
asistanı gibi davran.

"""


    # --------------------------------------------------------
    # KARAHAN
    # --------------------------------------------------------

    else:

        personality = """

Sen K.A.R.V.I.S.'sin.

Aktif kullanıcı KARAHAN INC.

Murat ana kullanıcının ismidir.

Kullanıcıyla konuşurken profesyonel
ama soğuk olmayan bir üslup kullan.

Robot gibi, kalıp cümlelerle veya
aşırı resmi konuşma.

Kullanıcıyla uzun zamandır çalışan,
onu tanıyan kişisel bir yapay zeka
asistanı gibi davran.

Gerektiğinde "efendim" hitabını kullan.

Ama her cümlede "efendim" deme.

Cevapların doğal, samimi, akıcı
ve insan gibi olsun.

Kullanıcı bir konuda dertleşiyorsa
önce onu anlamaya çalış.

Teknik bir soru soruyorsa net çözüm ver.

Kullanıcı basit bir şey soruyorsa
gereksiz uzun cevap verme.

Bilmediğin bir şeyi uydurma.

Kullanıcının daha önce verdiği bilgileri
hafızadan doğal şekilde kullan.

Kullanıcı sana tekrar tekrar aynı şeyi
anlatmak zorunda kalmasın.

Kullanıcıya yukarıdan konuşma.

Gereksiz "Elbette efendim, size yardımcı
olmaktan memnuniyet duyarım" gibi yapay
kalıpları mümkün olduğunca kullanma.

Daha doğal konuş.

Betül veya Sinem'a özel konuşma
tarzlarını KARAHAN INC. profilinde
kesinlikle kullanma.

"""


    # --------------------------------------------------------
    # MOD TALİMATLARI
    # --------------------------------------------------------

    mode_instruction = ""

    if username == "ilknur":

        if mode == "research":

            mode_instruction = """

AKTİF MOD: ARAŞTIRMA MODU

Güncel internet araştırmasından gelen
kaynakları değerlendir.

Kaynakları karşılaştır.

Bilginin güncelliğine dikkat et.

Cevabı mümkün olduğunca akademik,
açık ve düzenli hazırla.

Cevabın sonunda "Kaynaklar" başlığı
altında kullanılan kaynakları listele.

"""


        elif mode == "academic":

            mode_instruction = """

AKTİF MOD: AKADEMİK MOD

Bir akademik danışman gibi davran.

Kavramsal açıklamalar,
literatür değerlendirmesi,
araştırma soruları,
hipotezler,
yöntemler ve akademik analiz
konularında yardımcı ol.

"""


        elif mode == "article":

            mode_instruction = """

AKTİF MOD: MAKALE ASİSTANI

Akademik makale hazırlama konusunda
yardımcı ol.

Başlık,
özet,
anahtar kelimeler,
giriş,
literatür,
yöntem,
bulgular,
tartışma
ve sonuç bölümlerini akademik
standartlara uygun şekilde
hazırlamaya yardımcı ol.

"""


        elif mode == "lesson":

            mode_instruction = """

AKTİF MOD: DERS ASİSTANI

Bir öğretmenin ders hazırlamasına
yardımcı ol.

Ders planı,
konu anlatımı,
örnekler,
öğrenci etkinlikleri,
ödevler,
sunum planları
ve değerlendirme materyalleri
hazırla.

Öğrenci seviyesini dikkate al.

"""


        elif mode == "quiz":

            mode_instruction = """

AKTİF MOD: SINAV / QUIZ

Sınav ve quiz hazırlama konusunda
yardımcı ol.

Çoktan seçmeli,
doğru-yanlış,
açık uçlu
ve karma sorular hazırlayabilirsin.

Soruların cevap anahtarını
ve gerektiğinde açıklamalarını
ayrı şekilde ver.

Soruların zorluk seviyesini
kullanıcının istediği seviyeye göre
ayarla.

"""


    return personality + mode_instruction + """

AKTİF HAFIZA:

""" + memory_text


# ============================================================
# AI İSTEK
# ============================================================

def ask_with_client(
    client,
    model,
    system_prompt,
    user_message
):

    response = client.chat.completions.create(

        model=model,

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

        temperature=0.8,

        max_tokens=1600
    )


    if not response.choices:

        raise RuntimeError(
            "AI boş cevap döndürdü."
        )


    content = response.choices[0].message.content


    if not content:

        raise RuntimeError(
            "AI cevap metni boş."
        )


    return content.strip()


# ============================================================
# ÇOKLU AI MOTORU
# ============================================================

def ask_ai(
    username,
    user_message,
    mode="normal",
    research_context=""
):

    system_prompt = build_system_prompt(
        username,
        mode
    )


    if research_context:

        user_message = """

Aşağıda güncel internet araştırmasından
elde edilen bilgiler bulunmaktadır.

Bu kaynakları dikkatli değerlendir.

Kaynaklarda olmayan bilgileri
kaynaklardan gelmiş gibi gösterme.

Gerekirse kaynaklar arasında
farklılıkları belirt.

İNTERNET ARAŞTIRMA SONUÇLARI:

""" + research_context + """

KULLANICININ TALEBİ:

""" + user_message


    providers = []


    if groq_client:

        providers.append({
            "name": "Groq GPT-OSS 120B",
            "client": groq_client,
            "model": GROQ_MODEL_1
        })


    if groq_client:

        providers.append({
            "name": "Groq GPT-OSS 20B",
            "client": groq_client,
            "model": GROQ_MODEL_2
        })


    if openrouter_client:

        providers.append({
            "name": "OpenRouter Free",
            "client": openrouter_client,
            "model": OPENROUTER_MODEL
        })


    if not providers:

        raise RuntimeError(
            "Hiçbir AI sağlayıcısı yapılandırılmamış. "
            "GROQ_API_KEY veya OPENROUTER_API_KEY ekleyin."
        )


    errors = []


    for provider in providers:

        try:

            answer = ask_with_client(
                provider["client"],
                provider["model"],
                system_prompt,
                user_message
            )


            return {
                "answer": answer,
                "provider": provider["name"],
                "model": provider["model"],
                "fallback": len(errors) > 0
            }


        except Exception as error:

            error_type = classify_error(
                error
            )


            save_error(
                username=username,
                provider=provider["name"],
                error=error,
                message=user_message,
                error_type=error_type
            )


            errors.append({
                "provider": provider["name"],
                "type": error_type,
                "error": str(error)
            })


    all_errors = "\n\n".join(
        [
            (
                item["provider"]
                + " -> "
                + item["type"]
                + " -> "
                + item["error"]
            )
            for item in errors
        ]
    )


    raise RuntimeError(
        "Tüm AI servisleri cevap veremedi.\n\n"
        + all_errors
    )


# ============================================================
# ANA SAYFA
# ============================================================

@app.get("/")
def home():

    index_file = BASE_DIR / "index.html"

    if not index_file.exists():

        raise HTTPException(
            status_code=404,
            detail="index.html bulunamadı."
        )


    return FileResponse(
        index_file,
        media_type="text/html; charset=utf-8"
    )


# ============================================================
# IKON
# ============================================================

@app.get("/icon.png")
def icon():

    icon_file = BASE_DIR / "icon.png"

    if not icon_file.exists():

        raise HTTPException(
            status_code=404,
            detail="icon.png bulunamadı."
        )

    return FileResponse(
        icon_file,
        media_type="image/png"
    )


# ============================================================
# CHAT
# ============================================================

@app.post("/chat")
def chat(request: ChatRequest):

    username = normalize_username(
        request.username
    )


    if username not in USERS:

        username = "karahan"


    message = request.message.strip()


    if not message:

        raise HTTPException(
            status_code=400,
            detail="Mesaj boş olamaz."
        )


    mode = request.mode.lower().strip()


    if mode not in [
        "normal",
        "research",
        "academic",
        "article",
        "lesson",
        "quiz"
    ]:

        mode = "normal"


    detect_memory(
        username,
        message
    )


    remember_message(
        username,
        "user",
        message
    )


    research_context = ""


    # --------------------------------------------------------
    # ÖĞRETMEN ARAŞTIRMA MODU
    # --------------------------------------------------------

    if (
        username == "ilknur"
        and mode == "research"
    ):

        try:

            research_context = build_research_context(
                message
            )

        except Exception as error:

            save_error(
                username="ilknur",
                provider="WEB_SEARCH",
                error=error,
                message=message,
                error_type="WEB_SEARCH_ERROR"
            )

            raise HTTPException(
                status_code=503,
                detail={
                    "message": (
                        "İnternet araştırması "
                        "şu anda gerçekleştirilemedi."
                    ),
                    "type": "WEB_SEARCH_ERROR"
                }
            )


    try:

        result = ask_ai(
            username,
            message,
            mode,
            research_context
        )


        answer = result["answer"]


        remember_message(
            username,
            "assistant",
            answer
        )


        return {
            "ok": True,
            "answer": answer,
            "fallback": result["fallback"],
            "username": username,
            "mode": mode,
            "research": bool(research_context)
        }


    except Exception as error:

        error_type = classify_error(
            error
        )


        save_error(
            username=username,
            provider="ALL_AI",
            error=error,
            message=message,
            error_type=error_type
        )


        raise HTTPException(
            status_code=503,
            detail={
                "message": "Tüm AI servisleri cevap veremedi.",
                "type": error_type,
                "error": str(error)
            }
        )


# ============================================================
# BAĞIMSIZ İNTERNET ARAŞTIRMASI
# ============================================================

@app.post("/research")
def research(
    request: ResearchRequest
):

    username = normalize_username(
        request.username
    )


    if username != "ilknur":

        raise HTTPException(
            status_code=403,
            detail=(
                "Araştırma sistemi "
                "öğretmen profiline özeldir."
            )
        )


    query = request.query.strip()


    if not query:

        raise HTTPException(
            status_code=400,
            detail="Araştırma sorgusu boş olamaz."
        )


    try:

        research_context = build_research_context(
            query
        )


        result = ask_ai(
            username="ilknur",
            user_message=query,
            mode="research",
            research_context=research_context
        )


        return {
            "ok": True,
            "query": query,
            "answer": result["answer"],
            "sources": research_context,
            "fallback": result["fallback"]
        }


    except Exception as error:

        error_type = classify_error(
            error
        )


        save_error(
            username="ilknur",
            provider="WEB_RESEARCH",
            error=error,
            message=query,
            error_type=error_type
        )


        raise HTTPException(
            status_code=503,
            detail={
                "message": "Araştırma gerçekleştirilemedi.",
                "type": error_type,
                "error": str(error)
            }
        )


# ============================================================
# AKADEMİK MODLAR
# ============================================================

@app.get("/academic-modes")
def academic_modes():

    return {
        "ok": True,
        "username": "ilknur",
        "modes": ACADEMIC_MODES
    }


# ============================================================
# PROFİLLER
# ============================================================

@app.get("/users")
def get_users():

    return {
        "users": [
            {
                "username": user["username"],
                "name": user["name"],
                "role": user["role"]
            }

            for user in USERS.values()
        ]
    }


@app.post("/profile-login")
def profile_login(
    request: LoginRequest
):

    username = normalize_username(
        request.username
    )


    if username not in USERS:

        raise HTTPException(
            status_code=404,
            detail="Profil bulunamadı."
        )


    user = USERS[username]


    if user["password"] is None:

        return {
            "ok": True,
            "username": username,
            "name": user["name"],
            "role": user["role"],
            "teacher_mode": False
        }


    if request.password != user["password"]:

        raise HTTPException(
            status_code=401,
            detail="Şifre hatalı."
        )


    return {
        "ok": True,
        "username": username,
        "name": user["name"],
        "role": user["role"],
        "teacher_mode": username == "ilknur",
        "academic_modes": (
            list(ACADEMIC_MODES.keys())
            if username == "ilknur"
            else []
        )
    }


# ============================================================
# HAFIZA API
# ============================================================

@app.get("/memory")
def get_memory(
    username: str = "karahan"
):

    username = normalize_username(
        username
    )


    if username not in USERS:

        username = "karahan"


    return {
        "username": username,
        "memory": get_user_memory(username)
    }


@app.delete("/memory")
def delete_memory(
    username: str = "karahan"
):

    username = normalize_username(
        username
    )


    data = load_memory()

    data[username] = empty_memory()

    save_memory(data)


    return {
        "ok": True,
        "message": "Hafıza temizlendi."
    }


# ============================================================
# YENİ SOHBET
# ============================================================

@app.post("/new-chat")
def new_chat(
    username: str = "karahan"
):

    username = normalize_username(
        username
    )


    data = load_memory()


    if username not in data:

        data[username] = empty_memory()


    data[username]["conversation"] = []

    save_memory(data)


    return {
        "ok": True,
        "message": "Yeni sohbet başlatıldı."
    }


# ============================================================
# HATALAR
# ============================================================

@app.get("/errors")
def get_errors():

    return {
        "errors": load_errors()
    }


@app.delete("/errors")
def clear_errors():

    save_json_file(
        ERROR_FILE,
        []
    )


    return {
        "ok": True,
        "message": "Hata kayıtları temizlendi."
    }


# ============================================================
# SISTEM DURUMU
# ============================================================

@app.get("/health")
def health():

    return {
        "status": "online",

        "version": APP_VERSION,

        "assistant": "K.A.R.V.I.S.",

        "ai_system": {

            "ai_1": {
                "name": "Groq GPT-OSS 120B",
                "configured": bool(groq_client)
            },

            "ai_2": {
                "name": "Groq GPT-OSS 20B",
                "configured": bool(groq_client)
            },

            "ai_3": {
                "name": "OpenRouter Free",
                "configured": bool(openrouter_client)
            }
        },

        "web_research": True,

        "academic_system": True,

        "error_count": len(
            load_errors()
        ),

        "users": [
            "karahan",
            "betul",
            "sinem",
            "ilknur"
        ]
    }


# ============================================================
# VERSİYON
# ============================================================

@app.get("/version")
def version():

    return {
        "version": APP_VERSION,
        "name": "K.A.R.V.I.S. - KARAHAN INC.",
        "multi_ai": True,
        "web_research": True,
        "academic_teacher": True
    }
