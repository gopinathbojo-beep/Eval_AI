"""What an exam's printed reports say about it, and the Part B option each student answered."""

from alembic import op
import sqlalchemy as sa

revision = "20261106_exam_report_details"
down_revision = "20261104_generated_papers"
branch_labels = depends_on = None


def upgrade():
    def missing(table, column):
        if op.get_context().as_sql:
            return True
        return column not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}

    if missing("exams", "report_details"):
        op.add_column("exams", sa.Column("report_details", sa.JSON(), nullable=True))
    if missing("evaluations", "part_b_option"):
        op.add_column("evaluations", sa.Column("part_b_option", sa.String(20), nullable=True))


def downgrade():
    op.drop_column("evaluations", "part_b_option")
    op.drop_column("exams", "report_details")
