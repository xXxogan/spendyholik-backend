"""Seed the celery-beat periodic task schedules (idempotent)."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask

# Crontab fields: minute hour day-of-month month day-of-week (UTC).
SCHEDULES = [
    ("spendyholik.run_due_recurring", "5 0 * * *"),
    ("spendyholik.refresh_exchange_rates", "0 3 * * *"),
    ("spendyholik.send_weekly_report", "0 9 * * 0"),
    ("spendyholik.notify_upcoming_recurring", "0 8 * * *"),
]


class Command(BaseCommand):
    help = "Create the periodic tasks used by celery-beat (idempotent)."

    def handle(self, *args, **options):
        for name, crontab in SCHEDULES:
            minute, hour, dom, month, dow = crontab.split()
            schedule, _ = CrontabSchedule.objects.get_or_create(
                minute=minute, hour=hour, day_of_month=dom, month_of_year=month, day_of_week=dow
            )
            # update_or_create so a changed schedule is applied on redeploy.
            _, created = PeriodicTask.objects.update_or_create(
                name=name,
                defaults={"task": name, "crontab": schedule},
            )
            self.stdout.write(f"{'created' if created else 'updated'}: {name}")
