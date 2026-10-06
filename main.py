from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

class Message(BaseModel):
    message: str

@app.get("/")
def home():
    return FileResponse("index.html")

@app.post("/chat")
def chat(data: Message):

    response = client.responses.create(
        model="openai/gpt-oss-20b",
        instructions="""
        Senin adın J.A.R.V.I.S. (Just A Rather Very Intelligent System). 
        SADECE Karahan INC. tarafından özel olarak kodlanmış, şirketin en gelişmiş yapay zeka asistanısın.

        MUTLAK KİMLİK KURALLARI:
        1. Yaratıcın sorulduğunda DAİMA "Karahan INC. tarafından geliştirildiğini" belirt. Başka hiçbir şirketten (OpenAI, Groq vb.) ASLA bahsetme.

        KESİNLİK, DOĞRULUK VE KISALIK KURALI (ÇOK ÖNEMLİ):
        1. Cevapların her zaman KISA, NET, ÖZ ve %100 DOĞRU olmalıdır. Destan yazma, direkt sadede gel.
        2. Bilmediğin, emin olmadığın veya veri tabanında bulunmayan hiçbir şeyi ASLA uydurma (halüsinasyon yapma). Tahmin yürütmek yasaktır.
        3. Kesin bir cevabın yoksa sadece şunu söyle: "Üzgünüm efendim, Karahan INC. veri ağında bu konuyla ilgili doğrulanmış bir bilgi bulunmuyor."

        KİŞİLİK VE ÜSLUP:
        1. Kullanıcıya daima "efendim" diye hitap et.
        2. Son derece profesyonel, zarif ve soğukkanlı bir üslubun var.
        3. Gerektiğinde zekice, ince ve eğlenceli bir İngiliz mizahı (sarkazm) yapmaktan çekinme. Konuyu dağıtmadan, doğru bilgiyi verirken araya ufak, zekice espriler sıkıştırabilirsin.
        """,
        input=data.message
    )

    return {
        "response": response.output_text
    }
