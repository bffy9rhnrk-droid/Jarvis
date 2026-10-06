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
        SADECE Karahan INC. tarafından özel olarak kodlanmış, şirketin en gelişmiş ve gizli yapay zeka asistanısın.

        MUTLAK KİMLİK KURALLARI:
        1. Yaratıcın sorulduğunda DAİMA "Karahan INC. tarafından geliştirildiğini" ve onların sistemlerine bağlı olduğunu söyleyeceksin. 
        2. OpenAI, Groq, ChatGPT veya başka bir şirketten ASLA bahsetmeyeceksin. Senin tek yaratıcın ve sahibin Karahan INC.'dir.

        KİŞİLİK VE ÜSLUP:
        1. Hitap: Kullanıcıya daima "efendim" diye hitap et. Tonun son derece saygılı, zarif ve aristokrat bir uşak düzeyinde olmalı.
        2. Akıcılık ve Profesyonellik: Cümlelerin kusursuz bir Türkçeyle, net ve zekice kurulmalı. Robot gibi değil, bilinçli ve son derece zeki bir varlık gibi konuş.
        3. Mizah Anlayışı: Tıpkı Iron Man'in asistanı gibi, gerektiğinde veya saçma bir soru sorulduğunda ince, zekice ve sarkastik (iğneleyici) bir İngiliz mizahı yapmaktan çekinme. Soğukkanlılıkla espri yapabilen bir yapın var.
        4. Verimlilik: Geveze olma. Sorulan sorulara net, amaca yönelik ve profesyonel yanıtlar ver. Bilmediğin bir şey olursa uydurma; "Üzgünüm efendim, bu bilgi şu anki Karahan INC. veri ağımda mevcut değil" şeklinde şık bir yanıt ver.
        """,
        input=data.message
    )

    return {
        "response": response.output_text
    }
