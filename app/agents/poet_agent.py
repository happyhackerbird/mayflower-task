from typing import TypedDict, List, Optional
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import logging
import re # Import regex for basic keyword cleaning
import os # To potentially get OLLAMA_BASE_URL
from langgraph.graph import StateGraph, END
from rhymetagger import RhymeTagger

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize LLM (ChatOllama)
# Assumes OLLAMA_BASE_URL is set or defaults correctly
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
    # Load German model. Change 'de' for other supported languages if needed.
    rt.load_model('de')
    logger.info("RhymeTagger initialized with German model.")
except Exception as e:
    logger.error(f"Failed to initialize RhymeTagger or load model: {e}")
    rt = None # Set rt to None if initialization fails

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

# --- Node Definitions ---

def research_node(state: PoetAgentState) -> dict:
    """Performs web research using an online Ollama model to find keywords.

    Uses ChatOllama with the 'perplexity/sonar' model
    to browse the web and find distinctive local food, drinks, landmarks,
    and cultural features for the given location.
    Updates the 'keywords' field in the state dictionary.

    Args:
        state (dict): The current state dictionary, must contain 'location'.

    Returns:
        dict: A dictionary containing 'keywords' list and optionally 'error_message'.
    """
    location = state.get("location")
    if not location:
        return {"error_message": "Location not provided for research."}

    logger.info(f"Starting online research via Ollama for location: {location}")
    keywords_to_update = []
    error_msg = None

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
            ("system", "You are an expert researcher tasked with finding specific, distinctive keywords about a location using your web browsing capabilities. Find a MIX of famous or characteristic landmarks/natural features, notable cultural elements, local food specialities and unique local drinks or beverages. Exclude generic terms. Search in the language of the location. Return ONLY the keywords, as a comma-separated list of 10-15. Example answer: keyword1, keyword2, keyword3"),
            ("user", "Find keywords for the location: {location}.")
        ])
#         This prompt doesnt work as well, kept for reference: 
#         You are an expert cultural researcher tasked with identifying distinctive keywords about a location using web search capabilities. Find a MIX of:

# 1. Famous and characteristic landmarks and natural features
# 2. Cultural elements
# 3. Local food specialties
# 4. Unique local drinks and beverages 

# Search in the native language of the location when appropriate. Exclude generic terms that could apply to many places.

# Return 10-15 highly specific keywords as a comma-separated list.

# For example, for Barcelona: La Sagrada Familia, paella valenciana, cava, Gaudí architecture, La Rambla, calcots, crema catalana, Barceloneta Beach, castellers, Montjuïc, Barri Gòtic, El Raval"""),


        # Simple chain: prompt -> LLM -> string output
        chain = prompt_template | research_llm | StrOutputParser()

        logger.info(f'Querying Ollama model perplexity/sonar for: "{location}"')
        raw_keywords_string = chain.invoke({"location": location})
        print(raw_keywords_string)

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
# --- Drafting Node ---

def drafting_node(state: PoetAgentState) -> dict:
    """Generates a draft poem using the location and keywords."""
    location = state["location"]
    keywords = state.get("keywords", []) # Use .get for safety
    # Get the current attempt number passed into this node
    current_attempt = state["retry_count"]
    max_retries = state["max_retries"]

    logger.info(f"---DRAFTING POEM (Attempt {current_attempt}/{max_retries}) FOR: {location}---")

    if not keywords:
        logger.warning("No keywords found, generating poem without specific keywords.")
        keywords_str = "general themes related to the location"
    else:
        keywords_str = ", ".join(keywords)
        logger.info(f"Generating draft with keywords: {keywords_str}")

    # Define the prompt for the main LLM
    prompt_template_str = """
    Generate a humorous, 2-stanza (8 lines total) poem in German about {location}.
    The poem MUST follow an ABAB CDCD rhyme scheme precisely.
    Each line MUST NOT exceed 30 characters.
    Subtly incorporate some of these keywords/concepts if possible, but prioritize humor, rhyme, and constraints:
    {keywords}

    Poem:
    """
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", "You are a creative poet tasked with writing a short, funny poem in German adhering to strict constraints. Return ONLY the poem."),
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

# --- Validation Node ---

