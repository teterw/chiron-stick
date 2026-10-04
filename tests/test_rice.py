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


class SeeThroughTerminal(unittest.TestCase):
    """The terminal is 85% opaque with a compositor: the wallpaper's bright parts show through, and
    its text must stay as readable as on the solid background."""

    def check(self, pal, bright):
        c = rice.derive(pal)
        t = rice.terminal_colours(c, bright)
        self.assertGreaterEqual(t["alpha"], 0.85)
        seen = rice.mix(bright, c["bg"], t["alpha"])  # what the eye sees behind the text
        self.assertGreaterEqual(rice.contrast(t["fg"], seen), 7.0, "text readable (7:1)")
        for i, col in enumerate(t["term"]):
            if i not in (0, 8):
                self.assertGreaterEqual(rice.contrast(col, seen), 4.5, f"terminal colour {i}")
        return c, t

    def test_bright_backdrop(self):
        for pal in (BRIGHT, DARK, GREY):
            c, t = self.check(pal, rice.WHITE)
            self.assertEqual(t["alpha"], 0.85, "lighter text is enough: the see-through look stays")

    def test_dark_backdrop_changes_nothing(self):
        c, t = self.check(DARK, rice.BLACK)
        self.assertEqual((t["fg"], t["term"], t["alpha"]), (c["fg"], c["term"], 0.85))

    def test_settings(self):
        c = rice.derive(DARK)
        with mock.patch.object(rice, "bright_backdrop", return_value=rice.WHITE):
            solid = dict((p, v) for p, v, _ in rice.terminal_settings(c, "wall.png", solid=True))
            clear = dict((p, v) for p, v, _ in rice.terminal_settings(c, "wall.png", solid=False))
        self.assertEqual(solid["/background-mode"], "TERMINAL_BACKGROUND_SOLID")
        self.assertEqual(solid["/color-foreground"], rice.rgb2hex(c["fg"]), "no compositor: colours as before")
        self.assertEqual(clear["/background-mode"], "TERMINAL_BACKGROUND_TRANSPARENT")
        self.assertEqual(clear["/background-darkness"], 0.85)

    def test_bright_backdrop_of_an_image(self):
        """A bright sky counts, a few stars don't."""
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(rice, "CACHE", Path(tmp)):
            for name, white_rows, expect in (("sky.png", 20, rice.WHITE), ("stars.png", 1, rice.BLACK)):
                im = Image.new("RGB", (100, 100), (0, 0, 0))
                im.paste((255, 255, 255), (0, 0, 100, white_rows))
                im.save(Path(tmp) / name)
                got = rice.bright_backdrop(Path(tmp) / name)
                self.assertLess(max(abs(a - b) for a, b in zip(got, expect)), 0.05, name)


class WindowTheme(unittest.TestCase):
    def test_bigger_shadows(self):
        """xfwm4 reads shadow sizes only from the window theme's themerc (not xfconf): Chiron-wm is
        Mint's Default theme with a GNOME-like shadow."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "Default" / "xfwm4"
            base.mkdir(parents=True)
            (base / "themerc").write_text("button_spacing=2\nshadow_opacity=30\nshadow_delta_y=-8\n")
            (base / "close-active.png").write_bytes(b"png")
            with mock.patch.multiple(rice, HOME=Path(tmp), XFWM_BASE=base):
                rice.wm_theme()
                rice.wm_theme()  # again: same result
            out = Path(tmp) / ".local/share/themes" / rice.WM_THEME / "xfwm4"
            rc = (out / "themerc").read_text().splitlines()
            self.assertIn("button_spacing=2", rc)
            self.assertIn("shadow_opacity=70", rc)
            self.assertEqual(sum(l.startswith("shadow_opacity=") for l in rc), 1)
            self.assertEqual((out / "close-active.png").resolve(), base / "close-active.png")


class Keys(unittest.TestCase):
    def test_no_key_bound_twice(self):
        keys = [k for k, _ in rice.COMMAND_KEYS] + [k for k, _ in rice.WM_KEYS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn(("<Super>m", "show_desktop_key"), rice.WM_KEYS)
        actions = [a for _, a in rice.WM_KEYS]
        self.assertEqual(len(actions), len(set(actions)), "xfwm4 keeps one key per action")
        self.assertNotIn("close_window_key", actions, "Alt+F4 must keep closing windows")

    def test_old_keys_of_our_actions_go(self):
        """xfwm4 keeps one key per action, and which one wins is arbitrary: Mint's <Super>KP_Left kept
        tile_left and <Super>Left did nothing. So other keys for the actions we set are removed."""
        listing = ("/xfwm4/custom/<Super>KP_Left      tile_left_key\n"
                   "/xfwm4/custom/<Super>Left         tile_left_key\n"
                   "/xfwm4/custom/<Alt>F4             close_window_key\n"
                   "/xfwm4/custom/<Alt>F9             hide_window_key\n"
                   "/xfwm4/default/<Alt>F9            hide_window_key\n"
                   "/xfwm4/custom/<Super>q            close_window_key\n"  # 0.8.0 test build: a command now
                   "/commands/custom/<Super>e         thunar\n")
        self.assertEqual(rice.wm_key_conflicts(listing),
                         ["/xfwm4/custom/<Super>KP_Left", "/xfwm4/custom/<Alt>F9", "/xfwm4/custom/<Super>q"])


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
