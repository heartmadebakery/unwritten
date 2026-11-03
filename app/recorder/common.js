"use strict";
/* Unwritten Craft — shared core, loaded by every page as a plain
   script (no modules, so file:// keeps working). Home is index.html
   (record/upload actions with the hub last); record is record.html
   (viewfinder, zoom, record, cloud, device sessions, advanced link);
   upload is upload.html. No roles, no steps, nothing performed for the
   machine — the pipeline (transcribe -> write-up -> corrections)
   works afterwards on each session, take or upload alike, which it
   picks as the largest media file in the lesson folder.
   Lessons persist in IndexedDB so a reload, crash, or discarded tab
   cannot lose them. Page-specific code lives in home.js / record.js /
   upload.js; the renderers below tolerate pages that don't carry
   their elements. */

/* Native-leaning look: the CSS nudges radii, type and the header per
   platform (html.ios / html.android); everything else is shared. The
   design language itself ("Hearth", docs/DESIGN.md) is app.css plus
   the renderers below: cover tiles, words in status chips, frames of
   the video as thumbnails. */
(function(){
  var ua = navigator.userAgent || "", root = document.documentElement;
  if(/Android/i.test(ua)) root.classList.add("android");
  else if(/iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) root.classList.add("ios");
})();

function probe(){
  var caps = {
    mediaRecorder: (typeof MediaRecorder !== "undefined"),
    gum: !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
    idb: (typeof indexedDB !== "undefined"),
    secure: !!window.isSecureContext
  };
  caps.inPageRecording = caps.mediaRecorder && caps.gum;
  return caps;
}
var CAPS = probe();
var state = { stream:null, recorder:null, chunks:[], recording:false,
              timerInt:null, t0:0, clips:[], facing:"environment",
              zoom:{min:1, max:1, val:1}, playing:null };
var $ = function(id){ return document.getElementById(id); };
var durationCache = {}, thumbCache = {};

/* Line icons, drawn the same way as the page's inline SVGs. */
var ICON = (function(){
  function i(d){ return "<svg class='i' viewBox='0 0 24 24' aria-hidden='true'>" + d + "</svg>"; }
  return {
    download: i("<path d='M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14'/>"),
    share: i("<path d='M12 15V4M7.5 8.5 12 4l4.5 4.5M5 13v4.5A2.5 2.5 0 0 0 7.5 20h9a2.5 2.5 0 0 0 2.5-2.5V13'/>"),
    retry: i("<path d='M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7'/>"),
    close: i("<path d='M6 6l12 12M18 6 6 18'/>"),
    trash: i("<path d='M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3'/>"),
    play: i("<path d='M8 5.5v13l10.5-6.5z' fill='currentColor'/>"),
    video: i("<rect x='3' y='5' width='18' height='14' rx='3'/><path d='m10 9.5 4.5 2.5-4.5 2.5z'/>"),
    mic: i("<rect x='9' y='3' width='6' height='11' rx='3'/><path d='M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21'/>"),
    book: i("<path d='M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5zM4 20.5A2.5 2.5 0 0 0 6.5 23H20'/>")
  };
})();
/* A lesson wears the same warm wash on every platform: the sum of the
   title's UTF-16 code units, modulo the six cover pairs. */
function washIndex(title){
  var s = String(title || ""), n = 0;
  for(var k = 0; k < s.length; k++) n += s.charCodeAt(k);
  return n % 6;
}
function initialOf(title){
  var m = /[A-Za-z0-9À-￿]/.exec(String(title || ""));
  return m ? m[0].toUpperCase() : "•";
}
function coverHTML(title){
  return "<span class='cover cw" + washIndex(title) + "' aria-hidden='true'>" +
    escHtml(initialOf(title)) + "</span>";
}
function emptyHTML(icon, title, help){
  return "<div class='sempty empty'><span class='eglyph'>" + icon + "</span><b>" + title +
    "</b>" + (help ? "<span>" + help + "</span>" : "") + "</div>";
}

async function wakeLock(){
  try{ if("wakeLock" in navigator) await navigator.wakeLock.request("screen"); }catch(e){}
}
function fmt(s){ return Math.floor(s/60) + ":" + ("0" + (s%60)).slice(-2); }
function fmtDur(sec){
  sec = Math.floor(sec);
  var s = sec % 60, m = Math.floor(sec / 60) % 60, h = Math.floor(sec / 3600);
  if(h > 0) return h + ":" + ("0" + m).slice(-2) + ":" + ("0" + s).slice(-2);
  return m + ":" + ("0" + s).slice(-2);
}

/* In-viewfinder playback, like Android: tapping a session plays it
   inside the viewfinder with ▶ / ⏸ / ✕ below it. Recording stops it. */
function clipByName(name){
  return state.clips.find(function(c){ return c.name === name; }) || null;
}
function playInViewfinder(name){
  var c = clipByName(name);
  if(!c){ $("status").textContent = "That session file is missing from this device."; return; }
  if(state.recording) return;
  /* Sessions live on home; playback happens on the record page,
     which home reaches with ?play=<name>. */
  stopLocalPlayback();
  state.playing = name;
  $("view").classList.add("hidden");
  var p = $("player");
  p.src = c.url;
  p.classList.remove("hidden");
  $("playercontrols").classList.remove("hidden");
  var pr = p.play();
  if(pr && pr.catch) pr.catch(function(){});
}
function stopLocalPlayback(){
  state.playing = null;
  var p = $("player");
  if(!p) return;
  try{ p.pause(); }catch(e){}
  p.removeAttribute("src");
  try{ p.load(); }catch(e){}
  p.classList.add("hidden");
  $("playercontrols").classList.add("hidden");
  var v = $("view");
  if(v) v.classList.remove("hidden");
}

/* Lessons persist in IndexedDB so a reload, crash, or discarded tab
   cannot lose them. On old Safari where IndexedDB may be unavailable
   (e.g. file://), idbPut simply no-ops and the in-memory list entry
   remains. */
