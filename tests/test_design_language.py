"""Hearth design language contract (user-ordered Nov 2).

All three apps share one design language — docs/DESIGN.md — and draw
it in their own platform idiom: warm paper with a matching dark set
that follows the system, one ember accent, action tiles, cover tiles
for lessons, frames of the video for device sessions, and statuses in
words. These tests hold the shared tokens and components in step
across web, Android, and iOS; the per-platform files keep their own
contracts (test_recorder_streamlined.py, test_ios_recorder.py).
"""
import os
import re
import struct
import unittest
import zlib

ROOT = os.path.join(os.path.dirname(__file__), "..")
DESIGN = os.path.join(ROOT, "docs", "DESIGN.md")
CSS = os.path.join(ROOT, "app", "recorder", "app.css")
COMMON = os.path.join(ROOT, "app", "recorder", "common.js")
HOME_JS = os.path.join(ROOT, "app", "recorder", "home.js")
INDEX = os.path.join(ROOT, "app", "recorder", "index.html")
ANDROID_SRC = os.path.join(ROOT, "app", "android", "app", "src", "main")
MAIN = os.path.join(ANDROID_SRC, "java", "org", "tinio", "unwritten", "MainActivity.java")
GLYPHS = os.path.join(ANDROID_SRC, "java", "org", "tinio", "unwritten", "Glyphs.java")
LAUNCHER = os.path.join(ANDROID_SRC, "res", "mipmap-anydpi-v26", "ic_launcher.xml")
COLORS = os.path.join(ANDROID_SRC, "res", "values", "colors.xml")
VIEW = os.path.join(ROOT, "app", "ios", "UnwrittenRecorder", "ContentView.swift")
IOS_ICON = os.path.join(ROOT, "app", "ios", "UnwrittenRecorder", "Assets.xcassets",
                        "AppIcon.appiconset", "icon-1024.png")
PWA_ICON = os.path.join(ROOT, "app", "recorder", "icons", "icon-512.png")

