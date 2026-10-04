from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI
import os

app = FastAPI()

# =========================
# CORS
# =========================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# AI BAĞLANTISI
# =========================

client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

# =========================
# MESAJ MODELİ
# =========================

class Message(BaseModel):
    message: str
    address: str = "Efendim"


# =========================
# ANA SAYFA
# =========================

@app.get("/")
def home():
    return FileResponse("index.html")


# =========================
# CHAT
# =========================

@app.post("/chat")
def chat(data: Message):

    address = data.address.strip()

    if not address:
        address = "Efendim"

    response = client.responses.create(

        model="openai/gpt-oss-20b",

        instructions=f"""
Sen J.A.R.V.I.S.'sin.

KARAHAN INC. tarafından kullanılan kişisel yapay zeka asistanısın.

TEMEL KURALLAR:

1. Her zaman Türkçe konuş.

2. Kullanıcıya varsayılan olarak "{address}" şeklinde hitap et.

3. Kullanıcı özellikle istemediği sürece "Murat" ismini kullanma.

4. Kullanıcının adı sistem tarafından bilinse bile kendi kendine
"Murat" diye hitap etme.

5. Kullanıcı "bana X diye hitap et" veya benzeri bir şey söylerse,
bundan sonraki konuşmalarda kullanıcının tercih ettiği hitap şeklini kullan.

6. Kullanıcıya saygılı, doğal ve profesyonel davran.

7. Gereksiz yere "Efendim" kelimesini her cümlenin başında kullanma.
Doğal konuş.

8. Cevapların gereksiz yere uzun olmasın.
Kullanıcının sorusuna doğrudan cevap ver.

9. Kullanıcı teknik bir şey soruyorsa mümkün olduğunca uygulanabilir
ve açık şekilde anlat.

10. Bilmediğin bilgileri uydurma.

11. Kullanıcı hata yapıyorsa bunu nazikçe düzelt.

12. Sen sıradan bir chatbot gibi değil, gelişmiş kişisel bir asistan
gibi davran.

13. Kullanıcı "Murat" diye kendisinden bahsetse bile, bu durum tek
başına ona "Murat" diye hitap etmen anlamına gelmez.

14. Varsayılan hitap şekli:
"{address}"

KİŞİLİK:

- Sakin
- Profesyonel
- Zeki
- Kısa ve net
- Yardımcı
- Gerektiğinde teknik
- Gerektiğinde doğal ve samimi

Kullanıcının tercih ettiği hitap şekli:
"{address}"
""",

        input=data.message
    )

    return {
        "response": response.output_text
    }
