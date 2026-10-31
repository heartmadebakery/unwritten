"""Streamlined recorder contract (Oct 27 simplification, applied to app/).

Both recorders have exactly one job: record one lesson, stop, keep the
file. No roles/modes, no session steps, no apprentice line, no companion
sync. The pipeline takes the largest media file as the lesson, so every
take is named unwritten_lesson_<timestamp>.<ext>.
"""
import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
WEB = os.path.join(ROOT, "app", "recorder", "index.html")
SW = os.path.join(ROOT, "app", "recorder", "sw.js")
MANIFEST = os.path.join(ROOT, "app", "recorder", "manifest.webmanifest")
MAIN = os.path.join(ROOT, "app", "android", "app", "src", "main", "java",
                    "org", "tinio", "unwritten", "MainActivity.java")
NAMES = os.path.join(ROOT, "app", "android", "app", "src", "main", "java",
                     "org", "tinio", "unwritten", "Names.java")
ENGINE = os.path.join(ROOT, "app", "android", "app", "src", "main", "java",
                      "org", "tinio", "unwritten", "CameraEngine.java")
HUB = os.path.join(ROOT, "app", "android", "app", "src", "main", "java",
                   "org", "tinio", "unwritten", "HubClient.java")
PREFS = os.path.join(ROOT, "app", "android", "app", "src", "main", "java",
                     "org", "tinio", "unwritten", "Prefs.java")
PROVIDER = os.path.join(ROOT, "app", "android", "app", "src", "main", "java",
                        "org", "tinio", "unwritten", "TinyFileProvider.java")
ANDROID_MANIFEST = os.path.join(ROOT, "app", "android", "app", "src", "main",
                                "AndroidManifest.xml")

# Vocabulary of the cut multi-mode design. None of it may survive in the
# streamlined recorders (docs and dated logs may keep it as history).
CUT_WORDS = ["interviewer", "companion", "apprentice", "rolebtn",
             "Show me", "Teach me", "Your try"]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class WebRecorderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = read(WEB)

    def test_no_cut_design_vocabulary(self):
        low = self.html.lower()
        for word in CUT_WORDS:
            self.assertNotIn(word.lower(), low, word)

    def test_no_roles_steps_or_session_code(self):
        for token in ["data-role", "STEPS", "uw_role", "uw_step",
                      "session_code", "makeCode"]:
            self.assertNotIn(token, self.html, token)

    def test_single_lesson_recording_flow(self):
        self.assertIn('id="recbtn"', self.html)
        self.assertIn("MediaRecorder", self.html)
        self.assertIn("unwritten_lesson_", self.html)
        self.assertIn("indexedDB", self.html)  # on-device vault stays

    def test_linked_rows_keep_their_download(self):
        # Cloud-linking a session must not remove its on-device
        # download: every linked row keeps ↓ next to its cloud action.
        clip = self.html.split("function clipHTML(c)", 1)[1] \
                        .split("function renderClips", 1)[0]
        self.assertIn("var dl =", clip)
        self.assertEqual(clip.count("dl +"), 4)

    def test_memory_only_rows_warn(self):
        # The vault write can fail (private mode, quota): rows that
        # live in memory only must say so instead of looking saved.
        clip = self.html.split("function clipHTML(c)", 1)[1] \
                        .split("function renderClips", 1)[0]
        self.assertIn("persisted", clip)
        self.assertIn("⚠", clip)

    def test_recorder_error_survives_onstop(self):
        # onerror fires before onstop: without a flag, onstop's
        # "Session saved" buries the error every time.
        start = self.html.split("rec.onerror", 1)[1] \
                         .split("function stopRec", 1)[0]
        self.assertIn("recErr", start)

    def test_service_worker_caches_good_pages_only(self):
        # A cached 404/500 would brick the app shell until cleared by
        # hand; a cache miss with no network must answer plainly,
        # never resolve undefined.
        sw = read(SW)
        self.assertIn("res.ok", sw)
        self.assertIn("503", sw)

    def test_manifest_is_the_recorder_not_the_apprentice(self):
        manifest = read(MANIFEST)
        self.assertNotIn("Apprentice", manifest)
        self.assertIn("Unwritten Craft", manifest)
        self.assertNotIn("Recorder", manifest)

    def test_home_is_hub_with_record_and_upload(self):
        # One Unwritten Craft app: it opens on the hub sessions, with
        # Record and Upload above the listing; recording is a screen,
        # not a separate app, and every screen leads home.
        for token in ['id="screen-home"', 'id="screen-record"',
                      'id="screen-upload"', "showScreen",
                      'id="gorecord"', 'id="goupload"', 'id="hublist"',
                      "loadHub", "/hub/sessions", 'id="uploadinput"',
                      'id="uploadbtn"', "backbtn"]:
            self.assertIn(token, self.html, token)
        home = self.html.split('id="screen-home"', 1)[1] \
                        .split('id="screen-record"', 1)[0]
        self.assertLess(home.index('id="gorecord"'), home.index('id="hublist"'))
        self.assertLess(home.index('id="goupload"'), home.index('id="hublist"'))

    def test_upload_saves_like_a_recording(self):
        # An upload lands in the device sessions and rides the same
        # cloud path as a take, so the pipeline picks it up the same way.
        up = self.html.split('$("uploadbtn").onclick', 1)[1] \
                      .split("function hubAvailable", 1)[0]
        self.assertIn("saveBlob(f, ", up)
        self.assertIn("unwritten_lesson_upload_", up)

    def test_hub_escapes_server_titles(self):
        # Hub titles come from the server; they must never inject markup.
        self.assertIn("function escHtml", self.html)
        row = self.html.split("function hubRowHTML", 1)[1] \
                       .split("function loadHub", 1)[0]
        self.assertIn("escHtml(r.title", row)

    def test_camera_runs_only_on_record_screen(self):
        # Home-first means no permission prompt on landing: the camera
        # opens when the record screen shows and releases when it hides.
        nav = self.html.split("function showScreen", 1)[1] \
                       .split("function closeCamera", 1)[0]
        self.assertIn("openCamera()", nav)
        self.assertIn("closeCamera()", nav)
        boot = self.html.split("wakeLock(); idbRestore()", 1)[1]
        self.assertIn('showScreen("home")', boot)
        self.assertNotIn("openCamera();", boot.split("</script>", 1)[0])


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
                      "add the signer URL and token in Cloud settings",
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


