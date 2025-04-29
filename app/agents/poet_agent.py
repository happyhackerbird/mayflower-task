from typing import TypedDict, List, Optional
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import logging
import os # To potentially get OLLAMA_BASE_URL
from langgraph.graph import StateGraph, END
from rhymetagger import RhymeTagger
import re # Import regex for basic keyword cleaning
import sys
from dotenv import load_dotenv
import operator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize LLM (ChatOllama)
load_dotenv()
ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
try:
    llm = ChatOllama(model="anthropic/claude-3.5-sonnet", base_url=ollama_base_url)
    logger.info(f"ChatOllama initialized with model '{llm.model}' and base URL: {ollama_base_url}")
except Exception as e:
    logger.error(f"Failed to initialize ChatOllama: {e}. Ensure Ollama is running and the model is available.")
    # Consider how to handle this - maybe raise an error or have a fallback?
    llm = None # Set llm to None or raise an exception if initialization fails

# Initialize RhymeTagger Globally
try:
    rt = RhymeTagger()
    logger.info("RhymeTagger instance created. Model will be loaded dynamically.")
except Exception as e:
    logger.error(f"Failed to initialize RhymeTagger or load model: {e}")
    rt = None # Set rt to None if initialization fails

# Define languages supported by RhymeTagger model loading based on user request
SUPPORTED_RHYME_LANGUAGES = {'cs', 'de', 'en', 'es', 'fr', 'nl', 'ru'}

# Map English Country Names to Language Code and Name
# Assuming input 'location' contains the full English country name
COUNTRY_TO_LANGUAGE_MAP = {
    "Czech Republic": {"code": "cs", "name": "Czech"},
    "Germany": {"code": "de", "name": "German"},
    "Austria": {"code": "de", "name": "German"},
    "Switzerland": {"code": "de", "name": "German"},
    "Spain": {"code": "es", "name": "Spanish"},
    "France": {"code": "fr", "name": "French"},
    "Netherlands": {"code": "nl", "name": "Dutch"},
    "Russia": {"code": "ru", "name": "Russian"},
    # Add common English-speaking countries mapping to 'en'
    "United Kingdom": {"code": "en", "name": "English"},
    "United States": {"code": "en", "name": "English"},
    "Canada": {"code": "en", "name": "English"},
    "Australia": {"code": "en", "name": "English"},
    "Ireland": {"code": "en", "name": "English"},
    "New Zealand": {"code": "en", "name": "English"},
    # Add more mappings as needed
}

# Define the PoetAgentState type
class PoetAgentState(TypedDict):
    location: str
    keywords: Optional[List[str]]
    draft_poem: Optional[str]
    validated_poem: Optional[str]
    error_message: Optional[str]
    validation_passed: bool
    retry_count: int
    max_retries: int
    validation_errors: Optional[List[dict]]
    language_code: Optional[str]
    language_name: Optional[str] # e.g., "German"
    rhyme_model_ready: Optional[bool] # True if rhyme model loaded for this run

# --- Node Definitions ---

def load_rhyme_model_node(state: PoetAgentState) -> dict:
    """
    Loads the RhymeTagger model for the detected language (if supported) and sets rhyme_model_ready in state.
    """
    language_code = state.get("language_code", "en")
    language_name = state.get("language_name", "English")
    model_ready = False
    error_msg = None

    if rt is None:
        logger.error("RhymeTagger instance not available. Skipping model load.")
        error_msg = "RhymeTagger instance not available."
        return {"rhyme_model_ready": False, "error_message": error_msg}

    if language_code not in SUPPORTED_RHYME_LANGUAGES:
        logger.warning(f"Language '{language_code}' ({language_name}) is not supported by RhymeTagger. Skipping model load.")
        error_msg = f"Language '{language_code}' is not supported by RhymeTagger."
        return {"rhyme_model_ready": False, "error_message": error_msg}

    try:
        logger.info(f"Loading RhymeTagger model for '{language_code}'...")
        rt.load_model(language_code)
        logger.info(f"RhymeTagger model for '{language_code}' loaded successfully.")
        model_ready = True
    except Exception as e:
        logger.error(f"Failed to load RhymeTagger model for '{language_code}': {e}")
        error_msg = f"Failed to load RhymeTagger model: {e}"
        model_ready = False
    return {"rhyme_model_ready": model_ready, "error_message": error_msg}

