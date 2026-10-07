"""Persist workspace branding; tolerate the initial metadata-based migration."""

import sqlalchemy as sa
from alembic import op

revision = "20261006_0002"
down_revision = "20260927_0001"
branch_labels = None
depends_on = None


def upgrade():
    if "presentation" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("workspaces")}:
        op.add_column("workspaces", sa.Column("presentation", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    with op.batch_alter_table("workspaces") as batch:
        batch.drop_column("presentation")
