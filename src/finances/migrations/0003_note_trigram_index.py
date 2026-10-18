"""Trigram GIN index for ``note__icontains`` search (PostgreSQL only).

Kept out of ``Meta.indexes`` so the SQLite test fallback can still migrate.
"""

from django.db import migrations

CREATE = [
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE INDEX IF NOT EXISTS tx_note_trgm_idx ON finances_transaction "
    "USING gin (note gin_trgm_ops)",
]
DROP = ["DROP INDEX IF EXISTS tx_note_trgm_idx"]


def _run(statements):
    def apply(apps, schema_editor):
        if schema_editor.connection.vendor != "postgresql":
            return
        for sql in statements:
            schema_editor.execute(sql)

    return apply


class Migration(migrations.Migration):
    dependencies = [("finances", "0002_feed_index_recurring_uniqueness")]

    operations = [migrations.RunPython(_run(CREATE), _run(DROP))]
