"""iOS recorder contract: native port in parity with Android and web.

app/ios/ has exactly one job, like the other two recorders: record one
lesson, stop, keep the file. Same dark palette, same single-column
order (viewfinder, zoom, record, Cloud toggle, export, sessions), same
session-row contract (newest first, date + duration, tap to play in
the viewfinder, long-press to delete), same filename contract, same
presigned-TUS Cloud upload with the same link states.
"""
import glob
import os
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

    def test_leaving_mid_recording_keeps_the_take(self):
        self.assertIn("scenePhase", self.view)
        self.assertIn("stopVideo()", self.view)

    def test_mic_failure_warns_but_keeps_video(self):
        engine = read(ENGINE)
        self.assertIn("micWarning", engine)
        self.assertIn("No microphone", self.view)

    def test_session_start_never_throws_on_camera_less_devices(self):
        # startRunning throws an uncatchable ObjC exception with no
        # inputs (simulator, camera-less device): the engine must guard
        # it and start behind an exception handler instead.
        engine = read(ENGINE)
        self.assertIn("inputs.isEmpty", engine)
        self.assertIn("UWStartCaptureSession", engine)
        self.assertIn("UWStartCaptureSession", read(BRIDGE_H))
        self.assertIn("@try", read(BRIDGE_MM))

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

    def test_legacy_cloud_keys_migrated(self):
        # One-generation legacy storage key, marked legacy per the rule.
        self.assertIn("unwritten_bunny", self.cloud)  # legacy


class IOSParityTests(unittest.TestCase):
    """The iOS recorder mirrors the Android and web recorders' design.

    Same dark palette, same single-column order (viewfinder, zoom,
    record, cloud toggle, export, sessions), same session-row contract:
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
        self.assertIn("Unwritten Craft", self.view)
        self.assertIn("Film mentor session. Record and let it happen.", self.view)
        self.assertIn('"Sessions"', self.view)

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


if __name__ == "__main__":
    unittest.main()
