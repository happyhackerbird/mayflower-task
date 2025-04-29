import pytest
from sqlmodel import SQLModel, Session, create_engine
from fastapi.testclient import TestClient

# Use an in-memory SQLite database for testing
# Adding check_same_thread=False is recommended for SQLite with multiple test functions potentially accessing it.
# Use aiosqlite driver prefix if async operations are expected later.
TEST_DATABASE_URL = "sqlite:///./test.db?check_same_thread=False"
# Alternative: In-memory DB (resets completely each run)
# TEST_DATABASE_URL = "sqlite:///:memory:?check_same_thread=False"

# Create the test engine
engine = create_engine(TEST_DATABASE_URL, echo=False) # Set echo=True for SQL logging

# Assuming your FastAPI app object is named 'app' in 'main.py'
from main import app

@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    """Fixture to create tables before test session and drop after."""
    # Need to import models here so SQLModel knows about them
    from app.models import Address, Poem # Import all models that need tables
    print("\nCreating test database tables...")
    try:
        SQLModel.metadata.create_all(engine)
        yield # Test session runs here
        # Teardown: Drop tables after session (optional, useful for file DB)
        print("\nDropping test database tables...")
        SQLModel.metadata.drop_all(engine)
    except Exception as e:
        print(f"Error during test table setup/teardown: {e}")
        raise

@pytest.fixture(scope="function")
def db() -> Session:
    """Pytest fixture to provide a database session per test function."""
    # Use 'with Session(engine)' for context management (commit/rollback)
    with Session(engine) as session:
        yield session
        # Optional: Clean up data between tests if needed, 
        # especially if not using in-memory DB or session scope tables.
        # For function scope with in-memory, maybe not strictly needed,
        # but good practice for file-based test DBs.
        # Example: session.execute(text("DELETE FROM address"))
        #          session.execute(text("DELETE FROM poem"))
        #          session.commit()

@pytest.fixture(scope="module")
def client() -> TestClient:
    """
    Pytest fixture to create a TestClient instance for API testing.
    """
    # Here, you might potentially override dependencies for testing,
    # e.g., using the test DB session instead of the production one.
    # For now, we assume the app uses dependencies correctly or
    # dependency overrides are handled elsewhere if needed.
    with TestClient(app) as c:
        yield c
