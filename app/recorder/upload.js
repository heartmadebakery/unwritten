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
};
