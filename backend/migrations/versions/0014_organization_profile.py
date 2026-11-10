"""Organization profile: contact, address, regional and tax details."""

from alembic import op

revision = "0014_organization_profile"
down_revision = "0013_lead_status_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE crm.organizations
            ADD COLUMN logo_url text CHECK(length(logo_url) <= 500),
            ADD COLUMN website text CHECK(length(website) <= 300),
            ADD COLUMN industry text CHECK(length(industry) <= 100),
            ADD COLUMN company_size text CHECK(length(company_size) <= 20),
            ADD COLUMN business_email text CHECK(length(business_email) <= 320),
            ADD COLUMN business_phone text CHECK(length(business_phone) <= 20),
            ADD COLUMN address text CHECK(length(address) <= 500),
            ADD COLUMN city text CHECK(length(city) <= 100),
            ADD COLUMN state text CHECK(length(state) <= 100),
            ADD COLUMN postal_code text CHECK(length(postal_code) <= 12),
            ADD COLUMN country text NOT NULL DEFAULT 'IN' CHECK(length(country) = 2),
            ADD COLUMN gstin text CHECK(length(gstin) = 15)
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE crm.organizations
            DROP COLUMN logo_url, DROP COLUMN website, DROP COLUMN industry, DROP COLUMN company_size,
            DROP COLUMN business_email, DROP COLUMN business_phone, DROP COLUMN address, DROP COLUMN city,
            DROP COLUMN state, DROP COLUMN postal_code, DROP COLUMN country, DROP COLUMN gstin
    """)
