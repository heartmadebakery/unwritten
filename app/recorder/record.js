"use strict";
/* Unwritten Craft — record page (record.html): viewfinder, zoom, one
   Record/Stop button, in-viewfinder playback. Loaded after common.js
   as a plain script, so file:// keeps working. The camera opens at
   page boot and releases on exit, so landing on home never prompts
   for permission. */

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
        ? "⚠️ <b>Recording hit a problem</b> — the device may have been interrupted and nothing was captured. Check the home screen, then record again."
        : "⚠️ <b>That take was empty</b> — nothing was captured. Record the lesson again.";
      return;
    }
    var ext = (rec.mimeType || "").indexOf("mp4") >= 0 ? "mp4" : "webm";
    saveBlob(blob, "unwritten_lesson_" + stamp() + "." + ext);
    $("status").innerHTML = recErr
      ? "⚠️ <b>Session saved, but recording hit a problem</b> — the device may have been interrupted, so the take may be cut short. Check it below."
      : "✅ <b>Session saved</b> — on this device (see the home screen). Hand the file to whoever runs the pipeline.";
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
  this.textContent = state.facing === "environment" ? "📷 Back camera" : "🤳 Front camera";
  await openCamera();
};
$("capvideo").onclick = function(){ $("fileinput").click(); };
$("capaudio").onclick = function(){ $("audioinput").click(); };
$("fileinput").onchange = function(){ var f = this.files[0]; this.value = ""; if(f){ saveBlob(f, "unwritten_lesson_camera-app_" + stamp() + "." + extFor(f, "mp4")); $("status").innerHTML = "✅ <b>Session saved</b> from the camera app — see the home screen."; } };
$("audioinput").onchange = function(){ var f = this.files[0]; this.value = ""; if(f){ saveBlob(f, "unwritten_lesson_voice-app_" + stamp() + "." + extFor(f, "m4a")); $("status").innerHTML = "✅ <b>Session saved</b> from the voice app — see the home screen."; } };
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
/* Tapping a home session lands here with ?play=<name>: restore the
   vault, then play it in the viewfinder. */
openCamera();
wakeLock();
(function(){
  var m = /[?&]play=([^&]*)/.exec(location.search || "");
  if(!m || !m[1]) return;
  var name = decodeURIComponent(m[1]);
  idbRestore().then(function(){ playInViewfinder(name); });
})();
