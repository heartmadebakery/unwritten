"use strict";
/* Unwritten Craft — home page (index.html): Record and Upload actions
   over the hub, then cloud settings and the device sessions. Loaded
   after common.js as a plain script, so file:// keeps working. */

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
  loadHub();
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
$("cloudsettings").onclick = function(){
  var panel = $("cloudpanel");
  if(panel.classList.contains("hidden")){
    $("cloudsigner").value = cloudSignerUrl();
    $("cloudsignertoken").value = cloudToken();
    $("cloudlib").value = cloudCfg.libraryId || "";
    $("cloudkey").value = cloudCfg.apiKey || "";
    panel.classList.remove("hidden");
  } else {
    panel.classList.add("hidden");
    loadHub(); /* new signer settings show in the hub at once */
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
  else if(d){ e.preventDefault(); confirmDeleteLesson(d.getAttribute("data-cloud-delete")); }
  else{ var row = e.target.closest("[data-row]"); if(row) location.href = "record.html?play=" + encodeURIComponent(row.getAttribute("data-row")); }
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
$("hubclose").onclick = function(){ stopHubPlayback(); };
/* A hub row opens its detail (write-up, corrections, chapters) with
   Play / Share / Delete, like Android and iOS. */
$("hublist").onclick = function(e){
  var row = e.target.closest ? e.target.closest("[data-hub-open]") : null;
  if(row) openHubSession(row.getAttribute("data-hub-open"));
};
$("hubdetail").onclick = function(e){
  var b = e.target.closest ? e.target.closest("[data-hub-act]") : null;
  if(!b || !hubDetail) return;
  var act = b.getAttribute("data-hub-act");
  if(act === "close") closeHubSession();
  else if(act === "play") playHubSession(hubDetail);
  else if(act === "share") shareHubSession(hubDetail);
  else if(act === "delete") confirmDeleteHub(hubDetail);
};
paintCloudToggle();
$("caps").textContent = "This device: " +
  (CAPS.inPageRecording ? "can record in the page ✓" : "no in-page recording — its own camera/voice apps will be used") +
  " · " + (CAPS.secure ? "secure page ✓" : "⚠️ not a secure page (in-page camera needs https or a local file)") +
  " · " + (CAPS.idb ? "on-device vault ✓" : "no on-device vault (sessions only last until reload)");
wakeLock(); idbRestore().then(function(){ renderClips(); cloudResumePending(); }); loadHub();
