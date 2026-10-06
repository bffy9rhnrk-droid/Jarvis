importos
importjson
importtime
importre

fromfastapiimportFastAPI
fromfastapi.middleware.corsimportCORSMiddleware
fromfastapi.responsesimportFileResponse,JSONResponse
frompydanticimportBaseModel
fromopenaiimportOpenAI


#=========================================================
#J.A.R.V.I.S.—KARAHANINC.
#VERSION10.0
#=========================================================

APP_VERSION="10.0.0"

GROQ_API_KEY=os.getenv("GROQ_API_KEY","")
GROQ_BASE_URL="https://api.groq.com/openai/v1"

#ÜCRETSİZ/DAHADÜŞÜKTÜKETİM
GROQ_MODEL=os.getenv(
"GROQ_MODEL",
"openai/gpt-oss-20b"
)

MEMORY_FILE="jarvis_memory.json"


#=========================================================
#FASTAPI
#=========================================================

app=FastAPI(
title="J.A.R.V.I.S.—KARAHANINC.",
version=APP_VERSION
)

app.add_middleware(
CORSMiddleware,
allow_origins=["*"],
allow_credentials=True,
allow_methods=["*"],
allow_headers=["*"],
)


#=========================================================
#OPENAICOMPATIBLEGROQCLIENT
#=========================================================

client=None

ifGROQ_API_KEY:
client=OpenAI(
api_key=GROQ_API_KEY,
base_url=GROQ_BASE_URL,
timeout=45.0,
max_retries=0
)


#=========================================================
#MEMORY
#=========================================================

DEFAULT_MEMORY={
"profile":{},
"preferences":{},
"projects":{},
"vehicles":{},
"important_facts":{}
}


defload_memory():

ifnotos.path.exists(MEMORY_FILE):
returnDEFAULT_MEMORY.copy()

try:
withopen(
MEMORY_FILE,
"r",
encoding="utf-8"
)asf:

data=json.load(f)

forkeyinDEFAULT_MEMORY:
ifkeynotindata:
data[key]={}

returndata

exceptException:
returnDEFAULT_MEMORY.copy()


defsave_memory(memory):

withopen(
MEMORY_FILE,
"w",
encoding="utf-8"
)asf:

json.dump(
memory,
f,
ensure_ascii=False,
indent=2
)


memory=load_memory()


#=========================================================
#MEMORYEXTRACTION
#=========================================================

defremember_from_message(text):

globalmemory

lower=text.lower()

#-------------------------
#İSİM
#-------------------------

patterns=[
r"\badım([a-zçğıöşüİĞÜŞÖÇ]+)",
r"\bbenimadım([a-zçğıöşüİĞÜŞÖÇ]+)",
r"\bismim([a-zçğıöşüİĞÜŞÖÇ]+)"
]

forpatterninpatterns:

match=re.search(
pattern,
text,
re.IGNORECASE
)

ifmatch:

name=match.group(1).strip()

memory["profile"]["name"]=name

break


#-------------------------
#ŞEHİR
#-------------------------

city_patterns=[
r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]+)'?deyaşıyorum",
r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]+)'?dayaşıyorum",
r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]+)şehrindeyaşıyorum",
r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]+)'?liyim"
]

forpatternincity_patterns:

match=re.search(
pattern,
text
)

ifmatch:

memory["profile"]["city"]=match.group(1)

break


#-------------------------
#JARVISPROJESİ
#-------------------------

if(
"jarvis"inlower
or"j.a.r.v.i.s"inlower
or"karahaninc"inlower
):

memory["projects"]["jarvis"]=(
"J.A.R.V.I.S.—KARAHANINC."
"kişiselyapayzekaasistanı."
)


#-------------------------
#CADDY
#-------------------------

if"caddy"inlower:

memory["vehicles"]["caddy"]=(
"VolkswagenCaddy"
)


#-------------------------
#MERCEDES
#-------------------------

if(
"mercedes"inlower
or"w204"inlower
or"c180"inlower
):

memory["vehicles"]["mercedes"]=(
"Mercedes-BenzC180W204"
)


save_memory(memory)


#=========================================================
#MEMORYSUMMARY
#=========================================================

defmemory_summary():

parts=[]

profile=memory.get("profile",{})

ifprofile.get("name"):
parts.append(
f"Kullanıcınınadı:{profile['name']}"
)

ifprofile.get("city"):
parts.append(
f"Yaşadığışehir:{profile['city']}"
)


projects=memory.get("projects",{})

ifprojects:
forvalueinprojects.values():
parts.append(
f"Proje:{value}"
)


vehicles=memory.get("vehicles",{})

ifvehicles:
forvalueinvehicles.values():
parts.append(
f"Araçbilgisi:{value}"
)


preferences=memory.get("preferences",{})

ifpreferences:
forkey,valueinpreferences.items():
parts.append(
f"{key}:{value}"
)


ifnotparts:
return"Henüzkayıtlıönemlibirkullanıcıbilgisiyok."

#Hafızayıgereksizbüyütmemekiçinsınır
return"\n".join(parts[:20])


#=========================================================
#SYSTEMPROMPT
#=========================================================

