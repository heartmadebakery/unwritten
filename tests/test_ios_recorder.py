"""iOS app contract: native port in parity with Android and web.

app/ios/ lands on the hub sessions with Record and Upload above them,
like the other two apps. Same dark palette, same home landing, same
session-row contract (newest first, date + duration, tap to play in
the viewfinder, long-press to delete), same filename contract, same
presigned-TUS Cloud upload with the same link states.
"""
import glob
import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
IOS = os.path.join(ROOT, "app", "ios")
SRC = os.path.join(IOS, "UnwrittenRecorder")
VIEW = os.path.join(SRC, "ContentView.swift")
ENGINE = os.path.join(SRC, "CameraEngine.swift")
STORE = os.path.join(SRC, "SessionStore.swift")
CLOUD = os.path.join(SRC, "CloudStore.swift")
UPLOADER = os.path.join(SRC, "CloudUploader.swift")
NAMES = os.path.join(SRC, "Names.swift")
CONFIG = os.path.join(SRC, "CloudConfig.swift")
LUMA_CPP = os.path.join(SRC, "uwcore_luma.cpp")
LUMA_H = os.path.join(SRC, "uwcore_luma.h")
BRIDGE_H = os.path.join(SRC, "UWCoreBridge.h")
BRIDGE_MM = os.path.join(SRC, "UWCoreBridge.mm")
PLIST = os.path.join(SRC, "Info.plist")
PBXPROJ = os.path.join(IOS, "UnwrittenRecorder.xcodeproj", "project.pbxproj")
BUILD_SH = os.path.join(IOS, "build.sh")

CUT_WORDS = ["interviewer", "companion", "apprentice", "rolebtn",
             "Show me", "Teach me", "Your try"]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def all_sources():
    out = []
    for path in sorted(glob.glob(os.path.join(SRC, "*"))):
        if os.path.isfile(path):
            out.append(read(path))
    return "\n".join(out)


class IOSRecorderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = all_sources()
        cls.view = read(VIEW)
        cls.store = read(STORE)
        cls.names = read(NAMES)

    def test_no_cut_design_vocabulary(self):
        low = self.src.lower()
        for word in CUT_WORDS:
            self.assertNotIn(word.lower(), low, word)

    def test_no_roles_steps_or_session_code(self):
        for token in ["roleKeys", "STEPS", "getRole", "getStep",
                      "session_code", "makeCode", "data-role"]:
            self.assertNotIn(token, self.src, token)

    def test_single_lesson_naming(self):
        self.assertIn("lessonName", self.names)
        self.assertIn("unwritten_lesson_", self.names)
        for token in ["clipName", "brollName", "dialogueName", "photoName",
                      "CODE_WORDS"]:
            self.assertNotIn(token, self.names, token)

    def test_single_screen_records_one_lesson(self):
        self.assertIn("AVCaptureSession", read(ENGINE))
        self.assertIn("AVCaptureMovieFileOutput", read(ENGINE))
        self.assertIn("toggleRecord", self.view)
        self.assertIn("finishRecording", self.store)

    def test_local_save_still_comes_first(self):
        # The clips-dir write and list refresh stay; Cloud hooks after them.
        reg = self.store.index("registerLesson(url:")
        up = self.store.index("maybeCloudUpload")
        self.assertLess(reg, up)

    def test_remux_failure_keeps_original_before_cleanup(self):
        # Regression: the export handler deleted the temp .mov before
        # the fallback move ran, losing the lesson and registering a
        # phantom row. The temp file must survive until its case is
        # decided, and the fallback warning must survive registerLesson.
        handler = self.store.split("exportAsynchronously", 1)[1] \
                            .split("private func keepMovFallback", 1)[0]
        self.assertLess(handler.index("switch status"),
                        handler.index("removeItem(at: tempURL)"))
        self.assertIn("moveItem(at: tempURL, to: movURL)", handler)
        self.assertLess(handler.index("registerLesson(url: movURL)"),
                        handler.index("kept the original recording"))

    def test_leaving_mid_recording_keeps_the_take(self):
        self.assertIn("scenePhase", self.view)
        self.assertIn("stopVideo()", self.view)

    def test_mic_failure_warns_but_keeps_video(self):
        engine = read(ENGINE)
        self.assertIn("micWarning", engine)
        self.assertIn("No microphone", self.view)

    def test_live_mic_check_warns_after_quiet_minute(self):
        engine = read(ENGINE)
        for token in ["speechWarning", "AVCaptureAudioDataOutput",
                      "captureRms", "60000"]:
            self.assertIn(token, engine, token)
        self.assertIn("Quiet for a while", self.view)

    def test_session_start_never_throws_on_camera_less_devices(self):
        # startRunning throws an uncatchable ObjC exception with no
        # inputs (simulator, camera-less device): the engine must guard
        # it and start behind an exception handler instead.
        engine = read(ENGINE)
        self.assertIn("inputs.isEmpty", engine)
        self.assertIn("UWStartCaptureSession", engine)
        self.assertIn("UWStartCaptureSession", read(BRIDGE_H))
        self.assertIn("@try", read(BRIDGE_MM))

    def test_hub_lists_detail_plays_and_deletes(self):
        for token in ["HubSession", "hubAvailable", "loadHub",
                      "openHubSession", "hubDetail", "deleteHubSession",
                      "shareHubSession"]:
            self.assertIn(token, self.store, token)
        self.assertIn("deleteHubRecord", read(UPLOADER))
        for token in ["playHubSession", "hubDetailCard", '"Hub"']:
            self.assertIn(token, self.view, token)

    def test_hub_delete_removes_record_before_video(self):
        # Hub record first, then the Stream video: a failure between
        # the two must leave the bytes orphaned (playable,
        # re-publishable) — never a hub row pointing at a dead video
        # while the app claims nothing was lost. The partial outcome
        # is reported as partial.
        body = self.store.split("func deleteHubSession", 1)[1] \
                         .split("// ---------- share sheet", 1)[0]
        self.assertLess(body.index("deleteHubRecord"),
                        body.index("deleteVideo"))
        self.assertIn("but the cloud copy remains", body)

    def test_hub_section_always_visible_with_reason(self):
        # The Hub header renders regardless of Cloud state; the body
        # names the reason (Cloud off, missing signer token, server
        # not switched on, load failure, or simply empty) instead of
        # hiding the section.
        self.assertNotIn("if store.hubAvailable()", self.view)
        self.assertIn("hubStatusText()", self.view)
        for token in ["hubStatusText",
                      "add the signer URL and token in Cloud settings",
                      "Signer refused the token",
                      "isn't switched on at the server yet",
                      "Hub couldn't load"]:
            self.assertIn(token, self.store, token)

    def test_upload_fails_fast_without_credentials(self):
        # Fresh installs (Cloud on, no token yet) must not fire doomed
        # uploads that can only 401: canUpload gates the attempt, and
        # 401/403 failures name the token instead of the connection.
        for token in ["canUpload", "Cloud credentials missing",
                      "Signer refused the upload"]:
            self.assertIn(token, self.store, token)

    def test_session_committed_before_start_running(self):
        # Real-device bug (Oct 29 shakeout): startRunning threw
        # NSGenericException because it ran between beginConfiguration
        # and commitConfiguration. The configure path must commit first.
        engine = read(ENGINE)
        body = engine.split("func configureSession()", 1)[1] \
                     .split("func attachInputsLocked", 1)[0]
        begin = body.index("beginConfiguration")
        commit = body.index("commitConfiguration")
        start = body.index("UWStartCaptureSession")
        self.assertLess(begin, commit)
        self.assertLess(commit, start)

    def test_camera_switch_rechecks_recording_on_queue(self):
        # A take starting between the caller-thread check and the
        # queued reconfiguration must not get its inputs swapped
        # mid-take: the queue block re-checks before touching inputs.
        engine = read(ENGINE)
        body = engine.split("func switchCamera()", 1)[1] \
                     .split("func pauseSession()", 1)[0]
        self.assertEqual(body.count("movieOutput.isRecording"), 2)

    def test_foreground_refreshes_permissions_and_resumes(self):
        # Granting access in Settings then returning must unblock
        # Record (or lift video-only) without a relaunch, and the
        # session must pause in the background instead of running
        # behind the app's back.
        engine = read(ENGINE)
        for token in ["func refreshPermissions()", "func resumeSession()",
                      "func pauseSession()"]:
            self.assertIn(token, engine, token)
        self.assertNotIn("func shutdown()", engine)
        phase = self.view.split(".onChange(of: scenePhase)", 1)[1] \
                         .split(".alert(", 1)[0]
        for token in ["pauseSession()", "refreshPermissions()",
                      "resumeSession()"]:
            self.assertIn(token, phase, token)


