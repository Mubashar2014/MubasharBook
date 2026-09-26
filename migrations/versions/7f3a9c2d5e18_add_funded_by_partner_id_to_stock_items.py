"""Add funded_by_partner_id to stock_items

Revision ID: 7f3a9c2d5e18
Revises: 4db935a21e8f
Create Date: 2026-09-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7f3a9c2d5e18'
down_revision = '4db935a21e8f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('stock_items', sa.Column('funded_by_partner_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_stock_items_funded_by_partner_id'), 'stock_items', ['funded_by_partner_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_stock_items_funded_by_partner_id'), table_name='stock_items')
    op.drop_column('stock_items', 'funded_by_partner_id')
