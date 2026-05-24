"""APScheduler setup for daily and weekly digest jobs."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.utils.config import settings

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def setup_schedules(
    bot,
    user_ids: list[int],
    first_names: dict[int, str],
) -> None:
    """
    Register daily and weekly digest jobs for the given user IDs.

    For a personal bot the users list is just the admin(s) from config.yaml.
    The bot object is captured in the job closure so APScheduler can call it.
    """
    from bot.services.daily_digest import (  # noqa: PLC0415
        scheduled_daily_digest,
        scheduled_weekly_digest,
    )

    scheduler = get_scheduler()

    daily_h, daily_m = settings.digest.daily_time.split(":")
    weekly_h, weekly_m = settings.digest.weekly_time.split(":")
    weekly_day_abbr = settings.digest.weekly_day[:3].lower()  # "monday" → "mon"

    for user_id in user_ids:
        first_name = first_names.get(user_id, "User")

        if settings.features.daily_digest:
            scheduler.add_job(
                scheduled_daily_digest,
                CronTrigger(hour=int(daily_h), minute=int(daily_m)),
                args=[bot, user_id, first_name],
                id=f"daily_{user_id}",
                replace_existing=True,
                misfire_grace_time=3600,
            )
            logger.info(
                "Daily digest scheduled at %s for user %s",
                settings.digest.daily_time,
                user_id,
            )

        if settings.features.weekly_digest_push:
            scheduler.add_job(
                scheduled_weekly_digest,
                CronTrigger(
                    day_of_week=weekly_day_abbr,
                    hour=int(weekly_h),
                    minute=int(weekly_m),
                ),
                args=[bot, user_id, first_name],
                id=f"weekly_{user_id}",
                replace_existing=True,
                misfire_grace_time=3600,
            )
            logger.info(
                "Weekly digest scheduled (%s %s) for user %s",
                settings.digest.weekly_day,
                settings.digest.weekly_time,
                user_id,
            )


def start() -> None:
    get_scheduler().start()
    logger.info("APScheduler started.")


def stop() -> None:
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")