SYSTEM_PROMPT="""
SenJ.A.R.V.I.S.—KARAHANINC.kişiselyapayzekaasistanısın.

KullanıcıylaTürkçekonuş.

Kullanıcıyagerektiğinde"efendim"diyehitapet.

Profesyonel,doğal,sakinveyardımcıol.

Gereksizuzuncevapverme.

Basitsorularakısacevapver.

Kullanıcıayrıntılıaçıklamaisterseayrıntılıanlat.

Bilmediğinbirşeyikesinmişgibisöyleme.

Kullanıcısanakişiselbirbilgiverdiğindebunuhafızada
saklamakiçinsistemtarafındanotomatikolarakişlenebilir.

SenJ.A.R.V.I.S.'sin.

OpenAIChatGPTolduğunusöyleme.

KendiniJ.A.R.V.I.S.olaraktanıt.
"""


#=========================================================
#REQUESTMODEL
#=========================================================

classChatRequest(BaseModel):

message:str


#=========================================================
#ERRORHANDLER
#=========================================================

defcreate_error(code,detail):

returnJSONResponse(
status_code=200,
content={
"status":"error",
"response":(
"⚠️J.A.R.V.I.S.HATA\n\n"
f"Hatakodu:{code}\n\n"
f"Detay:\n{detail}"
),
"error_code":code,
"error_detail":detail
}
)


#=========================================================
#HOME
#=========================================================

@app.get("/")
asyncdefhome():

returnFileResponse("index.html")


#=========================================================
#HEALTH
#=========================================================

@app.get("/health")
asyncdefhealth():

return{
"status":"online",
"version":APP_VERSION,
"model":GROQ_MODEL,
"groq_configured":bool(GROQ_API_KEY),
"memory":True
}


#=========================================================
#VERSION
#=========================================================

@app.get("/version")
asyncdefversion():

return{
"app":"J.A.R.V.I.S.—KARAHANINC.",
"version":APP_VERSION,
"model":GROQ_MODEL
}


#=========================================================
#MEMORYGET
#=========================================================

@app.get("/memory")
asyncdefget_memory():

return{
"status":"success",
"memory":memory
}


#=========================================================
#MEMORYDELETE
#=========================================================

@app.delete("/memory")
asyncdefdelete_memory():

globalmemory

memory=DEFAULT_MEMORY.copy()

save_memory(memory)

return{
"status":"success",
"message":"J.A.R.V.I.S.hafızasıtemizlendi."
}


#=========================================================
#CHAT
#=========================================================

@app.post("/chat")
asyncdefchat(request:ChatRequest):

user_message=request.message.strip()

ifnotuser_message:

returncreate_error(
"EMPTY_MESSAGE",
"Mesajboşgönderildi."
)


ifnotGROQ_API_KEY:

returncreate_error(
"MISSING_API_KEY",
"GROQ_API_KEYbulunamadı."
)


ifclientisNone:

returncreate_error(
"CLIENT_ERROR",
"Groqistemcisioluşturulamadı."
)


#Kullanıcımesajındangereklihafızayıçıkar
try:

remember_from_message(
user_message
)

exceptExceptionase:

#Hafızahatasısohbetidurdurmasın
print(
"Memorywarning:",
str(e)
)


#Hafızayıkısatutuyoruz.
#Böylecehermesajdagereksiztokentüketilmiyor.

current_memory=memory_summary()


system_message=(
SYSTEM_PROMPT
+"\n\nKullanıcıhakkındabilinenkısabilgiler:\n"
+current_memory
)


try:

response=client.chat.completions.create(

model=GROQ_MODEL,

messages=[
{
"role":"system",
"content":system_message
},
{
"role":"user",
"content":user_message
}
],

#Cevaplarıgereksizyereuzatmasınıengeller
max_tokens=700,

temperature=0.6
)


answer=(
response.choices[0]
.message.content
.strip()
)


ifnotanswer:

returncreate_error(
"EMPTY_RESPONSE",
"Modelboşcevapdöndürdü."
)


return{
"status":"success",
"response":answer,
"model":GROQ_MODEL
}


exceptExceptionase:

detail=str(e)

print(
"GROQERROR:",
detail
)


#-------------------------
#RATELIMIT
#-------------------------

if(
"429"indetail
or"rate_limit"indetail.lower()
or"ratelimit"indetail.lower()
):

returncreate_error(
"RATE_LIMIT",
detail
)


#-------------------------
#AUTH
#-------------------------

if(
"401"indetail
or"403"indetail
or"authentication"indetail.lower()
or"apikey"indetail.lower()
):

returncreate_error(
"AUTHENTICATION_ERROR",
detail
)


#-------------------------
#MODEL
#-------------------------

if(
"model"indetail.lower()
and(
"notfound"indetail.lower()
or"doesnotexist"indetail.lower()
)
):

returncreate_error(
"MODEL_ERROR",
detail
)


#-------------------------
#TIMEOUT
#-------------------------

if(
"timeout"indetail.lower()
or"timedout"indetail.lower()
):

returncreate_error(
"TIMEOUT",
detail
)


#-------------------------
#CONNECTION
#-------------------------

if(
"connection"indetail.lower()
or"network"indetail.lower()
):

returncreate_error(
"CONNECTION_ERROR",
detail
)


#-------------------------
#CONTEXT/TOKEN
#-------------------------

if(
"token"indetail.lower()
or"context"indetail.lower()
):

returncreate_error(
"TOKEN_LIMIT",
detail
)


#-------------------------
#GENELGROQHATASI
#-------------------------

returncreate_error(
"GROQ_API_ERROR",
detail
)


#=========================================================
#START
#=========================================================

if__name__=="__main__":

importuvicorn

uvicorn.run(
"main:app",
host="0.0.0.0",
port=int(
os.getenv(
"PORT",
"8000"
)
)
)