class IOSNativeFeelTests(unittest.TestCase):
    """User-ordered Nov 1 (goal: apps feel native and intuitive).

    Record is an inset-grouped List like home, so its swipe actions
    really fire (they are no-ops inside a ScrollView); the shutter is
    a camera-style ring and disc; an empty device list is a system
    empty state; Fetch from link waits for a link."""

    @classmethod
    def setUpClass(cls):
        cls.view = read(VIEW)
        cls.record = cls.view.split("private var recordView", 1)[1] \
                             .split("private func showScreen", 1)[0]
        cls.home = cls.view.split("private var homeView", 1)[1] \
                           .split("private var recordView", 1)[0]

    def test_record_is_an_inset_grouped_list_so_swipe_deletes_work(self):
        self.assertIn("List {", self.record)
        self.assertIn(".listStyle(.insetGrouped)", self.record)
        # No ScrollView *container* (swipe actions don't fire inside one);
        # a ScrollViewReader around the List is only a scroll helper.
        self.assertNotIn("ScrollView {", self.record)
        self.assertIn(".swipeActions", self.view)

    def test_shutter_is_a_ring_and_disc_with_shared_labels(self):
        self.assertIn("shutterButton", self.record)
        shutter = self.view.split("private var shutterButton", 1)[1] \
                           .split("// ---------- screens", 1)[0]
        self.assertIn("Circle()", shutter)
        self.assertIn(".stroke(", shutter)
        self.assertIn("■ Stop  ", shutter)
        self.assertIn("● Record", shutter)
        self.assertIn(".accessibilityLabel", shutter)
        self.assertIn(".sensoryFeedback", shutter)

    def test_empty_device_list_is_a_system_empty_state(self):
        self.assertIn("ContentUnavailableView", self.record)

    def test_cloud_is_a_native_toggle_row(self):
        self.assertIn("Toggle(isOn:", self.record)
        self.assertIn('"Cloud"', self.record)
        # toggleCloud() flips persisted state; the binding must only act
        # on a real change, so a redundant set can never flip Cloud.
        self.assertIn("set: { on in if on != store.cloudOn", self.record)
        self.assertNotIn("set: { _ in store.toggleCloud() }", self.record)

    def test_fetch_waits_for_a_link_and_submits_from_keyboard(self):
        self.assertIn(".keyboardType(.URL)", self.home)
        self.assertIn(".submitLabel(.go)", self.home)
        self.assertIn(".onSubmit", self.home)
        self.assertIn(".disabled(", self.home)


class IOSPlaybackTests(unittest.TestCase):
    """Playback bugs reported Nov 1: hub videos never played and device
    recordings looked dead.

    Hub: the Cloud CDN's hotlink protection 403s any request without
    the player page as Referer (the pipeline fetcher already works
    around it the same way), and AVPlayer sends none — so every hub
    stream failed. Device: a session row sits far below the viewfinder
    on the Record list, so tapping it played the video off-screen."""

    @classmethod
    def setUpClass(cls):
        cls.view = read(VIEW)
        cls.play = cls.view.split("private func playHubSession", 1)[1] \
                           .split("private func stopLocalPlayback", 1)[0]
        cls.record = cls.view.split("private var recordView", 1)[1] \
                          .split("private func showScreen", 1)[0]

    def test_hub_playback_sends_the_player_page_as_referer(self):
        self.assertIn("AVURLAssetHTTPHeaderFieldsKey", self.play)
        self.assertIn('"Referer"', self.play)
        self.assertIn("hubEmbedUrl(", self.play)

    def test_hub_prefers_the_progressive_mp4_then_hls(self):
        self.assertLess(self.play.index("mp4Url"), self.play.index("hlsUrl"))

    def test_failed_hub_stream_falls_back_to_the_cloud_player(self):
        # Never a silent dead player: a failed item says so and opens
        # the embed page (Android's openInBrowser, the web's onerror).
        self.assertIn(".failed", self.play)
        self.assertIn("openURL(", self.play)
        self.assertIn("hubItemObserver", self.view)

    def test_hub_audio_uses_the_playback_category(self):
        # The camera engine leaves a record-capable session behind,
        # which routes video sound to the quiet earpiece.
        self.assertIn(".moviePlayback", self.play)

    def test_device_playback_is_a_full_screen_native_player(self):
        # Found on device: tapping a session row (scrolled far below the
        # viewfinder) played the video in the off-screen viewfinder, and
        # scrollTo inside the List did not bring it back. Playback is now
        # a full-screen cover with the system player's controls.
        self.assertIn(".fullScreenCover(", self.record)
        self.assertIn("devicePlayerCover", self.view)
        cover = self.view.split("private var devicePlayerCover", 1)[1] \
                         .split("// ---------- screens", 1)[0]
        self.assertIn("VideoPlayer(player:", cover)
        self.assertIn("stopLocalPlayback()", cover)
        self.assertNotIn("ScrollViewReader", self.view)

    def test_camera_rests_while_a_session_plays(self):
        start = self.view.split("private func startPlayer", 1)[1] \
                         .split("private func playInViewfinder", 1)[0]
        self.assertIn("engine.pauseSession()", start)
        self.assertIn(".moviePlayback", start)
        stop = self.view.split("private func stopLocalPlayback", 1)[1] \
                        .split("// ---------- sessions", 1)[0]
        self.assertIn("engine.resumeSession()", stop)


