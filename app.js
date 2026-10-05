"use strict";


/* =====================================================
   STORAGE
===================================================== */

const STORAGE = {
    address: "jarvis_address",
    fun: "jarvis_fun",
    scale: "jarvis_scale"
};


let address =
    localStorage.getItem(STORAGE.address) || "Efendim";

let funMode =
    localStorage.getItem(STORAGE.fun) === "true";

let scale =
    Number(
        localStorage.getItem(STORAGE.scale) || 100
    );


/* =====================================================
   ELEMENTLER
===================================================== */

const sidebar =
    document.getElementById("sidebar");

const openSidebar =
    document.getElementById("openSidebar");

const closeSidebar =
    document.getElementById("closeSidebar");

const pages = {
    home: document.getElementById("homePage"),
    chat: document.getElementById("chatPage"),
    settings: document.getElementById("settingsPage")
};

const navItems =
    document.querySelectorAll(".nav-item");

const startChat =
    document.getElementById("startChat");

const chatMessages =
    document.getElementById("chatMessages");

const input =
    document.getElementById("messageInput");

const sendButton =
    document.getElementById("sendButton");

const micButton =
    document.getElementById("micButton");

const addressInput =
    document.getElementById("addressInput");

const funToggle =
    document.getElementById("funToggle");

const scaleRange =
    document.getElementById("scaleRange");

const scaleValue =
    document.getElementById("scaleValue");


/* =====================================================
   AYARLARI YÜKLE
===================================================== */

addressInput.value = address;

scaleRange.value = scale;

scaleValue.textContent =
    scale + "%";


if (funMode) {
    funToggle.classList.add("active");
}


/* =====================================================
   SIDEBAR
===================================================== */

openSidebar.addEventListener(
    "click",
    function () {

        sidebar.classList.add("open");

    }
);


closeSidebar.addEventListener(
    "click",
    function () {

        sidebar.classList.remove("open");

    }
);


/* =====================================================
   SAYFA DEĞİŞTİR
===================================================== */

function showPage(pageName) {

    Object.values(pages).forEach(
        page => page.classList.remove("active-page")
    );


    if (pages[pageName]) {

        pages[pageName]
            .classList.add("active-page");

    }


    navItems.forEach(item => {

        item.classList.toggle(
            "active",
            item.dataset.page === pageName
        );

    });


    sidebar.classList.remove("open");


    if (pageName === "chat") {

        setTimeout(
            () => input.focus(),
            250
        );

    }

}


navItems.forEach(item => {

    item.addEventListener(
        "click",
        function () {

            showPage(
                this.dataset.page
            );

        }
    );

});


/* =====================================================
   ANA EKRANDAN CHAT
===================================================== */

startChat.addEventListener(
    "click",
    function () {

        showPage("chat");

    }
);


/* =====================================================
   HITAP
===================================================== */

addressInput.addEventListener(
    "input",
    function () {

        address =
            this.value.trim() || "Efendim";

        localStorage.setItem(
            STORAGE.address,
            address
        );

    }
);


/* =====================================================
   EĞLENCE MODU
===================================================== */

funToggle.addEventListener(
    "click",
    function () {

        funMode = !funMode;

        this.classList.toggle(
            "active",
            funMode
        );

        localStorage.setItem(
            STORAGE.fun,
            String(funMode)
        );

    }
);


/* =====================================================
   ÖLÇEK
===================================================== */

scaleRange.addEventListener(
    "input",
    function () {

        scale = Number(this.value);

        scaleValue.textContent =
            scale + "%";

        document.documentElement
            .style
            .setProperty(
                "--scale",
                scale / 100
            );

        localStorage.setItem(
            STORAGE.scale,
            String(scale)
        );

    }
);


/* =====================================================
   MESAJ
===================================================== */

