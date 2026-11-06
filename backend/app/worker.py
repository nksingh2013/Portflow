from celery import Celery

from app.config import settings

celery_app = Celery("portflow", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)


@celery_app.task(name="portflow.integrations.notification_delivery")
def dispatch_notification(delivery_id: str) -> dict:
    """Queue boundary for provider-backed delivery; never reports a stub as sent."""
    return {"delivery_id": delivery_id, "status": "not_configured", "sent": False}
