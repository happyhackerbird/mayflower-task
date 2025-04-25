# app/crud/poem.py
from typing import Optional, Callable
import logging # Add logging import

from sqlmodel import Session, select

from app.models import Poem, PoemBase
# Remove the placeholder import
# from app.services.poem_generator import generate_poem_for_location
# Import the actual agent runner
from app.agents.poet_agent import run_poet_agent, PoetAgentState

logger = logging.getLogger(__name__) # Initialize logger for this module

# Helper function to call the agent and extract the poem
def invoke_agent_and_get_poem(location_key: str) -> str:
    """Calls the poet agent and returns the validated poem text or raises an error."""
    logger.info(f"Invoking poet agent for location_key: {location_key}")
    try:
        # Run the agent
        final_state: PoetAgentState = run_poet_agent(location=location_key)

        # Check the result
        if final_state.get("validation_passed") and final_state.get("validated_poem"):
            poem_text = final_state["validated_poem"]
            logger.info(f"Agent successfully generated poem for {location_key}")
            return poem_text
        else:
            error_msg = final_state.get("error_message", "Unknown error during poem generation.")
            logger.error(f"Agent failed for {location_key}: {error_msg}")
            # Decide on error handling: return a default poem, or raise exception
            # Raising an exception might be better to signal failure upstream
            raise ValueError(f"Poem generation failed for {location_key}: {error_msg}")

    except Exception as e:
        logger.error(f"Exception while running poet agent for {location_key}: {e}", exc_info=True)
        # Re-raise or handle as appropriate
        raise ValueError(f"Poem generation failed due to an exception for {location_key}: {e}")


def get_poem(*, db: Session, id: int) -> Optional[Poem]:
    """Get a poem by its ID."""
    return db.get(Poem, id)


def get_poem_by_location_key(*, db: Session, location_key: str) -> Optional[Poem]:
    """
    Retrieves a poem by its location_key.
    """
    statement = select(Poem).where(Poem.location_key == location_key)
    results = db.exec(statement)
    return results.first()


def create_poem_from_base(*, db: Session, poem_in: PoemBase) -> Poem:
    """
    Creates a new poem in the database from a PoemBase model.
    Renamed to avoid conflict with the simpler create_poem below.
    """
    if not poem_in.location_key:
         raise ValueError("location_key is required to create a Poem")

    db_poem = Poem.model_validate(poem_in)
    db.add(db_poem)
    db.commit()
    db.refresh(db_poem)
    return db_poem


def find_poem_by_location_key(db: Session, location_key: str) -> Optional[Poem]:
    """Finds a poem by its unique location key."""
    statement = select(Poem).where(Poem.location_key == location_key)
    return db.exec(statement).first()


# This simpler create_poem is used internally by find_or_create_poem
def create_poem(db: Session, location_key: str, text: str) -> Poem:
    """Creates a new poem record directly."""
    db_poem = Poem(location_key=location_key, text=text)
    db.add(db_poem)
    db.commit()
    db.refresh(db_poem)
    return db_poem


def find_or_create_poem(
    db: Session,
    location_key: str,
    # Update the default generator function to use the agent wrapper
    generator_func: Callable[[str], str] = invoke_agent_and_get_poem
) -> Poem:
    """Finds a poem by location_key or creates a new one using the agent if not found."""
    logger.debug(f"Attempting to find/create poem for location_key: {location_key}")
    db_poem = find_poem_by_location_key(db=db, location_key=location_key)
    if db_poem:
        logger.debug(f"Found existing poem (ID: {db_poem.id}) for {location_key}")
        return db_poem

    # Poem not found, generate text using the agent wrapper and create it
    logger.info(f"No existing poem found for {location_key}. Generating new one...")
    # The generator_func now defaults to invoke_agent_and_get_poem
    try:
        poem_text = generator_func(location_key)
        new_poem = create_poem(db=db, location_key=location_key, text=poem_text)
        logger.info(f"Successfully created new poem (ID: {new_poem.id}) for {location_key}")
        return new_poem
    except ValueError as e:
         # Catch errors from the agent/wrapper and log/re-raise or handle
         logger.error(f"Failed to generate or create poem for {location_key}: {e}")
         # Re-raising allows the caller (e.g., create_address) to handle the failure
         raise e
    except Exception as e:
         # Catch unexpected errors during creation
         logger.error(f"Unexpected error creating poem for {location_key}: {e}", exc_info=True)
         raise ValueError(f"Unexpected error during poem creation for {location_key}")
