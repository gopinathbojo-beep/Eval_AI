"""Shared reference library (NCERT textbooks, CBSE marking schemes) for grounded answer keys and grading."""

from alembic import op
import sqlalchemy as sa

revision = "20261103_reference_library"
down_revision = "20261102_uploader_codes"
branch_labels = depends_on = None


def upgrade():
    tables = set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())
    if "reference_sources" not in tables:
        op.create_table(
            "reference_sources",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("kind", sa.String(30), nullable=False),
            sa.Column("standard", sa.Integer(), nullable=False),
            sa.Column("subject", sa.String(60), nullable=False),
            sa.Column("book", sa.String(200), nullable=True),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("path", sa.String(500), nullable=False, unique=True),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("pages", sa.Integer(), nullable=False),
            sa.Column("issues", sa.JSON(), nullable=False),
            sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_reference_sources_standard", "reference_sources", ["standard"])
        op.create_index("ix_reference_sources_subject", "reference_sources", ["subject"])
    if "reference_chunks" not in tables:
        op.create_table(
            "reference_chunks",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("source_id", sa.String(36), sa.ForeignKey("reference_sources.id", ondelete="CASCADE"), nullable=False),
            sa.Column("standard", sa.Integer(), nullable=False),
            sa.Column("subject", sa.String(60), nullable=False),
            sa.Column("kind", sa.String(30), nullable=False),
            sa.Column("chapter", sa.String(300), nullable=True),
            sa.Column("page_start", sa.Integer(), nullable=False),
            sa.Column("page_end", sa.Integer(), nullable=False),
            sa.Column("question_number", sa.String(50), nullable=True),
            sa.Column("marks", sa.Float(), nullable=True),
            sa.Column("criteria", sa.JSON(), nullable=True),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("embedding", sa.LargeBinary(), nullable=True),
            sa.Column("embedding_model", sa.String(100), nullable=True),
        )
        op.create_index("ix_reference_chunks_source_id", "reference_chunks", ["source_id"])
        op.create_index("ix_reference_chunks_scope", "reference_chunks", ["standard", "subject", "kind"])
        if op.get_context().dialect.name == "postgresql":
            op.execute("CREATE INDEX ix_reference_chunks_fts ON reference_chunks USING gin (to_tsvector('simple', text))")


def downgrade():
    op.drop_table("reference_chunks")
    op.drop_table("reference_sources")
