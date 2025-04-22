import os
from sqlmodel import SQLModel, create_engine, Session
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    logger.warning("DATABASE_URL environment variable not set. Using default SQLite database: ./database.db")
    DATABASE_URL = "sqlite:///./database.db" # Default to SQLite for ease of setup

# Special handling for PostgreSQL URLs on some platforms
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Set connect_args for SQLite
connect_args = {}
engine_args = {"echo": True} # Log SQL statements

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False} # Needed for SQLite only
    engine_args["connect_args"] = connect_args
    logger.info("Using SQLite database engine.")
elif DATABASE_URL.startswith("postgresql"):
     logger.info("Using PostgreSQL database engine.")
else:
    logger.warning(f"Unrecognized database type for URL: {DATABASE_URL}")


try:
    engine = create_engine(DATABASE_URL, **engine_args)
except Exception as e:
    logger.error(f"Error creating database engine: {e}")
    raise

def create_db_and_tables():
    """
    Creates database tables based on SQLModel metadata.
    NOTE: In production, use migrations (like Alembic) instead.
    """
    logger.info("Attempting to create database tables...")
    try:
        # Ensure models are imported before creating tables
        from . import models # noqa
        SQLModel.metadata.create_all(engine)
        logger.info("Database tables creation process completed.")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        # Depending on the error, you might want to exit or handle differently
        # For now, just log the error

def get_session():
    """
    Dependency function to get a database session.
    """
    with Session(engine) as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Error during database session: {e}")
            session.rollback()
            raise
        finally:
            session.close()
