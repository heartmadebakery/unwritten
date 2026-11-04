"use strict";
/* Unwritten Craft — link page (link.html): a direct video file
   downloads in the page, a watch-page link queues to the pipeline.
   Loaded after common.js as a plain script, so file:// keeps working. */
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
      st.innerHTML = "✅ <b>Saved on this device.</b> The video is saved here and uploading to Cloud — watch its progress on the record screen.";
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
    if(res.status === 401){ st.innerHTML = "Signer refused the token — rebuild the app to stamp a fresh one."; return; }
    if(!res.ok) throw new Error("HTTP " + res.status);
    $("urlinput").value = "";
    st.innerHTML = "✅ <b>Queued.</b> The pipeline will fetch the video and process it like a recording." +
      (joinTarget() ? " It joins <b>" + escHtml(joinTarget().title) + "</b> as its next part." : "");
  }catch(e){
    st.innerHTML = "⬇ <b>Couldn't queue that link</b> (" + escHtml(e.message) + ") Check the connection and Cloud settings.";
  }
};
