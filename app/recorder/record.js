"use strict";
/* Unwritten Craft — record page (record.html): viewfinder, zoom, one
   Record/Stop button, in-viewfinder playback, cloud, device sessions,
   and the debug Advanced settings link. Loaded after common.js as a
   plain script, so file:// keeps working. The camera opens at page
   boot and releases on exit, so landing on home never prompts for
   permission. */

async function openCamera(){
  stopLocalPlayback();
  stopSpeechMonitor();
  if(state.stream){ state.stream.getTracks().forEach(function(t){ t.stop(); }); state.stream = null; }
  if(!CAPS.gum){ showCaptureControls(); return; }
  var opts = { video:{ facingMode: state.facing, width:{ideal:1280}, height:{ideal:720} }, audio:true };
  try{ state.stream = await navigator.mediaDevices.getUserMedia(opts); }
  catch(e){
    /* A denied/busy microphone must not cost the video too. */
    try{ state.stream = await navigator.mediaDevices.getUserMedia({ video: opts.video, audio:false }); }
    catch(e2){ showCaptureControls(); return; }
  }
  $("view").srcObject = state.stream;
  /* A video-only stream must never be silent about being silent:
     the lesson IS the mentor's words. */
  var hasAudio = state.stream.getAudioTracks().length > 0;
  $("micwarn").classList.toggle("hidden", hasAudio);
  if(hasAudio){
    state.stream.getAudioTracks()[0].onended = function(){ $("micwarn").classList.remove("hidden"); };
  }
  if(!CAPS.mediaRecorder) showCaptureControls(); else hideCaptureControls();
}
function closeCamera(){
  stopLocalPlayback(); stopSpeechMonitor();
  if(state.stream){ state.stream.getTracks().forEach(function(t){ try{ t.stop(); }catch(e){} }); state.stream = null; }
  $("view").srcObject = null;
}
function showCaptureControls(){
  /* Old-device path: native camera / voice apps do the recording. */
  $("fallback").classList.remove("hidden");
  $("recbtn").classList.add("hidden");
  $("zoomrow").classList.add("hidden");
  $("capcontrols").classList.remove("hidden");
}
function hideCaptureControls(){
  $("fallback").classList.add("hidden");
  $("capcontrols").classList.add("hidden");
  $("recbtn").classList.remove("hidden");
  refreshZoomUi();
}
/* Live mic check: while recording, sample the mic level every 2 s
   and warn after a quiet minute — silence discovered now can still
   be fixed; silence discovered at transcription cannot. Purely
   local energy detection: no audio leaves the device. */
