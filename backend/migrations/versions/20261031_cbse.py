"""Add versioned CBSE profiles and persistent document evidence, without changing old exams."""

from alembic import op
import sqlalchemy as sa

revision = "20261031_cbse"
down_revision = "20261030_uploads"
branch_labels = depends_on = None


def upgrade():
    for name, typ in (
        ("standard_profile_id", sa.String(40)),
        ("standard_version", sa.String(30)),
        ("standard_options", sa.JSON()),
        ("standard_validation", sa.JSON()),
    ):
        op.add_column("exams", sa.Column(name, typ, nullable=True))
    op.add_column("exam_questions", sa.Column("structure", sa.JSON(), nullable=True))
    for table in ("question_paper_documents", "answer_key_documents"):
        op.add_column(table, sa.Column("extraction", sa.JSON(), nullable=True))


def downgrade():
    raise RuntimeError(
        "Restore a verified backup instead of deleting standard evidence."
    )