def determine_language_node(state: PoetAgentState) -> dict:
    """Determines the language by checking for supported country names in the location string."""
    location = state.get("location")
    lang_code = "en"  # Default to English
    lang_name = "English"
    error_msg = None

    if not location:
        logger.error("Location missing, cannot determine language.")
        return {"language_code": None, "language_name": None, "error_message": "Location not provided."}

    location_lower = location.lower()
    found_match = False
    for country, lang_info in COUNTRY_TO_LANGUAGE_MAP.items():
        # Simple check if the country name is in the location string (case-insensitive)
        if country.lower() in location_lower:
            lang_code = lang_info["code"]
            lang_name = lang_info["name"]
            logger.info(f"Determined language based on country '{country}': {lang_name} ({lang_code})")
            found_match = True
            break # Use the first match found

    if not found_match:
        logger.warning(f"No supported country name found in location '{location}'. Defaulting to English ('en').")
        # Keep default English

    # Ensure the determined code is actually loadable by RhymeTagger, though validation node does this too
    if lang_code not in SUPPORTED_RHYME_LANGUAGES:
         logger.warning(f"Determined language code '{lang_code}' from country name might not be supported by RhymeTagger ({SUPPORTED_RHYME_LANGUAGES}). Validation will attempt loading.")
         # We still pass the code along; validation node handles the final check/skip

    return {"language_code": lang_code, "language_name": lang_name, "error_message": error_msg}

