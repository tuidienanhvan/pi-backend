"""Celery background tasks."""

from app.core.logging_conf import get_logger
from app.worker import celery_app

logger = get_logger(__name__)


@celery_app.task(name="seo_bot.bulk_generate")
def seo_bot_bulk_generate(license_id: int, posts: list[dict]) -> dict:
    """Placeholder for bulk AI generation — runs in worker, not web process."""
    logger.info("seo_bot_bulk_generate_started", extra={"license_id": license_id, "n": len(posts)})
    # TODO: loop through posts, call SeoBotService.generate, persist results
    return {"processed": len(posts), "status": "completed"}


@celery_app.task(name="maintenance.cleanup_usage_logs")
def cleanup_usage_logs(days: int = 180) -> dict:
    """Periodic cleanup — delete UsageLog older than N days."""
    logger.info("cleanup_usage_logs", extra={"days": days})
    # TODO: run DELETE in batches
    return {"deleted": 0}
