"""Scheduler — triggers the deal-hunting pipeline on a recurring schedule."""

from apscheduler.schedulers.blocking import BlockingScheduler


def start_scheduler() -> None:
    """Configure and start the APScheduler to run the pipeline weekly.

    By default runs every Wednesday evening to find deals for the upcoming weekend.
    """
    pass


if __name__ == "__main__":
    start_scheduler()
