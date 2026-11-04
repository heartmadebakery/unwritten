"""Streamlined app contract (Oct 27 simplification, applied to app/).

Both apps open on the hub sessions with Record and Upload above them;
recording is one screen, not a separate app. No roles/modes, no
session steps, no apprentice line, no companion sync. The pipeline
takes the largest media file as the lesson, so every take is named
unwritten_lesson_<timestamp>.<ext> (uploads add an upload_ infix).
"""
import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
WEB = os.path.join(ROOT, "app", "recorder", "index.html")
SW = os.path.join(ROOT, "app", "recorder", "sw.js")
# User-ordered Oct 31: one page per screen (index/record/upload share
# common.js + per-page scripts), not a single showScreen file.
REC_RECORD = os.path.join(ROOT, "app", "recorder", "record.html")
REC_UPLOAD = os.path.join(ROOT, "app", "recorder", "upload.html")
REC_COMMON = os.path.join(ROOT, "app", "recorder", "common.js")
REC_HOME_JS = os.path.join(ROOT, "app", "recorder", "home.js")
REC_RECORD_JS = os.path.join(ROOT, "app", "recorder", "record.js")
REC_UPLOAD_JS = os.path.join(ROOT, "app", "recorder", "upload.js")
REC_CSS = os.path.join(ROOT, "app", "recorder", "app.css")
MANIFEST = os.path.join(ROOT, "app", "recorder", "manifest.webmanifest")
MAIN = os.path.join(ROOT, "app", "android", "app", "src", "main", "java",
                    "com", "heartmadebakery", "unwritten", "MainActivity.java")
NAMES = os.path.join(ROOT, "app", "android", "app", "src", "main", "java",
                     "com", "heartmadebakery", "unwritten", "Names.java")
ENGINE = os.path.join(ROOT, "app", "android", "app", "src", "main", "java",
                      "com", "heartmadebakery", "unwritten", "CameraEngine.java")
HUB = os.path.join(ROOT, "app", "android", "app", "src", "main", "java",
                   "com", "heartmadebakery", "unwritten", "HubClient.java")
PREFS = os.path.join(ROOT, "app", "android", "app", "src", "main", "java",
                     "com", "heartmadebakery", "unwritten", "Prefs.java")
PROVIDER = os.path.join(ROOT, "app", "android", "app", "src", "main", "java",
                        "com", "heartmadebakery", "unwritten", "TinyFileProvider.java")
ANDROID_MANIFEST = os.path.join(ROOT, "app", "android", "app", "src", "main",
                                "AndroidManifest.xml")

