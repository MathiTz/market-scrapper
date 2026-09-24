"""Tests for refresh.py: the one-command scrape, store, validate and publish."""

import json
import unittest
from unittest.mock import MagicMock, patch

import refresh
from models import ScrapeAttempt, SessionLocal, init_db
from refresh import ChainResult, evaluate_scrape

KEY, NAME = "refresh_test", "Refresh Test"


def snapshot_data(offers=3, retailers=("A", "B")):
    return {
        "products": [{"id": str(i)} for i in range(offers)],
        "retailers": [{"name": n} for n in retailers],
        "offers": [{"id": f"o{i}", "product_id": str(i), "price_cents": 100 + i,
                    "retailer_name": retailers[i % len(retailers)]} for i in range(offers)],
        "coverage": {"networks": len(retailers)},
    }


class TestEvaluateScrape(unittest.TestCase):
    def setUp(self):
        init_db()
        self.db = SessionLocal()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.db.query(ScrapeAttempt).filter(ScrapeAttempt.site_key == KEY).delete()
        self.db.commit()
        self.db.close()

    def attempt(self, run_id, items, success=True, error=None):
        row = ScrapeAttempt(site_key=KEY, success=success, items_found=items, error=error, run_id=run_id, duration_ms=2500)
        self.db.add(row)
        self.db.commit()
        return row.id

    def test_a_complete_run_is_ok(self):
        since = self.attempt("old", 100)
        self.attempt("new", 100)
        result = evaluate_scrape(self.db, KEY, NAME, since)
        self.assertEqual((result.status, result.items, result.seconds), ("ok", 100, 2.5))

    def test_no_attempt_after_the_run_started(self):
        since = self.attempt("old", 100)
        self.assertEqual(evaluate_scrape(self.db, KEY, NAME, since).status, "no result")

    def test_a_failure_carries_its_error(self):
        since = self.attempt("old", 100)
        self.attempt("new", 0, success=False, error="blocked by the site")
        result = evaluate_scrape(self.db, KEY, NAME, since)
        self.assertEqual((result.status, result.detail), ("failed", "blocked by the site"))

    def test_a_run_that_found_nothing(self):
        since = self.attempt("old", 100)
        self.attempt("new", 0)
        self.assertEqual(evaluate_scrape(self.db, KEY, NAME, since).status, "empty")

    def test_a_run_far_below_usual_is_set_aside(self):
        since = self.attempt("old", 100)
        self.attempt("new", 10)  # under a quarter of the usual 100
        result = evaluate_scrape(self.db, KEY, NAME, since)
        self.assertEqual((result.status, result.items), ("set aside", 10))

    def test_a_first_run_has_no_baseline_to_fall_short_of(self):
        self.assertEqual(evaluate_scrape(self.db, KEY, NAME, 0).status, "no result")
        since = self.attempt("first", 40)
        self.assertEqual(evaluate_scrape(self.db, KEY, NAME, since - 1).status, "ok")


def ok(key="pinheiro", name="Pinheiro", items=50):
    return ChainResult(key, name, "ok", items, 3.0)


