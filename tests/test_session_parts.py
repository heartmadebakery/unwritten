"""User-ordered Nov 3: record, upload, or fetch a video as the next part
of a previous session, or tie several sessions together, so they read
as one overall session.

The hub service owns the model (app/cloud-signer/worker.js:
session_parts, POST/DELETE /hub/parts, grouped list and detail, fetch
joinTo; behaviour lives in hub-check.mjs). These are the clients'
source contracts: web, Android and iOS move together — each offers
"Add a part" (Record / Upload / Fetch from link) and "Tie a session" on
a hub session, a visible "Adds a part to ..." note on the capture
screens, ties a take as soon as its upload has a video id (retried
until it lands), lists a tied session's parts, plays them in order,
unties one, and deletes the whole session only after naming every
part."""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REC = os.path.join(ROOT, "app", "recorder")
ANDROID = os.path.join(ROOT, "app", "android", "app", "src", "main", "java",
                       "org", "tinio", "unwritten")
IOS = os.path.join(ROOT, "app", "ios", "UnwrittenRecorder")
SIGNER = os.path.join(ROOT, "app", "cloud-signer")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def between(src, start, end):
    return src.split(start, 1)[1].split(end, 1)[0]


class SignerParts(unittest.TestCase):
    def test_migration_and_setup_name_0005(self):
        mig = read(SIGNER, "migrations", "0005_parts.sql")
        self.assertIn("CREATE TABLE IF NOT EXISTS session_parts", mig)
        self.assertIn("ADD COLUMN join_to", mig)
        worker = read(SIGNER, "worker.js")
        self.assertIn('session_parts: "0005_parts.sql"', worker)
        self.assertIn('join_to: "0005_parts.sql"', worker)
        for doc in [read(SIGNER, "wrangler.toml"), read(SIGNER, "README.md"),
                    read(ROOT, "docs", "SETUP.md")]:
            self.assertIn("0005_parts.sql", doc)
        self.assertIn("0005_parts.sql", read(SIGNER, "hub-check.mjs"))


class WebParts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.common = read(REC, "common.js")
        cls.home = read(REC, "home.js")
        cls.link = read(REC, "link.js")
        cls.pages = {n: read(REC, n) for n in
                     ("record.html", "upload.html", "link.html")}

    def test_capture_pages_show_the_session_they_add_to(self):
        for name, page in self.pages.items():
            self.assertIn('id="joinbanner"', page, name)
        self.assertIn("function joinTarget()", self.common)
        self.assertIn('get("after")', self.common)
        banner = between(self.common, "function paintJoinBanner()", "\n}\n")
        self.assertIn("Adds a part to", banner)
        # The way out is on the note itself: its own session instead.
        self.assertIn("data-join-clear", banner)
        # Upload's "Fetch from link" keeps the choice.
        self.assertIn("golink", banner)

    def test_a_take_is_tied_once_its_upload_has_an_id(self):
        save = between(self.common, "function saveBlob(", "\n}\n")
        self.assertIn("joinTo:", save)
        start = between(self.common, "async function startCloudUpload(", "\n}\n")
        self.assertIn("tieCloudPart(name)", start)
        tie = between(self.common, "async function tieCloudPart(", "\n}\n")
        self.assertIn("postParts([link.joinTo, link.videoId])", tie)
        post = between(self.common, "async function postParts(", "\n}\n")
        self.assertIn('"/hub/parts"', post)
        self.assertIn("videoIds: videoIds", post)
        self.assertIn("joined: true", tie)
        # Never silently stuck: a failed tie says so and is retried.
        self.assertIn("will retry", tie)
        resume = between(self.common, "function cloudResumePending(", "\n}\n")
        self.assertIn("tieCloudPart(", resume)
        self.assertIn("Part of", self.common)

    def test_link_queue_carries_the_session(self):
        self.assertIn("joinTo:", self.link)
        self.assertIn("joinTarget()", self.link)

    def test_hub_rows_and_detail_show_parts(self):
        row = between(self.common, "function hubRowHTML(", "\n}\n")
        self.assertIn("partCount", row)
        self.assertIn("pendingParts", row)
        detail = between(self.common, "function hubDetailHTML(", "\n}\n")
        for token in ["data-hub-part-play", "data-hub-untie", "Add a part",
                      "record.html?", "upload.html?", "link.html?",
                      "data-hub-act='tie'", "still processing", "Part "]:
            self.assertIn(token, detail, token)

    def test_play_untie_tie_and_delete_whole_session(self):
        play = between(self.common, "function playHubSession(", "\n}\n")
        self.assertIn("hubParts(whole)", play)
        self.assertIn("playHubSession(whole, i + 1)", play)
        self.assertIn("p.onended = next", play)
        self.assertIn("async function untieHubPart(", self.common)
        self.assertIn("async function tieHubSessions(", self.common)
        untie = between(self.common, "async function untieHubPart(", "\n}\n")
        self.assertIn('method: "DELETE"', untie)
        dele = between(self.common, "function confirmDeleteHub(", "\n}\n")
        self.assertIn("parts", dele)
        for token in ["data-hub-part-play", "data-hub-untie", "data-hub-tie",
                      '"tie"']:
            self.assertIn(token, self.home, token)