def research_node(state: PoetAgentState) -> dict:
    """Performs web research using an online Ollama model to find keywords."""
    location = state["location"]
    language_code = state.get("language_code", "en") # Default to 'en' if not set
    language_name = state.get("language_name", "English")
    keywords_to_update = []
    error_msg = None

    if not location:
        return {"error_message": "Location not provided for research."}

    logger.info(f"Starting online research via Ollama for location: {location} (Detected Language: {language_name})")
    try:
        # Initialize ChatOllama specifically for the online research model
        # Assumes OLLAMA_BASE_URL is set or defaults correctly
        research_llm = ChatOllama(
            model="perplexity/sonar",
            base_url=ollama_base_url, # Use the same base URL
            temperature=0.1 # Low temperature for factual  extraction
        )

        # Define the prompt for the research model
        # Instructs it to browse and extract specific types of keywords
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", f"""
            You are an expert researcher tasked with finding specific, distinctive keywords about a location using your web browsing capabilities. 
            Find a MIX of famous or characteristic landmarks/natural features, notable cultural elements, local food specialities and unique local drinks or beverages. 
            Exclude generic terms. Search in {language_name} (language code: {language_code}) as it is the detected language for the location. 
            Return ONLY the keywords, as a comma-separated list of 10-15. Example answer: keyword1, keyword2, keyword3
            """),
            ("user", f"Find keywords for the location: {location}.")
        ])

        # Simple chain: prompt -> LLM -> string output
        chain = prompt_template | research_llm | StrOutputParser()

        logger.info(f'Querying Ollama model perplexity/sonar for: "{location}"')
        raw_keywords_string = chain.invoke({"location": location})

        if raw_keywords_string:
            # Split by comma, strip whitespace, filter empty strings
            keywords_list = [kw.strip() for kw in raw_keywords_string.split(',') if kw.strip()]
            if keywords_list:
                keywords_to_update = keywords_list
                logger.info(f"Extracted keywords (direct split): {keywords_to_update}")
            else:
                logger.warning(f"Raw keyword string was not empty but produced no keywords after split/strip: '{raw_keywords_string}'")
                keywords_to_update = [] # Ensure it's an empty list
        else:
            logger.warning("Received empty or None keyword string from the research model.")
            keywords_to_update = [] # Ensure it's an empty list

    except Exception as e:
        logger.error(f"Error during Ollama online research for {location}: {e}", exc_info=True)
        error_msg = f"Online research failed: {e}"
        keywords_to_update = [] # Ensure empty list on error

    # Always return the keywords list and potential error message
    return {
        "keywords": keywords_to_update,
        "error_message": error_msg
    }

def drafting_node(state: PoetAgentState) -> dict:
    """Generates a draft poem using the location, keywords, and detected language."""
    location = state["location"]
    keywords = state.get("keywords", []) # Use .get for safety
    # Get the current attempt number passed into this node
    current_attempt = state["retry_count"]
    max_retries = state["max_retries"]
    # NEW: Get detected language
    language_code = state.get("language_code", "en") # Default to 'en'
    language_name = state.get("language_name", "English")

    logger.info(f"---DRAFTING POEM (Attempt {current_attempt}/{max_retries}) FOR: {location} IN {language_name} ({language_code})---")

    if not keywords:
        logger.warning("No keywords found, generating poem without specific keywords.")
        keywords_str = "general themes related to the location"
    else:
        keywords_str = ", ".join(keywords)
        logger.info(f"Generating draft with keywords: {keywords_str}")

    # Define the prompt for the main LLM - MODIFIED FOR LANGUAGE
    prompt_template_str = f"""
    Generate a humorous, 2-stanza (8 lines total) poem in {language_name} about {location}.
    The poem MUST follow an ABAB CDCD rhyme scheme precisely.
    Each line MUST NOT exceed 30 characters.
    Subtly incorporate some of these {language_name} keywords/concepts if possible, but prioritize humor, rhyme, and constraints:
    {keywords_str}

    Poem:
    """
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", f"You are a creative poet tasked with writing a short, funny poem in {language_name} adhering to strict constraints. Return ONLY the poem."),
        ("user", prompt_template_str)
    ])

    # Ensure llm is initialized
    if llm is None:
        logger.error("LLM not initialized. Cannot draft poem.")
        # Return state indicating failure, maybe add an error message?
        return {"draft_poem": None, "error_message": "LLM not initialized.", "retry_count": current_attempt + 1} # Still increment count

    chain = prompt_template | llm | StrOutputParser()

    try:
        draft_poem = chain.invoke({"location": location, "keywords": keywords_str})
        logger.info(f"Draft generated (Attempt {current_attempt}):\n{draft_poem}")
    except Exception as e:
        logger.error(f"Error during poem drafting (Attempt {current_attempt}): {e}", exc_info=True)
        draft_poem = None # Ensure draft_poem is None on error

    # Increment AFTER this attempt's work is done
    next_retry_count = current_attempt + 1

    return {
        "draft_poem": draft_poem,
        "retry_count": next_retry_count # Pass the *next* count forward
    }

def validation_node(state: PoetAgentState) -> dict:
    """
    Validates the draft poem:
    1. Checks if each line is <= 30 characters.
    2. Checks if there are exactly 8 lines.
    3. Checks if rt.tag(lines, output_format=3) returns exactly [1, 2, 1, 2, 3, 4, 3, 4].
    Logs the raw rt.tag result.
    """
    draft_poem = state.get("draft_poem")
    # retry_count from state is the *next* attempt number; the one just validated is current - 1
    attempt_just_validated = state["retry_count"] - 1
    max_retries = state["max_retries"]
    location = state["location"]
    # NEW: Get detected language
    language_code = state.get("language_code", "en") # Default to 'en'
    language_name = state.get("language_name", "English")

    logger.info(f"---VALIDATING POEM (From Attempt {attempt_just_validated}/{max_retries}) FOR: {location} IN {language_name} ({language_code})---")

    validation_passed = True # Start assuming true, checks can set it to false
    error_messages = []
    detailed_errors = []
    rhyme_check_skipped = False # Flag for skipped rhyme check
    rhyme_model_loaded = False

    if not draft_poem:
        msg = "No draft poem provided for validation."
        error_messages.append(msg)
        detailed_errors.append({"type": "missing_data", "message": msg})
        logger.error(msg)
        validation_passed = False
        return {"validation_passed": validation_passed, "error_message": "\n".join(error_messages), "validation_errors": detailed_errors}

    lines = [line.strip() for line in draft_poem.strip().split('\n')]
    lines = [line for line in lines if line] # Remove empty lines
    num_lines = len(lines)

    # 1. Check line count (Must be exactly 8 for the specific rhyme check)
    if num_lines != 8:
        validation_passed = False
        msg = f"Poem must have exactly 8 lines for this validation, found {num_lines}."
        error_messages.append(msg)
        detailed_errors.append({"type": "structure", "message": msg})
        logger.warning(msg)
        # If line count is wrong, no need to check length or rhyme
        final_error_message = "Validation FAILED:\n- " + "\n".join(sorted(list(set(error_messages))))
        return {
            "validation_passed": validation_passed,
            "validated_poem": None,
            "error_message": final_error_message,
            "validation_errors": detailed_errors
        }

    # 2. Check line length (max 30 chars)
    for i, line in enumerate(lines):
        if len(line) > 30:
            validation_passed = False
            msg = f"Line {i+1} exceeds 30 characters: '{line[:27]}...' ({len(line)} chars)"
            error_messages.append(msg)
            detailed_errors.append({"type": "line_length", "line_number": i + 1, "content": line, "actual": len(line), "expected": 30, "message": msg})
            logger.warning(msg)

    # 3. Check specific rhyme pattern [1, 2, 1, 2, 3, 4, 3, 4]
    rhyme_model_ready = state.get("rhyme_model_ready", False)
    if not rhyme_model_ready:
        logger.warning("RhymeTagger model not loaded for this language, skipping rhyme check.")
        rhyme_check_skipped = True
    else:
        expected_rhyme_pattern = [1, 2, 1, 2, 3, 4, 3, 4]
        logger.info(f"Checking if rhyme pattern matches: {expected_rhyme_pattern}")
        try:
            rhyme_ids_result = rt.tag(lines, output_format=3)
            logger.info(f"Raw result from rt.tag(lines, output_format=1): {rhyme_ids_result}")
            if rhyme_ids_result == expected_rhyme_pattern:
                logger.info(f"Rhyme check PASSED. Result matches expected pattern.")
            else:
                validation_passed = False
                msg = f"Rhyme check FAILED. Expected {expected_rhyme_pattern}, but got {rhyme_ids_result}."
                error_messages.append(msg)
                detailed_errors.append({"type": "rhyme", "expected": expected_rhyme_pattern, "actual": rhyme_ids_result, "message": msg})
                logger.warning(msg)
        except Exception as tag_exc:
            validation_passed = False
            msg = f"Error during rt.tag call: {tag_exc}"
            error_messages.append(msg)
            detailed_errors.append({"type": "rhyme_check_error", "message": msg})
            logger.error(msg, exc_info=True)
    # End rhyme check block

    # --- Construct Output ---
    final_error_message = None
    if not validation_passed:
        unique_error_messages = sorted(list(set(error_messages)))
        final_error_message = "Validation FAILED:\n- " + "\n".join(unique_error_messages)
        if rhyme_check_skipped:
             final_error_message += "\n- (Rhyme check was skipped due to unsupported language or model loading error)"

    # If validation passed *despite* skipping rhyme check, add a note
    if validation_passed and rhyme_check_skipped:
        logger.info("Validation PASSED, but rhyme check was skipped.")
        # Optionally add info to state? For now, just log.

    return {
        "validation_passed": validation_passed,
        "validated_poem": draft_poem if validation_passed else None,
        "error_message": final_error_message,
        "validation_errors": detailed_errors
        # language_code is already in state, no need to return again
    }

# --- Conditional Edge Logic ---

def check_rhyme_model_readiness(state: PoetAgentState) -> str:
    """Determines if the rhyme model loaded successfully."""
    if state.get("rhyme_model_ready", False):
        logger.info("Rhyme model ready, proceeding to research.")
        return "proceed"
    else:
        logger.error("Rhyme model failed to load or is not supported. Ending execution.")
        return "fail"

def should_retry_drafting(state: PoetAgentState) -> str:
    """
    Determines the next step after validation.
    Returns 'draft_poem_node' to retry or END if validation passed or max retries reached.
    """
    validation_passed = state["validation_passed"]
    retry_count = state["retry_count"]
    max_retries = state["max_retries"]
    error_message = state.get("error_message", "") # Get error message if present

    if validation_passed:
        logger.info("---VALIDATION PASSED - FINISHING---")
        return END
    elif retry_count < max_retries:
        logger.warning(f"---VALIDATION FAILED - RETRYING DRAFT ({retry_count}/{max_retries})---")
        return "drafting_node" # Name of the node to loop back to
    else:
        logger.error(f"---VALIDATION FAILED - MAX RETRIES ({max_retries}) REACHED - FINISHING WITH ERROR---")
        # Keep the last error message in the state
        return END

# --- Build the Graph ---

# Initialize the graph
workflow = StateGraph(PoetAgentState)

# Add nodes
workflow.add_node("determine_language", determine_language_node)
workflow.add_node("load_rhyme_model", load_rhyme_model_node)
workflow.add_node("research_keywords", research_node)
workflow.add_node("drafting_node", drafting_node)
workflow.add_node("validation_node", validation_node)

# Define edges
workflow.set_entry_point("determine_language")
workflow.add_edge("determine_language", "load_rhyme_model")
workflow.add_conditional_edges(
    "load_rhyme_model",
    check_rhyme_model_readiness, # NEW condition function
    {
        "proceed": "research_keywords", # Go to research if model is ready
        "fail": END          # End graph if model failed to load
    }
)
workflow.add_edge("research_keywords", "drafting_node")
workflow.add_edge("drafting_node", "validation_node")
workflow.add_conditional_edges(
    "validation_node",          # Source node
    should_retry_drafting,    # Function to decide the next node
    {
        "drafting_node": "drafting_node", # If function returns "drafting_node", go to drafting_node
        END: END                   # If function returns END, finish execution
    }
)

# Compile the graph
poet_agent_graph = workflow.compile()

logger.info("Poet Agent graph compiled successfully.")

# --- Optional: Function to invoke the graph ---
def run_poet_agent(location: str, max_retries: int = 7) -> PoetAgentState:
    """Runs the compiled poet agent graph for a given location."""
    logger.info(f"---STARTING POET AGENT RUN FOR: {location}---")
    initial_state: PoetAgentState = {
        "location": location,
        "keywords": None,
        "draft_poem": None,
        "validated_poem": None,
        "error_message": None,
        "validation_passed": False,
        "retry_count": 0,
        "max_retries": max_retries,
        "validation_errors": None,
        "language_code": None,
        "language_name": None
    }
    # LangGraph streaming can be complex, invoke synchronously for now
    final_state = poet_agent_graph.invoke(initial_state)
    logger.info(f"---POET AGENT RUN FINISHED FOR: {location}---")
    logger.info(f"Final State: {final_state}") # Log the entire final state
    return final_state

# Example usage (for testing)
if __name__ == "__main__":
    location = "Munich, Germany" # Example location
    print(f"--- STARTING POET AGENT FOR: {location} ---")
    inputs = {
        "location": location,
        "retry_count": 1, # Start at attempt 1
        "max_retries": 5  # Define maximum attempts
    }
    final_state = poet_agent_graph.invoke(inputs)