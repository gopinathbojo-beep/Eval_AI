"""Direct-upload leases without exposing a privileged key to the browser."""
from alembic import op
import sqlalchemy as sa

revision = "20261030_uploads"
down_revision = "20261030_cloud"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("background_jobs", sa.Column("worker_id", sa.String(36)))
    op.add_column("background_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
    op.create_table("pending_uploads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("exam_id", sa.String(36), sa.ForeignKey("exams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    for field in ("exam_id", "actor_id", "workspace_id"):
        op.create_index("ix_pending_uploads_" + field, "pending_uploads", [field])
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "pending_uploads" ENABLE ROW LEVEL SECURITY')


def downgrade():
    raise RuntimeError("Restore a verified backup to roll back upload records.")