def validation_node(state: PoetAgentState) -> dict:
    """
    Validates the draft poem:
    1. Checks if each line is <= 30 characters.
    2. Checks if there are exactly 8 lines.
    3. Checks if rt.tag(lines, output_format=1) returns exactly [1, 2, 1, 2, 3, 4, 3, 4].
    Logs the raw rt.tag result.
    """
    draft_poem = state.get("draft_poem")
    # retry_count from state is the *next* attempt number; the one just validated is current - 1
    attempt_just_validated = state["retry_count"] - 1
    max_retries = state["max_retries"]
    location = state["location"]

    logger.info(f"---VALIDATING POEM (From Attempt {attempt_just_validated}/{max_retries}) FOR: {location}---")

    validation_passed = True # Start assuming true, checks can set it to false
    error_messages = []
    detailed_errors = []

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
    if rt is None:
        logger.warning("RhymeTagger not initialized, skipping rhyme check.")
        # Decide if validation should fail if tagger isn't available
        # validation_passed = False
        # msg = "RhymeTagger not available for validation."
        # error_messages.append(msg)
        # detailed_errors.append({"type": "config", "message": msg})
    else:
        expected_rhyme_pattern = [1, 2, 1, 2, 3, 4, 3, 4]
        logger.info(f"Checking if rhyme pattern matches: {expected_rhyme_pattern}")
        try:
            logger.info("Calling rt.tag(lines, output_format=3)...")
            rhyme_ids_result = rt.tag(lines, output_format=3)
            logger.info(f"Raw result from rt.tag(lines, output_format=3): {rhyme_ids_result}")

            if rhyme_ids_result == expected_rhyme_pattern:
                logger.info(f"Rhyme check PASSED. Result matches expected pattern.")
            else:
                validation_passed = False
                msg = f"Rhyme check FAILED. Expected {expected_rhyme_pattern}, but got {rhyme_ids_result}."
                error_messages.append(msg)
                detailed_errors.append({"type": "rhyme", "expected": expected_rhyme_pattern, "actual": rhyme_ids_result, "message": msg})
                logger.warning(msg)

        except Exception as e:
            validation_passed = False
            msg = f"Error during rt.tag call: {e}"
            error_messages.append(msg)
            detailed_errors.append({"type": "rhyme_check_error", "message": msg})
            logger.error(msg, exc_info=True)

    # --- Construct Output ---
    final_error_message = None
    if not validation_passed:
        unique_error_messages = sorted(list(set(error_messages)))
        final_error_message = "Validation FAILED:\n- " + "\n".join(unique_error_messages)

    return {
        "validation_passed": validation_passed,
        "validated_poem": draft_poem if validation_passed else None,
        "error_message": final_error_message,
        "validation_errors": detailed_errors
    }

# --- Conditional Edge Logic ---

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
        return "draft_poem_node" # Name of the node to loop back to
    else:
        logger.error(f"---VALIDATION FAILED - MAX RETRIES ({max_retries}) REACHED - FINISHING WITH ERROR---")
        # Keep the last error message in the state
        return END

# --- Build the Graph ---

# Initialize the graph
workflow = StateGraph(PoetAgentState)

# Add nodes
workflow.add_node("research_keywords", research_node)
workflow.add_node("draft_poem_node", drafting_node)
workflow.add_node("validate_poem", validation_node)

# Define edges
workflow.set_entry_point("research_keywords")
workflow.add_edge("research_keywords", "draft_poem_node")
workflow.add_edge("draft_poem_node", "validate_poem")

# Add conditional edge from validation
workflow.add_conditional_edges(
    "validate_poem",          # Source node
    should_retry_drafting,    # Function to decide the next node
    {
        "draft_poem_node": "draft_poem_node", # If function returns "draft_poem_node", go to drafting_node
        END: END                   # If function returns END, finish execution
    }
)

# Compile the graph
poet_agent_graph = workflow.compile()

logger.info("Poet Agent graph compiled successfully.")

# --- Optional: Function to invoke the graph ---
def run_poet_agent(location: str, max_retries: int = 3) -> PoetAgentState:
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
    }
    # LangGraph streaming can be complex, invoke synchronously for now
    final_state = poet_agent_graph.invoke(initial_state)
    logger.info(f"---POET AGENT RUN FINISHED FOR: {location}---")
    logger.info(f"Final State: {final_state}") # Log the entire final state
    return final_state

# Example usage (for testing)
if __name__ == "__main__":
    location = "Isny im Allgäu, Deutschland" # Example location
    print(f"--- STARTING POET AGENT FOR: {location} ---")
    inputs = {
        "location": location,
        "retry_count": 1, # Start at attempt 1
        "max_retries": 5  # Define maximum attempts
    }
    final_state = poet_agent_graph.invoke(inputs)