function addMessage(text, type) {

    const wrapper =
        document.createElement("div");

    wrapper.className =
        "message " + type;


    const head =
        document.createElement("div");

    head.className =
        "message-head";

    head.textContent =
        type === "user"
            ? "YOU"
            : "J.A.R.V.I.S.";


    const body =
        document.createElement("div");

    body.className =
        "message-body";

    body.textContent =
        text;


    wrapper.appendChild(head);
    wrapper.appendChild(body);


    chatMessages.appendChild(wrapper);


    chatMessages.scrollTop =
        chatMessages.scrollHeight;


    return wrapper;
}


/* =====================================================
   DÜŞÜNÜYOR
===================================================== */

function showThinking() {

    const element =
        document.createElement("div");

    element.className =
        "message assistant";

    element.id =
        "thinking";


    element.innerHTML = `
        <div class="message-head">
            J.A.R.V.I.S.
        </div>

        <div class="message-body">
            Sistem yanıt hazırlıyor...
        </div>
    `;


    chatMessages.appendChild(element);


    chatMessages.scrollTop =
        chatMessages.scrollHeight;

}


/* =====================================================
   CHAT API
===================================================== */

async function sendMessage() {

    const text =
        input.value.trim();


    if (!text) {
        return;
    }


    addMessage(
        text,
        "user"
    );


    input.value = "";


    showThinking();


    sendButton.disabled = true;


    try {

        const response =
            await fetch(
                "/chat",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            message: text,

                            address: address,

                            fun_mode: funMode

                        })
                }
            );


        if (!response.ok) {

            throw new Error(
                "API bağlantısı başarısız."
            );

        }


        const data =
            await response.json();


        const thinking =
            document.getElementById(
                "thinking"
            );


        if (thinking) {
            thinking.remove();
        }


        addMessage(
            data.response ||
            "Yanıt alınamadı.",
            "assistant"
        );


    } catch (error) {

        const thinking =
            document.getElementById(
                "thinking"
            );


        if (thinking) {
            thinking.remove();
        }


        addMessage(
            "JARVIS sunucusuna bağlanılamadı.",
            "assistant"
        );


        console.error(error);

    } finally {

        sendButton.disabled =
            false;

        input.focus();

    }

}


/* =====================================================
   GÖNDER
===================================================== */

sendButton.addEventListener(
    "click",
    sendMessage
);


/* =====================================================
   ENTER
===================================================== */

input.addEventListener(
    "keydown",
    function (event) {

        if (event.key === "Enter") {

            event.preventDefault();

            sendMessage();

        }

    }
);


/* =====================================================
   SAFARI SPEECH RECOGNITION
===================================================== */

const SpeechRecognition =
    window.SpeechRecognition ||
    window.webkitSpeechRecognition;


let recognition = null;


if (SpeechRecognition) {

    recognition =
        new SpeechRecognition();


    recognition.lang =
        "tr-TR";


    recognition.continuous =
        false;


    recognition.interimResults =
        false;


    recognition.onstart =
        function () {

            micButton.textContent =
                "STOP";

        };


    recognition.onend =
        function () {

            micButton.textContent =
                "MIC";

        };


    recognition.onresult =
        function (event) {

            const transcript =
                event
                    .results[0][0]
                    .transcript;


            input.value =
                transcript;


            input.focus();

        };


    recognition.onerror =
        function () {

            micButton.textContent =
                "MIC";

        };


    micButton.addEventListener(
        "click",
        function () {

            try {

                recognition.start();

            } catch (error) {

                try {

                    recognition.stop();

                } catch (e) {}

            }

        }
    );

} else {

    micButton.addEventListener(
        "click",
        function () {

            addMessage(
                "Bu Safari sürümünde sesli giriş desteklenmiyor.",
                "assistant"
            );

        }
    );

}


/* =====================================================
   SAFARI KLAVYE
===================================================== */

input.addEventListener(
    "focus",
    function () {

        setTimeout(
            function () {

                input.scrollIntoView({
                    behavior: "smooth",
                    block: "center"
                });

            },
            350
        );

    }
);


/* =====================================================
   İLK BAŞLANGIÇ
===================================================== */

document.documentElement
    .style
    .setProperty(
        "--scale",
        scale / 100
    );


console.log(
    "J.A.R.V.I.S. K-CORE initialized."
);
