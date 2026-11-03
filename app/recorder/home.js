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
  else if(act === "tie") showTiePicker(hubDetail);
};
/* Parts of a tied session: play one, untie one, or tie another
   session onto the end (the picker under "Tie a session"). */
$("hubdetail").addEventListener("click", function(e){
  if(!hubDetail || !e.target.closest) return;
  var pp = e.target.closest("[data-hub-part-play]");
  if(pp){ playHubSession(hubDetail, +pp.getAttribute("data-hub-part-play")); return; }
  var un = e.target.closest("[data-hub-untie]");
  if(un){
    var vid = un.getAttribute("data-hub-untie");
    var p = hubParts(hubDetail).filter(function(x){ return x.videoId === vid; })[0];
    if(confirm("Untie '" + ((p && p.title) || vid) + "'?\n\nIt becomes its own session again. Nothing is deleted.")) untieHubPart(hubDetail, vid);
    return;
  }
  var tie = e.target.closest("[data-hub-tie]");
  if(tie) tieHubSessions(hubDetail, tie.getAttribute("data-hub-tie"));
});
/* A personal hello over the title, by the device's own clock. */
function greetingFor(hour){
  return hour < 5 ? "Good evening" : hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}
$("greeting").textContent = greetingFor(new Date().getHours());
/* Android's refresh action and iOS's pull to refresh, as a button. */
$("hubrefresh").onclick = function(){ loadHub(); };
wakeLock(); loadHub();
