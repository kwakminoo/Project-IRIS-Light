from __future__ import annotations

import unittest

from iris.browser._driver import youtube_like_fixture_driver
from iris.browser.registry import parse_command
from iris.browser.search import search_url
from iris.browser.session import BrowserSession
from iris.browser.types import (
    BrowserPhase,
    ByText,
    Click,
    HistoryStep,
    MiniHost,
    MiniPlayer,
    Navigate,
    Open,
    PanelHost,
    Scroll,
    Search,
    as_docked,
    as_mini,
    is_docked,
    is_mini,
    parse_page_url,
    parse_view_host,
)
from iris.system.control_surface import runs_off_ui_thread


class ParseBoundaryTests(unittest.TestCase):
    def test_reject_javascript_url(self) -> None:
        with self.assertRaises(ValueError):
            parse_page_url("javascript:alert(1)")

    def test_normalize_bare_host(self) -> None:
        self.assertEqual(parse_page_url("react.dev"), "https://react.dev")

    def test_parse_search_and_click(self) -> None:
        cmd = parse_command({"command": "search", "query": "IU night letter"})
        self.assertIsInstance(cmd, Search)
        click = parse_command({"command": "click", "by": "text", "value": "IU"})
        self.assertIsInstance(click, Click)
        assert isinstance(click, Click)
        self.assertIsInstance(click.target, ByText)

    def test_parse_google_and_youtube_play(self) -> None:
        g = parse_command({"command": "search", "query": "React 공식 문서", "engine": "google"})
        self.assertIsInstance(g, Search)
        assert isinstance(g, Search)
        self.assertEqual(g.engine, "google")
        self.assertFalse(g.play)
        y = parse_command(
            {"command": "search", "query": "음악", "engine": "youtube", "play": True}
        )
        self.assertIsInstance(y, Search)
        assert isinstance(y, Search)
        self.assertEqual(y.engine, "youtube")
        self.assertTrue(y.play)
        self.assertIn("google.com/search", search_url("React", engine="google"))
        self.assertIn("youtube.com/results", search_url("음악", engine="youtube"))


