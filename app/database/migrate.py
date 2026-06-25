from sqlalchemy import text


MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_token VARCHAR(255)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_expires TIMESTAMPTZ",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS gallery_urls TEXT",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS subtotal FLOAT DEFAULT 0",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS discount_amount FLOAT DEFAULT 0",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS coupon_code VARCHAR(50)",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS warehouse_id INTEGER",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'customer'",
]


async def apply_migrations(conn) -> None:
    for stmt in MIGRATIONS:
        await conn.execute(text(stmt))
