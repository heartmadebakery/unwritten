"""User-ordered Nov 3: the iOS app is a full iPad app, not an iPhone
app in compatibility mode — it supports the iPad in portrait and
landscape (all four orientations) while the iPhone stays portrait.
Recording and the viewfinder follow the iPad's orientation so a
landscape lesson is filmed landscape, upright.

Source-contract tests like the rest of the suite."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IOS = os.path.join(ROOT, "app", "ios")
APP = os.path.join(IOS, "UnwrittenRecorder")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


class IPadSupportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pbx = read(IOS, "UnwrittenRecorder.xcodeproj", "project.pbxproj")
        cls.plist = read(APP, "Info.plist")
        cls.engine = read(APP, "CameraEngine.swift")
        cls.view = read(APP, "ContentView.swift")

    def test_target_is_iphone_and_ipad(self):
        fams = re.findall(r"TARGETED_DEVICE_FAMILY = ([^;]+);", self.pbx)
        self.assertEqual(len(fams), 2, "Debug + Release")
        for f in fams:
            self.assertEqual(f.strip('"'), "1,2")

    def test_ipad_rotates_all_ways_iphone_stays_portrait(self):
        iphone = re.search(
            r"<key>UISupportedInterfaceOrientations</key>\s*<array>(.*?)</array>",
            self.plist, re.S).group(1)
        self.assertEqual(re.findall(r"<string>(.*?)</string>", iphone),
                         ["UIInterfaceOrientationPortrait"])
        ipad = re.search(
            r"<key>UISupportedInterfaceOrientations~ipad</key>\s*<array>(.*?)</array>",
            self.plist, re.S).group(1)
        self.assertEqual(
            sorted(re.findall(r"<string>(.*?)</string>", ipad)),
            sorted(["UIInterfaceOrientationPortrait",
                    "UIInterfaceOrientationPortraitUpsideDown",
                    "UIInterfaceOrientationLandscapeLeft",
                    "UIInterfaceOrientationLandscapeRight"]))

    def test_recording_follows_the_ipad_orientation(self):
        start = self.engine.split("func startVideo", 1)[1] \
                           .split("func stopVideo", 1)[0]
        self.assertIn("captureAngle", start)
        self.assertNotIn("videoRotationAngle = 90", start)
        # The iPhone keeps its portrait default.
        self.assertRegex(self.engine, r"captureAngle: CGFloat = 90")
        self.assertIn("func setInterfaceRotation", self.engine)

    def test_viewfinder_follows_the_ipad_orientation(self):
        pv = self.view.split("final class PreviewUIView", 1)[1] \
                      .split("struct CameraPreview", 1)[0]
        for token in ["userInterfaceIdiom == .pad",
                      "effectiveGeometry.interfaceOrientation",
                      "videoRotationAngle", "setInterfaceRotation"]:
            self.assertIn(token, pv, token)
        for angle in ["90", "270", "180"]:
            self.assertIn(angle, pv, angle)

    def test_screens_sit_in_a_readable_centered_column(self):
        # Edge-to-edge tiles and rows are unreadable on a 13-inch
        # screen in either orientation: every screen is a centered
        # column on the regular width class.
        self.assertIn("func readableColumn", self.view)
        body = self.view.split("var body: some View", 1)[1] \
                        .split(".tint(EMBER_INK)", 1)[0]
        for screen in ["homeView", "recordView", "uploadView",
                       "hubScreen(videoId)"]:
            self.assertRegex(body, screen.replace("(", r"\(").replace(")", r"\)")
                             + r"\s*\.readableColumn\(\)", screen)

    def test_home_title_moves_into_the_column_when_wide(self):
        self.assertIn("horizontalSizeClass", self.view)
        home = self.view.split("private var homeView", 1)[1] \
                        .split("private func actionTile", 1)[0]
        self.assertIn("Text(\"Unwritten Craft\")", home)
        body = self.view.split("var body: some View", 1)[1] \
                        .split(".tint(EMBER_INK)", 1)[0]
        self.assertIn("navigationBarTitleDisplayMode", body)

    def test_viewfinder_is_taller_on_the_ipad(self):
        record = self.view.split("private var recordView", 1)[1] \
                          .split("private func showScreen", 1)[0]
        self.assertNotIn(".frame(height: 300)", record)
        self.assertRegex(record, r"\.frame\(height: wide \? \d+ : 300\)")


if __name__ == "__main__":
    unittest.main()
