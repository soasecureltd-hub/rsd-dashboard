"""Foreign key ai_predictions.assessment_id -> assessments.id

Revision ID: 003
Revises: 002
Create Date: 2026-11-25
"""
from typing import Sequence, Union
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = "fk_ai_predictions_assessment_id_assessments"


def upgrade() -> None:
    # Postgres refuses to add the constraint while orphans exist. Orphaned
    # predictions are unreachable through the API (every route goes through an
    # owned assessment), so unlink them rather than delete them.
    op.execute(
        "UPDATE ai_predictions SET assessment_id = NULL "
        "WHERE assessment_id IS NOT NULL "
        "AND assessment_id NOT IN (SELECT id FROM assessments)"
    )
    with op.batch_alter_table("ai_predictions") as batch_op:
        batch_op.create_foreign_key(
            FK_NAME, "assessments", ["assessment_id"], ["id"], ondelete="CASCADE"
        )


def downgrade() -> None:
    with op.batch_alter_table("ai_predictions") as batch_op:
        batch_op.drop_constraint(FK_NAME, type_="foreignkey")
