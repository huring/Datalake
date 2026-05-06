"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("timestamp", sa.String(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.String(),
            nullable=False,
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"),
        ),
    )
    op.create_index("idx_events_source", "events", ["source"])
    op.create_index("idx_events_event_type", "events", ["event_type"])
    op.create_index("idx_events_timestamp", "events", ["timestamp"])
    op.create_index(
        "idx_events_source_ts",
        "events",
        ["source", sa.text("timestamp DESC")],
    )
    op.create_index("idx_events_id", "events", ["id"], unique=True)

    op.create_table(
        "sources",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.String(), nullable=False),
        sa.Column("last_seen_at", sa.String(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_table("sources")
    op.drop_index("idx_events_id", table_name="events")
    op.drop_index("idx_events_source_ts", table_name="events")
    op.drop_index("idx_events_timestamp", table_name="events")
    op.drop_index("idx_events_event_type", table_name="events")
    op.drop_index("idx_events_source", table_name="events")
    op.drop_table("events")