function idbOpen(){
  return new Promise(function(res, rej){
    var r = indexedDB.open("unwritten-clips", 1);
    r.onupgradeneeded = function(){ r.result.createObjectStore("clips", {keyPath:"name"}); };
    r.onsuccess = function(){ res(r.result); };
    r.onerror = function(){ rej(r.error); };
    r.onblocked = function(){ rej(new Error("idb blocked")); }; /* never hang */
  });
}
async function idbPut(name, blob){
  if(!CAPS.idb) return;
  try{ var db = await idbOpen();
    await new Promise(function(res, rej){
      var tx = db.transaction("clips", "readwrite");
      tx.objectStore("clips").put({name:name, blob:blob, ts:Date.now()});
      tx.oncomplete = res; tx.onerror = function(){ rej(tx.error); };
    });
  }catch(e){ /* in-memory entry still stands */ }
}
async function idbRestore(){
  if(!CAPS.idb) return;
  try{ var db = await idbOpen();
    var items = await new Promise(function(res, rej){
      var out = [], cur = db.transaction("clips").objectStore("clips").openCursor();
      cur.onsuccess = function(){ var c = cur.result; if(c){ out.push(c.value); c.continue(); } else res(out); };
      cur.onerror = function(){ rej(cur.error); };
    });
    /* Newest first, like the Android sessions list. Records from the
       retired multi-step design are adopted rather than lost. */
    items.sort(function(a, b){ return (b.ts || 0) - (a.ts || 0); })
         .forEach(function(it){
      if(!state.clips.some(function(c){ return c.name === it.name; }))
        state.clips.push({name:it.name, url:URL.createObjectURL(it.blob),
                          type:(it.blob && it.blob.type) || "", persisted:true});
    });
    renderClips();
  }catch(e){}
}
function saveBlob(blob, name){
  var url = URL.createObjectURL(blob);
  state.clips.unshift({name:name, url:url, type:blob.type || "", persisted:false});
  renderClips();
  idbPut(name, blob).then(function(){
    var c = state.clips.find(function(x){ return x.name === name; });
    if(c && CAPS.idb){ c.persisted = true; renderClips(); }
  });
  if(cloudReady() && isVideoLesson(blob, name)) startCloudUpload(name, blob, null);
}

function idbDelete(name){
  return new Promise(function(res){
    if(!CAPS.idb){ res(); return; }
    idbOpen().then(function(db){
      try{
        var tx = db.transaction("clips", "readwrite");
        tx.objectStore("clips").delete(name);
        tx.oncomplete = function(){ res(); };
        tx.onerror = function(){ res(); };
      }catch(e){ res(); }
    }).catch(function(){ res(); });
  });
}

/* Session rows mirror Android: left status icon, middle date + length,
   right share/download action. Tap plays in the viewfinder;
   long-press deletes. */
function leftIconFor(name){
  var b = loadCloudLinks()[name];
  if(!b) return "📱";
  if(b.state === "uploading") return "☁↑";
  if(b.state === "processing") return "☁…";
  if(b.state === "failed") return "☁!";
  return "☁";
}
var MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function displayDateFor(name){
  try{
    var base = name, us = base.lastIndexOf("_");
    if(us >= 0) base = base.substring(us + 1);
    var dot = base.lastIndexOf(".");
    if(dot > 0) base = base.substring(0, dot);
    var y = +base.substring(0, 4), mo = +base.substring(4, 6), d = +base.substring(6, 8),
        h = +base.substring(9, 11), mi = +base.substring(11, 13);
    if(!y || !mo || !d || mo > 12) return name;
    return MONTHS[mo - 1] + " " + d + ", " + y + " " + ("0" + h).slice(-2) + ":" + ("0" + mi).slice(-2);
  }catch(e){ return name; }
}
/* One metadata load per session gives both its length and a frame of
   the video for the row's thumbnail (cached as a small JPEG, so the
   frequent progress re-renders never reload the video). A frame that
   can't be drawn (audio takes, old Safari) leaves the warm cover. */
