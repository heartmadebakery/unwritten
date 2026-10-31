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
        self.assertIn("☁ Cloud: on", self.view)
        self.assertIn("☁ Cloud: off", self.view)
        self.assertIn("Export sessions to Downloads", self.view)
        self.assertIn("if !store.cloudOn", self.view)
        self.assertLess(self.view.index("☁ Cloud: on"),
                        self.view.index("Export sessions to Downloads"))

    def test_zoom_row_below_viewfinder(self):
        for token in ["maxZoom", "setZoom", "nudgeZoom", "%.1f×"]:
            self.assertIn(token, self.view, token)

    def test_in_viewfinder_playback(self):
        for token in ["PlayerView", "playInViewfinder",
                      "stopLocalPlayback"]:
            self.assertIn(token, self.view, token)

    def test_player_view_updates_its_player(self):
        # SwiftUI reuses the UIView: an empty updateUIView keeps
        # playing session A after the user taps session B.
        update = self.view.split(
            "func updateUIView(_ uiView: PlayerUIView", 1)[1] \
            .split("}", 1)[0]
        self.assertIn("playerLayer.player", update)

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
        self.assertIn("onLongPressGesture", self.view)

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
        self.assertIn("● Record", home)
        self.assertIn("Upload video", home)
        self.assertLess(home.index("Upload video"), home.index('"Hub"'))
        self.assertLess(home.index('"Hub"'), home.index('"This device"'))

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
        self.assertIn("‹ Home", self.view)

    def test_upload_picker_saves_like_a_take(self):
        for token in ["UIDocumentPickerViewController", ".movie",
                      "showUploadPicker", "registerUpload"]:
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
        play = self.view.split("private func playInViewfinder", 1)[1] \
                        .split("private func playHubSession", 1)[0]
        self.assertIn('showScreen("record")', play)


if __name__ == "__main__":
    unittest.main()
