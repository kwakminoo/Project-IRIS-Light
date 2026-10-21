from __future__ import annotations

import unittest

from iris.browser._driver import youtube_like_fixture_driver
from iris.browser.registry import parse_command
from iris.browser.session import BrowserSession
from iris.browser.types import (
    BrowserPhase,
    ByText,
    Click,
    HistoryStep,
    Navigate,
    Open,
    Scroll,
    Search,
    parse_page_url,
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


class SessionFakeDriverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = youtube_like_fixture_driver()
        self.session = BrowserSession(driver=self.driver)

    def test_open_ready(self) -> None:
        r = self.session.execute(Open())
        self.assertTrue(r.ok)
        self.assertEqual(r.snapshot.phase, BrowserPhase.READY)

    def test_search_then_click(self) -> None:
        r = self.session.execute(Search(query="IU night letter"))
        self.assertTrue(r.ok)
        self.assertIn("search", r.snapshot.url)
        r = self.session.execute(Click(target=ByText(text="IU")))
        self.assertTrue(r.ok)
        self.assertIn("watch?v=fixture-iu", r.snapshot.url)
        self.assertIn("IU", r.snapshot.title)

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
            ),
        )
        self.assertEqual(len(command_specs()), len(names))


if __name__ == "__main__":
    unittest.main()
