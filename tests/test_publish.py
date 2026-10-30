"""Tests for the hub publish step and the hub store schema."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import publish


SENT = {}


class FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_urlopen(req, timeout=None):
    url = req.full_url
    SENT["url"] = url
    SENT["token"] = req.get_header("X-signer-token")
    if url.startswith("https://video.bunnycdn.com/"):
        return FakeResponse(200, {"availableResolutions": "720p,480p"})
    if url.endswith("/hub/publish"):
        SENT["payload"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse(200, {"published": SENT["payload"]["videoId"]})
    raise AssertionError("unexpected url " + url)


def fixture_work(parent):
    work = os.path.join(parent, "lesson1")
    os.makedirs(work)
    with open(os.path.join(work, "writeup.md"), "w") as fh:
        fh.write("# Bread\n\nTasty body.\n")
    with open(os.path.join(work, "corrections.json"), "w") as fh:
        json.dump([{"start": "0:42", "quote": "q", "correcting": "c",
                   "segment": "s"}], fh)
    with open(os.path.join(work, "chapters.json"), "w") as fh:
        json.dump([{"start": "0:00", "label": "Intro"}], fh)
    return work


class TestPublish(unittest.TestCase):
    def setUp(self):
        SENT.clear()
        self.real = publish.urllib.request.urlopen
        publish.urllib.request.urlopen = fake_urlopen
        self.env = dict(os.environ)
        os.environ["CLOUD_LIBRARY_ID"] = "L"
        os.environ["CLOUD_LIBRARY_KEY"] = "K"
        os.environ["CLOUD_CDN_HOSTNAME"] = "cdn.example"

    def tearDown(self):
        publish.urllib.request.urlopen = self.real
        os.environ.clear()
        os.environ.update(self.env)

    def run_publish(self, td, extra=()):
        work = fixture_work(td)
        state = os.path.join(td, "cloud_state.json")
        with open(state, "w") as fh:
            json.dump({"vid-1": {"title": "Bread", "workDir": work}}, fh)
        argv = ["publish", "--work", work, "--state", state,
                "--signer", "https://signer.test", "--token", "sekret"]
        publish.main(list(argv[1:]) + list(extra))

    def test_posts_payload_to_hub_publish(self):
        with tempfile.TemporaryDirectory() as td:
            self.run_publish(td)
        self.assertEqual(SENT["url"],
                         "https://signer.test/hub/publish")
        self.assertEqual(SENT["token"], "sekret")
        body = SENT["payload"]
        self.assertEqual(body["videoId"], "vid-1")
        self.assertEqual(body["title"], "Bread")
        self.assertIn("Tasty body", body["writeupMd"])
        self.assertEqual(body["corrections"][0]["quote"], "q")
        self.assertEqual(body["chapters"][0]["label"], "Intro")
        self.assertIn("playlist.m3u8", body["hlsUrl"])
        self.assertIn("play_720p", body["mp4Url"])

    def test_guid_override(self):
        with tempfile.TemporaryDirectory() as td:
            work = fixture_work(td)
            state = os.path.join(td, "cloud_state.json")
            with open(state, "w") as fh:
                json.dump({}, fh)
            publish.main(["--work", work, "--state", state,
                          "--signer", "https://signer.test",
                          "--token", "sekret", "--guid", "vid-9"])
        self.assertEqual(SENT["payload"]["videoId"], "vid-9")

    def test_missing_guid_exits(self):
        with tempfile.TemporaryDirectory() as td:
            work = fixture_work(td)
            state = os.path.join(td, "cloud_state.json")
            with open(state, "w") as fh:
                json.dump({}, fh)
            with self.assertRaises(SystemExit):
                publish.main(["--work", work, "--state", state,
                              "--signer", "https://signer.test",
                              "--token", "sekret"])

    def test_missing_writeup_exits(self):
        with tempfile.TemporaryDirectory() as td:
            work = os.path.join(td, "empty")
            os.makedirs(work)
            state = os.path.join(td, "cloud_state.json")
            with open(state, "w") as fh:
                json.dump({"vid-1": {"workDir": work}}, fh)
            with self.assertRaises(SystemExit):
                publish.main(["--work", work, "--state", state,
                              "--signer", "https://signer.test",
                              "--token", "sekret", "--guid", "vid-1"])


class TestHubSchema(unittest.TestCase):
    def test_migration_builds_sessions_table(self):
        mig = os.path.join(ROOT, "app", "cloud-signer", "migrations",
                           "0001_sessions.sql")
        con = sqlite3.connect(":memory:")
        with open(mig) as fh:
            con.executescript(fh.read())
        con.execute(
            "INSERT INTO sessions (video_id, title) VALUES (?, ?)",
            ("v1", "Bread"))
        con.execute(
            "INSERT INTO sessions (video_id, title) VALUES (?, ?) "
            "ON CONFLICT(video_id) DO UPDATE SET title=excluded.title",
            ("v1", "Bread v2"))
        rows = con.execute(
            "SELECT video_id, title FROM sessions").fetchall()
        self.assertEqual(rows, [("v1", "Bread v2")])


if __name__ == "__main__":
    unittest.main()