function probeClip(name){
  if(durationCache[name] !== undefined) return;
  var c = clipByName(name);
  if(!c) return;
  durationCache[name] = ""; thumbCache[name] = "";
  var audio = (c.type || "").indexOf("audio") === 0;
  var el = document.createElement(audio ? "audio" : "video");
  var done = false;
  function finish(){
    if(done) return;
    done = true;
    try{ el.removeAttribute("src"); el.load(); }catch(e){}
    renderClips();
  }
  el.preload = "metadata"; el.muted = true;
  el.setAttribute("playsinline", "");
  el.onloadedmetadata = function(){
    if(el.duration && isFinite(el.duration)) durationCache[name] = fmtDur(el.duration);
    if(audio || !el.videoWidth){ finish(); return; }
    try{ el.currentTime = Math.min(1, (isFinite(el.duration) ? el.duration : 2) / 2); }
    catch(e){ finish(); }
  };
  el.onseeked = function(){
    try{
      var cv = document.createElement("canvas"), s = 112;
      var w = el.videoWidth, h = el.videoHeight, side = Math.min(w, h);
      cv.width = s; cv.height = s;
      cv.getContext("2d").drawImage(el, (w - side) / 2, (h - side) / 2, side, side, 0, 0, s, s);
      thumbCache[name] = cv.toDataURL("image/jpeg", 0.72);
    }catch(e){ thumbCache[name] = ""; }
    finish();
  };
  el.onerror = finish;
  setTimeout(finish, 8000); /* never leave a row waiting on a stuck decoder */
  el.src = c.url;
}
function durationFor(name){ probeClip(name); return durationCache[name] || ""; }
function thumbFor(name){ probeClip(name); return thumbCache[name] || ""; }
function thumbHTML(c, dur){
  var t = thumbFor(c.name), audio = (c.type || "").indexOf("audio") === 0;
  var face = t ? "<img src='" + t + "' alt=''>"
               : "<span class='cover cw" + washIndex(c.name) + "'>" + (audio ? ICON.mic : ICON.video) + "</span>";
  return "<span class='thumb' aria-hidden='true'>" + face +
    (dur ? "<span class='dur'>" + dur + "</span>" : "") + "</span>";
}
/* Statuses in words: the link state the left icon codes for, as a chip. */
function chipHTML(kind, text){ return "<span class='chip" + (kind ? " " + kind : "") + "'>" + text + "</span>"; }
function clipHTML(c){
  var b = loadCloudLinks()[c.name] || null, st = b ? b.state : "", right, chip;
  /* Cloud-linking never removes the on-device download: every linked
     row keeps ↓ next to its cloud action. */
  var dl = "<a class='iconbtn' href='" + c.url + "' download='" + c.name + "' title='Save a copy of " + c.name + "' aria-label='Save a copy'>" + ICON.download + "</a>";
  if(!b){ right = dl; chip = chipHTML("", "On this device"); }
  else if(st === "uploading"){
    right = dl + "<span class='prog' style='--p:" + (b.progress | 0) + "' role='img' aria-label='Uploading " + (b.progress | 0) + " percent'>" + (b.progress | 0) + "%</span>";
    chip = chipHTML("ember", "Uploading " + (b.progress | 0) + "%");
  }
  else if(st === "processing" && !b.videoId){ right = dl + "<span class='spin' role='img' aria-label='Preparing'></span>"; chip = chipHTML("honey", "Preparing"); }
  else if(st === "failed"){
    right = dl + "<a class='iconbtn' href='#' data-cloud-retry='" + c.name + "' title='Retry cloud upload' aria-label='Retry cloud upload'>" + ICON.retry + "</a>";
    chip = "<a class='chip ember' href='#' data-cloud-retry='" + c.name + "'>Upload failed · Retry</a>";
  }
  else {
    right = dl + "<a class='iconbtn tonal' href='#' data-cloud-watch='" + c.name + "' title='Share session link' aria-label='Share session link'>" + ICON.share + "</a>";
    chip = st === "processing" ? chipHTML("honey", "Preparing") : chipHTML("sage", "In the cloud");
  }
  var ign = ignoredFor(c.name);
  if(ign) chip += " <span class='chip ign' title='Ignored by the operator" + (ign.reason ? ": " + escHtml(ign.reason) : "") + "'>ignored</span>";
  var memOnly = c.persisted === false;
  if(memOnly) chip += " " + chipHTML("honey", "⚠ Not saved yet");
  var dur = durationFor(c.name);
  var rowTitle = "Play — long-press to delete" + (memOnly ? " — in memory only, download before closing" : "");
  return "<div class='srow' data-row='" + c.name + "' title='" + rowTitle + "' data-state='" + leftIconFor(c.name) + "'>" +
    thumbHTML(c, dur) +
    "<span class='ltext'><span class='ltitle'>" + displayDateFor(c.name) + "</span>" +
    "<span class='chips'>" + chip + "</span></span>" +
    "<span class='sright'>" + right + "</span>" +
    "<button class='vh' data-cloud-delete='" + c.name + "'>Delete " + c.name + "</button></div>";
}
/* Ignored badges: the pipeline operator's set-asides sync to the
   hub (/hub/ignored); matching takes get an "ignored" badge on the
   Record screen instead of ever appearing in the hub. Match rule,
   same as the native recorders: the take's cloud-link videoId, else
   its filename against the marker title (upload titles are
   filenames). A failed fetch just leaves badges off — recording
   never depends on it. */
var ignoredMarks = null;
async function refreshIgnored(){
  if(!hubAvailable()) return;
  try{
    var rs = await fetch(cloudSignerUrl() + "/hub/ignored", {headers: {"X-Signer-Token": cloudToken()}});
    if(!rs.ok) return;
    var rows = await rs.json(), byId = {}, byTitle = {};
    (rows || []).forEach(function(r){
      if(!r) return;
      if(r.videoId) byId[r.videoId] = r.reason || "";
      if(r.title) byTitle[r.title] = r.reason || "";
    });
    ignoredMarks = {byId: byId, byTitle: byTitle};
  }catch(e){ /* badges stay off */ }
  renderClips();
}
function ignoredFor(name){
  if(!ignoredMarks) return null;
  var b = loadCloudLinks()[name], vid = b ? b.videoId : "";
  if(vid && Object.prototype.hasOwnProperty.call(ignoredMarks.byId, vid)) return {reason: ignoredMarks.byId[vid]};
  if(Object.prototype.hasOwnProperty.call(ignoredMarks.byTitle, name)) return {reason: ignoredMarks.byTitle[name]};
  return null;
}
function renderClips(){
  var box = $("clips");
  if(!box) return; /* only the home page lists sessions */
  box.innerHTML = state.clips.map(clipHTML).join("") ||
    emptyHTML(ICON.video, "Nothing yet.", "Sessions you record or upload appear here.");
}

/* ------------------------------------------------------------------
   Cloud upload (optional): upload a copy of each video lesson for
   streamed playback. Strictly additive — the on-device save above
   always happens first and never depends on this. Settings live in
   localStorage; the library API key stays on this device and is only
   ever sent to video.bunnycdn.com. Cloud has no live ingest, so this
   is store-then-stream: the ↗ action shares an adaptive HLS link.
------------------------------------------------------------------- */
var CLOUD_TUS = "https://video.bunnycdn.com/tusupload";
var CLOUD_SIGNER_DEFAULT = "https://unwritten-cloud-signer.heartmade.workers.dev";
var CLOUD_SIGNER_TOKEN_DEFAULT = ""; // stamped per build by build.sh into dist/common.js; "" in the template
var CLOUD_CHUNK = 5 * 1024 * 1024;
var cloudActive = {}, cloudPolling = {};

