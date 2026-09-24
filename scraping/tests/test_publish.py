"""Tests for publishing the UI payload to the cloud database."""

import json
import os
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

from services import publish
from services.publish import PublishBlocked, build_snapshot, check_snapshot, publish_current

DATA = {"products": [{"id": "1", "name": "Café"}], "offers": [], "coverage": {"offers": 0},
        "generated_at": "2026-09-21T15:00:00+00:00"}


def snapshot(**changes):
    with patch("services.publish.build_public", return_value={**DATA, **changes}):
        return build_snapshot(db=None)


def snapshot_data(offers=3, retailers=("A", "B")):
    return {
        "products": [{"id": str(i)} for i in range(offers)],
        "retailers": [{"name": n} for n in retailers],
        "offers": [{"id": f"o{i}", "product_id": str(i), "price_cents": 100 + i,
                    "retailer_name": retailers[i % len(retailers)]} for i in range(offers)],
        "coverage": {"networks": len(retailers)},
    }


class TestCheckSnapshot(unittest.TestCase):
    """Both publishing paths - refresh.py's full flow and this module's own publish_current() - share this
    check, so neither can put an empty, broken, or much-smaller-than-usual snapshot live."""

    def levels(self, data, live):
        return [(f.level, f.message) for f in check_snapshot(data, live)]

    def test_a_healthy_snapshot_has_no_findings(self):
        self.assertEqual(self.levels(snapshot_data(), 3), [])

    def test_an_empty_snapshot_is_an_error(self):
        self.assertEqual([f.level for f in check_snapshot(snapshot_data(0), 100)], ["error"])

    def test_offers_without_a_valid_price_or_product_are_an_error(self):
        for change in ({"price_cents": 0}, {"price_cents": None}, {"price_cents": 1.5}, {"product_id": "missing"}):
            data = snapshot_data()
            data["offers"][1].update(change)
            self.assertEqual([f.level for f in check_snapshot(data, 3)], ["error"], change)

    def test_a_chain_without_offers_is_only_a_warning(self):
        findings = check_snapshot(snapshot_data(2, retailers=("A", "B", "C")), 2)
        self.assertEqual([(f.level, "C" in f.message) for f in findings], [("warning", True)])

    def test_a_snapshot_under_half_the_live_one_is_refused(self):
        self.assertEqual([f.level for f in check_snapshot(snapshot_data(4), 9)], ["error"])
        self.assertEqual(check_snapshot(snapshot_data(5), 10), [])  # exactly half is fine

    def test_not_knowing_the_live_size_is_a_warning_not_a_block(self):
        self.assertEqual([f.level for f in check_snapshot(snapshot_data(), None)], ["warning"])


class FakeConnection:
    """A connection that records SQL and answers the "latest etag" query."""

    def __init__(self, latest_etag=None):
        self.statements, self.latest_etag = [], latest_etag

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        result = MagicMock()
        result.fetchone.return_value = (self.latest_etag,) if self.latest_etag and "SELECT etag" in sql else None
        return result


class TestBuildSnapshot(unittest.TestCase):
    def test_payload_is_compact_json_that_keeps_accents(self):
        payload = snapshot()["payload"]
        self.assertNotIn(": ", payload)
        self.assertIn("Café", payload)
        self.assertEqual(json.loads(payload)["products"][0]["name"], "Café")

    def test_etag_ignores_generated_at(self):
        first = snapshot(generated_at="2026-09-21T15:00:00+00:00")
        later = snapshot(generated_at="2026-09-22T03:00:00+00:00")
        self.assertEqual(first["etag"], later["etag"])
        self.assertNotEqual(first["payload"], later["payload"])

    def test_etag_ignores_the_times_stamped_on_flyers_at_every_build(self):
        def flyers(stamp):
            return [{"id": "1", "title": "Feirão", "collected_at": stamp, "source_checked_at": stamp}]

        self.assertEqual(snapshot(flyers=flyers("2026-09-21T15:00:00+00:00"))["etag"],
                         snapshot(flyers=flyers("2026-09-21T15:05:00+00:00"))["etag"])
        changed = flyers("2026-09-21T15:00:00+00:00")
        changed[0]["title"] = "Outro"
        self.assertNotEqual(snapshot(flyers=flyers("2026-09-21T15:00:00+00:00"))["etag"], snapshot(flyers=changed)["etag"])

    def test_etag_changes_with_the_data(self):
        self.assertNotEqual(snapshot()["etag"], snapshot(offers=[{"id": "9"}])["etag"])

    def test_etag_does_not_depend_on_key_order(self):
        with patch("services.publish.build_public", return_value={"b": 1, "a": 2, "generated_at": "x"}):
            one = build_snapshot(None)["etag"]
        with patch("services.publish.build_public", return_value={"a": 2, "b": 1, "generated_at": "x"}):
            two = build_snapshot(None)["etag"]
        self.assertEqual(one, two)


