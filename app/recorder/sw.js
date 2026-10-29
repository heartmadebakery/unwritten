/* Unwritten Craft recorder — offline shell.
   Pages are network-first so design updates arrive when online; the
   cache only answers when the network is gone. Clips never pass
   through here — they live in IndexedDB and downloads, as before. */
var CACHE = "unwritten-recorder-v3";
var ASSETS = ["./", "index.html", "manifest.webmanifest",
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
  var isPage = e.request.mode === "navigate" ||
               (e.request.headers.get("accept") || "").indexOf("text/html") >= 0;
  if(isPage){
    e.respondWith(fetch(e.request).then(function(res){
      var copy = res.clone();
      caches.open(CACHE).then(function(c){ c.put("index.html", copy); });
      return res;
    }).catch(function(){ return caches.match("index.html"); }));
  }else{
    e.respondWith(caches.match(e.request).then(function(hit){
      return hit || fetch(e.request).then(function(res){
        var copy = res.clone();
        caches.open(CACHE).then(function(c){ c.put(e.request, copy); });
        return res;
      });
    }));
  }
});
