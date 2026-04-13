"""Scheduler — triggers the deal-hunting pipeline on a recurring schedule."""

from apscheduler.schedulers.blocking import BlockingScheduler

from orchestrator.pipeline import run_pipeline


def start_scheduler() -> None:
    """Configure and start the APScheduler to run the pipeline on schedule."""
    scheduler = BlockingScheduler()

    # Every 6 hours
    scheduler.add_job(run_pipeline, "interval", hours=6, id="regular_run")

    # Every Tuesday at 09:00 local time
    scheduler.add_job(
        run_pipeline,
        "cron",
        day_of_week="tue",
        hour=9,
        minute=0,
        id="tuesday_aggressive",
        kwargs={"aggressive": True},
    )

    # Log scheduled jobs
    for job in scheduler.get_jobs():
        print(f"[Scheduler] Job '{job.id}' next run: {job.next_run_time}")

    # Run once immediately on startup
    print("[Scheduler] Running initial pipeline...")
    run_pipeline()

    try:
        print("[Scheduler] Starting scheduler...")
        scheduler.start()
    except KeyboardInterrupt:
        print("[Scheduler] Scheduler stopped.")


if __name__ == "__main__":
    start_scheduler()
