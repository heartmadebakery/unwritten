"""User-ordered Nov 4: an iOS install link like the Android one on the
home page footer. An iPhone cannot sideload a download, so the route is
TestFlight: build.sh archives a token-stamped Release build (like the
APK, so testers' uploads work without pasting a token) and uploads it
to App Store Connect; every upload carries a fresh build number.

Source-contract tests like the rest of the suite."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IOS = os.path.join(ROOT, "app", "ios")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


class TestFlightBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = read(IOS, "build.sh")
        cls.plist = read(IOS, "UnwrittenRecorder", "Info.plist")

    def test_testflight_mode_archives_and_uploads(self):
        tf = self.build.split('"${TESTFLIGHT:-}"', 1)[1].split("\nelif ", 1)[0]
        for token in ["archive", "-configuration Release",
                      "generic/platform=iOS", "-exportArchive",
                      "app-store-connect", "<string>upload</string>",
                      "-allowProvisioningUpdates"]:
            self.assertIn(token, tf, token)

    def test_testflight_needs_a_team_and_fails_naming_it(self):
        tf = self.build.split('"${TESTFLIGHT:-}"', 1)[1].split("\nelif ", 1)[0]
        self.assertIn("DEVELOPMENT_TEAM", tf)
        self.assertRegex(tf, r"TESTFLIGHT=1 needs DEVELOPMENT_TEAM")

    def test_upload_can_use_an_api_key_and_names_the_fix(self):
        # Xcode's account may lack App Store Connect access from the
        # command line ("Failed to Use Accounts"): an API key works
        # unattended, and a failed upload says which setting fixes it.
        tf = self.build.split('"${TESTFLIGHT:-}"', 1)[1].split("\nelif ", 1)[0]
        for token in ["ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_PATH",
                      "-authenticationKeyPath", "-authenticationKeyID",
                      "-authenticationKeyIssuerID", "Failed to Use Accounts",
                      "Settings → Accounts", "App record",
                      "New App, bundle ID com.heartmadebakery.unwritten"]:
            self.assertIn(token, tf, token)

    def test_testflight_build_is_token_stamped(self):
        # The stamp runs before every build mode, TestFlight included.
        self.assertLess(self.build.index("== stamp (signer token) =="),
                        self.build.index('"${TESTFLIGHT:-}"'))

    def test_every_upload_has_a_fresh_build_number(self):
        tf = self.build.split('"${TESTFLIGHT:-}"', 1)[1].split("\nelif ", 1)[0]
        self.assertRegex(tf, r"CURRENT_PROJECT_VERSION=\"?\$")
        build_ver = re.search(
            r"<key>CFBundleVersion</key>\s*<string>(.*?)</string>",
            self.plist).group(1)
        self.assertEqual(build_ver, "$(CURRENT_PROJECT_VERSION)")
        short = re.search(
            r"<key>CFBundleShortVersionString</key>\s*<string>(.*?)</string>",
            self.plist).group(1)
        self.assertEqual(short, "$(MARKETING_VERSION)")

    def test_export_compliance_is_declared(self):
        # HTTPS only (the signer, Stream, the hub): exempt encryption,
        # so App Store Connect does not hold each build for the question.
        self.assertRegex(
            self.plist,
            r"<key>ITSAppUsesNonExemptEncryption</key>\s*<false/>")


if __name__ == "__main__":
    unittest.main()
