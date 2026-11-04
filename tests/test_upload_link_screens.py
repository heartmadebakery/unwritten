"""User-ordered Nov 3: home offers two main actions, Record or Upload
video. User-ordered Nov 4: the upload screen holds file and link —
choose a video, then Fetch from link, then previous attempts.
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
                    "com", "heartmadebakery", "unwritten", "MainActivity.java")
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

    def test_home_has_no_link_fetcher(self):
        for token in ['id="urlinput"', 'id="urlfetchbtn"', "Fetch from link",
                      "Paste a video link"]:
            self.assertNotIn(token, self.home, token)
        self.assertIn('href="upload.html"', self.home)

    def test_upload_holds_file_and_link(self):
        # User-ordered Nov 4: no separate link page — the fetch field
        # lives on the upload page after the upload section.
        for token in ['id="uploadinput"', 'id="uploadbtn"',
                      'id="urlinput"', 'id="urlfetchbtn"', 'id="urlstatus"',
                      "Fetch from link"]:
            self.assertIn(token, self.upload, token)
        self.assertIn('id="uphistory"', self.upload)
        for token in ['href="link.html"', 'id="golink"', 'src="link.js"',
                      'id="backbtn-link"']:
            self.assertNotIn(token, self.upload, token)
            self.assertNotIn(token, self.uploadjs, token)
        for token in ["/fetch/jobs", "Queued.", "Signer refused the token",
                      "function isDirectMediaUrl", "saveBlob(",
                      "joinTarget()", "logFetchAttempt"]:
            self.assertIn(token, self.uploadjs, token)
        self.assertNotIn("openCamera", self.uploadjs)

    def test_no_separate_link_page(self):
        # User-ordered Nov 4: link.html / link.js are gone; the shell
        # and the build ship only the upload page.
        for name in ["link.html", "link.js"]:
            self.assertFalse(os.path.exists(os.path.join(REC, name)), name)
        sw = read(REC, "sw.js")
        build = read(REC, "build.sh")
        for asset in ["link.html", "link.js"]:
            self.assertNotIn(asset, sw, asset)
            self.assertNotIn(asset, build, asset)

    def test_upload_page_lists_previous_attempts(self):
        # User-ordered Nov 4: the upload page lists previous
        # upload/fetch attempts, like the record page lists sessions —
        # an indicator that an upload or fetch occurred.
        for token in ['id="uphistory"', 'id="fetchhistory"']:
            self.assertIn(token, self.upload, token)
        for token in ["renderUploadHistory", '"upload_"', "map(clipHTML)",
                      "loadFetchAttempts", "data-cloud-retry"]:
            self.assertIn(token, self.uploadjs, token)

    def test_fetch_attempts_persist_locally(self):
        # Queue attempts log locally (URL + date + outcome, newest
        # first, capped) so the upload page can list them afterwards.
        common = read(REC, "common.js")
        for token in ["loadFetchAttempts", "logFetchAttempt",
                      "uw_fetch_attempts"]:
            self.assertIn(token, common, token)
        self.assertIn("logFetchAttempt", self.uploadjs)

    def test_shell_precaches_and_ships_the_upload_page(self):
        sw = read(REC, "sw.js")
        build = read(REC, "build.sh")
        for asset in ["upload.html", "upload.js"]:
            self.assertIn(asset, sw, asset)
            self.assertIn(asset, build, asset)

    def test_record_help_only_on_record_page(self):
        record = read(REC, "record.html")
        self.assertIn("teach the way you'd teach anyway", record)
        for name, src in [("home", self.home), ("upload", self.upload)]:
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

    def test_upload_screen_offers_file_and_link(self):
        # User-ordered Nov 4: no separate link screen — the fetch field
        # lives on the upload screen after the upload section.
        up = between(self.main, "private void buildUploadScreen",
                     "private void buildRecordScreen")
        for token in ["Choose a video", "pickUpload()", "Fetch from link",
                      "urlInput", "queueFetchUrl", "uploadHistory"]:
            self.assertIn(token, up, token)
        for token in ['showScreen("link")', "buildLinkScreen", "linkScreen"]:
            self.assertNotIn(token, self.main, token)

    def test_upload_screen_lists_previous_attempts(self):
        # User-ordered Nov 4: previous upload/fetch attempts list on
        # the upload screen like sessions list on the record screen —
        # an indicator that an upload or fetch occurred.
        up = between(self.main, "private void buildUploadScreen",
                     "private void buildRecordScreen")
        for token in ["uploadHistory", "renderUploadHistory()"]:
            self.assertIn(token, up, token)
        show = between(self.main, "private void showScreen",
                       "private void pickUpload")
        self.assertIn("renderUploadHistory()", show)
        for token in ["logFetchAttempt", "fetchAttempts",
                      '"upload_"', "retryCloud"]:
            self.assertIn(token, self.main, token)

    def test_screens_route_and_back_steps_up_one_level(self):
        show = between(self.main, "private void showScreen",
                       "private void pickUpload")
        for token in ['"upload"', "uploadScreen", "Upload video"]:
            self.assertIn(token, show, token)
        self.assertNotIn('"link"', show)
        back = between(self.main, "public void onBackPressed", "private String cloudWatchUrl")
        # Upload steps back to home; no link screen remains.
        self.assertNotIn('"link".equals(currentScreen)', back)
        self.assertIn('showScreen("home")', back)


class IOSUploadLinkScreens(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.view = read(IOS, "ContentView.swift")
        cls.store = read(IOS, "SessionStore.swift")
        cls.home = between(cls.view, "private var homeView",
                           "private func actionTile")
        cls.upload = between(cls.view, "private var uploadView",
                             "private var recordView")

    def test_routes(self):
        # User-ordered Nov 4: no separate fetch screen — record and
        # upload are the only capture routes.
        route = between(self.view, "enum Route", "}\n")
        for case in ["case record", "case upload"]:
            self.assertIn(case, route, case)
        self.assertNotIn("fetchLink", route)
        dest = between(self.view, ".navigationDestination(for: Route.self)",
                       "// Links, the back button")
        self.assertIn("uploadView", dest)
        self.assertNotIn("fetchLinkView", dest)
        for token in ["fetchLinkView", "case fetchLink",
                      "path.append(.fetchLink)"]:
            self.assertNotIn(token, self.view, token)

    def test_home_is_two_actions_then_hub(self):
        for token in ["Fetch from link", "fetchUrl", "TextField",
                      "store.status", "Menu {", "showPhotosPicker",
                      "showUploadPicker"]:
            self.assertNotIn(token, self.home, token)
        self.assertIn("path.append(.record)", self.home)
        self.assertIn("path.append(.upload)", self.home)
        self.assertLess(self.home.index("path.append(.upload)"),
                        self.home.index("store.hubRows"))

    def test_upload_screen_offers_file_and_link(self):
        # User-ordered Nov 4: no separate fetch screen — the fetch
        # field lives on the upload screen after the upload section.
        for token in ["Photo Library", "Files", "showPhotosPicker = true",
                      "showUploadPicker = true", "Fetch from link",
                      "TextField", "fetchUrl", "canFetchLink", "fetchLink()"]:
            self.assertIn(token, self.upload, token)

    def test_upload_screen_lists_previous_attempts(self):
        # User-ordered Nov 4: previous upload/fetch attempts list on
        # the upload screen like sessions list on the record screen —
        # an indicator that an upload or fetch occurred.
        for token in ["uploadHistory", "fetchAttempts", "upload_"]:
            self.assertIn(token, self.upload, token)
        cloud = read(IOS, "CloudStore.swift")
        for token in ["func fetchAttempts", "func logFetchAttempt",
                      "uw_cloud_fetchAttempts"]:
            self.assertIn(token, cloud, token)
        self.assertIn("logFetchAttempt", self.store)

    def test_record_help_is_the_record_screens_alone(self):
        # The store no longer boots with the camera help (it leaked onto
        # home); the record screen carries it as its own empty-status
        # line, and no other screen shows it.
        self.assertNotIn("Point the camera", self.store)
        record = between(self.view, "private var recordView",
                         "private func showScreen")
        self.assertIn("Point the camera at the mentor's hands", record)
        for name, src in [("home", self.home), ("upload", self.upload)]:
            self.assertNotIn("Point the camera", src, name)

    def test_status_never_follows_you_to_another_screen(self):
        change = between(self.view, ".onChange(of: path)",
                         ".onChange(of: engine.isRecording)")
        self.assertIn('store.status = ""', change)

    def test_upload_screen_shows_its_own_status(self):
        self.assertIn("store.status", self.upload)


if __name__ == "__main__":
    unittest.main()
