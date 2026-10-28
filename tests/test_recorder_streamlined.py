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


if __name__ == "__main__":
    unittest.main()
