"""Add versioned CBSE profiles and persistent document evidence, without changing old exams."""

from alembic import op
import sqlalchemy as sa

revision = "20261031_cbse"
down_revision = "20261101_accounts"
branch_labels = depends_on = None


def upgrade():
    tables = (
        "exams",
        "exam_questions",
        "question_paper_documents",
        "answer_key_documents",
    )
    if op.get_context().as_sql:
        columns = {table: set() for table in tables}
    else:
        inspector = sa.inspect(op.get_bind())
        columns = {
            table: {column["name"] for column in inspector.get_columns(table)}
            for table in tables
        }
    for name, typ in (
        ("standard_profile_id", sa.String(40)),
        ("standard_version", sa.String(30)),
        ("standard_options", sa.JSON()),
        ("standard_validation", sa.JSON()),
    ):
        if name not in columns["exams"]:
            op.add_column("exams", sa.Column(name, typ, nullable=True))
    if "structure" not in columns["exam_questions"]:
        op.add_column(
            "exam_questions", sa.Column("structure", sa.JSON(), nullable=True)
        )
    for table in ("question_paper_documents", "answer_key_documents"):
        if "extraction" not in columns[table]:
            op.add_column(table, sa.Column("extraction", sa.JSON(), nullable=True))


def downgrade():
    raise RuntimeError(
        "Restore a verified backup instead of deleting standard evidence."
    )