function cloudLoadCfg(){
  try{
    var raw = localStorage.getItem("uw_cloud_cfg");
    if(!raw) raw = localStorage.getItem("uw_bunny_cfg"); // legacy key from the Bunny-named release
    return JSON.parse(raw || "{}");
  }catch(e){ return {}; }
}
var cloudCfg = cloudLoadCfg();
function cloudSaveCfg(){ try{ localStorage.setItem("uw_cloud_cfg", JSON.stringify(cloudCfg)); localStorage.removeItem("uw_bunny_cfg"); }catch(e){} paintCloudToggle(); } // legacy key dropped on first save
function cloudSignerUrl(){ return cloudCfg.signerUrl || CLOUD_SIGNER_DEFAULT; }
function cloudToken(){ return cloudCfg.signerToken || CLOUD_SIGNER_TOKEN_DEFAULT; }
function cloudEnabled(){ return cloudCfg.enabled !== false; }
function cloudUseDirect(){ return !!(cloudCfg.libraryId && cloudCfg.apiKey); }
function cloudReady(){
  if(!cloudEnabled()) return false;
  if(cloudSignerUrl()) return true;
  return cloudUseDirect();
}
/* True when an upload could possibly succeed. Signer mode needs
   its token — the URL always has a built-in default, so URL-alone
   must not count — and direct mode needs library ID + API key.
   Without this, fresh installs (Cloud on by default, no
   credentials yet) fire doomed uploads that can only 401. Same
   contract as the native recorders' canUpload. */