# Vocabulary of the cut multi-mode design. None of it may survive in the
# streamlined apps (docs and dated logs may keep it as history).
CUT_WORDS = ["interviewer", "companion", "apprentice", "rolebtn",
             "Show me", "Teach me", "Your try"]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class WebRecorderTests(unittest.TestCase):
    # User-ordered Oct 31: one page per screen. Each assertion reads the
    # file that owns the contract; `all` covers cross-cutting sweeps.
    @classmethod
    def setUpClass(cls):
        cls.home = read(WEB)
        cls.record = read(REC_RECORD)
        cls.upload = read(REC_UPLOAD)
        cls.common = read(REC_COMMON)
        cls.homejs = read(REC_HOME_JS)
        cls.recordjs = read(REC_RECORD_JS)
        cls.uploadjs = read(REC_UPLOAD_JS)
        cls.all = "\n".join([cls.home, cls.record, cls.upload, cls.common,
                             cls.homejs, cls.recordjs, cls.uploadjs])

    def test_no_cut_design_vocabulary(self):
        low = self.all.lower()
        for word in CUT_WORDS:
            self.assertNotIn(word.lower(), low, word)

    def test_https_server_serves_the_stamped_build(self):
        # The phone-camera path served the unstamped source, so every
        # upload from a phone failed "credentials missing" — the same
        # build the plain-HTTP command serves goes out here, and the
        # unstamped fallback says so.
        serve = read(os.path.join(ROOT, "app", "recorder", "serve_https.py"))
        self.assertIn('"dist"', serve)
        self.assertIn("unstamped", serve)
        self.assertIn("directory=SITE", serve)

    def test_upload_page_claims_saved_only_once_saved(self):
        # The vault write was still running when the page said "saved
        # on this device — watch its progress on the record screen",
        # and leaving a page aborts its IndexedDB writes: a large
        # upload could vanish. saveBlob hands back the write; the
        # page says "saved" only after it lands. File choice and link
        # download both live on the upload page now (Nov 4 merge); both
        # handlers keep the promise.
        save = self.common.split("function saveBlob", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("return saved", save)
        saved_msg = self.uploadjs.split("var SAVED_HERE", 1)[1].split(";\n", 1)[0]
        self.assertIn("Saved on this device", saved_msg)
        upload_handler = self.uploadjs.split('$("uploadbtn").onclick', 1)[1]
        link_handler = self.uploadjs.split('$("urlfetchbtn").onclick', 1)[1] \
                                  .split("cloudToken()", 1)[0]
        link_before, _, link_after = link_handler.partition("await saved")
        for handler in (upload_handler, link_before):
            self.assertIn("Saving on this device", handler)
            self.assertNotIn("Saved on this device", handler)
            self.assertIn("saveBlob(", handler)
        self.assertLess(upload_handler.index("saveBlob("),
                        upload_handler.index("await saved"))
        self.assertLess(upload_handler.index("await saved"),
                        upload_handler.index("SAVED_HERE"))
        self.assertIn("Saved on this device", link_after)

    def test_resume_starts_sessions_that_never_linked(self):
        # A session whose page closed before its upload got a link
        # (the upload page, a reload mid-start) has no link at all:
        # with Cloud on and credentials present, the next page load
        # starts it instead of leaving it local-only, silently.
        resume = self.common.split("function cloudResumePending", 1)[1] \
                            .split("function paintCloudToggle", 1)[0]
        self.assertIn("state.clips.forEach", resume)
        self.assertIn("cloudCanUpload()", resume)
        self.assertIn("isVideoLesson(null, name)", resume)
        self.assertIn("startCloudUpload(name, blob, null)", resume)

    def test_no_roles_steps_or_session_code(self):
        for token in ["data-role", "STEPS", "uw_role", "uw_step",
                      "session_code", "makeCode"]:
            self.assertNotIn(token, self.all, token)

    def test_single_lesson_recording_flow(self):
        self.assertIn('id="recbtn"', self.record)
        self.assertIn("MediaRecorder", self.recordjs)
        self.assertIn("unwritten_lesson_", self.all)
        self.assertIn("indexedDB", self.common)  # on-device vault stays

    def test_linked_rows_keep_their_download(self):
        # Cloud-linking a session must not remove its on-device
        # download: every linked row keeps ↓ next to its cloud action.
        clip = self.common.split("function clipHTML(c)", 1)[1] \
                           .split("function renderClips", 1)[0]
        self.assertIn("var dl =", clip)
        self.assertEqual(clip.count("dl +"), 4)

    def test_memory_only_rows_warn(self):
        # The vault write can fail (private mode, quota): rows that
        # live in memory only must say so instead of looking saved.
        clip = self.common.split("function clipHTML(c)", 1)[1] \
                           .split("function renderClips", 1)[0]
        self.assertIn("persisted", clip)
        self.assertIn("⚠", clip)

    def test_recorder_error_survives_onstop(self):
        # onerror fires before onstop: without a flag, onstop's
        # "Session saved" buries the error every time.
        start = self.recordjs.split("rec.onerror", 1)[1] \
                             .split("function stopRec", 1)[0]
        self.assertIn("recErr", start)

    def test_service_worker_caches_good_pages_only(self):
        # A cached 404/500 would brick the app shell until cleared by
        # hand; a cache miss with no network must answer plainly,
        # never resolve undefined.
        sw = read(SW)
        self.assertIn("res.ok", sw)
        self.assertIn("503", sw)
        # User-ordered Nov 1: the offline shell precaches every page
        # and script of the split app, not just index.html.
        for asset in ["record.html", "upload.html", "app.css",
                      "common.js", "home.js", "record.js", "upload.js"]:
            self.assertIn(asset, sw, asset)

    def test_service_worker_never_touches_cross_origin_calls(self):
        # The signer (hub list, hub detail, ignored marks, upload
        # status) and Stream live on other origins. Cached, the first
        # hub list showed forever and every status poll saw the first
        # "processing" until the upload was marked failed.
        sw = read(SW)
        handler = sw.split('addEventListener("fetch"', 1)[1]
        guard = handler.index("self.location.origin")
        self.assertLess(guard, handler.index("respondWith"))

    def test_service_worker_serves_scripts_network_first(self):
        # Pages were network-first but scripts cache-first: an online
        # load paired new pages with old code until the next cache
        # bump. Every same-origin GET tries the network first.
        sw = read(SW)
        handler = sw.split('addEventListener("fetch"', 1)[1]
        self.assertEqual(handler.count("respondWith"), 1)
        self.assertLess(handler.index("fetch(e.request)"),
                        handler.index("caches.match"))

    @unittest.skipUnless(__import__("shutil").which("node"), "needs node")
    def test_service_worker_behavior_in_node(self):
        # Drive the real sw.js with stubbed caches/fetch: cross-origin
        # passes through untouched, online answers come from the
        # network (and refresh the cache), offline answers come from
        # the cache, and an offline deep link (?play=) still finds its
        # page.
        import json
        import subprocess
        script = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8");
const handlers = {};
const store = new Map();
let online = true;
const cache = {
  put: async (req, res) => { store.set(new URL(req.url || req, "https://app.test/").pathname, res); },
  addAll: async () => {},
};
const caches = {
  open: async () => cache,
  keys: async () => [],
  delete: async () => true,
  match: async (req, opts) => {
    const u = new URL(req.url || req, "https://app.test/");
    const key = u.pathname;
    if (!(opts && opts.ignoreSearch) && u.search) return undefined;
    const hit = store.get(key);
    return hit ? hit.clone() : undefined;
  },
};
const self = {
  location: new URL("https://app.test/sw.js"),
  addEventListener: (t, f) => { handlers[t] = f; },
  skipWaiting: () => {}, clients: { claim: () => {} },
};
const fetch = async (req) => {
  if (!online) throw new TypeError("offline");
  return new Response("net:" + new URL(req.url).pathname, { status: 200 });
};
new Function("self", "caches", "fetch", src)(self, caches, fetch);
async function go(url, mode) {
  let responded = null;
  const headers = new Headers(mode === "navigate" ? { accept: "text/html" } : {});
  handlers.fetch({ request: { url, method: "GET", mode: mode || "cors", headers },
                   respondWith: (p) => { responded = p; } });
  if (!responded) return null;
  const res = await responded;
  return res ? [res.status, await res.text()] : ["undefined", ""];
}
(async () => {
  const out = {};
  out.cross = await go("https://signer.test/hub/sessions");
  out.asset1 = await go("https://app.test/common.js");
  await new Promise((r) => setTimeout(r, 10));
  online = false;
  out.assetOffline = await go("https://app.test/common.js");
  online = true;
  out.page = await go("https://app.test/record.html", "navigate");
  await new Promise((r) => setTimeout(r, 10));
  online = false;
  out.deepLinkOffline = await go("https://app.test/record.html?play=x.webm", "navigate");
  console.log(JSON.stringify(out));
})();
"""
        proc = subprocess.run(["node", "-e", script, SW],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertIsNone(out["cross"])
        self.assertEqual(out["asset1"], [200, "net:/common.js"])
        self.assertEqual(out["assetOffline"], [200, "net:/common.js"])
        self.assertEqual(out["page"], [200, "net:/record.html"])
        self.assertEqual(out["deepLinkOffline"], [200, "net:/record.html"])

    def test_manifest_is_the_recorder_not_the_apprentice(self):
        manifest = read(MANIFEST)
        self.assertNotIn("Apprentice", manifest)
        self.assertIn("Unwritten Craft", manifest)
        self.assertNotIn("Recorder", manifest)

    def test_home_actions_then_hub_last(self):
        # One Unwritten Craft app: it opens on Record and Upload with
        # the hub last; recording is a screen, not a separate app, and
        # every screen leads home.
        # User-ordered Oct 31: screens are separate pages linked to each
        # other — no showScreen toggles remain anywhere.
        # User-ordered Nov 1: cloud + device sessions moved from home to
        # the record page; settings hide behind an advanced link.
        self.assertNotIn("showScreen", self.all)
        self.assertNotIn("screen-record", self.all)
        self.assertNotIn("screen-upload", self.all)
        for token in ['id="gorecord"', 'href="record.html"',
                      'id="goupload"', 'href="upload.html"',
                      'id="hublist"', 'src="common.js"', 'src="home.js"']:
            self.assertIn(token, self.home, token)
        self.assertLess(self.home.index('id="gorecord"'),
                        self.home.index('id="hublist"'))
        self.assertLess(self.home.index('id="goupload"'),
                        self.home.index('id="hublist"'))
        for token in ['id="cloudtoggle"', 'id="cloudpanel"',
                      'id="advancedlink"', 'id="clips"', 'id="exportbtn"',
                      'id="caps"']:
            self.assertNotIn(token, self.home, token)
        for token in ['id="cloudtoggle"', 'id="cloudpanel"',
                      'id="advancedlink"', 'id="clips"', 'id="exportbtn"',
                      'id="caps"', 'id="backhome-record"',
                      'href="index.html"', 'src="common.js"',
                      'src="record.js"', 'id="status"']:
            self.assertIn(token, self.record, token)
        self.assertIn("loadHub()", self.homejs)
        self.assertIn("/hub/sessions", self.common)
        self.assertIn('id="uploadinput"', self.upload)
        self.assertIn('id="uploadbtn"', self.upload)
        self.assertIn('id="backhome-upload"', self.upload)
        self.assertIn('href="index.html"', self.upload)
        # Every page loads the shared core plus its own script, and
        # carries the status line the shared code reports into.
        for token in ['src="common.js"', 'src="upload.js"', 'id="status"']:
            self.assertIn(token, self.upload, token)
        self.assertIn('id="status"', self.home)
        self.assertLess(self.home.index('id="gorecord"'),
                        self.home.index('id="hublist"'))
        self.assertLess(self.home.index('id="goupload"'),
                        self.home.index('id="hublist"'))

    def test_upload_saves_like_a_recording(self):
        # An upload lands in the device sessions and rides the same
        # cloud path as a take, so the pipeline picks it up the same way.
        up = self.uploadjs.split('$("uploadbtn").onclick', 1)[1]
        self.assertIn("saveBlob(f, ", up)
        self.assertIn("unwritten_lesson_upload_", up)

    def test_url_upload_field_queues_watch_links(self):
        # User-ordered Oct 31: paste a link — direct files download
        # in the page, watch pages queue to the pipeline fetcher.
        # User-ordered Nov 4: the link field folded back into the
        # upload page (upload.html / upload.js); see
        # test_upload_link_screens.py.
        page = read(os.path.join(ROOT, "app", "recorder", "upload.html"))
        pagejs = read(os.path.join(ROOT, "app", "recorder", "upload.js"))
        for token in ['id="urlinput"', 'id="urlfetchbtn"', 'id="urlstatus"']:
            self.assertIn(token, page, token)
        self.assertIn("/fetch/jobs", pagejs)
        self.assertIn("Queued.", pagejs)
        self.assertIn("Signer refused the token", pagejs)

    def test_direct_links_download_in_browser(self):
        # User-ordered Nov 4: lives in upload.js now.
        pagejs = read(os.path.join(ROOT, "app", "recorder", "upload.js"))
        self.assertIn("function isDirectMediaUrl", pagejs)
        up = pagejs.split("isDirectMediaUrl(u)", 1)[1] \
                          .split("cloudToken()", 1)[0]
        self.assertIn("saveBlob(", up)
        self.assertIn("unwritten_lesson_upload_", up)

    def test_hub_escapes_server_titles(self):
        # Hub titles come from the server; they must never inject markup.
        self.assertIn("function escHtml", self.common)
        row = self.common.split("function hubRowHTML", 1)[1] \
                         .split("function loadHub", 1)[0]
        self.assertIn("escHtml(r.title", row)

    def test_hub_rows_read_the_signer_field_names(self):
        # The signer answers camelCase (videoId, lessonDate); the list
        # route carries no playback URLs. Reading snake_case left every
        # web hub row dateless and unplayable.
        row = self.common.split("function hubRowHTML", 1)[1] \
                         .split("function ", 1)[0]
        self.assertIn("r.lessonDate", row)
        self.assertIn("r.videoId", row)
        for bad in ["lesson_date", "mp4_url", "hls_url"]:
            self.assertNotIn(bad, row, bad)

    def test_hub_opens_detail_plays_shares_and_deletes(self):
        # Parity with Android and iOS (Nov 1): a hub row opens the
        # session's detail — write-up, corrections, chapters — with
        # Play, Share, and Delete. Server text is always escaped.
        self.assertIn('id="hubdetail"', self.home)
        for token in ["function openHubSession", "function hubDetailHTML",
                      "function playHubSession", "function shareHubSession",
                      "function deleteHubSession", "function hubEmbedUrl",
                      '"/hub/sessions/" + encodeURIComponent(']:
            self.assertIn(token, self.common, token)
        detail = self.common.split("function hubDetailHTML", 1)[1] \
                            .split("\nfunction ", 1)[0]
        for token in ["d.writeupMd", "d.corrections", "d.chapters",
                      "escHtml(", "data-hub-act"]:
            self.assertIn(token, detail, token)
        self.assertIn("openHubSession(", self.homejs)

    def test_hub_writeup_renders_blocks_and_step_images(self):
        # User-ordered: the hub write-up is proper markdown, not
        # inline-only — headings, lists, and the step screengrabs the
        # pipeline embeds as data: URLs all render; raw HTML never does.
        render = self.common.split("function renderMd", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("<h", render)
        self.assertIn("<li>", render)
        self.assertIn("<img", render)
        self.assertIn("data:image", render)
        self.assertIn("escHtml", render)

    def test_hub_writeup_rejects_remote_and_relative_images(self):
        # Only embedded (data:image) stills render — remote or relative
        # image paths in server text must not become fetchable <img>.
        render = self.common.split("function renderMd", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("data:image", render)
        self.assertNotIn("http", render.replace("http-equiv", ""))

    def test_home_footer_links_android_dev_apk(self):
        # User-ordered: the home page bottom links the Android dev
        # build, so others can sideload it without adb or a checkout.
        self.assertIn("unwritten-craft.apk", self.home)
        self.assertIn("advlink", self.home)

    def test_web_build_ships_the_apk(self):
        # build.sh copies the prebuilt debug APK into dist/ beside
        # the pages, so the footer link resolves on the served site.
        build = read(os.path.join(ROOT, "app", "recorder", "build.sh"))
        self.assertIn("unwritten-craft.apk", build)
        self.assertIn("dist/", build)

    def test_service_worker_leaves_apk_downloads_alone(self):
        # Dev APKs download straight from the network, never cached:
        # a cached copy would go stale on every rebuild.
        sw = read(SW)
        self.assertIn(".apk", sw)

    def test_web_hub_playback_falls_back_to_embed(self):
        # An HLS-only session can't play in a plain <video> on Chrome:
        # a player error opens the Cloud embed page and says so.
        play = self.common.split("function playHubSession", 1)[1] \
                          .split("\nfunction ", 1)[0]
        self.assertIn("onerror", play)
        self.assertIn("hubEmbedUrl(", play)

    def test_web_hub_delete_removes_record_before_video(self):
        body = self.common.split("async function deleteHubSession", 1)[1] \
                          .split("\nfunction ", 1)[0]
        self.assertIn('method: "DELETE"', body)
        self.assertLess(body.index('"/hub/sessions/"'),
                        body.index("cloudDeleteVideo("))
        self.assertIn("but the cloud copy remains", body)
        self.assertIn("confirm(", self.common.split(
            "function confirmDeleteHub", 1)[1].split("\nfunction ", 1)[0])

    def test_camera_runs_only_on_record_screen(self):
        # Home-first means no permission prompt on landing: the camera
        # opens when the record screen shows and releases when it hides.
        # User-ordered Oct 31: the record page opens the camera at boot;
        # no other page may reference it at all.
        self.assertIn("openCamera()", self.recordjs)
        for name, src in [("home", self.home), ("upload", self.upload),
                          ("common", self.common), ("home.js", self.homejs),
                          ("upload.js", self.uploadjs)]:
            self.assertNotIn("openCamera", src, name)


class AndroidRecorderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = read(MAIN)
        cls.names = read(NAMES)

    def test_no_cut_design_vocabulary(self):
        low = self.main.lower()
        for word in CUT_WORDS:
            self.assertNotIn(word.lower(), low, word)
        self.assertNotIn("TextToSpeech", self.main)

    def test_no_roles_steps_or_session_code(self):
        for token in ["roleKeys", "STEPS", "getRole", "getStep",
                      "session_code"]:
            self.assertNotIn(token, self.main, token)

    def test_single_lesson_naming(self):
        self.assertIn("lessonName", self.names)
        self.assertIn("unwritten_lesson_", self.names)
        for token in ["clipName", "brollName", "dialogueName", "photoName",
                      "CODE_WORDS"]:
            self.assertNotIn(token, self.names, token)

    def test_prefs_class_is_gone(self):
        self.assertFalse(os.path.exists(PREFS),
                         "Prefs only stored role/code/step/apprentice line")

    def test_live_mic_check_warns_after_quiet_minute(self):
        self.assertIn("getMaxAmplitude", read(ENGINE))
        for token in ["speechRunnable", "speechQuietSince", "speechWarn",
                      "60000", "Quiet for a while"]:
            self.assertIn(token, self.main, token)

    def test_mic_denied_warns_out_loud(self):
        # Video-only takes must never be silent about being silent.
        self.assertIn("onMicUnavailable", read(ENGINE))
        for token in ["onMicUnavailable", "micWarn", "No microphone"]:
            self.assertIn(token, self.main, token)

    def test_camera_toggle_between_takes(self):
        engine = read(ENGINE)
        for token in ["switchCamera", "isFront", "preferredFacing"]:
            self.assertIn(token, engine, token)
        self.assertIn("Back camera", self.main)

    def test_hub_lists_detail_plays_and_deletes(self):
        self.assertIn("class HubClient", read(HUB))
        for token in ["/hub/sessions", "X-Signer-Token"]:
            self.assertIn(token, read(HUB), token)
        for token in ["hubContainer", "hubRows", "hubDetail", "loadHub",
                      "openHubSession", "hubEmbedUrl", "playHubRemote",
                      "shareHubSession", "confirmDeleteHub",
                      "deleteHubSession", "Hub sessions"]:
            self.assertIn(token, self.main, token)

    def test_hub_section_always_visible_with_reason(self):
        # The Hub header renders regardless of Cloud state; the body
        # names the reason (Cloud off, missing signer token, server
        # not switched on, load failure, or simply empty) instead of
        # hiding the section.
        for token in ["hubStatusText",
                      "no signer token",
                      "rebuild it to stamp one",
                      "Signer refused the token",
                      "isn't switched on at the server yet",
                      "Hub couldn't load"]:
            self.assertIn(token, self.main, token)

    def test_hub_delete_removes_record_before_video(self):
        # Hub record first, then the Stream video: a failure between
        # the two must leave the bytes orphaned (playable,
        # re-publishable) — never a hub row pointing at a dead video.
        # The partial outcome is reported as partial.
        body = self.main.split("private void deleteHubSession", 1)[1] \
                        .split("\n    private ", 1)[0]
        self.assertLess(body.index("HubClient("),
                        body.index("deleteVideo(videoId)"))
        self.assertIn("but the cloud copy remains", body)

    def test_url_upload_queues_to_pipeline(self):
        # User-ordered Oct 31: paste a link — natives queue every URL
        # to the pipeline fetcher (only the web page downloads direct
        # files itself).
        hub = read(HUB)
        self.assertIn("/fetch/jobs", hub)
        self.assertIn("queueFetchJob", hub)
        for token in ["Fetch from link", "queueFetchJob", "Queued"]:
            self.assertIn(token, self.main, token)

    def test_hub_writeup_strips_step_stills(self):
        # User-ordered 2026-11-04: parity with web/iOS — the hub detail
        # strips step stills (no still URLs in the hub).
        body = self.main.split("private CharSequence inlineMarkdown", 1)[1].split("\n    }\n", 1)[0]
        self.assertIn("Step", body)
        self.assertIn("noImg", body)

    def test_home_actions_then_hub_last(self):
        # User-ordered Nov 1: home is actions with the hub last; cloud
        # + device sessions moved to the record screen, settings behind
        # an advanced link.
        home = self.main.split("private void buildHomeScreen", 1)[1] \
                        .split("private void buildRecordScreen", 1)[0]
        record = self.main.split("private void buildRecordScreen", 1)[1] \
                          .split("// ---------- permissions", 1)[0]
        # User-ordered Nov 2 (Hearth redesign): the Record and Upload
        # buttons became action tiles (glyphs drawn, not ●/⬆ text).
        for token in ['actionTile("Record"', 'actionTile("Upload video"', "hubContainer"]:
            self.assertIn(token, home, token)
        self.assertLess(home.index('actionTile("Upload video"'),
                        home.index("hubContainer"))
        for token in ["cloudToggleButton", "lessonContainer", "exportBtn",
                      "Advanced settings"]:
            self.assertNotIn(token, home, token)
            self.assertIn(token, record, token)

    def test_errors_reach_the_user_not_a_hidden_view(self):
        # The status TextView is intentionally hidden; camera, record,
        # and permission failures must surface (Toast) instead of
        # dying in setText.
        self.assertIn("showError(", self.main)
        for token in ['status.setText("Camera', 'status.setText("Record',
                      'status.setText("Stop', 'status.setText("Could not']:
            self.assertNotIn(token, self.main, token)

    def test_clips_dir_survives_missing_external_storage(self):
        # getExternalFilesDir() returns null when external storage is
        # unavailable; the clips dir must fall back instead of NPEing.
        self.assertIn("getFilesDir()", self.main)

    def test_failed_upload_offers_retry(self):
        # The failed (!) badge re-triggers the upload, like the web
        # and iOS retry actions — a failed lesson must not strand.
        self.assertIn("retryCloud(", self.main)
        badge = self.main.split('} else if ("failed".equals(st)) {',
                                    1)[1].split("row.addView(stv);", 1)[0]
        self.assertIn("setOnClickListener", badge)

    def test_upload_fails_fast_without_credentials(self):
        # Fresh installs (Cloud on, no token yet) must not fire doomed
        # uploads that can only 401: canUpload gates the attempt, and
        # 401/403 failures name the token instead of staying silent.
        for token in ["canUpload", "Cloud credentials missing",
                      "Signer refused"]:
            self.assertIn(token, self.main, token)

    def test_hub_code_uses_defined_symbols_only(self):
        # First real build (Oct 30): javac failed because hub code used
        # INK (an iOS name — Android's identical constant is TEXT) and
        # HubClient declared get(String) twice (public JSONObject vs
        # private String), which also broke the JSONObject(String) call
        # sites. Guard the fixed shape.
        self.assertNotRegex(self.main, r"\bINK\b")
        hub = read(HUB)
        decls = re.findall(
            r"(?:public|private|protected)\s+[\w<>\[\]]+\s+get\s*\(", hub)
        self.assertEqual(len(decls), 1, decls)
        self.assertIn("getRaw(", hub)


class Pixel4BaselineTests(unittest.TestCase):
    """Base device (Oct 28): Google Pixel 4 — minSdk 29, arm64 only.

    The previous minSdk 26 / old-Android target is retired; nothing in
    the live Android code may keep a pre-29 fallback alive for it.
    """

    @classmethod
    def setUpClass(cls):
        root = os.path.join(os.path.dirname(__file__), "..")
        cls.gradle = read(os.path.join(root, "app", "android", "app", "build.gradle"))
        cls.build_sh = read(os.path.join(root, "app", "android", "build.sh"))
        cls.manifest = read(os.path.join(root, "app", "android", "app", "src",
                                         "main", "AndroidManifest.xml"))
        cls.main = read(MAIN)

    def test_min_sdk_is_pixel4_launch_os(self):
        self.assertIn("minSdk 29", self.gradle)
        self.assertIn("MIN_API=29", self.build_sh)

    def test_arm64_only_like_the_pixel4(self):
        self.assertIn('abiFilters "arm64-v8a"', self.gradle)
        self.assertNotIn("armeabi-v7a", self.gradle)
        self.assertNotIn("armeabi-v7a", self.build_sh)

    def test_no_pre29_storage_fallback(self):
        # MediaStore Downloads (API 29+) needs no storage permission,
        # and the legacy external-storage export path is deleted.
        self.assertNotIn("WRITE_EXTERNAL_STORAGE", self.manifest)
        self.assertNotIn("WRITE_EXTERNAL_STORAGE", self.main)
        self.assertNotIn("getExternalStoragePublicDirectory", self.main)
        self.assertNotIn("SDK_INT", self.main)


class AndroidBuildExitTests(unittest.TestCase):
    """build.sh exits 0 on a successful build (Oct 31).

    The script runs under `set -o pipefail`, so its final
    `aapt2 dump badging | head -4` line used to exit 141: badging prints
    21 lines, head closes the pipe early, aapt2 dies of SIGPIPE, and
    pipefail turns that into the script's exit code — breaking every
    `build.sh && ...` dev-loop chain on success.
    """

    @classmethod
    def setUpClass(cls):
        cls.build_sh = read(os.path.join(ROOT, "app", "android", "build.sh"))

    def test_badging_tail_is_sigpipe_safe(self):
        hits = [ln for ln in self.build_sh.splitlines()
                if "dump badging" in ln and not ln.lstrip().startswith("#")]
        self.assertEqual(len(hits), 1, hits)
        self.assertTrue(hits[0].rstrip().endswith("|| true"), hits[0])

    def test_link_accepts_new_value_resources(self):
        # Found by the first real build of the Hearth redesign (Nov 3):
        # the app's compiled resources reach `aapt2 link` as an overlay
        # (-R), and an overlay may not add a resource the base lacks —
        # so the new values/colors.xml (the launcher's ember background)
        # failed with "does not override an existing resource". The
        # link step must auto-add overlay resources.
        link = self.build_sh.split('"$BT/aapt2" link', 1)[1].split("\n\n", 1)[0]
        self.assertIn("-R ", link)
        self.assertIn("--auto-add-overlay", link)

    def test_wrong_jdk_fails_fast_naming_the_fix(self):
        # Found the same day: JDK 21's javac gives anonymous-class
        # constructors a Signature attribute that build-tools 34's d8
        # crashes on (an NPE deep in R8, naming MainActivity$25). The
        # script asks for JDK 17; it must check before compiling and
        # say which JAVA_HOME to use instead of dying inside d8.
        pre = self.build_sh.split('echo "== native', 1)[0]
        self.assertIn("javac -version", pre)
        self.assertIn("JDK 17", pre)
        self.assertIn("JAVA_HOME", pre)
        self.assertIn("exit 1", pre.split("javac -version", 1)[1])


CLOUD_UPLOADER = os.path.join(ROOT, "app", "android", "app", "src", "main",
                              "java", "com", "heartmadebakery", "unwritten",
                              "CloudUploader.java")
SIGNER = os.path.join(ROOT, "app", "cloud-signer", "worker.js")
ANDROID_MANIFEST = os.path.join(ROOT, "app", "android", "app", "src", "main",
                                "AndroidManifest.xml")


class CloudWebTests(unittest.TestCase):
    """Optional Cloud upload (Oct 2026): local save stays first;
    Cloud only ever receives a copy, and only when turned on."""

    @classmethod
    def setUpClass(cls):
        # User-ordered Oct 31: one page per screen; cloud logic in the
        # shared core. User-ordered Nov 1: cloud lives on the record
        # page, settings behind an advanced link.
        cls.page = read(REC_RECORD)
        cls.home = read(WEB)
        cls.common = read(REC_COMMON)
        cls.pagejs = read(REC_RECORD_JS)

    def test_cloud_is_opt_in_with_settings(self):
        self.assertIn('id="cloudtoggle"', self.page)
        self.assertIn('id="cloudpanel"', self.page)
        self.assertIn('id="advancedlink"', self.page)
        self.assertIn("cloudReady()", self.common)
        self.assertIn("CLOUD_SIGNER_DEFAULT", self.common)
        self.assertIn("data-cloud-delete", self.common)
        self.assertIn("cloudDeleteLesson", self.common)
        self.assertNotIn("a.click()", self.pagejs)

    def test_advanced_settings_are_read_only_debug_info(self):
        # User-ordered Nov 4: a stale saved signer URL once broke
        # every cloud request, so connection values no longer persist
        # anywhere — they load fresh from the stamped build on every
        # load, and Advanced settings only shows them for debugging.
        for token in ['id="clouddbgurl"', 'id="clouddbgtoken"']:
            self.assertIn(token, self.page, token)
        for token in ['id="cloudsigner"', 'id="cloudsignertoken"',
                      'id="cloudlib"', 'id="cloudkey"',
                      '$("cloudsigner")', '$("cloudlib")',
                      '$("cloudsignertoken")', '$("cloudkey")']:
            self.assertNotIn(token, self.page, token)
            self.assertNotIn(token, self.pagejs, token)

    def test_build_stamps_the_shared_core(self):
        # User-ordered Oct 31: the signer token placeholder lives in
        # exactly one place — common.js — and build.sh stamps the
        # served copy. No page carries its own placeholder.
        self.assertIn('var CLOUD_SIGNER_TOKEN_DEFAULT = "";', self.common)
        self.assertNotIn("CLOUD_SIGNER_TOKEN_DEFAULT", self.home)
        self.assertNotIn("CLOUD_SIGNER_TOKEN_DEFAULT", self.page)
        build = read(os.path.join(ROOT, "app", "recorder", "build.sh"))
        self.assertIn("dist/common.js", build)

    def test_upload_uses_presigned_tus(self):
        self.assertIn("https://video.bunnycdn.com/tusupload", self.common)
        self.assertIn("AuthorizationSignature", self.common)
        self.assertIn("AuthorizationExpire", self.common)
        self.assertIn("Upload-Offset", self.common)

    def test_streaming_link_is_cloud_embed(self):
        self.assertIn("https://player.mediadelivery.net/embed/", self.common)

    def test_local_save_still_comes_first(self):
        # The vault write and download copy stay; Cloud hooks after them.
        save = self.common.split("function saveBlob", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("idbPut", save)
        self.assertLess(save.index("idbPut"), save.index("startCloudUpload"))

    def test_connection_values_come_from_the_build(self):
        # User-ordered Nov 4: the signer URL and token load fresh from
        # the stamped build on every load — no saved override can
        # shadow them. Direct library-key mode is gone with the
        # overrides: every upload signs through the signer.
        for token in ["function cloudSignerUrl(){ return CLOUD_SIGNER_DEFAULT; }",
                      "function cloudToken(){ return CLOUD_SIGNER_TOKEN_DEFAULT; }"]:
            self.assertIn(token, self.common, token)
        for token in ["cloudCfg.signerUrl", "cloudCfg.signerToken",
                      "cloudCfg.libraryId", "cloudCfg.apiKey",
                      "cloudUseDirect", '"AccessKey"',
                      "video.bunnycdn.com/library"]:
            self.assertNotIn(token, self.common, token)

    def test_upload_fails_fast_without_credentials(self):
        # Fresh installs (Cloud on, no token yet) must not fire doomed
        # uploads that can only 401: cloudCanUpload gates the attempt,
        # and the failure names the rebuild instead of staying silent —
        # the same contract Android and iOS keep.
        for token in ["cloudCanUpload", "Cloud credentials missing",
                      "Rebuild the app to stamp one"]:
            self.assertIn(token, self.common, token)
        start = self.common.split("async function startCloudUpload", 1)[1]
        self.assertLess(start.index("cloudCanUpload"),
                        start.index("cloudCreds"))

    def test_enabling_cloud_sweeps_the_backlog(self):
        # Sessions recorded while Cloud was off (or failed) still
        # need their copy when Cloud comes back on — without a sweep
        # they would stay local-only forever, silently.
        self.assertIn("function sweepBacklog", self.pagejs)
        toggle = self.pagejs.split('$("cloudtoggle").onclick', 1)[1] \
                            .split('$("advancedlink").onclick', 1)[0]
        self.assertIn("sweepBacklog()", toggle)

    def test_processing_timeout_offers_retry(self):
        # pollCloudStatus must not leave a session on "…" forever when
        # Cloud never finishes preparing the stream: the poll ends in
        # the failed state (the ! retry action) with a reason.
        poll = self.common.split("async function pollCloudStatus", 1)[1] \
                          .split("async function startCloudUpload", 1)[0]
        self.assertIn("taking too long", poll)
        self.assertIn('"failed"', poll)

    def test_delete_offers_device_only_when_cloud_unreachable(self):
        # A dead cloud delete must not trap local storage: the user
        # gets a second confirm to delete this device's copy anyway
        # (the cloud copy stays where it is).
        delete = self.common.split("async function cloudDeleteLesson", 1)[1] \
                            .split("function cloudResumePending", 1)[0]
        self.assertIn("anyway", delete)


class CloudAndroidTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.main = read(MAIN)
        cls.uploader = read(CLOUD_UPLOADER)
        cls.manifest = read(ANDROID_MANIFEST)

    def test_internet_permission_added_for_upload_only(self):
        self.assertIn("android.permission.INTERNET", self.manifest)

    def test_uploader_speaks_presigned_tus(self):
        self.assertIn("https://video.bunnycdn.com/tusupload", self.uploader)
        self.assertIn("AuthorizationSignature", self.uploader)
        # User-ordered Nov 4: signer-only — nothing signs locally, so
        # the direct-mode SHA-256 helper is gone with the overrides.
        self.assertNotIn("SHA-256", self.uploader)
        self.assertNotIn("sha256Hex", self.uploader)

    def test_main_activity_gates_upload_behind_settings(self):
        self.assertIn("CloudUploader", self.main)
        self.assertIn("cloudEnabledCfg", self.main)
        self.assertIn("maybeCloudUpload", self.main)
        self.assertIn("CLOUD_SIGNER_DEFAULT", self.main)
        self.assertIn("CloudConfig.CLOUD_SIGNER_TOKEN_DEFAULT", self.main)
        self.assertIn("confirmDeleteLesson", self.main)
        self.assertIn("deleteLesson", self.main)
        # User-ordered Nov 4: no saved connection overrides — the
        # build constants are the whole config.
        for token in ['cloudCfgString("signerUrl")',
                      'cloudCfgString("signerToken")',
                      'cloudCfgString("libraryId")',
                      'cloudCfgString("apiKey")']:
            self.assertNotIn(token, self.main, token)

    def test_share_never_serves_another_lesson_link(self):
        # The lastLink fallback must be scoped to the same lesson:
        # sharing lesson B's URL under lesson A's name is a mixup.
        # And a link is only published when the library id is known
        # (no embed//videoId links).
        share = self.main.split("private void shareCloudLinkFor", 1)[1] \
                         .split("\n    private ", 1)[0]
        self.assertIn('getString("lastName"', share)
        finished = self.main.split("private void cloudFinished", 1)[1] \
                            .split("\n    private ", 1)[0]
        self.assertIn("!lib.isEmpty()", finished)

    def test_poll_timeout_and_errors_offer_retry(self):
        # A resumed poll must not sit on "…" forever when Cloud never
        # finishes, nor spin for ten minutes on dead status checks:
        # both end in the failed state (the ! retry action).
        poll = self.main.split("private void pollCloud", 1)[1] \
                        .split("\n    private ", 1)[0]
        self.assertIn("taking too long", poll)
        self.assertIn("kept failing", poll)
        self.assertIn("kept failing", read(CLOUD_UPLOADER))

    def test_delete_cancels_polls_and_ignores_stragglers(self):
        # Deleting mid-poll must stop the poll, and any late upload
        # or poll completion for a deleted file must not resurrect
        # its link row.
        self.assertIn("cloudPollTasks", self.main)
        delete = self.main.split("private void deleteLesson", 1)[1] \
                          .split("private void removeLocalSession", 1)[0]
        self.assertIn("removeLocalSession(", delete)
        local = self.main.split("private void removeLocalSession", 1)[1] \
                         .split("\n    private ", 1)[0]
        self.assertIn("cancel(true)", local)
        finished = self.main.split("private void cloudFinished", 1)[1] \
                            .split("\n    private ", 1)[0]
        failed = self.main.split("private void cloudFailed", 1)[1] \
                          .split("\n    private ", 1)[0]
        for region in (finished, failed):
            self.assertIn("!new File(clipsDir, name).exists()", region)

    def test_enabling_cloud_sweeps_the_backlog(self):
        # Sessions recorded while Cloud was off (or failed) still
        # need their copy when Cloud comes back on — without a sweep
        # they would stay local-only forever, silently.
        self.assertIn("sweepBacklog()", self.main)
        toggle = self.main.split("private void toggleCloudEnabled", 1)[1] \
                          .split("\n    private ", 1)[0]
        self.assertIn("sweepBacklog()", toggle)

    def test_delete_offers_device_only_when_cloud_unreachable(self):
        # A dead cloud delete must not trap local storage: the user
        # gets a second confirm to delete this phone's copy anyway
        # (the cloud copy stays where it is).
        delete = self.main.split("private void deleteLesson", 1)[1] \
                          .split("\n    // ----------", 1)[0]
        self.assertIn("Delete from phone", delete)
        self.assertIn("removeLocalSession(", self.main)

    def test_linked_rows_keep_their_download(self):
        # Cloud-linking a session must not remove its on-device
        # download: ready rows keep ↓ next to ↗.
        ready = self.main.split("} else if (isReady) {", 1)[1] \
                         .split("} else {", 1)[0]
        self.assertIn("downloadSingle", ready)

    def test_stop_defers_upload_until_take_finalizes(self):
        # MediaRecorder.stop runs on the camera thread; listing and
        # uploading inline would catch a partial file. The upload
        # waits for the stop-completion callback.
        self.assertIn("stopVideo(final Runnable onStopped)", read(ENGINE))
        stop = self.main.split("private void stopRecording", 1)[1] \
                        .split("\n    // ----------", 1)[0]
        self.assertIn("stopVideo(new Runnable", stop)
        self.assertIn("maybeCloudUpload(lastLessonFile)", stop)

    def test_camera_errors_reset_failed_start_ui(self):
        # startVideo() returns once posted: when the internal start
        # fails, the error path must put the button and timer back
        # instead of stranding them on "recording".
        err = self.main.split("public void onError(final String message)",
                              1)[1].split("@Override", 1)[0]
        self.assertIn("removeCallbacks(timerRunnable)", err)

    def test_export_cleans_pending_rows_and_continues(self):
        # A failed file must not orphan its IS_PENDING row in
        # Downloads, leak its streams, or abort the files after it.
        exp = self.main.split("private void doExport", 1)[1] \
                       .split("\n    // ----------", 1)[0]
        self.assertIn("cr.delete(uri, null, null)", exp)
        loop = exp.split("for (File f : files)", 1)[1]
        self.assertIn("catch (Throwable e)", loop)
        self.assertIn("finally", loop)

    def test_external_playback_uses_content_uris(self):
        # file:// intents reach external players unreadable on
        # Android 7+ (no grant possible); the StrictMode bypass only
        # silenced the sender-side crash. Playback goes through the
        # read-only provider with a real read grant.
        self.assertNotIn("Uri.fromFile", self.main)
        self.assertNotIn("setVmPolicy", self.main)
        play = self.main.split("private void fallbackExternalPlay", 1)[1] \
                        .split("\n    private ", 1)[0]
        self.assertIn("TinyFileProvider", play)
        self.assertIn("FLAG_GRANT_READ_URI_PERMISSION", play)

    def test_file_provider_declared_and_guarded(self):
        manifest = read(ANDROID_MANIFEST)
        self.assertIn("TinyFileProvider", manifest)
        # User-ordered Nov 4: the app ID (and so the authority) moved to
        # com.heartmadebakery.unwritten; the provider and manifest agree.
        self.assertIn("com.heartmadebakery.unwritten.files", manifest)
        self.assertIn('"com.heartmadebakery.unwritten.files"', read(PROVIDER))
        prov = read(PROVIDER)
        for token in ["getCanonicalPath", "MODE_READ_ONLY",
                      "OpenableColumns", "uriForFile"]:
            self.assertIn(token, prov, token)

    def test_background_releases_camera_and_foreground_reopens(self):
        # The camera must not be held in the background; returning
        # reopens it. A stop still finalizing when the app stops
        # closes the engine from its completion callback instead.
        self.assertIn("protected void onStop()", self.main)
        self.assertIn("protected void onStart()", self.main)
        onstop = self.main.split("protected void onStop()", 1)[1] \
                          .split("protected void ", 1)[0]
        onstart = self.main.split("protected void onStart()", 1)[1] \
                           .split("protected void ", 1)[0]
        self.assertIn("engine.close()", onstop)
        self.assertIn("openPreview()", onstart)
        stop = self.main.split("private void stopRecording", 1)[1] \
                        .split("\n    // ----------", 1)[0]
        self.assertIn("activityStopped", stop)

    def test_configured_needs_a_token_in_signer_mode(self):
        # The signer URL always has a compiled default, so URL-alone
        # must not count as configured (same contract as canUpload):
        # the token decides — otherwise credential-less builds fire
        # doomed uploads and hide the offline Export fallback.
        # User-ordered Nov 4: signer-only, no direct mode left.
        cfg = self.uploader.split("public boolean configured()", 1)[1] \
                           .split("public ", 1)[0]
        self.assertIn("signerToken", cfg)
        self.assertNotIn("if (!signerUrl.isEmpty()) return true;", cfg)
        for token in ["useDirect", "apiKey", "AccessKey"]:
            self.assertNotIn(token, self.uploader, token)

    def test_link_writes_are_serialized(self):
        # Upload callbacks persist from the cloud pool while the UI
        # thread writes too: the links blob's read-modify-write must
        # synchronize, or a late progress write clobbers finished
        # state back to uploading.
        writes = self.main.split("private void setCloudLink", 1)[1] \
                          .split("private String cloudSuffix", 1)[0]
        self.assertIn("synchronized (cloudLinkLock)", writes)
        deletes = self.main.split("private void delCloudLink", 1)[1] \
                           .split("private void confirmDeleteLesson", 1)[0]
        self.assertIn("synchronized (cloudLinkLock)", deletes)

    def test_cloud_settings_screen_exists(self):
        # Error and hub messages send the user to "Cloud settings" —
        # the dialog must exist. User-ordered Nov 1: it hides behind
        # a small Advanced settings link instead of a full button.
        # User-ordered Nov 4: read-only debug info — no fields, no
        # saving, no override shadowing; values load from the build.
        self.assertIn("showCloudSettings()", self.main)
        self.assertIn("Advanced settings", self.main)
        dlg = self.main.split("private void showCloudSettings", 1)[1] \
                       .split("\n    private ", 1)[0]
        self.assertIn("cloudEffSignerUrl()", dlg)
        for token in ["EditText", "putString(", "settingsField(",
                      "sweepBacklog()"]:
            self.assertNotIn(token, dlg, token)


class AndroidScreensTests(unittest.TestCase):
    """Single-app restructure: home lands on the hub with Record and
    Upload above it; record owns the camera; a picked video rides the
    take path (clips folder, then Cloud) like a recording."""

    @classmethod
    def setUpClass(cls):
        cls.main = read(MAIN)
        cls.names = read(NAMES)

    def test_home_is_the_landing_with_record_and_upload_above_hub(self):
        self.assertIn("Record, upload, and revisit craft lessons.", self.main)
        self.assertNotIn("Film mentor session. Record and let it happen.", self.main)
        created = self.main.split("protected void onCreate", 1)[1] \
                           .split("protected void onPause", 1)[0]
        self.assertIn('showScreen("home")', created)
        self.assertNotIn("openPreview()", created)
        home = self.main.split("private void buildHomeScreen", 1)[1] \
                        .split("private void buildRecordScreen", 1)[0]
        record = self.main.split("private void buildRecordScreen", 1)[1] \
                          .split("// ---------- permissions", 1)[0]
        self.assertLess(home.index("Upload video"), home.index("Hub sessions"))
        # User-ordered Nov 1: the hub is last on home; cloud + device
        # sessions moved to the record screen.
        self.assertNotIn("This device", home)
        self.assertIn("This device", record)

    def test_record_screen_owns_and_releases_the_camera(self):
        show = self.main.split("private void showScreen", 1)[1] \
                        .split("\n    private ", 1)[0]
        for token in ["stopRecording()", "engine.close()", "hasPermissions()",
                      "openPreview()", "refreshClipList()", "loadHub()"]:
            self.assertIn(token, show, token)
        # User-ordered Nov 1 (native-feel goal): the "‹ Home" button
        # became the ActionBar up arrow (android.R.id.home), which
        # routes through onBackPressed like the system back does.
        self.assertNotIn("‹ Home", self.main)
        self.assertIn("android.R.id.home", self.main)
        started = self.main.split("protected void onStart", 1)[1] \
                           .split("protected void onDestroy", 1)[0]
        self.assertIn('"record".equals(currentScreen)', started)

    def test_upload_picker_saves_like_a_take(self):
        for token in ["ACTION_GET_CONTENT", '"video/*"', "onActivityResult",
                      "uploadName"]:
            self.assertIn(token, self.main, token)
        self.assertIn("uploadName", self.names)
        self.assertIn("unwritten_lesson_upload_", self.names)
        save = self.main.split("private void savePickedVideo", 1)[1] \
                        .split("\n    // ----------", 1)[0]
        for token in ["isn't a video", "copyStream", "refreshClipList()",
                      "maybeCloudUpload"]:
            self.assertIn(token, save, token)
        self.assertLess(save.index("copyStream"), save.index("maybeCloudUpload"))

    def test_back_and_playback_return_through_home(self):
        back = self.main.split("void onBackPressed", 1)[1] \
                        .split("private String cloudWatchUrl", 1)[0]
        self.assertIn('showScreen("home")', back)
        play = self.main.split("private void playInViewfinder", 1)[1] \
                        .split("private void playLocalLesson", 1)[0]
        self.assertIn('showScreen("record")', play)


class AndroidNativeFeelTests(unittest.TestCase):
    """User-ordered Nov 1 (goal: apps feel native and intuitive).

    Android gets Material touches without AndroidX: an ActionBar with
    the up arrow (and the camera switch as a menu action), themed
    system bars, rounded ripple buttons instead of flat color blocks,
    a real Switch for Cloud, card-style lists with ripple rows, and
    48dp touch targets. Source-only: this host has no Android SDK, so
    these tests are the contract and the build is the next machine's."""

    @classmethod
    def setUpClass(cls):
        cls.main = read(MAIN)
        cls.manifest = read(ANDROID_MANIFEST)
        cls.home = cls.main.split("private void buildHomeScreen", 1)[1] \
                           .split("private void buildRecordScreen", 1)[0]
        cls.record = cls.main.split("private void buildRecordScreen", 1)[1] \
                             .split("// ---------- permissions", 1)[0]

    def test_theme_has_an_action_bar(self):
        # User-ordered Nov 2 (Hearth redesign, docs/DESIGN.md): the
        # always-dark Theme.Material became DeviceDefault.DayNight, so
        # dialogs, toasts and widgets follow the system's light/dark
        # setting along with the app's own palette. Still an ActionBar.
        self.assertIn("@android:style/Theme.DeviceDefault.DayNight", self.manifest)
        self.assertNotIn("NoActionBar", self.manifest)
        for token in ["getActionBar()", "setDisplayHomeAsUpEnabled",
                      "onOptionsItemSelected", "android.R.id.home",
                      "setStatusBarColor", "setNavigationBarColor"]:
            self.assertIn(token, self.main, token)

    def test_camera_switch_is_a_menu_action(self):
        for token in ["onCreateOptionsMenu", "onPrepareOptionsMenu",
                      "MENU_CAMERA", "SHOW_AS_ACTION_ALWAYS"]:
            self.assertIn(token, self.main, token)
        self.assertNotIn("camToggle = button(", self.record)

    def test_buttons_are_rounded_with_ripple(self):
        for token in ["RippleDrawable", "GradientDrawable", "setCornerRadius",
                      "setStateListAnimator(null)"]:
            self.assertIn(token, self.main, token)
        # Flat setBackgroundColor on a Button kills touch feedback.
        for region in (self.home, self.record):
            self.assertNotIn("Button.setBackgroundColor", region)
            self.assertNotIn("recordButton.setBackgroundColor", region)
            self.assertNotIn("exportBtn.setBackgroundColor", region)

    def test_record_is_the_primary_action(self):
        # User-ordered Nov 2 (Hearth redesign): home's Record is the
        # filled ember action tile; the record screen keeps the shared
        # primaryButton("● Record") label, drawn as the shutter.
        self.assertIn('actionTile("Record"', self.home)
        tile = self.home.split('actionTile("Record"', 1)[1].split(");", 1)[0]
        self.assertIn("true", tile)  # primary: filled ember
        self.assertIn('primaryButton("● Record"', self.record)

    def test_cloud_is_a_real_switch_that_only_acts_on_change(self):
        self.assertIn("android.widget.Switch cloudToggleButton", self.main)
        self.assertIn("setOnCheckedChangeListener", self.main)
        paint = self.main.split("private void paintCloudToggle", 1)[1] \
                         .split("\n    private ", 1)[0]
        self.assertIn("setChecked(", paint)
        self.assertNotIn("Cloud: on", self.main)
        self.assertIn("isChecked != cloudEnabledCfg()", self.main)

    def test_lists_are_cards_with_ripple_rows_and_an_empty_state(self):
        self.assertIn("rowRipple()", self.main)
        refresh = self.main.split("private void refreshClipList", 1)[1] \
                           .split("private String mimeFor", 1)[0]
        self.assertIn("rowRipple()", refresh)
        self.assertIn("Nothing yet.", refresh)
        self.assertIn("lessonContainer.setBackground(", self.record)
        self.assertIn("hubContainer.setBackground(", self.home)

    def test_touch_targets_are_48dp(self):
        self.assertIn("dp(48)", self.main)
        self.assertNotIn("LayoutParams(dp(40), dp(36))", self.main)


class CloudSignerTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.worker = read(SIGNER)

    def test_signer_holds_key_and_signs(self):
        self.assertIn("CLOUD_API_KEY", self.worker)
        self.assertIn("SHA-256", self.worker)
        self.assertIn("player.mediadelivery.net/embed/", self.worker)
        self.assertIn("SIGNER_TOKENS", self.worker)
        self.assertIn('"DELETE"', self.worker)

    def test_signer_supports_resume_and_status(self):
        self.assertIn("videoId", self.worker)
        self.assertIn("X-Signer-Token", self.worker)


class WebAndroidParityTests(unittest.TestCase):
    """The web app mirrors the native Android app's design.

    Same dark palette, same home landing (Record + Upload above the
    hub, then cloud and device sessions), same session-row contract:
    newest first, date + duration, tap to play in the viewfinder,
    long-press to delete, per-lesson share/download.
    """

    @classmethod
    def setUpClass(cls):
        # User-ordered Oct 31: one page per screen; style in app.css,
        # logic split between the shared core and per-page scripts.
        cls.home = read(WEB)
        cls.record = read(REC_RECORD)
        cls.common = read(REC_COMMON)
        cls.homejs = read(REC_HOME_JS)
        cls.recordjs = read(REC_RECORD_JS)
        cls.css = read(REC_CSS)
        cls.manifest = read(MANIFEST)

    def test_android_dark_palette(self):
        # User-ordered Nov 2 (Hearth redesign, docs/DESIGN.md): the one
        # dark palette became warm paper with a matching dark set that
        # follows the system — the same tokens as Android and iOS.
        light, dark = self.css.split("@media (prefers-color-scheme: dark)", 1)
        for color in ["#FAF6F1", "#FFFFFF", "#2A211C", "#6F625A", "#D2452A"]:
            self.assertIn(color, light, color)
        for color in ["#171310", "#221C18", "#F7EFE6", "#B9AA9C", "#FF8A6B"]:
            self.assertIn(color, dark, color)
        self.assertIn("color-scheme:light dark", self.css)

    def test_title_and_sessions_wording(self):
        # Post-restructure contract (user-ordered): the app is Unwritten
        # Craft, landing on Record/Upload actions with the hub last.
        # User-ordered Nov 1: device sessions sit on the record page
        # under "This device", not a recorder "Sessions" list.
        self.assertIn("Record, upload, and revisit craft lessons.", self.home)
        self.assertNotIn("Film mentor session. Record and let it happen.", self.home)
        self.assertIn(">Hub<", self.home)
        self.assertIn(">This device<", self.record)
        self.assertNotIn("This device", self.home)
        self.assertNotIn("Lessons on this device", self.home)

    def test_zoom_row_below_viewfinder(self):
        for token in ['id="zoomrow"', 'id="zoomseek"', 'id="zoomlabel"']:
            self.assertIn(token, self.record, token)
        self.assertLess(self.record.index('id="zoomrow"'),
                        self.record.index('id="recbtn"'))

    def test_in_viewfinder_playback(self):
        self.assertIn('id="player"', self.record)
        self.assertIn('id="playercontrols"', self.record)
        self.assertIn("playInViewfinder", self.common)
        self.assertIn("stopLocalPlayback", self.common)
        # User-ordered Nov 1: rows live on the record page and play
        # directly; ?play= still deep-links from a fresh load.
        self.assertIn("playInViewfinder(row.getAttribute", self.recordjs)
        self.assertIn("?play=", self.recordjs)

    def test_stop_button_carries_timer_like_android(self):
        self.assertIn("■ Stop  ", self.recordjs)

    def test_export_visible_only_when_cloud_off(self):
        self.assertIn('id="exportbtn"', self.record)
        self.assertIn("Export sessions to Downloads", self.record)

    def test_session_rows_newest_first_with_date_and_duration(self):
        for token in ["leftIconFor", "displayDateFor", "durationFor"]:
            self.assertIn(token, self.common, token)

    def test_long_press_deletes_like_android(self):
        self.assertIn("confirmDeleteLesson", self.common)
        self.assertIn("armPress", self.recordjs)

    def test_share_uses_cloud_link(self):
        self.assertIn("shareCloudLinkFor", self.common)

    def test_manifest_uses_android_theme_color(self):
        # User-ordered Nov 2 (Hearth redesign): the canvas colour, with
        # light/dark theme-color metas on every page.
        self.assertIn("#FAF6F1", self.manifest)
        for page in (self.home, self.record):
            self.assertIn('content="#FAF6F1" media="(prefers-color-scheme: light)"', page)
            self.assertIn('content="#171310" media="(prefers-color-scheme: dark)"', page)

    def test_live_mic_check_warns_after_quiet_minute(self):
        self.assertIn('id="speechwarn"', self.record)
        for token in ["startSpeechMonitor", "stopSpeechMonitor",
                      "getFloatTimeDomainData", "60000"]:
            self.assertIn(token, self.recordjs, token)


class AndroidSyncTests(unittest.TestCase):
    """Android parity sync (Nov 1, user-ordered): the Android app catches
    up with the web and iOS apps' behaviors, in Android idioms
    (ActionBar + Up, dialog players, ripples, launcher icon)."""

    RES = os.path.join(ROOT, "app", "android", "app", "src", "main", "res")

    @classmethod
    def setUpClass(cls):
        cls.main = read(MAIN)
        cls.manifest = read(ANDROID_MANIFEST)
        cls.build_sh = read(os.path.join(ROOT, "app", "android", "build.sh"))
        cls.home = cls.main.split("private void buildHomeScreen", 1)[1] \
                           .split("private void buildRecordScreen", 1)[0]
        cls.record = cls.main.split("private void buildRecordScreen", 1)[1] \
                             .split("// ---------- permissions", 1)[0]

    def test_hub_playback_own_player_with_hls(self):
        # Watching a published lesson never opens the camera (iOS hub
        # screen, web home player): hub playback gets its own dialog
        # player, trying mp4 then HLS, with the Cloud embed fallback.
        play = self.main.split("private void playHubRemote", 1)[1] \
                        .split("\n    private ", 1)[0]
        self.assertIn("hlsUrl", play)
        self.assertIn("AlertDialog", play)
        self.assertNotIn('showScreen("record")', play)

    def test_rec_badge_overlays_viewfinder(self):
        # iOS and the web badge REC + elapsed over the viewfinder; the
        # Stop button text alone is not enough.
        self.assertIn("recBadge", self.main)
        self.assertIn('"● REC"', self.record)
        toggle = self.main.split("private void toggleRecord", 1)[1] \
                          .split("\n    private ", 1)[0]
        stop = self.main.split("private void stopRecording", 1)[1] \
                        .split("\n    // ----------", 1)[0]
        self.assertIn("recBadge", toggle)
        self.assertIn("recBadge", stop)

    def test_zoom_row_hidden_without_range(self):
        # iOS and the web hide the zoom row when the camera reports no
        # zoom range, so it is never dead UI.
        self.assertIn("zoomRow", self.main)
        zu = self.main.split("private void refreshZoomUi", 1)[1] \
                      .split("\n}", 1)[0]
        self.assertIn("zoomRow", zu)
        self.assertIn("View.GONE", zu)

    def test_player_controls_close_button(self):
        # Web and iOS player controls carry ▶ / ⏸ / ✕; Android's Back
        # button alone hides the close action.
        self.assertIn('"✕"', self.record)

    def test_hub_refresh_action(self):
        # iOS pulls to refresh; Android (no SwipeRefreshLayout without
        # AndroidX) offers a refresh action on the hub header instead of
        # reloading only when home is re-entered. User-ordered Nov 2
        # (Hearth redesign): the ⟳ text became a drawn glyph button
        # with a spoken label.
        self.assertIn("Glyphs.REFRESH", self.home)
        self.assertIn('"Refresh the hub"', self.home)
        self.assertIn("loadHub()", self.home)

    def test_device_empty_state(self):
        # iOS and the web say "Nothing yet."; an empty device list must
        # not render as a bare header.
        rows = self.main.split("private void refreshClipList", 1)[1] \
                        .split("\n    private ", 1)[0]
        self.assertIn("Nothing yet.", rows)

    def test_denial_points_to_settings(self):
        # A denied permission that stays denied needs Settings, like
        # iOS says — not just a repeat of the request.
        denied = self.main.split("public void onRequestPermissionsResult",
                                 1)[1].split("\n    // ----------", 1)[0]
        self.assertIn("Settings", denied)

    def test_action_bar_titles_and_up(self):
        # Android idiom: the ActionBar carries the screen title and the
        # Up button off the record screen (iOS's NavigationStack back).
        # User-ordered Nov 2 (Hearth redesign): DayNight, not dark-only.
        self.assertIn('android:theme="@android:style/Theme.DeviceDefault.DayNight"',
                      self.manifest)
        self.assertIn("setDisplayHomeAsUpEnabled", self.main)
        self.assertIn("android.R.id.home", self.main)
        show = self.main.split("private void showScreen", 1)[1] \
                        .split("\n    private ", 1)[0]
        self.assertIn("setTitle(", show)
        # User-ordered Nov 2 (Hearth redesign): home carries its own
        # greeting and large title (Material's expanded large app bar),
        # so the bar steps aside there and returns with Up on Record.
        self.assertIn("bar.hide()", show)
        self.assertIn("bar.show()", show)

    def test_launcher_icon(self):
        # The worklog's open icon item: an adaptive icon (minSdk 29
        # needs no legacy PNGs), wired into the manifest and the
        # manual build's aapt2 resource step.
        self.assertIn('android:icon="@mipmap/ic_launcher"', self.manifest)
        self.assertTrue(os.path.isfile(os.path.join(
            self.RES, "mipmap-anydpi-v26", "ic_launcher.xml")))
        self.assertTrue(os.path.isfile(os.path.join(
            self.RES, "drawable", "uw_icon_fg.xml")))
        self.assertIn("compile --dir", self.build_sh)

    def test_record_button_is_the_primary_action(self):
        # The camera idiom: one filled red Record action, restyled for
        # both states instead of a plain panel button with new text.
        # Merge Nov 1: the native-feel pass's paint (ripple + BRIGHT,
        # recording goes dark with red text) stands over this sync's
        # GradientDrawable + RED original.
        self.assertIn("paintRecordButton", self.main)
        paint = self.main.split("private void paintRecordButton", 1)[1] \
                         .split("\n    private ", 1)[0]
        self.assertIn("ripple(", paint)
        self.assertIn("BRIGHT", paint)

    def test_rows_use_ripple(self):
        # Touch feedback is the Android idiom: session and hub rows
        # ripple instead of sitting on flat color.
        # Merge Nov 1: the native-feel pass's real RippleDrawable rows
        # stand over this sync's selectableItemBackground original.
        self.assertIn("rowRipple()", self.main)
        self.assertIn("RippleDrawable", self.main)

    def test_hub_card_has_elevation(self):
        # The hub detail reads as a Material card, not a flat panel.
        card = self.main.split("private View hubDetailView", 1)[1] \
                        .split("\n    private ", 1)[0]
        self.assertIn("setElevation", card)

    def test_hub_stream_sends_referer(self):
        # Merge Nov 1 (from the iOS playback fix): the Cloud CDN's
        # hotlink protection 403s streams without the player page as
        # Referer, so the dialog player sends the embed URL with the
        # stream request instead of failing to the browser fallback.
        play = self.main.split("private void playHubRemote", 1)[1] \
                        .split("\n    private ", 1)[0]
        self.assertIn("Referer", play)

    def test_link_field_submits_from_go(self):
        # Merge Nov 1 (iOS parity): the link field's keyboard Go
        # submits the queue action — the IME option alone is a dead key.
        self.assertIn("OnEditorActionListener", self.home)
        self.assertIn("IME_ACTION_GO", self.home)
        self.assertIn("queueFetchUrl", self.home)

    def test_device_playback_scrolls_the_viewfinder_into_view(self):
        # Merge Nov 1 (from the iOS playback fix): a row tapped below
        # the fold used to play in an off-screen viewfinder — the
        # record screen scrolls to the top so the video is visible.
        play = self.main.split("private void playInViewfinder", 1)[1] \
                        .split("\n    private ", 1)[0]
        self.assertIn("smoothScrollTo", play)


class WebNativeFeelTests(unittest.TestCase):
    """User-ordered Nov 1 (goal: apps feel native and intuitive).

    The web app reads as a mobile app, not a styled web page: a large
    title on home, a top bar with a back chevron on the other pages,
    grouped inset lists, a real switch for Cloud, a round shutter-style
    record button, 44px+ touch targets, and visible keyboard focus.
    Every element ID the scripts query is unchanged."""

    @classmethod
    def setUpClass(cls):
        cls.home = read(WEB)
        cls.record = read(REC_RECORD)
        cls.upload = read(REC_UPLOAD)
        cls.css = read(REC_CSS)
        cls.common = read(REC_COMMON)
        cls.recordjs = read(REC_RECORD_JS)
        cls.sw = read(SW)

    def test_home_has_large_title_others_have_topbar_with_back(self):
        self.assertIn('class="largetitle"', self.home)
        for page, back in ((self.record, "backhome-record"),
                           (self.upload, "backhome-upload")):
            self.assertIn('class="topbar"', page)
            self.assertIn('id="%s"' % back, page)
            self.assertLess(page.index('class="topbar"'),
                            page.index('id="status"'))
            self.assertNotIn("‹ Home", page)

    def test_actions_are_a_grouped_list_with_chevrons(self):
        # User-ordered Nov 2 (Hearth redesign): home's actions became
        # two action tiles (Record filled ember, Upload on surface);
        # hub rows keep their chevrons as lesson cards.
        self.assertIn('class="tile primary" id="gorecord"', self.home)
        self.assertIn('class="tile" id="goupload"', self.home)
        self.assertIn(".tile.primary", self.css)
        self.assertIn(".chev", self.css)
        self.assertIn("class='chev'", self.common)

    def test_cloud_is_a_real_switch(self):
        self.assertIn('role="switch"', self.record)
        paint = self.common.split("function paintCloudToggle", 1)[1] \
                           .split("function stamp", 1)[0]
        self.assertIn("aria-checked", paint)
        self.assertNotIn("Cloud: on", paint)
        self.assertIn('[aria-checked="true"]', self.css)

    def test_record_button_is_a_round_shutter(self):
        # Text still carries "● Record" / "■ Stop m:ss" (shared with the
        # native apps); the shape and color come from CSS.
        self.assertIn("#recbtn", self.css)
        self.assertIn("border-radius:50%", self.css.split("#recbtn{", 1)[1]
                                                  .split("}", 1)[0])
        self.assertIn("#recbtn.stop", self.css)

    def test_touch_targets_and_keyboard_focus(self):
        self.assertIn("--tap:48px", self.css)
        self.assertIn(":focus-visible", self.css)
        self.assertIn("prefers-reduced-motion", self.css)

    def test_platform_class_set_for_native_leaning_styles(self):
        self.assertIn('classList.add("ios")', self.common)
        self.assertIn('classList.add("android")', self.common)
        self.assertIn("html.ios", self.css)
        self.assertIn("html.android", self.css)

    def test_service_worker_cache_bumped_for_the_restyle(self):
        # Merged Nov 2 sweep + Hearth + link page (user-ordered): v9
        # served scripts cache-first and cached the signer's API
        # answers; the same-origin network-first shell and the link
        # page ship as v12, dropping every older cache on activate.
        # User-ordered Nov 4: the link page folds back into upload,
        # so the shell ships as v13 — bumped past v12, never back.
        self.assertIn("unwritten-recorder-v13", self.sw)
        for old in ("unwritten-recorder-v9", "unwritten-recorder-v10",
                    "unwritten-recorder-v11", "unwritten-recorder-v12"):
            self.assertNotIn(old, self.sw)


class CameraEngineTests(unittest.TestCase):
    """Device-critical engine paths: partial takes, queued starts,
    mid-take rebuilds."""

    @classmethod
    def setUpClass(cls):
        cls.engine = read(ENGINE)

    def test_early_stop_drops_the_partial_take(self):
        # stop() throwing under ~700ms means no valid data was
        # written: the partial file must be deleted, never listed or
        # uploaded as a lesson.
        stop = self.engine.split("private void stopVideoInternal()", 1)[1] \
                          .split("private void releaseRecorder()", 1)[0]
        self.assertIn("recordingFile", stop)
        self.assertIn("elapsed < 700", stop)
        self.assertIn(".delete()", stop)

    def test_camera_failure_fails_a_queued_start(self):
        # A start queued while the camera opens must not stick
        # forever when the camera errors, disconnects, or fails to
        # configure — every later take would report "already queued".
        open_cb = self.engine.split("new CameraDevice.StateCallback()", 1)[1] \
                             .split("}, handler());", 1)[0]
        self.assertEqual(open_cb.count("failQueuedStart("), 2)
        cfg = self.engine.split("public void onConfigureFailed", 1)[1] \
                         .split("}, handler());", 1)[0]
        self.assertIn("failQueuedStart(", cfg)

    def test_no_rebuild_while_recording(self):
        # A surface resize mid-take must not rebuild the capture
        # session under the running recorder.
        size = self.engine.split("public void onSurfaceTextureSizeChanged", 1)[1] \
                          .split("public boolean onSurfaceTextureDestroyed", 1)[0]
        self.assertIn("recorderStartPending", size)

    def test_luma_changes_are_for_between_takes(self):
        # Attaching the luma output rebuilds the session — like iOS,
        # mid-take changes are refused instead of churning the take.
        luma = self.engine.split("public void setLumaListener", 1)[1] \
                          .split("public boolean startVideo", 1)[0]
        self.assertIn("between takes", luma)


class IgnoredBadgeTests(unittest.TestCase):
    """Ignored takes (user-ordered): the pipeline's operator set-asides
    sync to the hub, and every recorder badges matching takes on the
    Record screen instead of showing them in the hub. Match rule,
    everywhere: the take's cloud-link videoId, else its filename
    against the marker title (upload titles are filenames)."""

    @classmethod
    def setUpClass(cls):
        cls.common = read(REC_COMMON)
        cls.record_js = read(REC_RECORD_JS)
        cls.hub = read(HUB)
        cls.main = read(MAIN)

    def test_web_fetches_ignored_for_record_rows(self):
        self.assertIn("/hub/ignored", self.common)
        self.assertIn("ignoredMarks", self.common)
        self.assertIn("refreshIgnored", self.record_js)

    def test_web_badges_matching_rows(self):
        row = self.common.split("function clipHTML", 1)[1] \
                         .split("function renderClips", 1)[0]
        self.assertIn("ignoredFor", row)
        self.assertIn("ignored</span>", row)
        match = self.common.split("function ignoredFor", 1)[1] \
                            .split("function renderClips", 1)[0]
        self.assertIn("videoId", match)

    def test_web_ignored_fetch_respects_cloud_off(self):
        # Cloud off means no network calls (Android's loadIgnored
        # checks it); the badge fetch called the signer anyway.
        fetch = self.common.split("async function refreshIgnored", 1)[1] \
                           .split("function ignoredFor", 1)[0]
        self.assertLess(fetch.index("cloudEnabled()"), fetch.index("fetch("))
        # Toggling Cloud re-reads the marks: off clears the badges.
        toggle = self.record_js.split('$("cloudtoggle").onclick', 1)[1] \
                               .split("function sweepBacklog", 1)[0]
        self.assertIn("refreshIgnored()", toggle)

    def test_android_lists_ignored(self):
        self.assertIn("/hub/ignored", self.hub)
        self.assertIn("public JSONArray ignored()", self.hub)

    def test_android_badges_record_rows(self):
        self.assertIn("loadIgnored", self.main)
        rows = self.main.split("private void refreshClipList", 1)[1] \
                        .split("private String mimeFor", 1)[0]
        self.assertIn("ignored", rows)
        self.assertIn("ignoredReasonFor", rows)


class AndroidBugSweepTests(unittest.TestCase):
    """Nov 2 bug sweep: Android session-list and threading defects."""

    @classmethod
    def setUpClass(cls):
        cls.main = read(MAIN)

    def method(self, signature):
        return self.main.split(signature, 1)[1].split("\n    }\n", 1)[0]

    def test_camera_error_resets_the_ui_on_the_ui_thread(self):
        # CameraEngine reports errors from its camera thread: the
        # Record button/timer reset must hop to the UI thread, or the
        # view write throws (swallowed by the engine) and the button
        # keeps showing "■ Stop" after a failed start.
        on_error = self.main.split("public void onError(final String message)", 1)[1] \
                            .split("public void onMicUnavailable", 1)[0]
        self.assertIn("runOnUiThread", on_error)
        self.assertLess(on_error.index("runOnUiThread"),
                        on_error.index("recordButton.setText"))

    def test_every_upload_extension_is_listed(self):
        # savePickedVideo names an upload by its MIME type; a name
        # mimeFor does not know never lists — an .mkv upload sat in
        # the clips folder invisible, undeletable, yet uploaded.
        pick = self.method("private void savePickedVideo")
        mime = self.method("private String mimeFor")
        for ext in re.findall(r'ext = "(\w+)"', pick):
            self.assertIn('".%s"' % ext, mime, ext)

    def test_live_take_is_not_a_session(self):
        # MediaRecorder writes the take under its final name: until
        # the stop callback finalizes it, it is no session. Listed, it
        # cached an empty duration for good, could be tapped or
        # deleted mid-take, and a backlog sweep could upload it half
        # written.
        self.assertIn("liveTake", self.method("private List<File> clipFiles()"))
        sweep = self.method("private void sweepBacklog()")
        self.assertIn("clipFiles()", sweep)
        self.assertNotIn("listFiles()", sweep)
        toggle = self.method("private void toggleRecord()")
        self.assertIn("liveTake = f", toggle)
        stop = self.method("private void stopRecording()")
        self.assertIn("liveTake = null", stop)
        self.assertIn("durationCache.remove", stop)

    def test_upload_copy_lands_atomically(self):
        # The picked video copies under a name the list ignores, then
        # renames: a refresh mid-copy never lists (or uploads) half a
        # lesson.
        pick = self.method("private void savePickedVideo")
        self.assertIn('".part"', pick)
        self.assertIn("renameTo(dest)", pick)

    def test_exports_copy_off_the_ui_thread(self):
        # Copying an hour-long lesson to Downloads on the UI thread is
        # an ANR; both exports run on the background pool.
        self.assertIn("copyStream", self.method("private void exportToDownloads"))
        for sig in ("private void doExport()", "private void downloadSingle"):
            body = self.method(sig)
            self.assertIn("cloudExec.execute", body, sig)
            self.assertNotIn("copyStream", body, sig)
            self.assertLess(body.index("cloudExec.execute"),
                            body.index("exportToDownloads"), sig)

    def test_failed_start_leaves_no_file(self):
        # MediaRecorder creates the output file at prepare(): a take
        # that then fails to start (setup, start(), or a session that
        # will not configure) must not leave that empty file behind as
        # a session row a backlog sweep would upload.
        engine = read(ENGINE)
        discard = engine.split("private void discardFailedTake()", 1)[1] \
                        .split("\n    }\n", 1)[0]
        self.assertIn(".delete()", discard)
        setup = engine.split("private void startVideoInternal", 1)[1] \
                      .split("private boolean hasAudioPermission", 1)[0]
        self.assertIn("out.delete()", setup.split("MediaRecorder setup failed", 1)[1]
                      .split("return;", 1)[0])
        session = engine.split("private void buildSession", 1)[1] \
                        .split("private void startRepeating", 1)[0]
        start_failed = session.split("MediaRecorder start failed", 1)[1] \
                              .split("return;", 1)[0]
        self.assertIn("discardFailedTake()", start_failed)
        configure_failed = session.split("public void onConfigureFailed", 1)[1]
        self.assertIn("discardFailedTake()", configure_failed)

    def test_empty_take_is_reported_not_silent(self):
        # iOS and the web say "That take was empty"; Android dropped a
        # too-short take without a word, or listed a zero-byte one.
        stop = self.method("private void stopRecording()")
        self.assertIn("length() == 0", stop)
        self.assertIn("take was empty", stop)


if __name__ == "__main__":
    unittest.main()
