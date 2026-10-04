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
        self.assertTrue(0.68 < h < 0.78, f"pure grey has no hue, so the accent is Chiron violet, not red (hue {h:.2f})")


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


class Palette(unittest.TestCase):
    def test_wallust_printout_and_cache(self):
        """The 16 colours come from wallust's printout (its info line ignored) and are kept in our
        own small cache, never in wallust's (which grows by megabytes per image)."""
        hexes = [f"#{i:02x}{i:02x}{i + 5:02x}" for i in range(0, 160, 10)]
        out = "\x1b[1m[I]\x1b[0m config: Not using a configuration file, using default values.\n" + "\n".join(hexes) + "\n"
        run = mock.Mock(return_value=mock.Mock(returncode=0, stdout=out, stderr=""))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(rice, "CACHE", Path(tmp)), \
                mock.patch.object(rice.subprocess, "run", run):
            img = Path(tmp) / "wall.jpg"
            img.write_bytes(b"not read: wallust is mocked")
            p = rice.run_wallust(img)
            self.assertEqual([p[f"color{i}"] for i in range(16)], hexes)
            self.assertEqual((p["background"], p["foreground"]), (hexes[0], hexes[15]))
            self.assertEqual(rice.run_wallust(img), p)
            self.assertEqual(run.call_count, 1, "the second time comes from the cache")
            args = run.call_args[0][0]
            self.assertIn("-n", args)  # wallust's own cache off
            self.assertIn("--print-scheme", args)


class Collections(unittest.TestCase):
    def test_sets_and_review(self):
        """Collections in wallsources.conf order, then folders of your own; still pictures only;
        .git skipped; pictures removed in the review never show; client mode keeps to calm ones."""
        with tempfile.TemporaryDirectory() as tmp:
            walls = Path(tmp) / "walls"
            for rel in ("mine/f.webp", "d3ext/images/e.gif", "d3ext/.git/objects/x.jpg", "rose-pine/anime/d.png",
                        "rose-pine/photography/c.png", "elementary/backgrounds/b.jpg", "space/a.jpg"):
                (walls / rel).parent.mkdir(parents=True, exist_ok=True)
                (walls / rel).write_bytes(b"x")
            with mock.patch.multiple(rice, WALLS=walls, REVIEW=Path(tmp) / "review.json"):
                rice.save_review({"keep": set(), "drop": {"rose-pine/anime/d.png"}})
                personal = [str(p.relative_to(walls)) for p in rice.wallpapers("personal")]
                client = [str(p.relative_to(walls)) for p in rice.wallpapers("client")]
        self.assertEqual(personal, ["space/a.jpg", "elementary/backgrounds/b.jpg", "rose-pine/photography/c.png", "mine/f.webp"])
        self.assertEqual(client, ["space/a.jpg", "elementary/backgrounds/b.jpg", "rose-pine/photography/c.png"])

    def test_removed_pictures_stay_out_of_the_checkout(self):
        pats = rice.sparse_patterns({"paths": "/*/ !/.github/"}, {"x/[1] y.jpg", "anime/a*b.png"}).splitlines()
        self.assertEqual(pats, ["/*/", "!/.github/", "!/anime/a\\*b.png", "!/x/\\[1] y.jpg"])

    def test_space_list(self):
        """Every space picture is pinned to a SHA-256, comes over https and carries its credit."""
        entries = rice.list_entries(rice.wallsources()["space"]["list"])
        self.assertGreater(len(entries), 20)
        self.assertEqual(len({f for _s, _u, f, _t, _c in entries}), len(entries), "file names are unique")
        for sha, url, name, title, credit in entries:
            self.assertRegex(sha, r"^[0-9a-f]{64}$")
            self.assertTrue(url.startswith("https://"), url)
            self.assertTrue(name.endswith(".jpg") and title and credit, name)
        sha, url, name, title, credit = entries[0]
        with mock.patch.object(rice, "WALLS", Path("/w")):
            self.assertEqual(rice.describe(Path("/w/space") / name), ("space", "", title, credit))


if __name__ == "__main__":
    unittest.main()
