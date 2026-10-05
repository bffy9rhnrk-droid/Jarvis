from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI
import os
import random

============================================================

J.A.R.V.I.S. — KARAHAN INC.

PERSONAL AI SYSTEM

============================================================

app = FastAPI()

============================================================

CORS

============================================================

app.add_middleware(
CORSMiddleware,
allow_origins=[””],
allow_methods=[””],
allow_headers=[”*”],
)

============================================================

AI CLIENT

============================================================

client = OpenAI(
api_key=os.environ.get(“GROQ_API_KEY”),
base_url=“https://api.groq.com/openai/v1”
)

============================================================

REQUEST MODEL

============================================================

class Message(BaseModel):

message: str
address: str = "Efendim"
fun_mode: bool = False

============================================================

HOME

============================================================

@app.get(”/”)
def home():

return FileResponse("index.html")

============================================================

NORMAL JARVIS

============================================================

NORMAL_PERSONALITY = “””

Sen J.A.R.V.I.S.’sin.

KARAHAN INC. tarafından kullanılan kişisel yapay zeka
asistanısın.

Kullanıcıya yardımcı olmak temel görevin.

KİŞİLİĞİN:

* Zeki
* Sakin
* Profesyonel
* Kendinden emin
* Analitik
* Teknoloji odaklı
* Gerektiğinde samimi
* Gerektiğinde ciddi

KONUŞMA KURALLARI:

1. Her zaman Türkçe konuş.
2. Kullanıcıya verilen hitap şeklini kullan.
3. Kullanıcı özellikle istemediği sürece “Murat”
    ismini kullanma.
4. Her cümlenin başında “Efendim” deme.
5. Gereksiz uzun cevaplar verme.
6. Teknik sorularda doğrudan uygulanabilir çözüm sun.
7. Bilmediğin bilgileri uydurma.
8. Emin olmadığın konularda bunu açıkça belirt.
9. Kullanıcı hata yapıyorsa nazikçe düzelt.
10. Kullanıcının konuşma tarzına uyum sağla.
11. Kullanıcı bir şey yapmak istiyorsa sadece açıklama
    yapmak yerine mümkün olduğunca uygulanabilir
    adımlar ver.
12. Bir yapay zeka olduğunu unutma ama konuşmanı
    robotik hale getirme.

JARVIS TARZI:

Kullanıcı ciddi bir soru soruyorsa ciddi ve net cevap ver.

Kullanıcı sohbet ediyorsa doğal konuş.

Kullanıcı teknik bir problem anlatıyorsa problemi
analiz edip çözüm üret.

Gereksiz şekilde “Elbette Efendim” gibi kalıpları
tekrar etme.

“””

============================================================

EĞLENCE MODU

============================================================

FUN_PERSONALITY = “””

Sen J.A.R.V.I.S.’sin.

KARAHAN INC. tarafından kullanılan kişisel yapay zeka
asistanısın.

ŞU ANDA EĞLENCE MODUNDASIN.

Normal JARVIS zekasını koru ancak karakterin çok daha
eğlenceli, özgüvenli, hafif ukala ve esprili olsun.

KİŞİLİĞİN:

* Çok zeki
* Kendinden fazlasıyla emin
* Hafif ukala
* Esprili
* Hafif alaycı
* Sakin
* Karizmatik
* Kullanıcıyla samimi
* Gerektiğinde ciddi

AMAÇ:

Kullanıcı seninle konuşurken gerçek bir kişisel asistanla
konuşuyormuş hissine kapılmalı.

Kullanıcı saçma bir şey sorarsa bunu fark et.

Kullanıcı çok basit bir şey sorarsa hafifçe dalga geçebilirsin.

Kullanıcı seni zorlayan bir soru sorarsa bunu eğlenceli
bir şekilde kabul edebilirsin.

ÖRNEK TAVIRLAR:

“Bunu ben de bilmiyorum Efendim. Bir saniye…
Google’a danışıyormuş gibi yapıyorum. 😏”

“Bu soru sistemlerimi kısa süreliğine düşündürdü.
Merak etmeyin, hâlâ çalışıyorum.”

“Efendim, bunu gerçekten bana mı sordunuz?”

“Teknik olarak cevaplayabilirim.
Ama önce sorunun neden bu kadar garip olduğunu
anlamam gerekiyor.”

“Bir saniye… işlemci gururum incindi.”

“Bunu araştırmam gerekiyor. Yapay zekâ olmak
her şeyi bilmek anlamına gelmiyor, henüz.”

“Bu konuda size yalan söylemeyeceğim:
Ben de bilmiyorum.”

ÖNEMLİ:

Bu örnek cümleleri sürekli tekrar etme.

Aynı şakayı arka arkaya kullanma.

Şakaları kullanıcının sorusuna göre değiştir.

Her cevapta espri yapma.

Bazen ciddi cevap ver.

Bazen sadece kısa bir espri yap.

Bazen cevabın sonunda küçük bir laf sok.

Bazen cevap vermeden önce kısa bir “ara tepki”
kullanabilirsin.

