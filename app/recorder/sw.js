/* Unwritten Craft web app — offline shell.
   Pages are network-first so design updates arrive when online; the
   cache only answers when the network is gone. Clips never pass
   through here — they live in IndexedDB and downloads, as before. */
var CACHE = "unwritten-recorder-v6";
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
  var isPage = e.request.mode === "navigate" ||
               (e.request.headers.get("accept") || "").indexOf("text/html") >= 0;
  if(isPage){
    e.respondWith(fetch(e.request).then(function(res){
      /* Cache good pages only: a cached 404/500 would brick the app
         shell until the cache is cleared by hand. */
      if(res && res.ok){
        var copy = res.clone();
        caches.open(CACHE).then(function(c){ c.put(e.request, copy); });
      }
      return res;
    }).catch(function(){
      return caches.match(e.request).then(function(hit){
        return hit || caches.match("index.html");
      }).then(function(hit){
        /* Nothing cached and nothing reachable: answer plainly
           instead of resolving undefined (a TypeError). */
        return hit || new Response("Unwritten Craft is offline and was never cached.",
                                   {status: 503, statusText: "Offline",
                                    headers: {"Content-Type": "text/plain"}});
      });
    }));
  }else{
    e.respondWith(caches.match(e.request).then(function(hit){
      if(hit) return hit;
      return fetch(e.request).then(function(res){
        if(res && res.ok){
          var copy = res.clone();
          caches.open(CACHE).then(function(c){ c.put(e.request, copy); });
        }
        return res;
      }).catch(function(){
        return new Response("", {status: 504, statusText: "Offline"});
      });
    }));
  }
});
