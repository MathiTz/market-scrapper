"""Seeding must be repeatable, and the scheduler must refresh the offers the UI shows."""

import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scheduler
import seed
from models.database import Base
from models.store import Store


class TestSeed(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=engine)
        self.session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        patcher = patch.multiple(seed, SessionLocal=self.session, init_db=lambda: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def names(self):
        db = self.session()
        try:
            return sorted(name for (name,) in db.query(Store.name))
        finally:
            db.close()

    def test_running_the_seed_twice_does_not_duplicate_stores(self):
        seed.seed()
        first = self.names()
        seed.seed()
        self.assertEqual(self.names(), first)
        self.assertEqual(len(first), len(set(first)))
        self.assertGreater(len(first), 1)

    def test_a_missing_store_is_added_and_existing_ones_are_kept(self):
        seed.seed()
        db = self.session()
        db.query(Store).filter(Store.name == "Cometa").delete()
        db.commit()
        db.close()
        seed.seed()
        self.assertEqual(self.names().count("Cometa"), 1)


class TestScheduler(unittest.TestCase):
    """scrape_all() goes through refresh.run()'s validated path (see scheduler.py's docstring for why:
    it used to publish unconditionally, and once published an empty snapshot live after a silent failure)."""

    @patch("scheduler.refresh.run", return_value=0)
    def test_scrape_all_delegates_to_refreshs_validated_path(self, mock_run):
        scheduler.scrape_all()
        mock_run.assert_called_once()
        self.assertTrue(callable(mock_run.call_args.kwargs["out"]))

    @patch("scheduler.logger")
    @patch("scheduler.refresh.run", return_value=1)
    def test_a_blocked_or_failed_refresh_is_logged_not_raised(self, _, mock_logger):
        scheduler.scrape_all()  # must not raise
        mock_logger.error.assert_called_once()

    @patch("scheduler.logger")
    @patch("scheduler.refresh.run", return_value=0)
    def test_a_clean_refresh_logs_no_error(self, mock_run, mock_logger):
        scheduler.scrape_all()
        mock_logger.error.assert_not_called()

    @patch("scheduler.BlockingScheduler")
    def test_runs_at_fixed_clock_times_not_an_interval_from_process_start(self, mock_cls):
        # This process gets started ad-hoc (whatever machine happens to have it open), not kept alive on a
        # server - an "every N hours from now" interval would drift with every restart. A cron trigger at
        # fixed hours fires at the same wall-clock times regardless of when the process last started.
        mock_sched = mock_cls.return_value
        scheduler.main()
        mock_sched.add_job.assert_called_once()
        _, trigger = mock_sched.add_job.call_args.args[:2]
        fields = {f.name: str(f) for f in trigger.fields}
        self.assertEqual(fields["hour"], "6,12")
        self.assertEqual(fields["minute"], "0")
        mock_sched.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
