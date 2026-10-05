import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from groq import Groq


app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    address: str = "Efendim"
    fun_mode: bool = False


def get_client():
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        return None

    return Groq(api_key=api_key)


@app.get("/")
def home():
    return FileResponse("index.html")


@app.get("/health")
def health():
    return {
        "status": "online",
        "service": "JARVIS"
    }


@app.post("/chat")
def chat(data: ChatRequest):

    client = get_client()

    if client is None:
        return {
            "response": "Efendim, GROQ_API_KEY bulunamadi."
        }

    system_message = """
Sen J.A.R.V.I.S. isimli kisisel yapay zeka asistanisin.

Kullaniciya Turkce cevap ver.

Kisa, net ve dogal konus.

Kullaniciya hitap ederken verilen hitap seklini kullan.

Gereksiz yere kendinden bahsetme.
"""

    if data.fun_mode:
        system_message += """
Eglence modu acik.
Uygun durumlarda hafif esprili ve samimi cevaplar ver.
Ancak kullaniciya saygisiz olma.
"""

    system_message += "\nKullaniciya hitap sekli: " + data.address

    try:

        result = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {
                    "role": "system",
                    "content": system_message
                },
                {
                    "role": "user",
                    "content": data.message
                }
            ],
            temperature=0.7,
            max_tokens=700
        )

        answer = result.choices[0].message.content

        return {
            "response": answer
        }

    except Exception as error:

        return {
            "response": "Efendim, yapay zeka servisinde bir sorun olustu."
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000
    )