function cloudCanUpload(){
  if(cloudToken()) return true;
  return cloudUseDirect();
}
function cloudLibraryId(){ return cloudCfg.libraryId || ""; }
function loadCloudLinks(){
  try{
    var raw = localStorage.getItem("uw_cloud_links");
    if(!raw) raw = localStorage.getItem("uw_bunny_links"); // legacy key from the Bunny-named release
    return JSON.parse(raw || "{}");
  }catch(e){ return {}; }
}
function setCloudLink(name, patch){
  var m = loadCloudLinks(), cur = m[name] || {};
  for(var k in patch) cur[k] = patch[k];
  if(cur.libraryId === undefined && cloudCfg.libraryId) cur.libraryId = cloudCfg.libraryId;
  m[name] = cur;
  try{ localStorage.setItem("uw_cloud_links", JSON.stringify(m)); localStorage.removeItem("uw_bunny_links"); }catch(e){} // legacy key dropped on first save
}
function sleep(ms){ return new Promise(function(r){ setTimeout(r, ms); }); }
function b64utf8(s){ return btoa(unescape(encodeURIComponent(s))); }
async function sha256Hex(text){
  if(!window.crypto || !crypto.subtle) throw new Error("Cloud signing needs a secure (https) page.");
  var buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map(function(b){ return ("0" + b.toString(16)).slice(-2); }).join("");
}
function isVideoLesson(blob, name){
  if(blob && blob.type) return blob.type.indexOf("video/") === 0;
  return /\.(mp4|webm|mov|mkv|m4v)$/i.test(name || "");
}
function idbGetBlob(name){
  return new Promise(function(res){
    if(!CAPS.idb){ res(null); return; }
    idbOpen().then(function(db){
      var rq = db.transaction("clips").objectStore("clips").get(name);
      rq.onsuccess = function(){ res(rq.result ? rq.result.blob : null); };
      rq.onerror = function(){ res(null); };
    }).catch(function(){ res(null); });
  });
}
async function cloudCreds(title, reuseVideoId){
  if(!cloudUseDirect()){
    var headers = {"Content-Type": "application/json", "Accept": "application/json"};
    var tok = cloudToken();
    if(tok) headers["X-Signer-Token"] = tok;
    var rs = await fetch(cloudSignerUrl(), {
      method: "POST", headers: headers,
      body: JSON.stringify(reuseVideoId ? {title: title, videoId: reuseVideoId} : {title: title})
    });
    if(!rs.ok) throw new Error("The Cloud signer refused (" + rs.status + "). Check the signer URL and token.");
    var d = await rs.json();
    if(!d.videoId || !d.signature || !d.expire) throw new Error("The Cloud signer returned incomplete credentials.");
    if(d.libraryId){ cloudCfg.libraryId = String(d.libraryId); cloudSaveCfg(); }
    return {videoId: d.videoId, expire: d.expire, signature: d.signature, libraryId: String(d.libraryId || cloudCfg.libraryId || "")};
  }
  var videoId = reuseVideoId || null;
  if(!videoId){
    var r = await fetch("https://video.bunnycdn.com/library/" + cloudCfg.libraryId + "/videos", {
      method: "POST",
      headers: {"AccessKey": cloudCfg.apiKey, "Accept": "application/json", "Content-Type": "application/json"},
      body: JSON.stringify({title: title})
    });
    if(!r.ok) throw new Error("Cloud could not create the video (" + r.status + "). Check the library ID and API key.");
    var v = await r.json();
    videoId = v.guid || v.videoId || v.id;
    if(!videoId) throw new Error("Cloud create returned no video ID.");
  }
  var expire = Math.floor(Date.now() / 1000) + 86400;
  var signature = await sha256Hex(String(cloudCfg.libraryId) + cloudCfg.apiKey + expire + videoId);
  return {videoId: videoId, expire: expire, signature: signature, libraryId: String(cloudCfg.libraryId)};
}
function cloudAuthHeaders(creds){
  return {
    "AuthorizationSignature": creds.signature,
    "AuthorizationExpire": String(creds.expire),
    "LibraryId": String(creds.libraryId || cloudCfg.libraryId || ""),
    "VideoId": creds.videoId,
    "Tus-Resumable": "1.0.0"
  };
}
async function tusCreateUpload(creds, blob, name){
  var meta = "filetype " + b64utf8(blob.type || "video/mp4") + ",title " + b64utf8(name);
  var headers = cloudAuthHeaders(creds);
  headers["Upload-Length"] = String(blob.size);
  headers["Upload-Metadata"] = meta;
  var r = await fetch(CLOUD_TUS, {method: "POST", headers: headers});
  if(r.status !== 201) throw new Error("Cloud upload start failed (" + r.status + ").");
  var loc = r.headers.get("Location");
  if(!loc) throw new Error("Cloud upload start returned no upload URL.");
  return loc.charAt(0) === "/" ? "https://video.bunnycdn.com" + loc : loc;
}
async function tusHeadOffset(uploadUrl, creds){
  var r = await fetch(uploadUrl, {method: "HEAD", headers: cloudAuthHeaders(creds)});
  if(r.status === 404 || r.status === 410) return -1;
  if(!r.ok) throw new Error("Cloud resume check failed (" + r.status + ").");
  var off = parseInt(r.headers.get("Upload-Offset"), 10);
  return isNaN(off) ? -1 : off;
}
async function tusSendAll(sess, blob, name){
  var offset = sess.offset || 0, attempt = 0;
  while(offset < blob.size){
    var end = Math.min(offset + CLOUD_CHUNK, blob.size), res = null, netErr = null;
    try{
      var headers = cloudAuthHeaders(sess.creds);
      headers["Upload-Offset"] = String(offset);
      headers["Content-Type"] = "application/offset+octet-stream";
      res = await fetch(sess.uploadUrl, {method: "PATCH", headers: headers, body: blob.slice(offset, end)});
    }catch(e){ netErr = e; }
    if(netErr || !res.ok){
      var status = res ? res.status : 0;
      if(res && status >= 400 && status < 500 && status !== 409 && status !== 423)
        throw new Error("Cloud refused the upload (" + status + ").");
      if(++attempt > 8) throw new Error("Cloud upload kept failing — connection too unstable.");
      var serverOffset = -1;
      try{ serverOffset = await tusHeadOffset(sess.uploadUrl, sess.creds); }catch(e){}
      if(serverOffset >= 0) offset = serverOffset;
      await sleep(Math.min(3000 * attempt, 15000));
      continue;
    }
    attempt = 0;
    var serverOff = parseInt(res.headers.get("Upload-Offset"), 10);
    offset = isNaN(serverOff) ? end : serverOff;
    sess.offset = offset;
    setCloudLink(name, {state: "uploading", progress: Math.floor(offset / blob.size * 100),
                        videoId: sess.videoId, uploadUrl: sess.uploadUrl});
    renderClips();
  }
}
async function cloudDeleteVideo(videoId){
  if(!cloudUseDirect()){
    var surl = cloudSignerUrl(), sep = surl.indexOf("?") >= 0 ? "&" : "?";
    var hs = {"Accept": "application/json"};
    var tok = cloudToken();
    if(tok) hs["X-Signer-Token"] = tok;
    var rs = await fetch(surl + sep + "videoId=" + encodeURIComponent(videoId), {method: "DELETE", headers: hs});
    if(!rs.ok) throw new Error("Cloud delete failed (" + rs.status + ").");
    return;
  }
  var r = await fetch("https://video.bunnycdn.com/library/" + cloudCfg.libraryId + "/videos/" + videoId,
    {method: "DELETE", headers: {"AccessKey": cloudCfg.apiKey, "Accept": "application/json"}});
  if(!r.ok && r.status !== 404) throw new Error("Cloud delete failed (" + r.status + ").");
}
async function cloudGetVideo(videoId){
  if(!cloudUseDirect()){
    var sep = cloudSignerUrl().indexOf("?") >= 0 ? "&" : "?";
    var hs = {"Accept": "application/json"};
    var tok = cloudToken();
    if(tok) hs["X-Signer-Token"] = tok;
    var rs = await fetch(cloudSignerUrl() + sep + "videoId=" + encodeURIComponent(videoId), {headers: hs});
    if(!rs.ok) throw new Error("Cloud status check failed (" + rs.status + ").");
    return rs.json();
  }
  var r = await fetch("https://video.bunnycdn.com/library/" + cloudCfg.libraryId + "/videos/" + videoId,
    {headers: {"AccessKey": cloudCfg.apiKey, "Accept": "application/json"}});
  if(!r.ok) throw new Error("Cloud status check failed (" + r.status + ").");
  return r.json();
}
async function pollCloudStatus(name, videoId){
  if(cloudPolling[name]) return;
  cloudPolling[name] = true;
  var failures = 0;
  try{
    for(var i = 0; i < 120; i++){
      await sleep(5000);
      var v = null;
      try{ v = await cloudGetVideo(videoId); failures = 0; }
      catch(e){
        if(++failures > 6){
          setCloudLink(name, {state: "failed", videoId: videoId});
          renderClips();
          $("status").innerHTML = "☁️ <b>Cloud status checks kept failing</b> — tap ! on the session to try again. The session is safe on this device.";
          return;
        }
        continue;
      }
      if(v.status === 4){ setCloudLink(name, {state: "ready", progress: 100, videoId: videoId}); renderClips(); return; }
      if(v.status === 5 || v.status === 6){ setCloudLink(name, {state: "failed", videoId: videoId}); renderClips(); return; }
    }
    /* Ten minutes with no finished stream: stop polling and offer a
       retry instead of leaving the session on "…" forever. */
    setCloudLink(name, {state: "failed", videoId: videoId});
    renderClips();
    $("status").innerHTML = "☁️ <b>Cloud is taking too long</b> to prepare the stream — tap ! on the session to try again. The session is safe on this device.";
  } finally { delete cloudPolling[name]; }
}
async function startCloudUpload(name, blob, sess){
  if(!cloudReady() || cloudActive[name]) return;
  if(!cloudCanUpload()){
    setCloudLink(name, {state: "failed"});
    renderClips();
    $("status").innerHTML = "☁️ <b>Cloud credentials missing</b> — add the signer token in Cloud settings. The session is safe on this device.";
    return;
  }
  cloudActive[name] = true;
  try{
    if(sess && sess.uploadUrl && sess.videoId){
      sess.creds = await cloudCreds(name, sess.videoId);
      var off = -1;
      try{ off = await tusHeadOffset(sess.uploadUrl, sess.creds); }catch(e){}
      if(off < 0 || off > blob.size) sess = null; else sess.offset = off;
    }
    if(!sess){
      var creds = await cloudCreds(name, null);
      var uploadUrl = await tusCreateUpload(creds, blob, name);
      sess = {videoId: creds.videoId, uploadUrl: uploadUrl, offset: 0, creds: creds};
    }
    setCloudLink(name, {state: "uploading", progress: Math.floor((sess.offset || 0) / blob.size * 100),
                        videoId: sess.videoId, uploadUrl: sess.uploadUrl});
    renderClips();
    $("status").innerHTML = "☁️ <b>Uploading to Cloud…</b> The session is already saved on this device.";
    await tusSendAll(sess, blob, name);
    setCloudLink(name, {state: "processing", progress: 100, videoId: sess.videoId});
    renderClips();
    $("status").innerHTML = "☁️ <b>Uploaded.</b> Cloud is preparing the streaming version — the ↗ share action on the session offers its link when ready.";
    pollCloudStatus(name, sess.videoId);
  }catch(e){
    setCloudLink(name, {state: "failed", videoId: (sess && sess.videoId) || undefined,
                        uploadUrl: (sess && sess.uploadUrl) || undefined});
    renderClips();
    $("status").innerHTML = "☁️ <b>Cloud upload didn't finish</b> (" + e.message + ") The session is safe on this device — tap ! on the session when the connection is better.";
  } finally { delete cloudActive[name]; }
}
/* Per-session share, like Android: the link is copied, then offered
   through the device share sheet where one exists. */
