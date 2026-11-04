"use strict";
/* Unwritten Craft — upload page (upload.html): pick a video file and
   it rides the exact session path of a take. Loaded after common.js
   as a plain script, so file:// keeps working. */
/* Said once the vault write lands — never before: leaving a page
   aborts its IndexedDB writes, so "saved" while the write runs could
   send the user away from a lesson that then vanishes. */
var SAVED_HERE = "✅ <b>Saved on this device</b> and uploading to Cloud. You can leave this page — the record screen lists the session and resumes the upload.";
/* The drop zone names the picked file, so the choice is visible. */
$("uploadinput").onchange = function(){
  var f = this.files[0];
  $("pickname").textContent = f ? f.name : "From your library or Files";
};
/* Previous upload/fetch attempts, like the record page lists
   sessions — an indicator that an upload or fetch occurred. Upload
   rows reuse the record list's own row markup (same states, same
   retry); fetch rows log the queued link and when. */
function fetchAttemptHTML(a){
  var when = "";
  try{ when = new Date(a.date).toLocaleString(); }catch(e){}
  return "<div class='srow' data-fetch>" +
    "<span class='ltext'><span class='ltitle linkurl'>" + escHtml(a.url) + "</span>" +
    "<span class='chips'>" + chipHTML(a.ok ? "sage" : "ember", (a.ok ? "Queued ✓" : "Couldn't queue") + (when ? " · " + escHtml(when) : "")) + "</span></span></div>";
}
function renderUploadHistory(){
  var up = $("uphistory"), fh = $("fetchhistory");
  if(!up || !fh) return;
  var ups = state.clips.filter(function(c){ return c.name.indexOf("upload_") >= 0; });
  up.innerHTML = "<h3 class='subhead'>Uploads</h3>" +
    (ups.map(clipHTML).join("") ||
      emptyHTML(ICON.video, "No uploads yet.", "Videos you pick above are saved here as sessions."));
  var attempts = loadFetchAttempts();
  fh.innerHTML = "<h3 class='subhead'>Fetches</h3>" +
    (attempts.map(fetchAttemptHTML).join("") ||
      "<p class='note'>No links queued yet — fetch one with the link field above.</p>");
}
document.addEventListener("click", function(e){
  var r = e.target.closest ? e.target.closest("[data-cloud-retry]") : null;
  if(!r) return;
  e.preventDefault();
  cloudRetry(r.getAttribute("data-cloud-retry"));
  setTimeout(renderUploadHistory, 2000);
});
function isDirectMediaUrl(u){
  try{
    var p = new URL(u).pathname.toLowerCase();
    return /\.(mp4|webm|mov|mkv|m4v|mp3|m4a|wav)$/.test(p);
  }catch(e){ return false; }
}
$("urlfetchbtn").onclick = async function(){
  var u = $("urlinput").value.trim();
  var st = $("urlstatus");
  if(!u){ st.textContent = "Paste a link first."; return; }
  /* Direct files download in the page, into the normal session path;
     watch pages (YouTube and the like) queue to the pipeline, which
     fetches them with yt-dlp — the browser cannot download those. */
  if(isDirectMediaUrl(u)){
    st.textContent = "⬇ Downloading…";
    try{
      var rs = await fetch(u);
      if(!rs.ok) throw new Error("HTTP " + rs.status);
      var blob = await rs.blob();
      if(!blob.size) throw new Error("empty file");
      st.innerHTML = "⬇ <b>Saving on this device…</b> Keep this page open until it says saved.";
      var saved = saveBlob(blob, "unwritten_lesson_upload_" + stamp() + "." + extFor({type: blob.type || "", name: u}, "mp4"));
      $("urlinput").value = "";
      await saved;
      st.innerHTML = "✅ <b>Saved on this device.</b> The video is saved here and uploading to Cloud — watch its progress below.";
      renderUploadHistory();
    }catch(e){
      st.innerHTML = "⬇ <b>Couldn't download that link</b> (" + escHtml(e.message) + ") The site may block cross-site downloads.";
    }
    return;
  }
  if(!cloudToken()){ st.innerHTML = "⬇ Queuing needs the signer token — rebuild the app to stamp one."; return; }
  st.textContent = "⬇ Queuing…";
  try{
    var res = await fetch(cloudSignerUrl() + "/fetch/jobs", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Signer-Token": cloudToken()},
      /* Continuing a session: the pipeline's fetched video becomes
         its next part (the signer ties it when the job is done). */
      body: JSON.stringify(joinTarget() ? {url: u, joinTo: joinTarget().videoId} : {url: u})
    });
    if(res.status === 401){ st.innerHTML = "Signer refused the token — rebuild the app to stamp a fresh one."; logFetchAttempt(u, false); return; }
    if(!res.ok) throw new Error("HTTP " + res.status);
    $("urlinput").value = "";
    st.innerHTML = "✅ <b>Queued.</b> The pipeline will fetch the video and process it like a recording." +
      (joinTarget() ? " It joins <b>" + escHtml(joinTarget().title) + "</b> as its next part." : "");
    logFetchAttempt(u, true);
    renderUploadHistory();
  }catch(e){
    st.innerHTML = "⬇ <b>Couldn't queue that link</b> (" + escHtml(e.message) + ") Check the connection and Cloud settings.";
    logFetchAttempt(u, false);
  }
};
$("uploadbtn").onclick = async function(){
  var f = $("uploadinput").files[0];
  if(!f){ $("uploadstatus").innerHTML = "Pick a video file first."; return; }
  if(f.type && f.type.indexOf("video/") !== 0){ $("uploadstatus").innerHTML = "That file isn't a video — pick a video file."; return; }
  /* An upload rides the exact session path of a take: saved on this
     device, then cloud-uploaded, so the pipeline picks it up the
     same way a recording is picked up. */
  $("uploadstatus").innerHTML = "⬆ <b>Saving on this device…</b> Keep this page open until it says saved.";
  var saved = saveBlob(f, "unwritten_lesson_upload_" + stamp() + "." + extFor(f, "mp4"));
  $("uploadinput").value = "";
  $("pickname").textContent = "From your library or Files";
  await saved;
  $("uploadstatus").innerHTML = SAVED_HERE;
  renderUploadHistory();
};
idbRestore().then(function(){ renderClips(); renderUploadHistory(); });
window.addEventListener("pageshow", renderUploadHistory);
