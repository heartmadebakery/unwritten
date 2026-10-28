"""Streamlined recorder contract (Oct 27 simplification, applied to app/).

Both recorders have exactly one job: record one lesson, stop, keep the
file. No roles/modes, no session steps, no apprentice line, no companion
sync. The pipeline takes the largest media file as the lesson, so every
take is named unwritten_lesson_<timestamp>.<ext>.
"""
import os
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
WEB = os.path.join(ROOT, "app", "recorder", "index.html")
MANIFEST = os.path.join(ROOT, "app", "recorder", "manifest.webmanifest")
MAIN = os.path.join(ROOT, "app", "android", "app", "src", "main", "java",
                    "org", "tinio", "unwritten", "MainActivity.java")
NAMES = os.path.join(ROOT, "app", "android", "app", "src", "main", "java",
                     "org", "tinio", "unwritten", "Names.java")
PREFS = os.path.join(ROOT, "app", "android", "app", "src", "main", "java",
                     "org", "tinio", "unwritten", "Prefs.java")

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

    def test_manifest_is_the_recorder_not_the_apprentice(self):
        manifest = read(MANIFEST)
        self.assertNotIn("Apprentice", manifest)
        self.assertIn("Recorder", manifest)


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


BUNNY_UPLOADER = os.path.join(ROOT, "app", "android", "app", "src", "main",
                              "java", "org", "tinio", "unwritten",
                              "BunnyUploader.java")
SIGNER = os.path.join(ROOT, "app", "bunny-signer", "worker.js")
ANDROID_MANIFEST = os.path.join(ROOT, "app", "android", "app", "src", "main",
                                "AndroidManifest.xml")


class BunnyWebTests(unittest.TestCase):
    """Optional Bunny Stream upload (Oct 2026): local save stays first;
    Bunny only ever receives a copy, and only when turned on."""

    @classmethod
    def setUpClass(cls):
        cls.html = read(WEB)

    def test_bunny_is_opt_in_with_settings(self):
        self.assertIn('id="bunnytoggle"', self.html)
        self.assertIn('id="bunnypanel"', self.html)
        self.assertIn('id="bunnysigner"', self.html)
        self.assertIn("bunnyReady()", self.html)

    def test_upload_uses_presigned_tus(self):
        self.assertIn("https://video.bunnycdn.com/tusupload", self.html)
        self.assertIn("AuthorizationSignature", self.html)
        self.assertIn("AuthorizationExpire", self.html)
        self.assertIn("Upload-Offset", self.html)

    def test_streaming_link_is_bunny_embed(self):
        self.assertIn("https://player.mediadelivery.net/embed/", self.html)

    def test_local_save_still_comes_first(self):
        # The vault write and download copy stay; Bunny hooks after them.
        save = self.html.split("function saveBlob", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("idbPut", save)
        self.assertLess(save.index("idbPut"), save.index("startBunnyUpload"))


class BunnyAndroidTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.main = read(MAIN)
        cls.uploader = read(BUNNY_UPLOADER)
        cls.manifest = read(ANDROID_MANIFEST)

    def test_internet_permission_added_for_upload_only(self):
        self.assertIn("android.permission.INTERNET", self.manifest)

    def test_uploader_speaks_presigned_tus(self):
        self.assertIn("https://video.bunnycdn.com/tusupload", self.uploader)
        self.assertIn("AuthorizationSignature", self.uploader)
        self.assertIn("SHA-256", self.uploader)

    def test_main_activity_gates_upload_behind_settings(self):
        self.assertIn("BunnyUploader", self.main)
        self.assertIn("bunnyEnabledCfg", self.main)
        self.assertIn("maybeBunnyUpload", self.main)


class BunnySignerTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.worker = read(SIGNER)

    def test_signer_holds_key_and_signs(self):
        self.assertIn("BUNNY_API_KEY", self.worker)
        self.assertIn("SHA-256", self.worker)
        self.assertIn("player.mediadelivery.net/embed/", self.worker)

    def test_signer_supports_resume_and_status(self):
        self.assertIn("videoId", self.worker)
        self.assertIn("X-Signer-Token", self.worker)


if __name__ == "__main__":
    unittest.main()
