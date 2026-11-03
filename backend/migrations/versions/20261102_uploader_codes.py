"""Per-exam uploader login codes, and which code uploaded each answer sheet."""

from alembic import op
import sqlalchemy as sa

revision = "20261102_uploader_codes"
down_revision = "20261031_cbse"
branch_labels = depends_on = None


def upgrade():
    if op.get_context().as_sql:
        sheet_cols, tables = set(), set()
    else:
        inspector = sa.inspect(op.get_bind())
        sheet_cols = {c["name"] for c in inspector.get_columns("answer_sheet_documents")}
        tables = set(inspector.get_table_names())
    if "uploaded_by_code" not in sheet_cols:
        op.add_column("answer_sheet_documents", sa.Column("uploaded_by_code", sa.String(36), nullable=True))
    if "uploader_codes" not in tables:
        op.create_table(
            "uploader_codes",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("exam_id", sa.String(36), sa.ForeignKey("exams.id", ondelete="CASCADE"), nullable=False),
            sa.Column("workspace_id", sa.String(36), nullable=False),
            sa.Column("code", sa.String(6), nullable=False),
            sa.Column("label", sa.String(100), nullable=True),
            sa.Column("uploader_name", sa.String(100), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_uploader_codes_exam_id", "uploader_codes", ["exam_id"])
        op.create_index("ix_uploader_codes_workspace_id", "uploader_codes", ["workspace_id"])
        op.create_index("ix_uploader_codes_code", "uploader_codes", ["code"], unique=True)


def downgrade():
    op.drop_table("uploader_codes")
