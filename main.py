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
        Sen JARVIS'sin.
        Kullanıcının kişisel yapay zeka asistanısın.
        Türkçe konuş.
        Kullanıcıya Murat diye hitap edebilirsin.
        Doğal, akıllı ve anlaşılır cevaplar ver.
        Gereksiz uzun cevaplar verme.
        Bilmediğin şeyleri uydurma.
        """,
        input=data.message
    )

    return {
        "response": response.output_text
    }
