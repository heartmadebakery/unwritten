"""User-ordered Nov 3: home offers two main actions, Record or Upload
video. Upload video opens its own screen with two ways in — choose a
file, or Fetch from link — and Fetch from link is a screen of its own.
Status lines belong to the screen they report on: the "Point the
camera at the mentor's hands..." help is the Record screen's alone and
nothing leaks onto home or a sibling screen.

Source-contract tests like the rest of the suite: web, Android and iOS
move together."""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REC = os.path.join(ROOT, "app", "recorder")
MAIN = os.path.join(ROOT, "app", "android", "app", "src", "main", "java",
                    "org", "tinio", "unwritten", "MainActivity.java")
IOS = os.path.join(ROOT, "app", "ios", "UnwrittenRecorder")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def between(src, start, end):
    return src.split(start, 1)[1].split(end, 1)[0]


class WebUploadLinkScreens(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = read(REC, "index.html")
        cls.upload = read(REC, "upload.html")
        cls.uploadjs = read(REC, "upload.js")
        cls.link = read(REC, "link.html")
        cls.linkjs = read(REC, "link.js")

    def test_home_has_no_link_fetcher(self):
        for token in ['id="urlinput"', 'id="urlfetchbtn"', "Fetch from link",
                      "Paste a video link"]:
            self.assertNotIn(token, self.home, token)
        self.assertIn('href="upload.html"', self.home)

    def test_upload_offers_file_or_link(self):
        for token in ['id="uploadinput"', 'id="uploadbtn"',
                      'id="golink"', 'href="link.html"', "Fetch from link"]:
            self.assertIn(token, self.upload, token)
        # The link fetcher itself lives on its own page.
        for token in ['id="urlinput"', 'id="urlfetchbtn"', 'id="urlstatus"']:
            self.assertNotIn(token, self.upload, token)
        self.assertNotIn("/fetch/jobs", self.uploadjs)
        self.assertNotIn("urlfetchbtn", self.uploadjs)

    def test_link_page_is_its_own_screen(self):
        for token in ['id="urlinput"', 'id="urlfetchbtn"', 'id="urlstatus"',
                      'src="common.js"', 'src="link.js"', 'id="status"',
                      'id="backbtn-link"', 'href="upload.html"']:
            self.assertIn(token, self.link, token)
        for token in ["/fetch/jobs", "Queued.", "Signer refused the token",
                      "function isDirectMediaUrl", "saveBlob("]:
            self.assertIn(token, self.linkjs, token)
        self.assertNotIn("openCamera", self.linkjs)

    def test_shell_precaches_and_ships_the_link_page(self):
        sw = read(REC, "sw.js")
        build = read(REC, "build.sh")
        for asset in ["link.html", "link.js"]:
            self.assertIn(asset, sw, asset)
            self.assertIn(asset, build, asset)

    def test_record_help_only_on_record_page(self):
        record = read(REC, "record.html")
        self.assertIn("teach the way you'd teach anyway", record)
        for name, src in [("home", self.home), ("upload", self.upload),
                          ("link", self.link)]:
            self.assertNotIn("Record a new lesson", src, name)
            self.assertNotIn("Point the camera", src, name)


class AndroidUploadLinkScreens(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = read(MAIN)
        cls.home = between(cls.main, "private void buildHomeScreen",
                           "/** Upload video")

    def test_home_has_no_link_card(self):
        for token in ["Fetch from link", "urlInput", "Paste a link",
                      "queueFetchUrl", "pickUpload"]:
            self.assertNotIn(token, self.home, token)
        self.assertIn('showScreen("upload")', self.home)

    def test_upload_screen_offers_file_or_link(self):
        up = between(self.main, "private void buildUploadScreen",
                     "private void buildLinkScreen")
        for token in ["Choose a video", "pickUpload()", "Fetch from link",
                      'showScreen("link")']:
            self.assertIn(token, up, token)
        self.assertNotIn("urlInput", up)

    def test_link_screen_is_its_own_screen(self):
        link = between(self.main, "private void buildLinkScreen",
                       "/** A personal hello")
        for token in ["urlInput", "Fetch from link", "queueFetchUrl"]:
            self.assertIn(token, link, token)

    def test_screens_route_and_back_steps_up_one_level(self):
        show = between(self.main, "private void showScreen",
                       "private void pickUpload")
        for token in ['"upload"', '"link"', "uploadScreen", "linkScreen",
                      "Upload video", "Fetch from link"]:
            self.assertIn(token, show, token)
        back = between(self.main, "public void onBackPressed", "private String cloudWatchUrl")
        # Link steps back to Upload, Upload to home.
        self.assertIn('"link".equals(currentScreen)', back)
        self.assertIn('showScreen("upload")', back)


class IOSUploadLinkScreens(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.view = read(IOS, "ContentView.swift")
        cls.store = read(IOS, "SessionStore.swift")
        cls.home = between(cls.view, "private var homeView",
                           "private func actionTile")
        cls.upload = between(cls.view, "private var uploadView",
                             "private var fetchLinkView")
        cls.fetch = between(cls.view, "private var fetchLinkView",
                            "private var recordView")

    def test_routes(self):
        route = between(self.view, "enum Route", "}\n")
        for case in ["case record", "case upload", "case fetchLink"]:
            self.assertIn(case, route, case)
        dest = between(self.view, ".navigationDestination(for: Route.self)",
                       "// Links, the back button")
        for token in ["uploadView", "fetchLinkView"]:
            self.assertIn(token, dest, token)

    def test_home_is_two_actions_then_hub(self):
        for token in ["Fetch from link", "fetchUrl", "TextField",
                      "store.status", "Menu {", "showPhotosPicker",
                      "showUploadPicker"]:
            self.assertNotIn(token, self.home, token)
        self.assertIn("path.append(.record)", self.home)
        self.assertIn("path.append(.upload)", self.home)
        self.assertLess(self.home.index("path.append(.upload)"),
                        self.home.index("store.hubRows"))

    def test_upload_screen_offers_file_or_link(self):
        for token in ["Photo Library", "Files", "showPhotosPicker = true",
                      "showUploadPicker = true", "Fetch from link",
                      "path.append(.fetchLink)"]:
            self.assertIn(token, self.upload, token)
        for token in ["TextField", "fetchUrl"]:
            self.assertNotIn(token, self.upload, token)

    def test_fetch_link_screen_is_its_own_screen(self):
        for token in ["TextField", "fetchUrl", "canFetchLink", "fetchLink()",
                      "Fetch from link", ".navigationTitle"]:
            self.assertIn(token, self.fetch, token)

    def test_record_help_is_the_record_screens_alone(self):
        # The store no longer boots with the camera help (it leaked onto
        # home); the record screen carries it as its own empty-status
        # line, and no other screen shows it.
        self.assertNotIn("Point the camera", self.store)
        record = between(self.view, "private var recordView",
                         "private func showScreen")
        self.assertIn("Point the camera at the mentor's hands", record)
        for name, src in [("home", self.home), ("upload", self.upload),
                          ("fetch", self.fetch)]:
            self.assertNotIn("Point the camera", src, name)

    def test_status_never_follows_you_to_another_screen(self):
        change = between(self.view, ".onChange(of: path)",
                         ".onChange(of: engine.isRecording)")
        self.assertIn('store.status = ""', change)

    def test_upload_and_fetch_screens_show_their_own_status(self):
        for name, src in [("upload", self.upload), ("fetch", self.fetch)]:
            self.assertIn("store.status", src, name)


if __name__ == "__main__":
    unittest.main()
