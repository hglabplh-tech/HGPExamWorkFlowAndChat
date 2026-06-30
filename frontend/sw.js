const CACHE="study-harbour-v1";
self.addEventListener("install",event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(["/","/static/styles.css","/static/app.js"]))));
self.addEventListener("fetch",event=>{if(event.request.method==="GET")event.respondWith(caches.match(event.request).then(hit=>hit||fetch(event.request)));});

