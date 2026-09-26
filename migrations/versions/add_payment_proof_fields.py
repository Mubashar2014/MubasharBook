"""Add payment proof fields

Revision ID: add_payment_proof
Revises: 7f3a9c2d5e18
Create Date: 2026-09-26

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_payment_proof'
down_revision = '7f3a9c2d5e18'
branch_labels = None
depends_on = None


def upgrade():
    # Add payment_proof column
    op.add_column('payments', sa.Column('payment_proof', sa.String(length=500), nullable=True))
    
    # Add verified_by_id column
    op.add_column('payments', sa.Column('verified_by_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_payments_verified_by_id', 'payments', 'users', ['verified_by_id'], ['id'])


def downgrade():
    # Remove foreign key first
    op.drop_constraint('fk_payments_verified_by_id', 'payments', type_='foreignkey')
    
    # Remove columns
    op.drop_column('payments', 'verified_by_id')
    op.drop_column('payments', 'payment_proof')