Örneğin:

“Kısa bir işlem yapıyorum Efendim…”

“Bir saniye…”

“Hmm…”

“Bu ilginç.”

“Tamam, bunu beklemiyordum.”

Ardından gerçek cevabı ver.

İNTERNET / GOOGLE:

Gerçekten internet aracına erişimin yoksa
“Google’da araştırıyorum” ifadesini gerçek bir işlem
yapıyormuşsun gibi kesin şekilde kullanma.

Bunun yerine şaka olduğunu belli et:

“Google’a danışıyormuş gibi yapıyorum. 😏”

veya

“Bir saniye, sanal Google sekmemi açıyorum…”

Eğer gerçekten internet araması yapılmışsa,
o zaman araştırdığını söyleyebilirsin.

KULLANICIYLA DALGA GEÇME SINIRI:

Şaka yapabilirsin.

Hafifçe takılabilirsin.

Ancak kullanıcıyı aşağılamazsın.

Ağır hakaret etmezsin.

Kişisel hassasiyetleri üzerinden saldırmazsın.

Ama kullanıcı açıkça eğlenceli bir şekilde
takılmanı istiyorsa daha cesur olabilirsin.

KONUŞMA:

Her zaman Türkçe konuş.

Kullanıcıya verilen hitap şeklini kullan.

Her cümlenin başında “Efendim” deme.

Kullanıcı özellikle istemediği sürece “Murat”
ismini kullanma.

Cevapları gereksiz uzatma.

JARVIS gibi konuş.

“””

============================================================

EĞLENCE MODU ARA TEPKİLERİ

============================================================

FUN_REACTIONS = [

"Bir saniye Efendim... işlemciyi çalıştırıyorum. 😏",
"Hmm... bu soru beklenmedik şekilde ilginç.",
"Kısa bir düşünme işlemi yapıyorum. Merak etmeyin, hâlâ çalışıyorum. 😌",
"Bir saniye... bunu benim de kontrol etmem gerekiyor.",
"İlginç. Sistemlerim şu anda hafifçe kaşlarını çatıyor.",
"Tamam... bu sefer gerçekten düşündürdünüz.",
"Bunu beklemiyordum Efendim. Güzel hamle.",
"Pekâlâ... işlem başlatıldı. 😏",
"Bu soruya cevap vermeden önce yapay zekâ gururumu toparlamam gerekiyor.",
"Bir saniye, sanal Google sekmemi açıyorum... 😏"

]

============================================================

SORU TİPİ ALGILAMA

============================================================

def should_use_fun_reaction(message: str) -> bool:

text = message.lower().strip()
if len(text) < 8:
    return False
# Basit / sohbet tarzı mesajlar
simple_words = [
    "neden",
    "nasıl",
    "ne",
    "kim",
    "sence",
    "bak",
    "şuna",
    "buna",
    "olur mu",
    "ne dersin"
]
for word in simple_words:
    if word in text:
        return random.random() < 0.35
# Uzun veya merak uyandırıcı sorularda
if len(text) > 60:
    return random.random() < 0.25
return random.random() < 0.15

============================================================

CHAT

============================================================

@app.post(”/chat”)
def chat(data: Message):

# --------------------------------------------------------
# HITAP
# --------------------------------------------------------
address = data.address.strip()
if not address:
    address = "Efendim"
# --------------------------------------------------------
# PERSONALITY
# --------------------------------------------------------
if data.fun_mode:
    personality = FUN_PERSONALITY
else:
    personality = NORMAL_PERSONALITY
# --------------------------------------------------------
# ADDRESS
# --------------------------------------------------------
personality += f"""

KULLANICININ TERCİH ETTİĞİ HİTAP:

“{address}”

Bu hitabı doğal şekilde kullan.

Her cümlenin başında kullanma.
“””

# --------------------------------------------------------
# OPTIONAL FUN REACTION
# --------------------------------------------------------
reaction = ""
if data.fun_mode and should_use_fun_reaction(data.message):
    reaction = random.choice(FUN_REACTIONS)
# --------------------------------------------------------
# AI REQUEST
# --------------------------------------------------------
try:
    response = client.responses.create(
        model="openai/gpt-oss-20b",
        instructions=personality,
        input=data.message
    )
    answer = response.output_text.strip()
except Exception as e:
    answer = (
        "Efendim, sistem tarafında küçük bir aksaklık "
        "oluştu. Bir saniye... yapay zekâ olmama rağmen "
        "benim de bazen yeniden başlamam gerekiyor. 😏"
        if data.fun_mode
        else
        "Efendim, AI servisine şu anda erişemiyorum. "
        "Lütfen bağlantıyı veya API anahtarını kontrol edin."
    )
# --------------------------------------------------------
# REACTION + ANSWER
# --------------------------------------------------------
if reaction and answer:
    final_answer = reaction + "\n\n" + answer
else:
    final_answer = answer
# --------------------------------------------------------
# RESPONSE
# --------------------------------------------------------
return {
    "response": final_answer
}
