"""Load the Celery app with Django so ``@shared_task`` uses its settings."""

from config.celery import app as celery_app

__all__ = ("celery_app",)
