"use strict";
/* Unwritten Craft — upload page (upload.html): pick a video file and
   it rides the exact session path of a take. Loaded after common.js
   as a plain script, so file:// keeps working. */
/* Said once the vault write lands — never before: leaving a page
   aborts its IndexedDB writes, so "saved" while the write runs could
   send the user away from a lesson that then vanishes. */
var SAVED_HERE = "✅ <b>Saved on this device</b> and uploading to Cloud. You can leave this page — the record screen lists the session and resumes the upload.";
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
  await saved;
  $("uploadstatus").innerHTML = SAVED_HERE;
};
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
      st.innerHTML = SAVED_HERE;
    }catch(e){
      st.innerHTML = "⬇ <b>Couldn't download that link</b> (" + escHtml(e.message) + ") The site may block cross-site downloads.";
    }
    return;
  }
  if(!cloudToken()){ st.innerHTML = "⬇ Queuing needs the signer token — add it in Advanced settings on the record screen."; return; }
  st.textContent = "⬇ Queuing…";
  try{
    var res = await fetch(cloudSignerUrl() + "/fetch/jobs", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Signer-Token": cloudToken()},
      body: JSON.stringify({url: u})
    });
    if(res.status === 401){ st.innerHTML = "Signer refused the token — check it in Cloud settings."; return; }
    if(!res.ok) throw new Error("HTTP " + res.status);
    $("urlinput").value = "";
    st.innerHTML = "✅ <b>Queued.</b> The pipeline will fetch the video and process it like a recording.";
  }catch(e){
    st.innerHTML = "⬇ <b>Couldn't queue that link</b> (" + escHtml(e.message) + ") Check the connection and Cloud settings.";
  }
};
