"""Account/workspace rollout compatibility marker.

The frozen cloud baseline already contains the school and family account schema.
Production databases were stamped with this revision when that rollout completed,
so the marker must remain in the migration graph even though no DDL is required.
"""

revision = "20261101_accounts"
down_revision = "20261030_uploads"
branch_labels = depends_on = None


def upgrade():
    pass


def downgrade():
    raise RuntimeError(
        "Restore a verified backup instead of rolling back the account rollout."
    )
