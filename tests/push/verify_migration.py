"""Verify the push migration DDL matches the ORM models.

Runs the migration against an empty SQLite database, then compares the
reflected schema with the model metadata using alembic autogenerate.
"""
# ruff: noqa: T201 (standalone verification script; output is the point)
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "push"))

from alembic.autogenerate import produce_migrations
from alembic.migration import MigrationContext
from alembic.operations import Operations
import conftest  # installs the fake nonebot_plugin_orm and loads the models
from push_test.core.db.models import credit, push, record  # noqa: F401
from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine.reflection import Inspector

metadata = push.PushEvent.metadata

engine = create_engine("sqlite://")
with engine.connect() as conn:
    # Simulate the pre-migration database: legacy tables with the exact
    # schema from the previous migration (59a1e7813b63), no push tables.
    legacy = MetaData()
    for table in metadata.sorted_tables:
        if table.name.startswith("push_"):
            continue
        table.to_metadata(legacy)
    legacy.tables["credit_transaction"]._columns.remove(
        legacy.tables["credit_transaction"].columns["push_delivery_id"]
    )
    for constraint in list(legacy.tables["credit_transaction"].constraints):
        if constraint.columns and {c.name for c in constraint.columns} == {"push_delivery_id"}:
            legacy.tables["credit_transaction"].constraints.remove(constraint)
    legacy.create_all(conn)

    ctx = MigrationContext.configure(conn, opts={"as_sql": False, "render_as_batch": True})
    op = Operations(ctx)
    migration = conftest.load_module(
        "push_migration", "migrations/versions/b3f7a2c91d84_push_service.py"
    )
    # The migration guards on `name`; call the underlying body directly.
    import alembic

    alembic.op._proxy = op  # bind op.* used inside the migration
    with Operations.context(ctx):
        migration.upgrade()

    insp = Inspector(conn)
    print("tables after migration:", sorted(insp.get_table_names()))

    compare_ctx = MigrationContext.configure(
        conn, opts={"as_sql": False, "render_as_batch": True, "target_metadata": metadata}
    )
    diffs = produce_migrations(compare_ctx, metadata).upgrade_ops.as_diffs()
    if diffs:
        print("DIFFS FOUND:")
        for diff in diffs:
            print(" ", diff)
        sys.exit(1)
    print("OK: migration schema matches model metadata")

    with Operations.context(ctx):
        migration.downgrade()
    remaining = sorted(name for name in Inspector(conn).get_table_names() if name.startswith("push_"))
    columns = [c["name"] for c in Inspector(conn).get_columns("credit_transaction")]
    assert remaining == [], f"push tables still present: {remaining}"
    assert "push_delivery_id" not in columns, "push_delivery_id not dropped"
    print("OK: downgrade removes push tables and column")