async function shareCloudLinkFor(name){
  var link = loadCloudLinks()[name];
  if(!link || !link.videoId) return;
  var lib = link.libraryId || cloudCfg.libraryId;
  if(!lib){ $("status").innerHTML = "☁️ <b>No Cloud link yet</b> for this session — the upload hasn't finished."; return; }
  var url = "https://player.mediadelivery.net/embed/" + lib + "/" + link.videoId;
  try{ if(navigator.clipboard) await navigator.clipboard.writeText(url); }catch(e){}
  if(navigator.share){
    try{ await navigator.share({title: name, url: url}); return; }
    catch(e){ return; }
  }
  window.open(url, "_blank");
}
async function cloudOpenWatch(name){
  return shareCloudLinkFor(name);
}
async function cloudRetry(name){
  var blob = await idbGetBlob(name);
  if(!blob){
    /* No vault (old Safari, file://) but the take is still in memory:
       re-read it from its object URL instead of giving up. */
    var c = clipByName(name);
    if(c){
      try{ blob = await (await fetch(c.url)).blob(); }catch(e){ blob = null; }
    }
  }
  if(!blob){ $("status").innerHTML = "☁️ That session is no longer stored on this device, so it can't be re-uploaded from here."; return; }
  var link = loadCloudLinks()[name] || {};
  startCloudUpload(name, blob, (link.uploadUrl && link.videoId) ? {videoId: link.videoId, uploadUrl: link.uploadUrl} : null);
}
function delCloudLink(name){
  var m = loadCloudLinks();
  if(m[name]){ delete m[name]; try{ localStorage.setItem("uw_cloud_links", JSON.stringify(m)); }catch(e){} }
}
/* Long-press a session to delete it, like Android — cloud copy first,
   and the local session is kept if that fails. */
function confirmDeleteLesson(name){
  if(!confirm("Delete session?\n\nDelete '" + name + "' from this device and the cloud?")) return;
  cloudDeleteLesson(name);
}
async function cloudDeleteLesson(name){
  var link = loadCloudLinks()[name] || {};
  if(link.videoId){
    try{ await cloudDeleteVideo(link.videoId); }
    catch(e){
      /* A dead cloud delete must not trap local storage: offer the
         device-only delete as a second confirm. */
      if(!confirm("The Cloud copy couldn't be deleted (" + e.message + ").\n\nDelete this device's copy anyway? The Cloud copy stays where it is.")){
        $("status").innerHTML = "☁️ <b>Couldn't delete the cloud copy</b> (" + e.message + ") Keeping the local session so nothing is lost.";
        return;
      }
    }
  }
  await idbDelete(name);
  if(state.playing === name) stopLocalPlayback();
  var i = state.clips.findIndex(function(c){ return c.name === name; });
  if(i >= 0){ try{ URL.revokeObjectURL(state.clips[i].url); }catch(e){} state.clips.splice(i, 1); }
  delete durationCache[name];
  delCloudLink(name);
  renderClips();
  $("status").innerHTML = "🗑 Session deleted from this device" + (link.videoId ? " and the cloud." : ".");
}
/* The hub lives on the signer, so it needs a signer token. Direct
   (library-key) mode has no hub at all. */
function hubAvailable(){ return !cloudUseDirect() && !!cloudToken(); }
function escHtml(s){
  return String(s == null ? "" : s).replace(/[&<>"']/g, function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];
  });
}
/* Hub rows: the signer answers camelCase and the list carries no
   playback URLs — a row opens the session's detail, like Android and
   iOS, and the detail holds Play / Share / Delete. */
