import pytest
from sqlalchemy import text
from app.database.connection import engine
from app.core.logger import logger

# Configure pytest-asyncio to handle the event loop scope
pytestmark = pytest.mark.asyncio

async def test_db_connection_success():
    """
    Verifies that the application can successfully establish an asynchronous
    connection to the Neon serverless PostgreSQL instance and run a test query.
    
    This is an integration test validating:
    1. The correctness of the connection string.
    2. Connection pool allocation and SSL handshake.
    3. Proper SQL execution through SQLAlchemy 2.0 and asyncpg.
    """
    logger.info("Initiating database connection verification test...")
    
    try:
        # Obtain a connection from the connection pool
        async with engine.connect() as connection:
            # Execute simple standard SQL ping
            result = await connection.execute(text("SELECT 1"))
            value = result.scalar()
            
            logger.info("Connection test query execution successful! Result: %s", value)
            
            # Assert response is correct
            assert value == 1, f"Expected query to return 1, but got {value}"
            
    except Exception as exc:
        logger.error("Database connection verification failed: %s", exc, exc_info=True)
        pytest.fail(f"Failed to connect to the cloud Neon database. Error details: {exc}")