class TestRun(unittest.TestCase):
    def setUp(self):
        self.lines = []
        self.publish = MagicMock(return_value=True)
        self.scrape = MagicMock(side_effect=lambda key: ok(key, key))
        self.live = MagicMock(return_value=3)
        self.sync_locations = MagicMock(return_value={})
        self.data = snapshot_data()
        self.snapshot = {"payload": json.dumps(self.data), "etag": "e", "generated_at": "now"}
        for target, replacement in [
            ("scrape_chain", self.scrape), ("publish", self.publish), ("published_offer_count", self.live),
            ("build_snapshot", MagicMock(return_value=self.snapshot)), ("sync_store_locations", self.sync_locations),
        ]:
            patcher = patch.object(refresh, target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(refresh.config, "PUBLISH_DATABASE_URL", "postgresql://live")
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_refresh(self, **options):
        return refresh.run(out=self.lines.append, **options)

    def text(self):
        return "\n".join(self.lines)

    def test_scrapes_every_chain_validates_and_publishes(self):
        self.assertEqual(self.run_refresh(), 0)
        self.assertEqual([c.args[0] for c in self.scrape.call_args_list], list(refresh.SCRAPER_MAP))
        self.publish.assert_called_once_with("postgresql://live", self.snapshot)
        self.assertIn("Published.", self.text())

    def test_reports_when_the_live_snapshot_is_already_identical(self):
        self.publish.return_value = False
        self.assertEqual(self.run_refresh(), 0)
        self.assertIn("Nothing new", self.text())

    def test_only_scrapes_the_chains_asked_for(self):
        self.run_refresh(only=["pinheiro", "cometa"])
        self.assertEqual([c.args[0] for c in self.scrape.call_args_list], ["pinheiro", "cometa"])

    def test_sync_locations_is_off_by_default(self):
        self.run_refresh()
        self.sync_locations.assert_not_called()

    def test_sync_locations_flag_refreshes_branches_for_every_chain(self):
        self.sync_locations.return_value = {"mercadinho": 19, "atacadao": 11}
        self.assertEqual(self.run_refresh(sync_locations=True), 0)
        self.sync_locations.assert_called_once_with(site_key=None)
        self.assertIn("mercadinho: 19", self.text())

    def test_sync_locations_with_only_one_chain_scopes_to_it(self):
        self.run_refresh(only=["mercadinho"], sync_locations=True)
        self.sync_locations.assert_called_once_with(site_key="mercadinho")

    def test_sync_locations_with_several_only_chains_still_runs_all_of_them(self):
        # --only picks which chains get PRICES scraped; sync_store_locations has its own per-chain
        # participation (only scrapers with fetch_locations do anything), so it is not narrowed the same way.
        self.run_refresh(only=["mercadinho", "cometa"], sync_locations=True)
        self.sync_locations.assert_called_once_with(site_key=None)

    def test_a_chain_that_fails_is_a_warning_and_the_rest_still_publish(self):
        self.scrape.side_effect = lambda key: ChainResult(key, key, "failed", detail="boom") if key == "cometa" else ok(key, key)
        self.assertEqual(self.run_refresh(), 0)
        self.assertIn("WARNING cometa: failed", self.text())
        self.publish.assert_called_once()

    def test_when_no_chain_produced_fresh_data_nothing_is_published(self):
        self.scrape.side_effect = lambda key: ChainResult(key, key, "failed", detail="down")
        self.assertEqual(self.run_refresh(), 1)
        self.publish.assert_not_called()
        self.assertIn("no chain produced fresh data", self.text())

    def test_a_snapshot_far_smaller_than_the_live_one_is_blocked(self):
        self.live.return_value = 1000
        self.assertEqual(self.run_refresh(), 1)
        self.publish.assert_not_called()
        self.assertIn("Blocked", self.text())

    def test_force_publishes_past_a_blocking_error(self):
        self.live.return_value = 1000
        self.assertEqual(self.run_refresh(force=True), 0)
        self.publish.assert_called_once()
        self.assertIn("forced", self.text())

    def test_no_publish_stops_after_validating(self):
        self.assertEqual(self.run_refresh(publish_data=False), 0)
        self.publish.assert_not_called()
        self.assertIn("Publish skipped", self.text())

    def test_no_publish_needs_no_publish_database(self):
        with patch.object(refresh.config, "PUBLISH_DATABASE_URL", ""):
            self.assertEqual(self.run_refresh(publish_data=False), 0)
        self.live.assert_not_called()

    def test_skip_scrape_publishes_what_is_stored(self):
        self.assertEqual(self.run_refresh(skip_scrape=True), 0)
        self.scrape.assert_not_called()
        self.publish.assert_called_once()

    def test_without_a_publish_database_it_stops_before_scraping(self):
        with patch.object(refresh.config, "PUBLISH_DATABASE_URL", ""):
            self.assertEqual(self.run_refresh(), 2)
        self.scrape.assert_not_called()
        self.assertIn("--no-publish", self.text())

    def test_an_unknown_chain_stops_before_scraping(self):
        self.assertEqual(self.run_refresh(only=["nope"]), 2)
        self.scrape.assert_not_called()
        self.assertIn("Unknown chain: nope", self.text())

    def test_a_publish_failure_is_reported_with_status_1(self):
        self.publish.side_effect = RuntimeError("connection refused")
        self.assertEqual(self.run_refresh(), 1)
        self.assertIn("Publishing failed: connection refused", self.text())


class TestScrapeChain(unittest.TestCase):
    def test_an_exception_around_the_scrape_becomes_a_failed_result(self):
        scrape = MagicMock(side_effect=RuntimeError("browser crashed"))
        result = refresh.scrape_chain("pinheiro", scrape=scrape)
        self.assertEqual((result.status, result.detail), ("failed", "browser crashed"))
        scrape.assert_called_once_with(site="pinheiro")


if __name__ == "__main__":
    unittest.main()