# The canonical tokens (docs/DESIGN.md), light then dark.
PALETTE = {
    "canvas": ("FAF6F1", "171310"), "surface": ("FFFFFF", "221C18"),
    "sunken": ("F3ECE4", "2D2621"), "ink": ("2A211C", "F7EFE6"),
    "ink2": ("6F625A", "B9AA9C"), "line": ("EADFD3", "3A312A"),
    "ring": ("DCCFC2", "5A4E44"), "emberInk": ("B83A20", "FF8A6B"),
    "emberSoft": ("FCE8E1", "3A2420"), "sage": ("2F7A4B", "7FD39B"),
    "sageSoft": ("E3F2E7", "1F2E24"), "honey": ("8A5A00", "F2C46B"),
    "honeySoft": ("FFF3D6", "33281A"),
}
EMBER = "D2452A"
WASHES = [("FCE3D9", "B5432A", "3A2420", "FF9C82"), ("FBEFD2", "8A5A00", "33281A", "F2C46B"),
          ("E2EFE1", "2F6B3F", "1F2E24", "7FD39B"), ("DDEBF4", "2B5F80", "1C2A33", "8CC4E6"),
          ("ECE3F3", "6A4486", "2B2233", "C7A6E0"), ("F2E3D8", "8A4F2E", "33251C", "E0A884")]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def png_pixel(path, x, y):
    """RGB of one pixel of an 8-bit RGB PNG (no external libraries)."""
    with open(path, "rb") as f:
        data = f.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, width, height = 8, b"", 0, 0
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, ctype = struct.unpack(">IIBB", body[:10])
            assert (depth, ctype) == (8, 2), "expects 8-bit RGB"
        elif kind == b"IDAT":
            idat += body
        pos += 12 + length
    raw, stride, prev, rows = zlib.decompress(idat), width * 3, None, []
    for r in range(height):
        f = raw[r * (stride + 1)]
        line = bytearray(raw[r * (stride + 1) + 1:(r + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - 3] if i >= 3 else 0
            b = prev[i] if prev else 0
            c = prev[i - 3] if prev and i >= 3 else 0
            if f == 1: line[i] = (line[i] + a) & 255
            elif f == 2: line[i] = (line[i] + b) & 255
            elif f == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        rows.append(line)
        prev = line
    return tuple(rows[y][x * 3:x * 3 + 3])


class HearthTokensTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = read(DESIGN)
        cls.css = read(CSS).upper()
        cls.main = read(MAIN).upper()
        cls.view = read(VIEW).upper()

    def test_design_doc_is_the_spec(self):
        for token in ["Hearth", "canvas", "ember", "Cover tiles", "Status chips",
                      "Shutter dock", "Per platform"]:
            self.assertIn(token, self.design, token)
        for light, dark in PALETTE.values():
            self.assertIn("`#%s`" % light, self.design)
            self.assertIn("`#%s`" % dark, self.design)

    def test_same_palette_on_every_platform(self):
        for name, (light, dark) in PALETTE.items():
            for platform, src in (("web", self.css), ("android", self.main), ("ios", self.view)):
                self.assertIn(light, src, "%s light on %s" % (name, platform))
                self.assertIn(dark, src, "%s dark on %s" % (name, platform))
        for src in (self.css, self.main, self.view):
            self.assertIn(EMBER, src)

    def test_same_cover_washes_on_every_platform(self):
        for wash in WASHES:
            for hexv in wash:
                for platform, src in (("web", self.css), ("android", self.main), ("ios", self.view)):
                    self.assertIn(hexv, src, "%s on %s" % (hexv, platform))

    def test_same_wash_rule_on_every_platform(self):
        # Sum of the title's UTF-16 code units, modulo 6: a lesson wears
        # the same colour on every platform.
        common = read(COMMON)
        self.assertIn("n += s.charCodeAt(k)", common)
        self.assertIn("return n % 6;", common)
        main = read(MAIN)
        self.assertIn("n += title.charAt(i)", main)
        self.assertIn("return n % 6;", main)
        view = read(VIEW)
        self.assertIn("title.utf16.reduce(0) { $0 + Int($1) } % 6", view)


class HearthComponentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = read(CSS)
        cls.common = read(COMMON)
        cls.homejs = read(HOME_JS)
        cls.index = read(INDEX)
        cls.main = read(MAIN)
        cls.view = read(VIEW)

    def test_light_and_dark_follow_the_system(self):
        self.assertIn("@media (prefers-color-scheme: dark)", self.css)
        self.assertIn("UI_MODE_NIGHT_MASK", self.main)
        self.assertIn("SYSTEM_UI_FLAG_LIGHT_STATUS_BAR", self.main)
        self.assertIn("userInterfaceStyle == .dark", self.view)
        # iOS no longer forces dark: only the full-screen device player
        # (video on black) keeps a dark scheme.
        self.assertEqual(self.view.count(".preferredColorScheme(.dark)"), 1)
        cover = self.view.split("private var devicePlayerCover", 1)[1] \
                         .split("// ---------- screens", 1)[0]
        self.assertIn(".preferredColorScheme(.dark)", cover)

    def test_greeting_on_every_home(self):
        for src in (self.homejs, self.main, self.view):
            for word in ["Good morning", "Good afternoon", "Good evening"]:
                self.assertIn(word, src, word)
        self.assertIn('id="greeting"', self.index)

    def test_action_tiles_on_every_home(self):
        self.assertIn('class="tile primary" id="gorecord"', self.index)
        self.assertIn("private LinearLayout actionTile(", self.main)
        self.assertIn("private func actionTile(", self.view)
        for src in (self.index, self.main, self.view):
            self.assertIn("Film a lesson, the way you'd teach anyway", src)
            self.assertIn("From your phone or a link", src)

    def test_lessons_wear_cover_tiles(self):
        row = self.common.split("function hubRowHTML", 1)[1].split("\nvar ", 1)[0]
        self.assertIn("coverHTML(", row)
        rows = self.main.split("private void refreshHubRows", 1)[1] \
                        .split("\n    private ", 1)[0]
        self.assertIn("cover(title", rows)
        self.assertIn("coverTile(row.title", self.view)

    def test_device_sessions_show_a_frame_of_the_video(self):
        # Probed once, off the main thread, cached; a warm cover until then.
        self.assertIn("function probeClip", self.common)
        self.assertIn('toDataURL("image/jpeg"', self.common)
        probe = self.main.split("private void probeClip", 1)[1] \
                         .split("\n    private ", 1)[0]
        self.assertIn("cloudExec.execute", probe)
        self.assertIn("getFrameAtTime", probe)
        self.assertIn("runOnUiThread", probe)
        self.assertIn("struct LessonThumb", self.view)
        self.assertIn("AVAssetImageGenerator", self.view)

    def test_statuses_are_words_in_chips(self):
        for word in ["Uploading ", "Preparing", "In the cloud", "Upload failed"]:
            for platform, src in (("web", self.common), ("android", self.main), ("ios", self.view)):
                self.assertIn(word, src, "%s on %s" % (word, platform))
        self.assertIn(".chip.sage", self.css)
        self.assertIn("private TextView chip(", self.main)
        self.assertIn("private func statusChip(", self.view)

    def test_corrections_are_quote_cards(self):
        for src in (self.common, self.main, self.view):
            self.assertIn("Correcting: ", src)
        self.assertIn("<figure class='quote'>", self.common)

    def test_upload_progress_is_a_ring(self):
        self.assertIn("conic-gradient", self.css)
        self.assertIn("progressRing(", self.main)
        self.assertIn(".trim(from: 0, to:", self.view)

    def test_press_feedback_respects_reduced_motion(self):
        motion = self.css.split("@media (prefers-reduced-motion: reduce)", 1)[1]
        self.assertIn(".tile:active", motion)
        self.assertIn("transform:none", motion)
        self.assertIn("struct SquishStyle", self.view)
        self.assertIn("scaleX(0.96f)", self.main)

    def test_android_icons_are_drawn_in_code(self):
        # No icon assets and no AndroidX: line glyphs drawn on a canvas,
        # javac-checkable with the rest of the UI.
        glyphs = read(GLYPHS)
        self.assertIn("final class Glyphs extends Drawable", glyphs)
        for name in ["RECORD", "UPLOAD", "SHARE", "DOWNLOAD", "RETRY", "REFRESH", "TRASH", "CAMERA"]:
            self.assertIn(name, glyphs, name)
        self.assertNotIn("android.R.drawable.ic_menu_camera", self.main)


class HearthIconTests(unittest.TestCase):
    def test_launchers_are_ember(self):
        self.assertIn("@color/uw_ember", read(LAUNCHER))
        self.assertIn("#D2452A", read(COLORS))
        ember = (0xD2, 0x45, 0x2A)
        self.assertEqual(png_pixel(PWA_ICON, 4, 4), ember)
        self.assertEqual(png_pixel(IOS_ICON, 8, 8), ember)


if __name__ == "__main__":
    unittest.main()
