"""Periodic scraping scheduler using APScheduler.

Run with:  python scheduler.py
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

import refresh

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Fixed clock times, not an interval from whenever this process happens to start: this runs ad-hoc, on
# whatever machine happens to have it open, not a always-on server, so "every N hours starting now" drifts
# with every restart and can silently stop firing at a useful time of day. A cron trigger fires at the
# same wall-clock times regardless of when (or how many times) the process was last started; if the
# machine was off at 06:00, the 12:00 run still happens on schedule rather than 12h after whenever it
# came back.
SCRAPE_HOURS = "6,12"


def scrape_all() -> None:
    """Scrape every chain and publish, through refresh.run()'s validated path.

    Publishing used to happen unconditionally here (scrape, then publish whatever the database held
    regardless of how the scrape went), which once published an empty snapshot live after a scrape failed
    silently. refresh.run() is the same one-command path ``python refresh.py`` uses by hand: it refuses to
    publish a snapshot that is empty, has broken offers, or is far smaller than what is already live.
    """
    status = refresh.run(out=lambda line: logger.info(line))
    if status != 0:
        logger.error("Scheduled refresh did not complete cleanly (exit status %d); see the lines above.", status)


def main() -> None:
    scheduler = BlockingScheduler(timezone="America/Sao_Paulo")
    trigger = CronTrigger(hour=SCRAPE_HOURS, minute=0)
    scheduler.add_job(scrape_all, trigger, id="scrape_all", replace_existing=True)
    logger.info("Scheduler started (daily at %s:00). Press Ctrl+C to stop.", SCRAPE_HOURS.replace(",", ":00 and "))
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