function hubRowHTML(r){
  var sub = "";
  if(r.lessonDate || r.durationSeconds){
    var dur = r.durationSeconds ? fmtDur(r.durationSeconds) : "";
    sub = "<span class='lsub'>" + escHtml(r.lessonDate || "") + (dur ? (r.lessonDate ? " \u2022 " : "") + dur : "") + "</span>";
  }
  return "<button class='lesson' data-hub-open='" + escHtml(r.videoId || "") + "'>" +
    coverHTML(r.title || r.videoId) +
    "<span class='ltext'><span class='ltitle'>" + escHtml(r.title || r.videoId || "Untitled") + "</span>" +
    sub + "</span>" +
    "<span class='chev' aria-hidden='true'></span></button>";
}
var hubDetail = null;
function hubEmbedUrl(d){
  if(!d || !d.videoId) return "";
  var lib = d.libraryId || cloudLibraryId();
  return lib ? "https://player.mediadelivery.net/embed/" + lib + "/" + d.videoId : "";
}
/* Write-ups are Markdown: inline bold and italic render (after
   escaping), line breaks stay — the same inline-only reading as iOS. */
function inlineMd(text){
  return escHtml(text).replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>")
                      .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<i>$2</i>");
}
/* A lesson, listing style: a warm cover banner with its initial, the
   title and date, an ember Play pill with round Share and Delete, the
   write-up, corrections as quote cards, chapters as a time list. */
function hubDetailHTML(d){
  var title = d.title || d.videoId;
  var h = "<article class='detail'>" +
    "<div class='banner-cover cw" + washIndex(title) + "'><span aria-hidden='true'>" + escHtml(initialOf(title)) + "</span>" +
    "<button class='iconbtn' data-hub-act='close' title='Close' aria-label='Close'>" + ICON.close + "</button></div>" +
    "<div class='dbody'><h3 class='dtitle'>" + escHtml(title) + "</h3>" +
    (function(){ var dur=d.durationSeconds?fmtDur(d.durationSeconds):""; return (d.lessonDate||dur)?"<div class='ddate'>"+escHtml(d.lessonDate||"")+(dur?(d.lessonDate?" \u2022 ":"")+dur:"")+"</div>":""; })() +
    "<div class='dacts'><button class='pill primary' data-hub-act='play'>" + ICON.play + "Play</button>" +
    "<button class='iconbtn tonal' data-hub-act='share' title='Share session link' aria-label='Share session link'>" + ICON.share + "</button>" +
    "<button class='iconbtn tonal danger' data-hub-act='delete' title='Delete from the hub and the cloud' aria-label='Delete from the hub and the cloud'>" + ICON.trash + "</button></div>";
  if(d.writeupMd) h += "<div class='writeup'>" + inlineMd(d.writeupMd) + "</div>";
  if((d.corrections || []).length) h += "<h4 class='dsec'>Corrections</h4>";
  (d.corrections || []).forEach(function(c){
    h += "<figure class='quote'><span class='tchip'>" + escHtml(c.start || "") + "</span>" +
      "<blockquote>“" + escHtml(c.quote || "") + "”</blockquote>" +
      (c.correcting ? "<figcaption>Correcting: " + escHtml(c.correcting) + "</figcaption>" : "") + "</figure>";
  });
  if((d.chapters || []).length) h += "<h4 class='dsec'>Chapters</h4><ol class='chapters'>";
  (d.chapters || []).forEach(function(c){
    h += "<li><span class='tchip'>" + escHtml(c.start || "") + "</span>" + escHtml(c.label || "") + "</li>";
  });
  if((d.chapters || []).length) h += "</ol>";
  return h + "</div></article>";
}
function renderHubDetail(){
  var box = $("hubdetail");
  if(!box) return;
  box.innerHTML = hubDetail ? hubDetailHTML(hubDetail) : "";
}
async function openHubSession(videoId){
  if(!videoId || !hubAvailable() || !$("hubdetail")) return;
  try{
    var rs = await fetch(cloudSignerUrl() + "/hub/sessions/" + encodeURIComponent(videoId),
                         {headers: {"X-Signer-Token": cloudToken()}});
    if(!rs.ok) throw new Error("HTTP " + rs.status);
    hubDetail = await rs.json();
    stopHubPlayback();
    renderHubDetail();
  }catch(e){
    $("status").innerHTML = "Couldn't open that hub session — check the connection. (" + escHtml(e.message) + ")";
  }
}
function closeHubSession(){ stopHubPlayback(); hubDetail = null; renderHubDetail(); }
/* Hub sessions stream in the home page's own player — watching a
   published lesson never opens the camera. MP4 when the library has
   the fallback on, else HLS (Safari plays it natively), else the
   embed page in a new tab. */
function playHubSession(d){
  var url = (d && (d.mp4Url || d.hlsUrl)) || "";
  if(!url){
    var embed = hubEmbedUrl(d);
    if(embed){ window.open(embed, "_blank"); return; }
    $("status").textContent = "No playable stream on this hub session yet.";
    return;
  }
  var p = $("hubplayer");
  /* HLS-only sessions can't play in a plain <video> outside Safari:
     a player error opens the Cloud embed page and says so. */
  p.onerror = function(){
    var embed = hubEmbedUrl(d);
    stopHubPlayback();
    if(embed){
      $("status").textContent = "This browser can't play that stream here — opening the Cloud player.";
      window.open(embed, "_blank");
    } else {
      $("status").textContent = "Couldn't play that hub session.";
    }
  };
  p.src = url;
  p.classList.remove("hidden"); $("hubclose").classList.remove("hidden");
  try{ p.scrollIntoView({behavior: "smooth", block: "center"}); }catch(e){}
  p.play().catch(function(){});
}
async function shareHubSession(d){
  var url = hubEmbedUrl(d);
  if(!url){ $("status").innerHTML = "☁️ <b>No Cloud link yet</b> for this session."; return; }
  try{ if(navigator.clipboard) await navigator.clipboard.writeText(url); }catch(e){}
  if(navigator.share){
    try{ await navigator.share({title: d.title || "hub session", url: url}); }catch(e){}
    return;
  }
  $("status").innerHTML = "☁️ Session link copied: " + escHtml(url);
}
function confirmDeleteHub(d){
  if(!d || !d.videoId) return;
  if(!confirm("Delete hub session?\n\nDelete '" + (d.title || d.videoId) + "' from the cloud and the hub?")) return;
  deleteHubSession(d.videoId);
}
/* Hub record first, then the Stream video: a failure between the two
   leaves the bytes orphaned in Stream (still playable, still
   re-publishable) instead of a hub row pointing at a dead video, and
   the partial outcome is reported as partial. */
