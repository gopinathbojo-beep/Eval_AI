"""The account merge: our signup, invite, consent, credits, support and parent tables, our account columns on
teachers (phone, console role, lockout, email check) and school details on workspaces. Additive only: old K-level
columns stay where they are, unused."""
from alembic import op
import sqlalchemy as sa


revision = '20261101_accounts'
down_revision = '20261031_cbse'
branch_labels = None
depends_on = None


# Some databases already have parts of this (tables made by the old create_all, columns added by hand): each table,
# index and column is created only when it is missing, so the upgrade runs on those and on a fresh database alike.
def _inspector():
    return sa.inspect(op.get_bind())


def _create_table(name, *columns, **kw):
    if not _inspector().has_table(name):
        op.create_table(name, *columns, **kw)


def _create_index(name, table, columns, **kw):
    if name not in {i["name"] for i in _inspector().get_indexes(table)}:
        op.create_index(name, table, columns, **kw)


def _add_column(table, column):
    if column.name not in {c["name"] for c in _inspector().get_columns(table)}:
        op.add_column(table, column)


def upgrade():
    _create_table('credit_packs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('credits', sa.Integer(), nullable=False),
    sa.Column('price_inr', sa.Float(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    _create_table('credit_settings',
    sa.Column('key', sa.String(length=50), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    _create_table('signup_requests',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=False),
    sa.Column('phone_key', sa.String(length=10), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_user_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _create_index(op.f('ix_signup_requests_email'), 'signup_requests', ['email'], unique=False)
    _create_index(op.f('ix_signup_requests_phone_key'), 'signup_requests', ['phone_key'], unique=False)
    _create_table('wallets',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('owner_type', sa.String(length=10), nullable=False),
    sa.Column('owner_id', sa.String(length=36), nullable=False),
    sa.Column('balance', sa.Integer(), nullable=False),
    sa.Column('held', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('owner_type', 'owner_id', name='uq_wallet_owner')
    )
    _create_index(op.f('ix_wallets_owner_id'), 'wallets', ['owner_id'], unique=False)
    _create_table('credit_ledger',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('wallet_id', sa.String(length=36), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('balance_after', sa.Integer(), nullable=False),
    sa.Column('ref_type', sa.String(length=20), nullable=False),
    sa.Column('ref_id', sa.String(length=64), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('actor_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['wallet_id'], ['wallets.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('type', 'ref_id', name='uq_ledger_type_ref')
    )
    _create_index(op.f('ix_credit_ledger_wallet_id'), 'credit_ledger', ['wallet_id'], unique=False)
    _create_table('payments',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('wallet_id', sa.String(length=36), nullable=False),
    sa.Column('pack_id', sa.String(length=36), nullable=False),
    sa.Column('credits', sa.Integer(), nullable=False),
    sa.Column('amount_inr', sa.Float(), nullable=False),
    sa.Column('gst_amount', sa.Float(), nullable=False),
    sa.Column('razorpay_order_id', sa.String(length=64), nullable=False),
    sa.Column('razorpay_payment_id', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('invoice_no', sa.String(length=30), nullable=True),
    sa.Column('created_by', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['pack_id'], ['credit_packs.id'], ),
    sa.ForeignKeyConstraint(['wallet_id'], ['wallets.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('invoice_no'),
    sa.UniqueConstraint('razorpay_payment_id')
    )
    _create_index(op.f('ix_payments_razorpay_order_id'), 'payments', ['razorpay_order_id'], unique=True)
    _create_index(op.f('ix_payments_wallet_id'), 'payments', ['wallet_id'], unique=False)
    _create_table('auth_tokens',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=True),
    sa.Column('signup_id', sa.String(length=36), nullable=True),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['teachers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_index(op.f('ix_auth_tokens_signup_id'), 'auth_tokens', ['signup_id'], unique=False)
    _create_index(op.f('ix_auth_tokens_token_hash'), 'auth_tokens', ['token_hash'], unique=True)
    _create_index(op.f('ix_auth_tokens_user_id'), 'auth_tokens', ['user_id'], unique=False)
    _create_table('consents',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('version', sa.String(length=20), nullable=False),
    sa.Column('ip', sa.String(length=64), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['teachers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_index(op.f('ix_consents_user_id'), 'consents', ['user_id'], unique=False)
    _create_table('support_tickets',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('subject', sa.String(length=200), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('reply', sa.Text(), nullable=False),
    sa.Column('replied_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['teachers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_index(op.f('ix_support_tickets_user_id'), 'support_tickets', ['user_id'], unique=False)
    _create_table('children',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('parent_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('standard', sa.Integer(), nullable=False),
    sa.Column('subjects', sa.JSON(), nullable=False),
    sa.Column('class_id', sa.String(length=36), nullable=True),
    sa.Column('student_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['class_id'], ['classes.id'], ),
    sa.ForeignKeyConstraint(['parent_id'], ['teachers.id'], ),
    sa.ForeignKeyConstraint(['student_id'], ['students.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_index(op.f('ix_children_parent_id'), 'children', ['parent_id'], unique=False)
    _create_table('generated_papers',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('standard', sa.Integer(), nullable=False),
    sa.Column('subject', sa.String(length=100), nullable=False),
    sa.Column('units', sa.JSON(), nullable=False),
    sa.Column('exam_id', sa.String(length=36), nullable=True),
    sa.Column('sources', sa.JSON(), nullable=False),
    sa.Column('validation', sa.JSON(), nullable=False),
    sa.Column('model', sa.String(length=100), nullable=False),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_table('parent_exams',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('child_id', sa.String(length=36), nullable=False),
    sa.Column('paper_id', sa.String(length=36), nullable=False),
    sa.Column('exam_id', sa.String(length=36), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('duration_minutes', sa.Integer(), nullable=False),
    sa.Column('selected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('upload_closes_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('pages', sa.Integer(), nullable=False),
    sa.Column('evaluation_id', sa.String(length=36), nullable=True),
    sa.Column('credits_paper', sa.Integer(), nullable=False),
    sa.Column('credits_eval', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['child_id'], ['children.id'], ),
    sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], ),
    sa.ForeignKeyConstraint(['paper_id'], ['generated_papers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_index(op.f('ix_parent_exams_child_id'), 'parent_exams', ['child_id'], unique=False)
    _create_table('disputes',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('raised_by', sa.String(length=36), nullable=False),
    sa.Column('evaluation_id', sa.String(length=36), nullable=False),
    sa.Column('exam_question_id', sa.String(length=36), nullable=True),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('resolution', sa.Text(), nullable=False),
    sa.Column('refund_credits', sa.Integer(), nullable=False),
    sa.Column('resolved_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['evaluation_id'], ['evaluations.id'], ),
    sa.ForeignKeyConstraint(['raised_by'], ['teachers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_index(op.f('ix_disputes_raised_by'), 'disputes', ['raised_by'], unique=False)
    _add_column('audit_logs', sa.Column('ip', sa.String(length=64), server_default='', nullable=False))
    _add_column('exams', sa.Column('origin', sa.String(length=20), server_default='TEACHER', nullable=False))
    _add_column('teachers', sa.Column('phone', sa.String(length=30), server_default='', nullable=False))
    _add_column('teachers', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
    _add_column('teachers', sa.Column('failed_attempts', sa.Integer(), server_default='0', nullable=False))
    _add_column('teachers', sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))
    _add_column('teachers', sa.Column('created_by', sa.String(length=36), nullable=True))
    _add_column('teachers', sa.Column('admin_role', sa.String(length=20), nullable=True))
    with op.batch_alter_table('teachers') as batch:  # null = Google-only or invited (batch: SQLite cannot alter)
        batch.alter_column('password_hash', existing_type=sa.VARCHAR(length=200), nullable=True)
    _add_column('workspaces', sa.Column('status', sa.String(length=20), server_default='ACTIVE', nullable=False))
    _add_column('workspaces', sa.Column('board', sa.String(length=20), server_default='CBSE', nullable=False))
    _add_column('workspaces', sa.Column('address', sa.Text(), server_default='', nullable=False))
    _add_column('workspaces', sa.Column('city', sa.String(length=100), server_default='', nullable=False))
    _add_column('workspaces', sa.Column('state', sa.String(length=100), server_default='', nullable=False))
    _add_column('workspaces', sa.Column('phone', sa.String(length=30), server_default='', nullable=False))
    _add_column('workspaces', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    _add_column('workspaces', sa.Column('approved_by', sa.String(length=36), nullable=True))


def downgrade():
    raise RuntimeError("Restore a verified backup instead of deleting account, credit and consent records.")