class AndroidParts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = read(ANDROID, "MainActivity.java")
        cls.hub = read(ANDROID, "HubClient.java")

    def test_hub_client_ties_unties_and_queues_with_join(self):
        self.assertIn("public JSONObject tie(java.util.List<String> videoIds)", self.hub)
        self.assertIn('"/hub/parts"', self.hub)
        self.assertIn("public boolean untie(String videoId)", self.hub)
        self.assertIn("public String queueFetchJob(String url, String joinTo)", self.hub)
        self.assertIn('put("joinTo", joinTo', self.hub)

    def test_capture_screens_show_the_session_they_add_to(self):
        self.assertIn("private String joinToVideoId", self.main)
        banner = between(self.main, "private LinearLayout joinBannerView()", "\n    }\n")
        paint = between(self.main, "private void paintJoinBanners()", "\n    }\n")
        self.assertIn("Adds a part to", paint)
        self.assertIn("Make it its own session", banner)
        for screen in ["recordScreen.addView(joinBannerView())",
                       "uploadScreen.addView(joinBannerView())",
                       "linkScreen.addView(joinBannerView())"]:
            self.assertIn(screen, self.main, screen)
        show = between(self.main, "private void showScreen(String name)", "\n    }\n")
        self.assertIn("paintJoinBanners()", show)
        # Home is the end of a continue: the choice never lingers.
        self.assertIn("if (home) clearJoinTarget()", show)

    def test_a_take_is_tied_once_its_upload_has_an_id(self):
        self.assertIn("private void markJoin(String name)", self.main)
        self.assertGreaterEqual(self.main.count("markJoin("), 3)  # def + take + upload
        start = between(self.main, "private void startCloudUpload(final File f)", "\n    }\n")
        on_session = between(start, "public void onSession(", "}")
        self.assertIn("tieCloudPart(name)", on_session)
        tie = between(self.main, "private void tieCloudPart(final String name)", "\n    }\n")
        self.assertIn(".tie(", tie)
        self.assertIn('"joined"', tie)
        self.assertIn("will retry", tie)
        resume = between(self.main, "private void cloudResumePending()", "\n    }\n")
        self.assertIn("tieCloudPart(", resume)
        self.assertIn("Part of ", self.main)

    def test_link_queue_carries_the_session(self):
        q = between(self.main, "private void queueFetchUrl(final String url)", "\n    }\n")
        self.assertIn("queueFetchJob(url, join)", q)

    def test_hub_rows_and_detail_show_parts(self):
        rows = between(self.main, "private void refreshHubRows()", "\n    }\n")
        self.assertIn("partCount", rows)
        self.assertIn("pendingParts", rows)
        detail = between(self.main, "private View hubDetailView(final JSONObject obj)", "\n    }\n")
        for token in ["Add a part", "Tie a session to this one", "Untie",
                      "still processing", "\"Part \" +", "startJoin(",
                      "showTiePicker(obj)", "playHubRemote(obj, idx)"]:
            self.assertIn(token, detail, token)

    def test_play_in_order_untie_and_delete_whole_session(self):
        play = between(self.main, "private void playHubRemote(final JSONObject whole, final int from)", "\n    }\n")
        self.assertIn("setOnCompletionListener", play)
        self.assertIn("playHubRemote(whole, from + 1)", play)
        self.assertIn("private void untieHubPart(", self.main)
        self.assertIn("private void tieHubSessions(", self.main)
        self.assertIn("private void confirmDeleteHubParts(", self.main)
        self.assertIn("Delete all ", self.main)