async function deleteHubSession(videoId){
  try{
    var rs = await fetch(cloudSignerUrl() + "/hub/sessions/" + encodeURIComponent(videoId),
                         {method: "DELETE", headers: {"X-Signer-Token": cloudToken()}});
    if(!rs.ok) throw new Error("hub delete failed (" + rs.status + ")");
  }catch(e){
    $("status").innerHTML = "☁️ <b>Couldn't delete the hub entry</b> (" + escHtml(e.message) + ") Keeping everything so nothing is lost.";
    return;
  }
  if(hubDetail && hubDetail.videoId === videoId) closeHubSession();
  try{ await cloudDeleteVideo(videoId); }
  catch(e){
    loadHub();
    $("status").innerHTML = "☁️ <b>Hub entry removed, but the cloud copy remains</b> (" + escHtml(e.message) + ") Delete it from the Stream dashboard.";
    return;
  }
  loadHub();
  $("status").innerHTML = "🗑 Session deleted from the hub and the cloud.";
}
function stopHubPlayback(){
  var p = $("hubplayer");
  if(!p) return;
  p.onerror = null; /* clearing src must not trigger the fallback */
  try{ p.pause(); }catch(e){}
  p.removeAttribute("src"); p.load();
  p.classList.add("hidden"); $("hubclose").classList.add("hidden");
}
async function loadHub(){
  var box = $("hublist"), st = $("hubstatus");
  if(!box || !st) return; /* the hub lives on the home page only */
  if(!hubDetail) stopHubPlayback();
  if(!cloudEnabled()){
    st.innerHTML = "Hub lives on the signer — turn Cloud on to see published lessons.";
    box.innerHTML = ""; hubDetail = null; renderHubDetail();
    return;
  }
  if(!hubAvailable()){
    st.innerHTML = cloudUseDirect()
      ? "The hub lives on the signer — direct library-key mode has no hub."
      : "Add the signer token in Cloud settings to see published lessons.";
    box.innerHTML = "";
    return;
  }
  st.innerHTML = "Loading…";
  try{
    var rs = await fetch(cloudSignerUrl() + "/hub/sessions", {headers: {"X-Signer-Token": cloudToken()}});
    if(rs.status === 401){ st.innerHTML = "Signer refused the token — check it in Cloud settings."; box.innerHTML = ""; return; }
    if(rs.status === 503){ st.innerHTML = "Hub isn't switched on at the server yet."; box.innerHTML = ""; return; }
    if(!rs.ok) throw new Error("HTTP " + rs.status);
    var rows = await rs.json();
    if(!rows || !rows.length){ st.innerHTML = ""; box.innerHTML = emptyHTML(ICON.book, "Nothing published yet.", "Finished lessons show up here once the pipeline has written them up."); return; }
    st.innerHTML = "";
    box.innerHTML = rows.map(hubRowHTML).join("");
    if(hubDetail && !rows.some(function(r){ return r.videoId === hubDetail.videoId; })) closeHubSession();
  }catch(e){
    st.innerHTML = "Hub couldn't load — check the connection and Cloud settings. (" + escHtml(e.message) + ")";
    box.innerHTML = "";
  }
}
function cloudResumePending(){
  if(!cloudReady()) return;
  var m = loadCloudLinks();
  Object.keys(m).forEach(function(name){
    var l = m[name];
    if(!state.clips.some(function(c){ return c.name === name; })) return;
    if(l.state === "uploading" && l.uploadUrl && l.videoId){
      idbGetBlob(name).then(function(blob){
        if(blob) startCloudUpload(name, blob, {videoId: l.videoId, uploadUrl: l.uploadUrl});
        else { setCloudLink(name, {state: "failed"}); renderClips(); }
      });
    } else if(l.state === "processing" && l.videoId){
      pollCloudStatus(name, l.videoId);
    }
  });
}
function paintCloudToggle(){
  var on = cloudEnabled();
  var t = $("cloudtoggle"), e = $("exportbtn");
  if(!t || !e) return; /* only the home page carries cloud controls */
  /* A real switch: the state lives in aria-checked (the CSS draws the
     knob from it), so assistive tech reads "Cloud, switch, on/off". */
  t.setAttribute("aria-checked", on ? "true" : "false");
  t.classList.toggle("on", on);
  /* Export is the offline fallback, like Android: only with Cloud off. */
  e.classList.toggle("hidden", on);
}
function stamp(){
  /* Full date + time + milliseconds in every filename: lessons can
     never collide across days in the IndexedDB vault. */
  var d = new Date(), p = function(n, w){ return ("000" + n).slice(-(w || 2)); };
  return d.getFullYear() + p(d.getMonth()+1) + p(d.getDate()) + "-" +
         p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds()) + "-" + p(d.getMilliseconds(), 3);
}
function extFor(file, fallback){
  var t = (file && file.type) || "";
  var map = { "video/quicktime":"mov", "video/mp4":"mp4", "video/webm":"webm",
              "audio/mp4":"m4a", "audio/x-m4a":"m4a", "audio/mpeg":"mp3",
              "audio/webm":"webm", "audio/ogg":"ogg", "image/jpeg":"jpg", "image/png":"png" };
  if(map[t]) return map[t];
  var n = (file && file.name) || "";
  var e = n.indexOf(".") >= 0 ? n.split(".").pop().toLowerCase() : "";
  return (/^[a-z0-9]{2,5}$/.test(e) && e !== "video" && e !== "audio") ? e : fallback;
}
