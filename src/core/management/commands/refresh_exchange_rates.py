"""Fetch the latest exchange rates now (also run after each deploy)."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.interfaces.deps import container
from shared.exceptions import ExchangeRatesUnavailableError


class Command(BaseCommand):
    help = "Fetch the latest exchange rates from the configured provider."

    def handle(self, *args, **options):
        try:
            updated = container.refresh_exchange_rates().execute()
        except ExchangeRatesUnavailableError as exc:
            raise CommandError(f"Exchange rates unavailable: {exc.detail}") from exc
        self.stdout.write(f"updated {updated} rates")
