"use strict";
/* Unwritten Craft — upload page (upload.html): pick a video file and
   it rides the exact session path of a take. Loaded after common.js
   as a plain script, so file:// keeps working. */
$("uploadbtn").onclick = function(){
  var f = $("uploadinput").files[0];
  if(!f){ $("uploadstatus").innerHTML = "Pick a video file first."; return; }
  if(f.type && f.type.indexOf("video/") !== 0){ $("uploadstatus").innerHTML = "That file isn't a video — pick a video file."; return; }
  /* An upload rides the exact session path of a take: saved on this
     device, then cloud-uploaded, so the pipeline picks it up the
     same way a recording is picked up. */
  saveBlob(f, "unwritten_lesson_upload_" + stamp() + "." + extFor(f, "mp4"));
  $("uploadinput").value = "";
  $("uploadstatus").innerHTML = "✅ <b>Upload started.</b> The video is saved on this device and uploading to Cloud — watch its progress on the home screen.";
};