class TestPublish(unittest.TestCase):
    def test_writes_a_new_snapshot_and_prunes_old_ones(self):
        conn = FakeConnection(latest_etag="old")
        self.assertTrue(publish.publish("dsn", snapshot(), connect=lambda dsn: conn, keep=3))
        sql = [s for s, _ in conn.statements]
        self.assertIn("CREATE TABLE IF NOT EXISTS snapshots", sql[0])
        self.assertTrue(any(s.startswith("INSERT INTO snapshots") for s in sql))
        delete = next(p for s, p in conn.statements if s.startswith("DELETE FROM snapshots"))
        self.assertEqual(delete, (3,))

    def test_unchanged_data_is_not_written_again(self):
        snap = snapshot()
        conn = FakeConnection(latest_etag=snap["etag"])
        self.assertFalse(publish.publish("dsn", snap, connect=lambda dsn: conn))
        self.assertFalse(any(s.startswith("INSERT") or s.startswith("DELETE") for s, _ in conn.statements))

    def test_the_first_publish_into_an_empty_table_writes(self):
        conn = FakeConnection(latest_etag=None)
        self.assertTrue(publish.publish("dsn", snapshot(), connect=lambda dsn: conn))

    def test_the_connection_string_is_passed_through(self):
        seen = []
        publish.publish("postgresql://x", snapshot(), connect=lambda dsn: seen.append(dsn) or FakeConnection())
        self.assertEqual(seen, ["postgresql://x"])


VALID_DATA = {**DATA, "offers": [{"id": "o1", "product_id": "1", "price_cents": 100, "retailer_name": "A"}],
              "retailers": [{"name": "A"}]}


class TestPublishCurrent(unittest.TestCase):
    def test_does_nothing_without_a_configured_database(self):
        with patch.object(publish.config, "PUBLISH_DATABASE_URL", ""), \
                patch("services.publish.build_public") as mock_build:
            self.assertIsNone(publish_current())
        mock_build.assert_not_called()

    def test_publishes_when_configured(self):
        with patch.object(publish.config, "PUBLISH_DATABASE_URL", "postgresql://x"), \
                patch("services.publish.SessionLocal"), patch("services.publish.init_db") as mock_init, \
                patch("services.publish.build_public", return_value=VALID_DATA), \
                patch("services.publish.published_offer_count", return_value=1), \
                patch("services.publish.publish", return_value=True) as mock_publish:
            self.assertTrue(publish_current())
        self.assertEqual(mock_publish.call_args.args[0], "postgresql://x")
        mock_init.assert_called_once()  # the local schema is brought up to date before building

    def test_refuses_to_publish_something_worse_than_what_is_live(self):
        # DATA has no offers at all - exactly the case that caused a real outage once, before this guard
        # existed: this function used to publish unconditionally.
        with patch.object(publish.config, "PUBLISH_DATABASE_URL", "postgresql://x"), \
                patch("services.publish.SessionLocal"), patch("services.publish.init_db"), \
                patch("services.publish.build_public", return_value=DATA), \
                patch("services.publish.published_offer_count", return_value=100), \
                patch("services.publish.publish") as mock_publish:
            with self.assertRaises(PublishBlocked) as ctx:
                publish_current()
        mock_publish.assert_not_called()
        self.assertTrue(any(f.level == "error" for f in ctx.exception.findings))

    def test_force_publishes_past_a_blocking_error(self):
        with patch.object(publish.config, "PUBLISH_DATABASE_URL", "postgresql://x"), \
                patch("services.publish.SessionLocal"), patch("services.publish.init_db"), \
                patch("services.publish.build_public", return_value=DATA), \
                patch("services.publish.published_offer_count", return_value=100), \
                patch("services.publish.publish", return_value=True) as mock_publish:
            self.assertTrue(publish_current(force=True))
        mock_publish.assert_called_once()

    def test_cli_without_a_database_explains_what_to_set(self):
        with patch.object(publish.config, "PUBLISH_DATABASE_URL", ""):
            self.assertEqual(publish.main([]), 2)

    def test_cli_reports_a_blocked_publish_and_leaves_live_data_untouched(self):
        with patch.object(publish.config, "PUBLISH_DATABASE_URL", "postgresql://x"), \
                patch("services.publish.SessionLocal"), patch("services.publish.init_db"), \
                patch("services.publish.build_public", return_value=DATA), \
                patch("services.publish.published_offer_count", return_value=100), \
                patch("services.publish.publish") as mock_publish:
            self.assertEqual(publish.main([]), 1)
        mock_publish.assert_not_called()


def _scratch_dsn():
    """PUBLISH_TEST_DSN, only if it names a database with "test" in it: these tests DROP the snapshots table."""
    dsn = os.environ.get("PUBLISH_TEST_DSN", "")
    return dsn if "test" in urlparse(dsn).path.lower() else ""


@unittest.skipUnless(_scratch_dsn(), "set PUBLISH_TEST_DSN to a scratch Postgres database whose name contains 'test'")
class TestAgainstRealPostgres(unittest.TestCase):
    def setUp(self):
        import psycopg

        self.dsn = _scratch_dsn()
        with psycopg.connect(self.dsn) as conn:
            conn.execute("DROP TABLE IF EXISTS snapshots")

    def rows(self):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            return conn.execute("SELECT etag, payload, generated_at FROM snapshots ORDER BY id").fetchall()

    def test_round_trip_dedupe_and_prune(self):
        first = snapshot()
        self.assertTrue(publish.publish(self.dsn, first))
        self.assertFalse(publish.publish(self.dsn, snapshot(generated_at="2026-09-22T03:00:00+00:00")))
        stored = self.rows()
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0][1], first["payload"])  # byte for byte, accents included
        self.assertEqual(stored[0][2], datetime.fromisoformat("2026-09-21T15:00:00+00:00"))  # same instant, any zone
        for n in range(5):
            self.assertTrue(publish.publish(self.dsn, snapshot(offers=[{"id": str(n)}]), keep=3))
        self.assertEqual(len(self.rows()), 3)


if __name__ == "__main__":
    unittest.main()
