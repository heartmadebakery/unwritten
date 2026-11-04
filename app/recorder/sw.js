/* Unwritten Craft web app — offline shell.
   Every page and script is network-first, so design and code updates
   arrive together when online; the cache only answers when the
   network is gone. Only this origin's files pass through here: the
   signer and Stream (hub lists, upload status polls) always go
   straight to the network. Clips never pass through here — they live
   in IndexedDB and downloads, as before. */
var CACHE = "unwritten-recorder-v13";
var ASSETS = ["./", "index.html", "record.html", "upload.html",
              "app.css", "common.js", "home.js", "record.js",
              "upload.js", "manifest.webmanifest",
              "icons/apple-touch-icon.png", "icons/icon-192.png",
              "icons/icon-512.png", "icons/icon-512-maskable.png"];

self.addEventListener("install", function(e){
  e.waitUntil(caches.open(CACHE).then(function(c){ return c.addAll(ASSETS); })
    .then(function(){ return self.skipWaiting(); }));
});
self.addEventListener("activate", function(e){
  e.waitUntil(caches.keys().then(function(keys){
    return Promise.all(keys.filter(function(k){ return k !== CACHE; })
      .map(function(k){ return caches.delete(k); }));
  }).then(function(){ return self.clients.claim(); }));
});
self.addEventListener("fetch", function(e){
  if(e.request.method !== "GET") return;
  /* Other origins are API calls, never shell files: cached, the first
     hub list showed forever and every upload status poll saw the
     first "processing" until the upload was marked failed. */
  if(new URL(e.request.url).origin !== self.location.origin) return;
  /* Dev APKs download straight from the network, never cached: a
     cached copy would go stale on every rebuild. */
  if(new URL(e.request.url).pathname.slice(-4) === ".apk") return;
  var isPage = e.request.mode === "navigate" ||
               (e.request.headers.get("accept") || "").indexOf("text/html") >= 0;
  e.respondWith(fetch(e.request).then(function(res){
    /* Cache good answers only: a cached 404/500 would brick the app
       shell until the cache is cleared by hand. */
    if(res && res.ok){
      var copy = res.clone();
      e.waitUntil(caches.open(CACHE).then(function(c){ return c.put(e.request, copy); }));
    }
    return res;
  }).catch(function(){
    /* Offline. A page deep link (record.html?play=…) still finds its
       cached page; an unknown page falls back to home. */
    return caches.match(e.request, {ignoreSearch: isPage}).then(function(hit){
      return hit || (isPage ? caches.match("index.html") : hit);
    }).then(function(hit){
      if(hit) return hit;
      /* Nothing cached and nothing reachable: answer plainly instead
         of resolving undefined (a TypeError). */
      return isPage
        ? new Response("Unwritten Craft is offline and was never cached.",
                       {status: 503, statusText: "Offline",
                        headers: {"Content-Type": "text/plain"}})
        : new Response("", {status: 504, statusText: "Offline"});
    });
  }));
});