class IOSBaselineTests(unittest.TestCase):
    """Base device: iPhone (2019-class, like the Pixel 4) — iOS 17+,
    iPhone-only, no storyboards, programmatic SwiftUI like Android's
    programmatic UI."""

    @classmethod
    def setUpClass(cls):
        cls.pbxproj = read(PBXPROJ)
        cls.plist = read(PLIST)

    def test_ios17_iphone_baseline(self):
        self.assertIn("IPHONEOS_DEPLOYMENT_TARGET = 17.0", self.pbxproj)
        self.assertIn("TARGETED_DEVICE_FAMILY = 1", self.pbxproj)
        self.assertIn("SDKROOT = iphoneos", self.pbxproj)

    def test_app_icon_matches_web_pwa_icon(self):
        # One 1024 AppIcon (iOS 17 single-size), made from the PWA icon.
        assets = os.path.join(SRC, "Assets.xcassets", "AppIcon.appiconset")
        meta = read(os.path.join(assets, "Contents.json"))
        self.assertIn("icon-1024.png", meta)
        self.assertTrue(os.path.isfile(os.path.join(assets, "icon-1024.png")))
        with open(os.path.join(assets, "icon-1024.png"), "rb") as f:
            head = f.read(32)
        self.assertEqual(head[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(int.from_bytes(head[16:20], "big"), 1024)
        self.assertEqual(int.from_bytes(head[20:24], "big"), 1024)
        self.assertNotEqual(head[25], 6, "icon must be opaque (no alpha)")
        self.assertIn("Assets.xcassets", self.pbxproj)
        self.assertIn("ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon",
                      self.pbxproj)

    def test_same_bundle_id_as_android(self):
        self.assertIn("org.tinio.unwritten", self.plist)
        self.assertIn("org.tinio.unwritten", self.pbxproj)

    def test_camera_and_mic_permissions_declared(self):
        self.assertIn("NSCameraUsageDescription", self.plist)
        self.assertIn("NSMicrophoneUsageDescription", self.plist)

    def test_lessons_visible_in_files_app(self):
        self.assertIn("UIFileSharingEnabled", self.plist)
        self.assertIn("LSSupportsOpeningDocumentsInPlace", self.plist)

    def test_no_storyboards_or_dependencies(self):
        self.assertEqual(glob.glob(os.path.join(SRC, "*.storyboard")), [])
        self.assertEqual(glob.glob(os.path.join(SRC, "*.xib")), [])
        self.assertNotIn("Pods", self.pbxproj)

    def test_native_core_links_through_bridge(self):
        self.assertIn("ComputeLumaStats", read(LUMA_CPP))
        self.assertIn("ComputeLumaStats", read(LUMA_H))
        self.assertIn("UWComputeLumaMean", read(BRIDGE_H))
        self.assertIn("UWComputeLumaMean", read(BRIDGE_MM))
        self.assertIn("SWIFT_OBJC_BRIDGING_HEADER", self.pbxproj)
        self.assertIn("setLumaListener", read(ENGINE))

    def test_build_stamps_signer_token_like_android(self):
        build = read(BUILD_SH)
        self.assertIn("tokens.txt", build)
        self.assertIn("CLOUD_SIGNER_TOKEN_DEFAULT", build)
        self.assertIn("restored after build", build)
        # The committed template carries no real token.
        self.assertIn('CLOUD_SIGNER_TOKEN_DEFAULT = ""', read(CONFIG))
        # Device builds go through the same stamp (DEVELOPMENT_TEAM
        # selects the signed device path); uwcore linkage is verified
        # via the link list, which survives Debug symtab stripping.
        self.assertIn("DEVELOPMENT_TEAM", build)
        self.assertIn("LinkFileList", build)
        self.assertIn("uwcore_luma", build)


class CloudIOSTests(unittest.TestCase):
    """Optional Cloud upload: local save stays first; Cloud only ever
    receives a copy, and only when turned on."""

    @classmethod
    def setUpClass(cls):
        cls.uploader = read(UPLOADER)
        cls.store = read(STORE)
        cls.cloud = read(CLOUD)

    def test_uploader_speaks_presigned_tus(self):
        self.assertIn("https://video.bunnycdn.com/tusupload", self.uploader)
        self.assertIn("AuthorizationSignature", self.uploader)
        self.assertIn("AuthorizationExpire", self.uploader)
        self.assertIn("Upload-Offset", self.uploader)
        self.assertIn("sha256Hex", self.uploader)

    def test_streaming_link_is_cloud_embed(self):
        self.assertIn("https://player.mediadelivery.net/embed/", self.uploader)
        self.assertIn("https://player.mediadelivery.net/embed/", self.cloud)

    def test_store_gates_upload_behind_settings(self):
        self.assertIn("CloudUploader", self.cloud)  # vended by the store
        self.assertIn("cloud.uploader()", self.store)
        self.assertIn("cloudEnabledCfg", self.store)
        self.assertIn("maybeCloudUpload", self.store)
        self.assertIn("startCloudUpload", self.store)
        self.assertIn("CLOUD_SIGNER_DEFAULT", self.cloud)
        self.assertIn("CLOUD_SIGNER_TOKEN_DEFAULT", self.cloud)
        self.assertIn("confirmDeleteLesson", read(VIEW))
        self.assertIn("deleteLesson", self.store)

    def test_uploads_resume_after_restart(self):
        self.assertIn("cloudResumePending", self.store)
        self.assertIn("onSession", self.uploader)

    def test_no_force_unwrapped_request_urls(self):
        # A mistyped signer URL or a corrupt persisted upload URL must
        # surface as an error, never crash the app. The only allowed
        # force-unwrap is the compile-time vendor constant.
        bangs = re.findall(r"URL\(string: [^)]+\)!", self.uploader)
        self.assertEqual(bangs, ["URL(string: Self.TUS_URL)!"], bangs)

    def test_poll_timeout_and_errors_offer_retry(self):
        # A resumed poll must not sit on "…" forever when Cloud never
        # finishes, nor spin for ten minutes on dead status checks:
        # both end in the failed state (the ! retry action).
        poll = self.store.split("private func pollCloud", 1)[1] \
                         .split("func cloudResumePending", 1)[0]
        self.assertIn("taking too long", poll)
        self.assertIn("kept failing", poll)
        loop = self.uploader.split("for _ in 0 ..< 120", 1)[1] \
                            .split("Still processing on Cloud", 1)[0]
        self.assertIn("kept failing", loop)

    def test_delete_cancels_polls_and_ignores_stragglers(self):
        # Deleting mid-poll must stop the poll, and any late upload
        # or poll completion for a deleted file must not resurrect
        # its link row.
        self.assertIn("pollTasks", self.store)
        delete = self.store.split("func deleteLesson", 1)[1] \
                           .split("func retryCloud", 1)[0]
        self.assertIn("pollTasks[name]?.cancel()", delete)
        finished = self.store.split("private func cloudFinished", 1)[1] \
                             .split("private func cloudFailed", 1)[0]
        failed = self.store.split("private func cloudFailed", 1)[1] \
                           .split("private func pollCloud", 1)[0]
        for region in (finished, failed):
            self.assertIn("guard url(for: name) != nil", region)

    def test_hub_load_reports_cause_and_clears_rows(self):
        # A failed hub load names its cause (like Android), and the
        # docstring must not claim cleared rows are kept.
        load = self.store.split("func loadHub()", 1)[1] \
                         .split("func openHubSession", 1)[0]
        self.assertIn("localizedDescription", load)
        self.assertNotIn("keep the last rows", self.store)

    def test_enabling_cloud_sweeps_the_backlog(self):
        # Sessions recorded while Cloud was off (or failed) still
        # need their copy when Cloud comes back on — without a sweep
        # they would stay local-only forever, silently.
        self.assertIn("func sweepBacklog", self.store)
        toggle = self.store.split("func toggleCloud()", 1)[1] \
                           .split("func paintCloudToggle", 1)[0]
        self.assertIn("sweepBacklog()", toggle)

    def test_legacy_cloud_keys_migrated(self):
        # One-generation legacy storage key, marked legacy per the rule.
        self.assertIn("unwritten_bunny", self.cloud)  # legacy

    def test_share_never_serves_another_lesson_link(self):
        # The lastLink fallback must be scoped to the same lesson:
        # sharing lesson B's URL under lesson A's name is a mixup.
        # And a link is only published when the library id is known
        # (no embed//videoId links).
        self.assertIn("cloud.lastName == name", self.store)
        finished = self.store.split("private func cloudFinished", 1)[1] \
                             .split("private func cloudFailed", 1)[0]
        self.assertIn("if !lib.isEmpty", finished)


class IOSParityTests(unittest.TestCase):
    """The iOS app mirrors the Android and web apps' design.

    Same dark palette, same home landing (Record + Upload above the
    hub, then cloud and device sessions), same session-row contract:
    newest first, date + duration, tap to play in the viewfinder,
    long-press to delete, per-lesson share/download.
    """

    @classmethod
    def setUpClass(cls):
        cls.view = read(VIEW)
        cls.store = read(STORE)
        cls.cloud = read(CLOUD)

    def test_android_dark_palette(self):
        for color in ["17130E", "241C12", "F5EAD6", "B8A888"]:
            self.assertIn(color, self.view, color)

    def test_title_and_sessions_wording(self):
        # Post-restructure contract (user-ordered): Unwritten Craft
        # lands on the hub; "Sessions" split into Hub + This device.
        self.assertIn("Unwritten Craft", self.view)
        self.assertIn("Record, upload, and revisit craft lessons.", self.view)
        self.assertNotIn("Film mentor session. Record and let it happen.", self.view)
        self.assertNotIn('"Sessions"', self.view)
        self.assertIn('"This device"', self.view)

    def test_cloud_toggle_below_record_and_export_when_off(self):
        # User-ordered Nov 1 (native iOS idioms): the "☁ Cloud: on/off"
        # button became a system Toggle bound to the same store state;
        # Export still follows it and still shows only with Cloud off.
        self.assertIn("Toggle(isOn:", self.view)
        self.assertIn("store.toggleCloud()", self.view)
        self.assertIn("Export sessions to Downloads", self.view)
        self.assertIn("if !store.cloudOn", self.view)
        self.assertLess(self.view.index("Toggle(isOn:"),
                        self.view.index("Export sessions to Downloads"))

    def test_zoom_row_below_viewfinder(self):
        for token in ["maxZoom", "setZoom", "nudgeZoom", "%.1f×"]:
            self.assertIn(token, self.view, token)

    def test_in_viewfinder_playback(self):
        # User-ordered Nov 1 (playback bug fix): a tapped session no
        # longer plays in the viewfinder strip — which sat off-screen
        # whenever the row was scrolled into view — but in a full-screen
        # native VideoPlayer. The shared entry points keep their names.
        for token in ["VideoPlayer(player:", "playInViewfinder",
                      "stopLocalPlayback"]:
            self.assertIn(token, self.view, token)
        self.assertNotIn("PlayerView(player:", self.view)

    def test_settings_show_stored_values_not_effective(self):
        # Loading effective (compiled-default) values into the fields
        # persists them as overrides on open, shadowing later stamp
        # rotations. Fields bind stored values; placeholders name the
        # build defaults.
        load = self.view.split("private func loadCloudFields()", 1)[1] \
                        .split("private static func fmt", 1)[0]
        self.assertNotIn("effSignerUrl()", load)
        self.assertNotIn("effSignerToken()", load)
        self.assertIn("store.cloud.signerUrl", load)
        self.assertIn("store.cloud.signerToken", load)
        self.assertIn("prompt", self.view)

    def test_delete_offers_device_only_when_cloud_unreachable(self):
        # A dead cloud delete must not trap local storage: the user
        # gets a second confirm to delete this phone's copy anyway
        # (the cloud copy stays where it is).
        self.assertIn("pendingForceDelete", self.view)
        self.assertIn("forceDeleteLocal", self.store)
        self.assertIn("removeLocalSession", self.store)

    def test_linked_rows_keep_their_download(self):
        # Cloud-linking a session must not remove its on-device
        # download: linked rows keep ↓ next to their cloud action.
        row = self.view.split("private func sessionRow", 1)[1] \
                       .split("private func rightAction", 1)[0]
        self.assertIn("downloadSingle", row)

    def test_stop_button_carries_timer_like_android(self):
        self.assertIn("■ Stop  ", self.view)

    def test_session_rows_newest_first_with_date_and_duration(self):
        for token in ["leftIconFor", "displayDateFor", "durationCache"]:
            self.assertIn(token, self.store, token)
        self.assertIn("MMM d, yyyy HH:mm", self.store)

    def test_long_press_deletes_like_android(self):
        # User-ordered Nov 1 (native iOS idioms): long-press opens the
        # system context menu (Delete among its actions) and a trailing
        # swipe deletes too — both route through the same confirm.
        row = self.view.split("private func sessionRow", 1)[1] \
                       .split("private func rightAction", 1)[0]
        self.assertIn(".contextMenu", row)
        self.assertIn(".swipeActions", row)
        self.assertGreaterEqual(row.count("confirmDeleteLesson"), 2)

    def test_share_uses_cloud_link(self):
        self.assertIn("shareCloudLinkFor", self.view)
        self.assertIn("UIPasteboard", self.store)

    def test_filename_contract_matches_android(self):
        self.assertIn("unwritten_lesson_", self.store)


class IOSScreensTests(unittest.TestCase):
    """Single-app restructure: home lands on the hub with Record and
    Upload above it; record owns the camera; a picked video rides the
    take path (clips folder, then Cloud) like a recording."""

    @classmethod
    def setUpClass(cls):
        cls.view = read(VIEW)
        cls.store = read(STORE)
        cls.names = read(NAMES)

    def test_home_is_the_landing_with_record_and_upload_above_hub(self):
        home = self.view.split("private var homeView", 1)[1] \
                        .split("private var recordView", 1)[0]
        record = self.view.split("private var recordView", 1)[1] \
                          .split("private func showScreen", 1)[0]
        # User-ordered Nov 1 (native iOS idioms): home's actions are
        # SF Symbol labels ("Record" with record.circle) — the record
        # screen's shutter keeps the shared "● Record" text.
        self.assertIn('Text("Record")', home)
        self.assertIn("● Record", self.view)
        self.assertIn("Upload video", home)
        self.assertLess(home.index("Upload video"), home.index('"Hub"'))
        # User-ordered Nov 1 (layout): the hub is last on home; cloud
        # + device sessions moved to the record screen.
        for token in ["Toggle(isOn:", '"This device"', "sessionRow("]:
            self.assertNotIn(token, home, token)
            self.assertIn(token, record, token)

    def test_record_screen_owns_the_camera(self):
        appear = self.view.split(".onAppear", 1)[1] \
                          .split(".onChange(of: showCloudPanel)", 1)[0]
        self.assertNotIn("requestAccessAndConfigure", appear)
        show = self.view.split("private func showScreen", 1)[1] \
                        .split("// ---------- recording", 1)[0]
        for token in ["stopVideo()", "pauseSession()",
                      "requestAccessAndConfigure()", "resumeSession()",
                      "refresh()", "loadHub()"]:
            self.assertIn(token, show, token)
        # User-ordered Nov 1 (native iOS idioms): Record is pushed on a
        # NavigationStack and left with the system back button / edge
        # swipe instead of a custom "‹ Home" button. Every way off the
        # record screen changes the path, and the path drives
        # showScreen — so a pop still stops the take and parks the
        # camera.
        self.assertIn("NavigationStack(path:", self.view)
        self.assertIn(".navigationDestination(for: Route.self)", self.view)
        self.assertNotIn("‹ Home", self.view)
        self.assertNotIn('@State private var screen = "home"', self.view)
        path = self.view.split(".onChange(of: path)", 1)[1] \
                        .split("\n        }", 1)[0]
        self.assertIn("showScreen(", path)

    def test_scene_phase_knows_record_is_on_top(self):
        # With no screen string left, foregrounding must still resume
        # the camera only when Record is the top screen.
        phase = self.view.split(".onChange(of: scenePhase)", 1)[1] \
                         .split(".alert(", 1)[0]
        self.assertIn("onRecordScreen", phase)
        self.assertIn("path.last == .record", self.view)

    def test_cloud_settings_is_a_sheet_form(self):
        # User-ordered Nov 1: settings are a system sheet with a Form
        # (Android uses a dialog; web an inline panel). Closing it
        # still reloads the hub.
        self.assertIn(".sheet(isPresented: $showCloudPanel)", self.view)
        self.assertIn("Form {", self.view)
        changed = self.view.split(".onChange(of: showCloudPanel)", 1)[1] \
                           .split("}", 1)[0]
        self.assertIn("loadHub()", changed)
        # User-ordered Nov 1 (layout): no toolbar gear — a small
        # Advanced settings link on the record screen opens the sheet.
        self.assertNotIn("gearshape", self.view)
        record = self.view.split("private var recordView", 1)[1] \
                          .split("private func showScreen", 1)[0]
        self.assertIn("Advanced settings", record)
        self.assertIn("showCloudPanel = true", record)

    def test_hub_refreshes_by_pull(self):
        self.assertIn(".refreshable", self.view)

    def test_upload_picker_saves_like_a_take(self):
        for token in ["UIDocumentPickerViewController", ".movie",
                      "showUploadPicker", "registerUpload"]:
            self.assertIn(token, self.view, token)
        # User-ordered Nov 1: lesson videos on an iPhone live in Photos,
        # so Upload offers the Photos picker alongside Files (Android's
        # system picker reaches the gallery the same way).
        for token in ["import PhotosUI", ".photosPicker(",
                      "matching: .videos", "loadTransferable"]:
            self.assertIn(token, self.view, token)
        self.assertIn("uploadName", self.names)
        self.assertIn("unwritten_lesson_upload_", self.names)
        save = self.store.split("func registerUpload", 1)[1] \
                         .split("\n    // ----------", 1)[0]
        for token in ["isn't a video", "copyItem", "registerLesson(url:"]:
            self.assertIn(token, save, token)
        self.assertLess(save.index("copyItem"),
                        save.index("registerLesson(url:"))

    def test_home_playback_moves_to_record_screen(self):
        # Device sessions play from the record screen (user-ordered Nov 1
        # the route there is a push; the player itself is a full-screen
        # cover now).
        play = self.view.split("private func playInViewfinder", 1)[1] \
                        .split("private func playHubSession", 1)[0]
        self.assertIn("path.append(.record)", play)

    def test_hub_playback_never_opens_the_camera(self):
        # Watching a published lesson must not prompt for the camera:
        # hub sessions play in the hub detail screen's own player.
        play = self.view.split("private func playHubSession", 1)[1] \
                        .split("private func stopLocalPlayback", 1)[0]
        self.assertNotIn(".record", play)
        self.assertNotIn("requestAccessAndConfigure", play)
        self.assertIn("hubPlayer", play)
        self.assertIn("VideoPlayer(player:", self.view)
        # No stream URL must never be a dead button: fall back to the
        # Cloud embed page, like Android's openInBrowser.
        self.assertIn("openURL(", play)
        self.assertIn("hubEmbedUrl(", play)
        self.assertIn("import AVKit", self.view)

    def test_url_upload_queues_to_pipeline(self):
        # User-ordered Oct 31: paste a link — natives queue every URL
        # to the pipeline fetcher (only the web page downloads direct
        # files itself).
        self.assertIn("/fetch/jobs", self.store)
        self.assertIn("queueFetchUrl", self.store)
        for token in ["fetchUrl", "Fetch from link", "TextField"]:
            self.assertIn(token, self.view, token)


if __name__ == "__main__":
    unittest.main()
