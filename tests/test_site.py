"""Tests for the Unwritten website builder: session discovery,
metadata, hub rendering, and the full build."""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import make_site


def fixture_work(parent, name="work"):
    path = os.path.join(parent, name)
    os.makedirs(os.path.join(path, "clips"))
    with open(os.path.join(path, "writeup.md"), "w") as fh:
        fh.write("# Mentor's Soup — the write-up\n\nA short blurb here.\n\n"
                 "## Steps\n\n1. Boil.\n")
    with open(os.path.join(path, "corrections.json"), "w") as fh:
        json.dump([], fh)
    with open(os.path.join(path, "manifest.json"), "w") as fh:
        fh.write('{"lesson": "unwritten_lesson_20261029-123022.mp4"}')
    with open(os.path.join(path, "poster.jpg"), "wb") as fh:
        fh.write(b"fakejpeg")
    return path


class TestDiscovery(unittest.TestCase):
    def test_finds_writeup_dirs_only(self):
        with tempfile.TemporaryDirectory() as td:
            fixture_work(td, "a")
            os.makedirs(os.path.join(td, "notasession"))
            found = make_site.find_sessions(td)
        self.assertEqual([name for name, _ in found], ["a"])

    def test_meta_from_files(self):
        with tempfile.TemporaryDirectory() as td:
            path = fixture_work(td)
            title, date, blurb = make_site.session_meta(path)
        self.assertEqual(title, "Mentor's Soup — the write-up")
        self.assertEqual(date, "Oct 29, 2026")
        self.assertEqual(blurb, "A short blurb here.")

    def test_meta_falls_back(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "w")
            os.makedirs(path)
            with open(os.path.join(path, "writeup.md"), "w") as fh:
                fh.write("no heading here\n")
            title, date, blurb = make_site.session_meta(path)
        self.assertEqual(title, "w")
        self.assertEqual(blurb, "")
        self.assertRegex(date, r"^[A-Z][a-z]{2} \d{1,2}, \d{4}$")


class TestRenderHub(unittest.TestCase):
    def test_cards_and_empty_state(self):
        html = make_site.render_hub(
            [("abc", "T", "Oct 29, 2026", "B", True)])
        self.assertIn('href="recorder/"', html)
        self.assertIn("sessions/abc/page.html", html)
        self.assertIn("sessions/abc/poster.jpg", html)
        self.assertIn("#17130E", html)
        empty = make_site.render_hub([])
        self.assertIn("No sessions yet", empty)


class TestBuild(unittest.TestCase):
    def test_full_build(self):
        with tempfile.TemporaryDirectory() as td:
            root = os.path.join(td, "root")
            os.makedirs(root)
            fixture_work(root, "lesson1")
            rec = os.path.join(td, "rec")
            os.makedirs(rec)
            with open(os.path.join(rec, "index.html"), "w") as fh:
                fh.write("<p>recorder</p>")
            site = os.path.join(td, "site")
            argv = sys.argv
            sys.argv = ["make_site", root, site, "--recorder", rec]
            try:
                make_site.main()
            finally:
                sys.argv = argv
            self.assertTrue(os.path.isfile(
                os.path.join(site, "index.html")))
            self.assertTrue(os.path.isfile(
                os.path.join(site, "recorder", "index.html")))
            page = os.path.join(site, "sessions", "lesson1", "page.html")
            self.assertTrue(os.path.isfile(page))
            with open(page) as fh:
                self.assertIn("Boil.", fh.read())


class TestPageNav(unittest.TestCase):
    def test_session_pages_link_hub_and_recorder(self):
        with tempfile.TemporaryDirectory() as td:
            root = os.path.join(td, "root")
            os.makedirs(root)
            fixture_work(root, "lesson1")
            site = os.path.join(td, "site")
            rec = os.path.join(td, "rec")
            os.makedirs(rec)
            with open(os.path.join(rec, "index.html"), "w") as fh:
                fh.write("<p>recorder</p>")
            argv = sys.argv
            sys.argv = ["make_site", root, site, "--recorder", rec]
            try:
                make_site.main()
            finally:
                sys.argv = argv
            with open(os.path.join(
                    site, "sessions", "lesson1", "page.html")) as fh:
                html = fh.read()
            # Back to the hub list and over to the recorder, by
            # relative path so the site works from any base URL.
            self.assertIn('href="../../"', html)
            self.assertIn('href="../../recorder/"', html)


if __name__ == "__main__":
    unittest.main()
