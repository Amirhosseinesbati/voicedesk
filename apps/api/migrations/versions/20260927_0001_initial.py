"""Initial VoiceDesk schema.

Revision ID: 20260927_0001
Revises:
"""

from alembic import op

import voicedesk.models  # noqa: F401
from voicedesk.db import Base

revision = "20260927_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(bind=op.get_bind())


def downgrade():
    Base.metadata.drop_all(bind=op.get_bind())