class ViewHostParseTests(unittest.TestCase):
    def test_parse_rejects_panel_string(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_view_host("panel", docked_default="dedicated")
        self.assertIn("panel", str(ctx.exception))

    def test_parse_mini_uses_docked_default(self) -> None:
        host = parse_view_host("mini", docked_default="ide_internal")
        self.assertEqual(host, MiniHost(resume="ide_internal"))

    def test_parse_site_strings_and_pass_through(self) -> None:
        self.assertEqual(
            parse_view_host("dedicated", docked_default="ide_internal"),
            PanelHost(site="dedicated"),
        )
        self.assertEqual(
            parse_view_host("ide_internal", docked_default="dedicated"),
            PanelHost(site="ide_internal"),
        )
        existing = MiniHost(resume="dedicated")
        self.assertIs(parse_view_host(existing, docked_default="ide_internal"), existing)

    def test_as_mini_as_docked_roundtrip(self) -> None:
        docked = PanelHost(site="ide_internal")
        mini = as_mini(docked)
        self.assertTrue(is_mini(mini))
        self.assertEqual(as_docked(mini), docked)


class SessionFakeDriverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = youtube_like_fixture_driver()
        self.session = BrowserSession(driver=self.driver)

    def test_open_ready(self) -> None:
        r = self.session.execute(Open())
        self.assertTrue(r.ok)
        self.assertEqual(r.snapshot.phase, BrowserPhase.READY)
        self.assertIn("google.com", r.snapshot.url)
        self.assertTrue(is_docked(self.session.view_host()))
        self.assertEqual(self.session.view_host(), PanelHost(site="dedicated"))

    def test_mini_player_toggle_and_idempotent(self) -> None:
        self.session.execute(Open())
        r = self.session.execute(MiniPlayer(on=True))
        self.assertTrue(r.ok)
        self.assertTrue(r.snapshot.mini_player)
        self.assertTrue(is_mini(self.session.view_host()))
        again = self.session.execute(MiniPlayer(on=True))
        self.assertEqual(again.detail, "idempotent")
        off = self.session.execute(MiniPlayer(on=False))
        self.assertTrue(off.ok)
        self.assertFalse(off.snapshot.mini_player)
        self.assertTrue(is_docked(self.session.view_host()))
        self.assertEqual(self.session.view_host(), PanelHost(site="dedicated"))

    def test_search_then_click(self) -> None:
        r = self.session.execute(Search(query="IU night letter"))
        self.assertTrue(r.ok)
        self.assertIn("search", r.snapshot.url)
        r = self.session.execute(Click(target=ByText(text="IU")))
        self.assertTrue(r.ok)
        self.assertIn("watch?v=fixture-iu", r.snapshot.url)
        self.assertIn("IU", r.snapshot.title)

    def test_youtube_play_clicks_first_result(self) -> None:
        r = self.session.execute(Search(query="IU night letter", engine="youtube", play=True))
        self.assertTrue(r.ok, r.detail)
        self.assertIn("watch?v=fixture-iu", r.snapshot.url)
        self.assertTrue(r.snapshot.media and r.snapshot.media.playing)
        last = self.session.last_result()
        self.assertIsNotNone(last)
        assert last is not None
        self.assertTrue(last.ok)
        self.assertEqual(last.command_kind, "search")
        self.assertIs(last, r)

    def test_youtube_play_fails_without_watch(self) -> None:
        from iris.browser._driver import FakePageDriver, _FakePage

        driver = FakePageDriver({"https://fixture.local/empty": _FakePage(url="https://fixture.local/empty", title="none")})
        driver._pages["__search__"] = driver._pages["https://fixture.local/empty"]
        session = BrowserSession(driver=driver)
        r = session.execute(Search(query="nothing", engine="youtube", play=True))
        self.assertFalse(r.ok)
        self.assertFalse(bool(r.snapshot.media and r.snapshot.media.playing))

    def test_media_pause_resume(self) -> None:
        from iris.browser.types import Media

        self.session.execute(Search(query="IU night letter", engine="youtube", play=True))
        paused = self.session.execute(Media(action="pause"))
        self.assertTrue(paused.ok, paused.detail)
        self.assertFalse(paused.snapshot.media.playing)
        resumed = self.session.execute(Media(action="resume"))
        self.assertTrue(resumed.ok, resumed.detail)
        self.assertTrue(resumed.snapshot.media.playing)

    def test_google_search_hits_fixture(self) -> None:
        r = self.session.execute(Search(query="React docs", engine="google"))
        self.assertTrue(r.ok)
        self.assertIn("search", r.snapshot.url)

    def test_navigate_react_fixture(self) -> None:
        r = self.session.execute(Navigate(url="https://react.dev"))
        self.assertTrue(r.ok)
        self.assertIn("react", r.snapshot.url.lower())
        self.assertEqual(r.snapshot.title, "React")
        self.assertEqual(r.snapshot.phase, BrowserPhase.READY)

    def test_scroll_increases_y(self) -> None:
        self.session.execute(Navigate(url="https://react.dev/learn"))
        before = self.session.snapshot().scroll_y
        r = self.session.execute(Scroll(delta_y=800))
        self.assertTrue(r.ok)
        self.assertGreater(r.snapshot.scroll_y, before)

    def test_idempotent_navigate(self) -> None:
        self.session.execute(Navigate(url="https://react.dev"))
        r = self.session.execute(Navigate(url="https://react.dev"))
        self.assertTrue(r.ok)
        self.assertEqual(r.detail, "idempotent")

    def test_history_edge_false(self) -> None:
        r = self.session.execute(HistoryStep(delta=-1))
        self.assertFalse(r.ok)

    def test_browser_actions_off_ui(self) -> None:
        for name in (
            "browser.open",
            "browser.navigate",
            "browser.search",
            "browser.click",
            "browser.type",
            "browser.scroll",
            "browser.back",
            "browser.forward",
            "browser.reload",
            "browser.snapshot",
            "browser.mini_player",
            "browser.media",
        ):
            self.assertTrue(runs_off_ui_thread(name), name)


class RegistrySyncTests(unittest.TestCase):
    def test_control_names_match_specs(self) -> None:
        from iris.browser.registry import command_specs, control_action_names

        names = control_action_names()
        self.assertEqual(
            names,
            (
                "browser.open",
                "browser.navigate",
                "browser.reload",
                "browser.back",
                "browser.forward",
                "browser.search",
                "browser.click",
                "browser.type",
                "browser.scroll",
                "browser.snapshot",
                "browser.mini_player",
                "browser.media",
            ),
        )
        self.assertEqual(len(command_specs()), len(names))


if __name__ == "__main__":
    unittest.main()
