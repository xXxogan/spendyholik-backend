"""Django transaction-backed unit of work."""

from __future__ import annotations

from types import TracebackType

from django.db import transaction

from shared.application.ports import UnitOfWork


class DjangoUnitOfWork(UnitOfWork):
    """Wraps ``transaction.atomic`` — commits on clean exit, rolls back on error."""

    def __init__(self) -> None:
        self._atomic: transaction.Atomic | None = None

    def __enter__(self) -> "DjangoUnitOfWork":
        self._atomic = transaction.atomic()
        self._atomic.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        assert self._atomic is not None
        return self._atomic.__exit__(exc_type, exc, tb)

    def commit(self) -> None:
        # The atomic block commits when the context exits cleanly.
        return

    def rollback(self) -> None:
        transaction.set_rollback(True)
