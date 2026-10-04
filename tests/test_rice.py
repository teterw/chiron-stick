"""Tests for the desktop theme engine (rice/chiron-rice): readable colours from any wallpaper palette."""
import importlib.machinery
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PATH = Path(__file__).resolve().parent.parent / "rice" / "chiron-rice"
loader = importlib.machinery.SourceFileLoader("chiron_rice", str(PATH))
spec = importlib.util.spec_from_loader("chiron_rice", loader)
rice = importlib.util.module_from_spec(spec)
loader.exec_module(rice)


def palette(bg, fg, colors):
    p = {"background": bg, "foreground": fg, "cursor": fg}
    p.update({f"color{i}": c for i, c in enumerate(colors)})
    return p


BRIGHT = palette("#f2efe9", "#2a2a2a", ["#e8e4dc", "#e9a3a3", "#a3d9a5", "#f2e2a0", "#a7c7e7", "#d7b4e8", "#a8e0dc", "#ffffff"] * 2)
DARK = palette("#101418", "#d6dde3", ["#101418", "#c0392b", "#27ae60", "#f1c40f", "#2980b9", "#8e44ad", "#16a085", "#ecf0f1"] * 2)
GREY = palette("#3a3a3a", "#9a9a9a", ["#3a3a3a", "#505050", "#5a5a5a", "#646464", "#6e6e6e", "#787878", "#828282", "#9a9a9a"] * 2)


class Colours(unittest.TestCase):
    def check(self, pal):
        c = rice.derive(pal)
        self.assertLessEqual(rice.luminance(c["bg"]), 0.03, "background must be dark")
        self.assertGreaterEqual(rice.contrast(c["fg"], c["bg"]), 7.0, "text must be readable (7:1)")
        self.assertGreaterEqual(rice.contrast(c["accent"], c["bg"]), 3.0, "accent must stand out (3:1)")
        self.assertGreaterEqual(rice.contrast(c["on_accent"], c["accent"]), 3.0, "text on accent readable")
        self.assertGreaterEqual(rice.contrast(c["muted"], c["bg"]), 4.5)
        for i, t in enumerate(c["term"]):
            if i not in (0, 8):
                self.assertGreaterEqual(rice.contrast(t, c["bg"]), 4.5, f"terminal colour {i}")

    def test_bright_wallpaper(self):
        self.check(BRIGHT)

    def test_dark_wallpaper(self):
        self.check(DARK)

    def test_low_colour_wallpaper(self):
        self.check(GREY)
        h, l, s = rice.colorsys.rgb_to_hls(*rice.derive(GREY)["accent"])
        self.assertGreaterEqual(s, 0.25, "a grey wallpaper still gets an accent with some colour")
        self.assertTrue(0.4 < h < 0.56, f"pure grey has no hue, so the accent is Chiron teal, not red (hue {h:.2f})")


class Layout(unittest.TestCase):
    def test_islands_match_plugin_order(self):
        layout = rice.load_layout()
        isl = rice.islands(layout)
        widgets = [w for i in isl for w in i["widgets"]]
        self.assertEqual(widgets[0], "whiskermenu-1")
        self.assertEqual(len(widgets), len(set(widgets)))
        css = rice.gtk_css(rice.derive(DARK), layout, solid_panel=False)
        for w in widgets:
            self.assertIn(f"#{w}", css)
        for launcher in (p.split(":")[1] for panel in layout["panels"] for item in panel["items"]
                         if item != "expand" for p in item if p.startswith("launcher:")):
            self.assertIn(launcher, layout["launchers"])


class Apply(unittest.TestCase):
    def test_failure_keeps_old_theme(self):
        """If any part of a new theme can't be made, nothing is written: no half-themed desktop."""
        with tempfile.TemporaryDirectory() as tmp, mock.patch.multiple(
                rice, HOME=Path(tmp), CACHE=Path(tmp) / "cache", run_wallust=lambda img: DARK,
                compositing=lambda: False, xfconf_get=lambda *a: "Chiron-a", xfconf=mock.DEFAULT,
                sh=mock.DEFAULT, fastfetch_jsonc=mock.Mock(side_effect=RuntimeError("boom"))) as mocks:
            img = Path(tmp) / "wall.png"
            img.write_bytes(b"not read: wallust is mocked")
            with self.assertRaises(RuntimeError):
                rice.apply(img)
            self.assertEqual([p for p in Path(tmp).rglob("*") if p.is_file() and p != img], [])
            mocks["xfconf"].assert_not_called()
            mocks["sh"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