var speechMon = {ctx:null, analyser:null, timer:null, quietSince:0};
function startSpeechMonitor(){
  stopSpeechMonitor();
  try{
    if(!state.stream || !state.stream.getAudioTracks().length) return;
    var AC = window.AudioContext || window.webkitAudioContext;
    if(!AC) return;
    var ctx = new AC();
    if(ctx.resume) ctx.resume();
    var src = ctx.createMediaStreamSource(state.stream);
    var an = ctx.createAnalyser(); an.fftSize = 512;
    src.connect(an);
    speechMon.ctx = ctx; speechMon.analyser = an;
    speechMon.quietSince = Date.now();
    var buf = new Float32Array(an.fftSize);
    speechMon.timer = setInterval(function(){
      if(!state.recording) return;
      an.getFloatTimeDomainData(buf);
      var sum = 0, i;
      for(i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
      if(Math.sqrt(sum / buf.length) > 0.008){
        speechMon.quietSince = Date.now();
        $("speechwarn").classList.add("hidden");
      }else if(Date.now() - speechMon.quietSince > 60000){
        $("speechwarn").classList.remove("hidden");
      }
    }, 2000);
  }catch(e){}
}
function stopSpeechMonitor(){
  if(speechMon.timer){ clearInterval(speechMon.timer); speechMon.timer = null; }
  if(speechMon.ctx){ try{ speechMon.ctx.close(); }catch(e){} speechMon.ctx = null; }
  speechMon.analyser = null;
  $("speechwarn").classList.add("hidden");
}

/* Zoom mirrors the Android zoom row (− / slider / + / label). It stays
   hidden when the camera reports no zoom range, so it is never dead UI. */
function zoomTrack(){
  if(!state.stream || !state.stream.getVideoTracks) return null;
  return state.stream.getVideoTracks()[0] || null;
}
function refreshZoomUi(){
  var row = $("zoomrow"), t = zoomTrack(), z = state.zoom;
  var min = 1, max = 1, val = 1;
  try{
    if(t && t.getCapabilities){
      var c = t.getCapabilities();
      if(c && c.zoom){ min = c.zoom.min || 1; max = c.zoom.max || 1; }
    }
    if(t && t.getSettings){
      var s = t.getSettings();
      if(s && s.zoom) val = s.zoom;
    }
  }catch(e){}
  z.min = min; z.max = max; z.val = Math.max(min, Math.min(max, val));
  if(max <= min + 0.01 || $("recbtn").classList.contains("hidden")){ row.classList.add("hidden"); return; }
  row.classList.remove("hidden");
  $("zoomseek").value = String(Math.round((z.val - min) / (max - min) * 100));
  $("zoomlabel").textContent = z.val.toFixed(1) + "×";
}
function applyZoom(v){
  var z = state.zoom, t = zoomTrack();
  v = Math.max(z.min, Math.min(z.max, v));
  z.val = v;
  $("zoomlabel").textContent = v.toFixed(1) + "×";
  if(t && t.applyConstraints) t.applyConstraints({advanced:[{zoom:v}]}).catch(function(){});
}
function nudgeZoom(d){
  var z = state.zoom;
  applyZoom(z.val + d * ((z.max - z.min) || 1));
}

function pickMime(types){
  for(var i=0;i<types.length;i++){
    try{ if(MediaRecorder.isTypeSupported(types[i])) return types[i]; }catch(e){}
  }
  return "";
}
function startRec(){
  if(!state.stream){ openCamera().then(function(){ if(state.stream) startRec(); }); return; }
  if(!CAPS.mediaRecorder){ showCaptureControls(); return; }
  stopLocalPlayback();
  /* VP8 before VP9: the Pixel 4 base device encodes VP8 in hardware
     and it is the most compatible WebM codec. video/mp4 in the list is
     what old/new Safari accepts. */
  var mime = pickMime(["video/webm;codecs=vp8,opus","video/webm;codecs=vp9,opus","video/webm","video/mp4"]);
  state.chunks = [];
  try{ state.recorder = new MediaRecorder(state.stream, mime ? {mimeType:mime, videoBitsPerSecond:2500000} : undefined); }
  catch(e){ showCaptureControls(); return; }
  /* Capture everything the async onstop needs NOW, in case anything
     changes before it fires. */
  var rec = state.recorder, recChunks = state.chunks, recErr = false;
  rec.ondataavailable = function(e){ if(e.data && e.data.size) recChunks.push(e.data); };
  /* onerror fires before onstop: the flag carries the failure across,
     or onstop's "Session saved" buries it every time. */
  rec.onerror = function(){ recErr = true; stopRec(); };
  rec.onstop = function(){
    var blob = new Blob(recChunks, {type: rec.mimeType || "video/webm"});
    if(!blob.size){
      $("status").innerHTML = recErr
        ? "⚠️ <b>Recording hit a problem</b> — the device may have been interrupted and nothing was captured. Check the list below, then record again."
        : "⚠️ <b>That take was empty</b> — nothing was captured. Record the lesson again.";
      return;
    }
    var ext = (rec.mimeType || "").indexOf("mp4") >= 0 ? "mp4" : "webm";
    saveBlob(blob, "unwritten_lesson_" + stamp() + "." + ext);
    $("status").innerHTML = recErr
      ? "⚠️ <b>Session saved, but recording hit a problem</b> — the device may have been interrupted, so the take may be cut short. Check it below."
      : "✅ <b>Session saved</b> — on this device (in the list below). Hand the file to whoever runs the pipeline.";
  };
  try{ rec.start(250); }catch(e){ try{ rec.start(); }catch(e2){ showCaptureControls(); return; } }
  state.recording = true;
  startSpeechMonitor();
  $("recbtn").textContent = "■ Stop  0:00"; $("recbtn").classList.add("stop");
  $("recbadge").classList.remove("hidden");
  $("status").innerHTML = "● <b>Recording.</b> Teach the way you'd teach anyway — the corrections are found afterwards.";
  state.t0 = Date.now();
  $("timer").textContent = "0:00";
  state.timerInt = setInterval(function(){
    var t = fmt(Math.floor((Date.now()-state.t0)/1000));
    $("timer").textContent = t;
    $("recbtn").textContent = "■ Stop  " + t;
  }, 500);
}
function stopRec(){
  if(state.recorder && state.recording){ try{ state.recorder.stop(); }catch(e){} }
  state.recording = false;
  stopSpeechMonitor();
  $("recbtn").textContent = "● Record"; $("recbtn").classList.remove("stop");
  $("recbadge").classList.add("hidden");
  clearInterval(state.timerInt);
}

$("recbtn").onclick = function(){ state.recording ? stopRec() : startRec(); };
$("camtoggle").onclick = async function(){
  if(state.recording) return;
  state.facing = state.facing === "environment" ? "user" : "environment";
  this.setAttribute("aria-label", state.facing === "environment"
    ? "Back camera — switch to front" : "Front camera — switch to back");
  await openCamera();
};
$("capvideo").onclick = function(){ $("fileinput").click(); };
$("capaudio").onclick = function(){ $("audioinput").click(); };
$("fileinput").onchange = function(){ var f = this.files[0]; this.value = ""; if(f){ saveBlob(f, "unwritten_lesson_camera-app_" + stamp() + "." + extFor(f, "mp4")); $("status").innerHTML = "✅ <b>Session saved</b> from the camera app — in the list below."; } };
$("audioinput").onchange = function(){ var f = this.files[0]; this.value = ""; if(f){ saveBlob(f, "unwritten_lesson_voice-app_" + stamp() + "." + extFor(f, "m4a")); $("status").innerHTML = "✅ <b>Session saved</b> from the voice app — in the list below."; } };
$("zoomout").onclick = function(){ nudgeZoom(-0.1); };
$("zoomin").onclick = function(){ nudgeZoom(+0.1); };
$("zoomseek").addEventListener("input", function(){
  var z = state.zoom;
  applyZoom(z.min + (this.value / 100) * (z.max - z.min));
});
$("vfplay").onclick = function(){ if(!state.playing) return; var pr = $("player").play(); if(pr && pr.catch) pr.catch(function(){}); };
$("vfpause").onclick = function(){ $("player").pause(); };
$("vfclose").onclick = stopLocalPlayback;
$("player").addEventListener("ended", stopLocalPlayback);
document.addEventListener("visibilitychange", function(){
  /* Leaving the page mid-recording stops and keeps the take. */
  if(document.hidden && state.recording) stopRec();
  if(!document.hidden) wakeLock();
});
/* Bulk export, like Android's Export button: an explicit tap saves a
   download copy of every session. (Saving a session itself never
   fires a download — the vault write is the save.) */
function exportSessions(){
  if(!state.clips.length){ $("status").textContent = "Exported 0 sessions — nothing recorded yet."; return; }
  var i = 0, total = state.clips.length;
  $("status").textContent = "Exporting " + total + " sessions to Downloads…";
  (function next(){
    if(i >= total){ $("status").textContent = "Exported " + total + " sessions to Downloads."; return; }
    var c = state.clips[i++];
    var link = document.createElement("a");
    link.href = c.url; link.download = c.name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(next, 400);
  })();
}

$("cloudtoggle").onclick = function(){
  cloudCfg.enabled = !cloudEnabled(); cloudSaveCfg();
  $("status").innerHTML = cloudEnabled()
    ? "☁️ <b>Cloud on.</b> New video sessions will also upload for streamed playback; the ↗ action on each session offers its link when ready."
    : "☁️ <b>Cloud off.</b> Sessions stay on this device only. Export sessions to Downloads below to move them.";
  if(cloudEnabled()) sweepBacklog();
  /* The hub lives on another page now; refresh it when present. */
  if($("hublist")) loadHub();
};
/* Sessions recorded while Cloud was off (or failed) still need
   their copy when Cloud comes back on — without this sweep they
   would stay local-only forever, silently. */
function sweepBacklog(){
  if(!cloudCanUpload()) return;
  state.clips.forEach(function(c){
    var l = loadCloudLinks()[c.name];
    if(isVideoLesson(null, c.name) && (!l || l.state === "failed")) cloudRetry(c.name);
  });
}
/* Debug overrides hide behind a small link at the page bottom. */
$("advancedlink").onclick = function(){
  var panel = $("cloudpanel");
  if(panel.classList.contains("hidden")){
    $("cloudsigner").value = cloudSignerUrl();
    $("cloudsignertoken").value = cloudToken();
    $("cloudlib").value = cloudCfg.libraryId || "";
    $("cloudkey").value = cloudCfg.apiKey || "";
    panel.classList.remove("hidden");
  } else {
    panel.classList.add("hidden");
    if($("hublist")) loadHub(); /* new signer settings show in the hub at once */
  }
};
$("cloudsigner").addEventListener("change", function(){ cloudCfg.signerUrl = this.value.trim(); cloudSaveCfg(); });
$("cloudsignertoken").addEventListener("change", function(){ cloudCfg.signerToken = this.value.trim(); cloudSaveCfg(); });
$("cloudlib").addEventListener("change", function(){ cloudCfg.libraryId = this.value.trim(); cloudSaveCfg(); });
$("cloudkey").addEventListener("change", function(){ cloudCfg.apiKey = this.value.trim(); cloudSaveCfg(); });
$("exportbtn").onclick = exportSessions;
/* Tap a row to play it; long-press (touch or mouse) to delete it. */
var pressTimer = null, pressFired = false;
function armPress(name){
  cancelPress(); pressFired = false;
  pressTimer = setTimeout(function(){ pressFired = true; confirmDeleteLesson(name); }, 600);
}
function cancelPress(){ if(pressTimer){ clearTimeout(pressTimer); pressTimer = null; } }
$("clips").addEventListener("click", function(e){
  if(pressFired){ pressFired = false; e.preventDefault(); return; }
  if(!e.target.closest) return;
  var w = e.target.closest("[data-cloud-watch]"), r = e.target.closest("[data-cloud-retry]"), d = e.target.closest("[data-cloud-delete]");
  if(w){ e.preventDefault(); cloudOpenWatch(w.getAttribute("data-cloud-watch")); }
  else if(r){ e.preventDefault(); cloudRetry(r.getAttribute("data-cloud-retry")); }
  else{ var row = e.target.closest("[data-row]"); if(row) playInViewfinder(row.getAttribute("data-row")); }
});
$("clips").addEventListener("touchstart", function(e){
  var row = e.target.closest && e.target.closest("[data-row]");
  if(row) armPress(row.getAttribute("data-row"));
}, {passive:true});
$("clips").addEventListener("touchend", cancelPress);
$("clips").addEventListener("touchmove", cancelPress);
$("clips").addEventListener("mousedown", function(e){
  var row = e.target.closest && e.target.closest("[data-row]");
  if(row && e.button === 0) armPress(row.getAttribute("data-row"));
});
$("clips").addEventListener("mouseup", cancelPress);
/* Tapping a home session lands here with ?play=<name>: restore the
   vault, then play it in the viewfinder. */
openCamera();
wakeLock();
paintCloudToggle();
$("caps").textContent = "This device: " +
  (CAPS.inPageRecording ? "can record in the page ✓" : "no in-page recording — its own camera/voice apps will be used") +
  " · " + (CAPS.secure ? "secure page ✓" : "⚠️ not a secure page (in-page camera needs https or a local file)") +
  " · " + (CAPS.idb ? "on-device vault ✓" : "no on-device vault (sessions only last until reload)");
idbRestore().then(function(){ renderClips(); cloudResumePending(); refreshIgnored(); });
(function(){
  var m = /[?&]play=([^&]*)/.exec(location.search || "");
  if(!m || !m[1]) return;
  var name = decodeURIComponent(m[1]);
  idbRestore().then(function(){ playInViewfinder(name); });
})();
