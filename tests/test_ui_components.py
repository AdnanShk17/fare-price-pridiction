import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ui_components as ui  # noqa: E402
from branding import APP_NAME  # noqa: E402


class UiComponentTests(unittest.TestCase):
    def test_external_text_is_escaped(self):
        evil = '<script>alert(1)</script>"><img src=x onerror=alert(1)>'
        for html in (ui.location_chip("#000", evil, evil), ui.poi_row(evil, evil, evil), ui.tile("x", evil, evil, evil),
                     ui.ride_card("x", evil, evil, 100, evil), ui.step_banner(evil, evil)):
            self.assertNotIn("<script>", html)
            self.assertNotIn("<img", html)
            self.assertIn("&lt;", html)

    def test_no_blank_lines_that_would_break_markdown_html_blocks(self):
        samples = [ui.navbar(["📍 Mumbai"]), ui.rides_grid([ui.ride_card("x", "a", "b", 10)]), ui.how_it_works(),
                   ui.tiles_row([ui.tile("x", "a", "b")]), ui.footer(), ui.css()]
        for html in samples:
            self.assertNotIn("\n\n", html)

    def test_money_format(self):
        self.assertEqual(ui.inr(1234.4), "₹1,234")
        self.assertEqual(ui.inr(99.6), "₹100")

    def test_unavailable_card(self):
        html = ui.ride_card("🚕", "Taxi", "SUV", None, "Not offered for SUV")
        self.assertIn("Not available", html)
        self.assertIn("na", html.split('"')[1])

    def test_best_and_estimate_classes(self):
        self.assertIn("best", ui.ride_card("x", "a", "b", 5, best=True).split('"')[1])
        self.assertIn("est", ui.ride_card("x", "a", "b", 5, estimate=True).split('"')[1])

    def test_savings_banner_only_mentions_saving_when_meaningful(self):
        self.assertIn("save up to", ui.savings_banner("Ola", 100, 50))
        self.assertNotIn("save up to", ui.savings_banner("Ola", 100, 0))

    def test_navbar_has_brand(self):
        html = ui.navbar(["a", "", "b"])
        self.assertIn(APP_NAME[:4], html)
        self.assertEqual(html.count('class="fc-chip"'), 2)  # empty chips are skipped

    def test_outlook_handles_missing_temperature(self):
        html = ui.outlook_strip([{"label": "4 PM", "temperature_c": None, "precipitation_mm": 0, "icon": "☀️"}])
        self.assertIn("–", html)
        self.assertEqual(ui.outlook_strip([]), "")

    def test_no_internal_wording_in_user_facing_components(self):
        text = " ".join([ui.how_it_works(), ui.footer()]).lower()
        for banned in ("machine learning", "viva", "random forest", "r²", "model"):
            self.assertNotIn(banned, text)


if __name__ == "__main__":
    unittest.main()
