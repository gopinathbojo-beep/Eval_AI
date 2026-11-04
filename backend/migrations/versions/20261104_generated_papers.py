"""AI-generated question papers and answer keys grounded in the reference library."""

from alembic import op
import sqlalchemy as sa

revision = "20261104_generated_papers"
down_revision = "20261103_reference_library"
branch_labels = depends_on = None


def upgrade():
    tables = set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())
    if "generated_papers" in tables:
        return
    op.create_table(
        "generated_papers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("teacher_id", sa.String(36), sa.ForeignKey("teachers.id"), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("exam_id", sa.String(36), nullable=True),
        sa.Column("standard", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(60), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stage", sa.String(200), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("paper", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for col in ("teacher_id", "workspace_id", "exam_id"):
        op.create_index(f"ix_generated_papers_{col}", "generated_papers", [col])


def downgrade():
    op.drop_table("generated_papers")
