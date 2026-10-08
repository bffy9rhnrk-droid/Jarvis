self.addEventListener("push", event => {
    let data = {};
    try { data = event.data ? event.data.json() : {}; }
    catch (_) { data = { body: event.data ? event.data.text() : "" }; }

    const title = data.title || "K.A.R.V.I.S.";
    const options = {
        body: data.body || "Yeni bir bildiriminiz var.",
        icon: "/icon-192.png",
        badge: "/icon-192.png",
        data: { url: data.url || "/" },
        tag: "karvis-notification",
        renotify: true
    };

    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", event => {
    event.notification.close();
    const target = event.notification.data?.url || "/";
    event.waitUntil(
        clients.matchAll({type:"window", includeUncontrolled:true}).then(list => {
            for (const client of list) {
                if ("focus" in client) {
                    if (target && target !== "/" && "navigate" in client) client.navigate(target);
                    return client.focus();
                }
            }
            if (clients.openWindow) return clients.openWindow(target);
        })
    );
});
