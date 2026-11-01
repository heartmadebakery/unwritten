"use strict";
/* Unwritten Craft — home page (index.html): Record and Upload actions
   with the published hub last. Loaded after common.js as a plain
   script, so file:// keeps working. Cloud, the device sessions, and
   the debug overrides live on the record page. */
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
wakeLock(); loadHub();