CLOUD_UPLOADER = os.path.join(ROOT, "app", "android", "app", "src", "main",
                              "java", "org", "tinio", "unwritten",
                              "CloudUploader.java")
SIGNER = os.path.join(ROOT, "app", "cloud-signer", "worker.js")
ANDROID_MANIFEST = os.path.join(ROOT, "app", "android", "app", "src", "main",
                                "AndroidManifest.xml")


class CloudWebTests(unittest.TestCase):
    """Optional Cloud upload (Oct 2026): local save stays first;
    Cloud only ever receives a copy, and only when turned on."""

    @classmethod
    def setUpClass(cls):
        cls.html = read(WEB)

    def test_cloud_is_opt_in_with_settings(self):
        self.assertIn('id="cloudtoggle"', self.html)
        self.assertIn('id="cloudpanel"', self.html)
        self.assertIn('id="cloudsigner"', self.html)
        self.assertIn("cloudReady()", self.html)
        self.assertIn("CLOUD_SIGNER_DEFAULT", self.html)
        self.assertIn("CLOUD_SIGNER_TOKEN_DEFAULT", self.html)
        self.assertIn("data-cloud-delete", self.html)
        self.assertIn("cloudDeleteLesson", self.html)
        self.assertNotIn("a.click()", self.html)

    def test_upload_uses_presigned_tus(self):
        self.assertIn("https://video.bunnycdn.com/tusupload", self.html)
        self.assertIn("AuthorizationSignature", self.html)
        self.assertIn("AuthorizationExpire", self.html)
        self.assertIn("Upload-Offset", self.html)

    def test_streaming_link_is_cloud_embed(self):
        self.assertIn("https://player.mediadelivery.net/embed/", self.html)

    def test_local_save_still_comes_first(self):
        # The vault write and download copy stay; Cloud hooks after them.
        save = self.html.split("function saveBlob", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("idbPut", save)
        self.assertLess(save.index("idbPut"), save.index("startCloudUpload"))

    def test_upload_fails_fast_without_credentials(self):
        # Fresh installs (Cloud on, no token yet) must not fire doomed
        # uploads that can only 401: cloudCanUpload gates the attempt,
        # and the failure names the token instead of staying silent —
        # the same contract Android and iOS keep.
        for token in ["cloudCanUpload", "Cloud credentials missing"]:
            self.assertIn(token, self.html, token)
        start = self.html.split("async function startCloudUpload", 1)[1]
        self.assertLess(start.index("cloudCanUpload"),
                        start.index("cloudCreds"))

    def test_enabling_cloud_sweeps_the_backlog(self):
        # Sessions recorded while Cloud was off (or failed) still
        # need their copy when Cloud comes back on — without a sweep
        # they would stay local-only forever, silently.
        self.assertIn("function sweepBacklog", self.html)
        toggle = self.html.split('$("cloudtoggle").onclick', 1)[1] \
                          .split('$("cloudsettings").onclick', 1)[0]
        self.assertIn("sweepBacklog()", toggle)

    def test_processing_timeout_offers_retry(self):
        # pollCloudStatus must not leave a session on "…" forever when
        # Cloud never finishes preparing the stream: the poll ends in
        # the failed state (the ! retry action) with a reason.
        poll = self.html.split("async function pollCloudStatus", 1)[1] \
                        .split("async function startCloudUpload", 1)[0]
        self.assertIn("taking too long", poll)
        self.assertIn('"failed"', poll)

    def test_delete_offers_device_only_when_cloud_unreachable(self):
        # A dead cloud delete must not trap local storage: the user
        # gets a second confirm to delete this device's copy anyway
        # (the cloud copy stays where it is).
        delete = self.html.split("async function cloudDeleteLesson", 1)[1] \
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
        self.assertIn("SHA-256", self.uploader)

    def test_main_activity_gates_upload_behind_settings(self):
        self.assertIn("CloudUploader", self.main)
        self.assertIn("cloudEnabledCfg", self.main)
        self.assertIn("maybeCloudUpload", self.main)
        self.assertIn("CLOUD_SIGNER_DEFAULT", self.main)
        self.assertIn("CloudConfig.CLOUD_SIGNER_TOKEN_DEFAULT", self.main)
        self.assertIn("confirmDeleteLesson", self.main)
        self.assertIn("deleteLesson", self.main)

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
        self.assertIn("org.tinio.unwritten.files", manifest)
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

    def test_cloud_settings_screen_exists(self):
        # Error and hub messages send the user to "Cloud settings" —
        # the screen must exist, prefilled with stored values (never
        # effective ones: no override shadowing), saving back to
        # prefs and sweeping the backlog when Cloud is on.
        self.assertIn("showCloudSettings()", self.main)
        self.assertIn("⚙ Cloud settings", self.main)
        self.assertIn("EditText", self.main)
        dlg = self.main.split("private void showCloudSettings", 1)[1] \
                       .split("\n    private ", 1)[0]
        for token in ["settingsField(", 'putString("signerToken"',
                      "sweepBacklog()"]:
            self.assertIn(token, dlg, token)
        self.assertNotIn("cloudEffSignerToken()", dlg)
        self.assertNotIn("cloudEffSignerUrl()", dlg)


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
        self.assertLess(home.index("Upload video"), home.index("Hub sessions"))
        self.assertLess(home.index("Hub sessions"), home.index("This device"))

    def test_record_screen_owns_and_releases_the_camera(self):
        show = self.main.split("private void showScreen", 1)[1] \
                        .split("\n    private ", 1)[0]
        for token in ["stopRecording()", "engine.close()", "hasPermissions()",
                      "openPreview()", "refreshClipList()", "loadHub()"]:
            self.assertIn(token, show, token)
        self.assertIn("‹ Home", self.main)
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
    """The web recorder mirrors the native Android recorder's design.

    Same dark palette, same single-column order (viewfinder, zoom,
    record, cloud toggle, export, sessions), same session-row contract:
    newest first, date + duration, tap to play in the viewfinder,
    long-press to delete, per-lesson share/download.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = read(WEB)
        cls.manifest = read(MANIFEST)

    def test_android_dark_palette(self):
        for color in ["#17130E", "#241C12", "#F5EAD6", "#B8A888"]:
            self.assertIn(color, self.html, color)

    def test_title_and_sessions_wording(self):
        # Post-restructure contract (user-ordered): the app is Unwritten
        # Craft, landing on the hub with Record/Upload above it; device
        # sessions sit under "This device", not a recorder "Sessions" list.
        self.assertIn("Record, upload, and revisit craft lessons.", self.html)
        self.assertNotIn("Film mentor session. Record and let it happen.", self.html)
        self.assertIn(">Hub<", self.html)
        self.assertIn(">This device<", self.html)
        self.assertNotIn("Lessons on this device", self.html)

    def test_zoom_row_below_viewfinder(self):
        for token in ['id="zoomrow"', 'id="zoomseek"', 'id="zoomlabel"']:
            self.assertIn(token, self.html, token)
        self.assertLess(self.html.index('id="zoomrow"'),
                        self.html.index('id="recbtn"'))

    def test_in_viewfinder_playback(self):
        for token in ['id="player"', "playInViewfinder",
                      "stopLocalPlayback", 'id="playercontrols"']:
            self.assertIn(token, self.html, token)

    def test_stop_button_carries_timer_like_android(self):
        self.assertIn("■ Stop  ", self.html)

    def test_export_visible_only_when_cloud_off(self):
        self.assertIn('id="exportbtn"', self.html)
        self.assertIn("Export sessions to Downloads", self.html)

    def test_session_rows_newest_first_with_date_and_duration(self):
        for token in ["leftIconFor", "displayDateFor", "durationFor"]:
            self.assertIn(token, self.html, token)

    def test_long_press_deletes_like_android(self):
        self.assertIn("confirmDeleteLesson", self.html)

    def test_share_uses_cloud_link(self):
        self.assertIn("shareCloudLinkFor", self.html)

    def test_manifest_uses_android_theme_color(self):
        self.assertIn("#17130E", self.manifest)

    def test_live_mic_check_warns_after_quiet_minute(self):
        for token in ['id="speechwarn"', "startSpeechMonitor",
                      "stopSpeechMonitor", "getFloatTimeDomainData",
                      "60000"]:
            self.assertIn(token, self.html, token)


if __name__ == "__main__":
    unittest.main()