class IOSParts(unittest.TestCase):
    """No Xcode on Linux hosts: these are the contract; the build and a
    device walk-through happen on a Mac (docs/ios-app-worklog.md)."""

    @classmethod
    def setUpClass(cls):
        cls.store = read(IOS, "SessionStore.swift")
        cls.view = read(IOS, "ContentView.swift")
        cls.cloud = read(IOS, "CloudStore.swift")

    def test_models_carry_parts(self):
        self.assertIn("struct HubPart: Decodable", self.store)
        session = between(self.store, "struct HubSession: Decodable, Identifiable {", "\n}\n")
        for field in ["var parts: [HubPart]?", "var partCount: Int?",
                      "var pendingParts: Int?", "var groupId: String?"]:
            self.assertIn(field, session, field)
        self.assertIn("var part: Int?", between(self.store, "struct HubCorrection", "\n}\n"))
        self.assertIn("var part: Int?", between(self.store, "struct HubChapter", "\n}\n"))
        self.assertIn("func setLinkFields(", self.cloud)

    def test_capture_screens_show_the_session_they_add_to(self):
        self.assertIn("@Published var joinTo: HubSession?", self.store)
        self.assertIn("Adds a part to", self.view)
        self.assertIn("Make it its own session", self.view)
        self.assertGreaterEqual(self.view.count("joinBanner"), 4)  # def + 3 screens
        # Home is the end of a continue: the choice never lingers.
        on_path = between(self.view, ".onChange(of: path) { old, new in", "\n        }\n")
        self.assertIn("if new.isEmpty { store.joinTo = nil }", on_path)

    def test_a_take_is_tied_once_its_upload_has_an_id(self):
        reg = between(self.store, "private func registerLesson(url: URL)", "\n    }\n")
        self.assertIn("markJoin(", reg)
        start = between(self.store, "func startCloudUpload(_ name: String)", "\n    }\n")
        self.assertIn("tieCloudPart(name)", between(start, "onSession:", "onProgress:"))
        tie = between(self.store, "func tieCloudPart(_ name: String)", "\n    }\n")
        self.assertIn('"/hub/parts"', tie)
        self.assertIn('"joined": true', tie)
        self.assertIn("will retry", tie)
        resume = between(self.store, "func cloudResumePending()", "\n    }\n")
        self.assertIn("tieCloudPart(", resume)
        self.assertIn("Part of ", self.view)

    def test_link_queue_carries_the_session(self):
        q = between(self.store, "func queueFetchUrl(_ url: String)", "\n    }\n")
        self.assertIn('body["joinTo"] = join.videoId', q)

    def test_hub_rows_and_detail_show_parts(self):
        sub = between(self.store, "func hubSubtitle(for row: HubSession)", "\n    }\n")
        self.assertIn("partCount", sub)
        self.assertIn("pendingParts", sub)
        card = between(self.view, "private func hubDetailCard(_ detail: HubSession)", "\n    }\n")
        for token in ["Add a part", "Tie a session to this one", "Untie",
                      "still processing", "Part \\(", "store.joinTo = detail",
                      "pendingTie = detail", "playHubSession(detail, from: i)"]:
            self.assertIn(token, card, token)

    def test_play_in_order_untie_tie_and_delete_whole_session(self):
        play = between(self.view, "private func playHubSession(_ whole: HubSession, from: Int = 0)", "\n    }\n")
        self.assertIn("AVPlayerItemDidPlayToEndTime", play)
        self.assertIn("playHubSession(whole, from: from + 1)", play)
        for fn in ["func untieHubPart(", "func tieHubSessions(", "func hubParts("]:
            self.assertIn(fn, self.store, fn)
        dele = between(self.store, "func deleteHubSession(_ session: HubSession)", "\n    }\n")
        self.assertIn("hubParts(session)", dele)
        self.assertIn("Delete all \\(", self.view)


if __name__ == "__main__":
    unittest.main()
