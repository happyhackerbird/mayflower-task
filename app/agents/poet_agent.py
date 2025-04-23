from typing import TypedDict, List, Optional
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import logging
import re # Import regex for basic keyword cleaning
import os # To potentially get OLLAMA_BASE_URL
from langgraph.graph import StateGraph, END
import pronouncing # Use pronouncing for rhyme checks

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize LLM (ChatOllama)
# Assumes Ollama is running and accessible.
# Set OLLAMA_BASE_URL in .env if not default (http://localhost:11434)
# Fallback to default if not set
ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

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
    """Performs web research AND drafts a poem using an online Ollama model.

    Uses ChatOllama with the 'perplexity/sonar' model
    to browse the web for distinctive local features (food, drinks, landmarks, culture)
    for the given location AND then drafts a short poem based on that research.
    The poem should be in the dominant language of the location, have 2 stanzas
    of 4 lines each, and adhere to a 30-character line limit.
    Updates the 'draft_poem' field in the state dictionary.

    Args:
        state (dict): The current state dictionary, must contain 'location'.

    Returns:
        dict: A dictionary containing 'draft_poem' and optionally 'error_message'.
    """
    location = state.get("location")
    if not location:
        return {"error_message": "Location not provided for research."}

    logger.info(f"Starting online research & drafting via Ollama for location: {location}")
    draft_poem_output = None
    error_msg = None
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    try:
        # Initialize ChatOllama specifically for the online research/drafting model
        research_draft_llm = ChatOllama(
            model="perplexity/sonar",
            base_url=ollama_base_url,
        )

        # Define the combined prompt for research and drafting
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", """
You are a creative, concise, and culturally sensitive poet.

Rules:
1. Always answer ONLY with a poem, never with explanations, lists, or commentary.
2. Use the dominant local language of the location (e.g., German for Germany).
3. Structure: 2 stanzas, 4 lines per stanza.
4. Each line must be under 30 characters.
5. Choose a consistent rhyme scheme (AABB or ABAB).
6. Incorporate specific local foods, drinks, landmarks, and cultural features based on the user's query.
7. Never include a title, introduction, or any extra text—only the poem.
"""),
            ("user", "What are some famous local foods, drinks, landmarks, and cultural features of {location}? Answer ONLY in poem format, following the rules provided.")
        ])

        # Simple chain: prompt -> LLM -> string output (the draft poem)
        chain = prompt_template | research_draft_llm | StrOutputParser()

        logger.info(f'Querying Ollama model (research & draft) for: "{location}"')
        draft_poem_output = chain.invoke({"location": location})

        # Basic cleanup: remove potential leading/trailing whitespace
        if draft_poem_output:
            draft_poem_output = draft_poem_output.strip()
            logger.info(f"""Draft poem received from Ollama:
---
{draft_poem_output}
---""")
        else:
            logger.warning(f"Ollama online model returned an empty draft for {location}.")
            error_msg = "Ollama returned an empty draft."

    except Exception as e:
        logger.error(f"Error during Ollama online research/drafting for {location}: {e}", exc_info=True)
        error_msg = f"Online research/drafting failed: {e}"
        draft_poem_output = None

    # Return the draft poem, ready for validation
    # Clear keywords as they are no longer generated here
    return {"draft_poem": draft_poem_output, "keywords": [], "error_message": error_msg}


# --- Helper Function using rhyming_part ---
def check_rhyme_via_part(word1: Optional[str], word2: Optional[str]) -> bool:
    """
    Checks if two words rhyme by comparing their 'rhyming parts'
    as determined by the pronouncing library.
    Handles multiple pronunciations and words not found.
    """
    if not word1 or not word2:
        return False # Cannot rhyme if a word is missing

    try:
        # Get phones first to handle not found words gracefully
        phones1 = pronouncing.phones_for_word(word1)
        phones2 = pronouncing.phones_for_word(word2)

        if not phones1 or not phones2:
            logger.warning(f"Word not found in dictionary: '{word1 if not phones1 else word2}'")
            return False # Word not found in dictionary

        # Get all rhyming parts for potentially multiple pronunciations
        # Use the raw phone string with rhyming_part
        parts1 = [pronouncing.rhyming_part(p) for p in phones1 if p]
        parts2 = [pronouncing.rhyming_part(p) for p in phones2 if p]

        if not parts1 or not parts2:
             # Should not happen if phones were found, but safety check
             logger.warning(f"Could not determine rhyming part for '{word1}' or '{word2}'")
             return False

        # Check if *any* rhyming part matches between the two words
        return any(part1 == part2 for part1 in parts1 for part2 in parts2)

    except Exception as e:
        logger.error(f"Error checking rhyming_part for '{word1}' and '{word2}': {e}")
        return False

# --- Validation Node ---

def check_line_length(poem_text: str, max_len: int = 30) -> List[str]:
    """Checks if any line in the poem exceeds the maximum length."""
    errors = []
    lines = [line for line in poem_text.split('\n') if line.strip()] # Ignore empty lines
    for i, line in enumerate(lines):
        if len(line) > max_len:
            errors.append(f"Line {i+1} exceeds {max_len} characters: '{line[:max_len]}...' ({len(line)} chars)")
    return errors

def validation_node(state: PoetAgentState) -> dict:
    """
    Validates the draft poem against constraints (line length, rhyme scheme).
    Updates 'validation_passed', 'validated_poem', and 'error_message'.
    Increments 'retry_count' if validation fails.
    """
    draft_poem = state.get("draft_poem")
    location = state.get("location") # Used for logging
    current_retry = state.get("retry_count", 0)
    max_retries_allowed = state.get("max_retries", 3)
    logger.info(f"---VALIDATING POEM (Attempt {current_retry}/{max_retries_allowed}) FOR: {location}---")
    validation_passed = True
    error_messages = []
    detailed_errors = []

    if not draft_poem:
        logger.warning("No draft poem provided for validation.")
        return {
            "validation_passed": False,
            "error_message": "No draft poem provided for validation.",
            "validated_poem": None,
            "validation_errors": [{"type": "missing_draft", "message": "No draft poem"}],
            "retry_count": current_retry + 1
        }

    lines = [line.strip() for line in draft_poem.strip().split('\n') if line.strip()]
    num_lines = len(lines)

    # 1. Check total line count (expecting 8 for 2 stanzas of 4 lines)
    if num_lines != 8:
        msg = f"Poem has {num_lines} lines, expected 8."
        error_messages.append(msg)
        detailed_errors.append({"type": "line_count", "expected": 8, "actual": num_lines, "message": msg})
        validation_passed = False

    # 2. Check line length (max 30 chars)
    for i, line in enumerate(lines):
        line_num = i + 1
        if len(line) > 30:
            msg = f"Line {line_num} exceeds 30 characters: '{line[:25]}...' ({len(line)} chars)"
            error_messages.append(msg)
            detailed_errors.append({
                "type": "line_length",
                "line_number": line_num,
                "content": line,
                "actual": len(line),
                "expected": 30,
                "message": msg
            })
            validation_passed = False

    # 3. Check ABAB rhyme scheme per stanza using check_rhyme_via_part helper
    if num_lines % 4 == 0:
        for i in range(0, num_lines - num_lines % 4, 4): # Iterate through full 4-line stanzas
            stanza_num = (i // 4) + 1
            try:
                # Extract last words
                words_a1 = re.findall(r'\b\w+\b', lines[i].lower())
                words_b1 = re.findall(r'\b\w+\b', lines[i+1].lower())
                words_a2 = re.findall(r'\b\w+\b', lines[i+2].lower())
                words_b2 = re.findall(r'\b\w+\b', lines[i+3].lower())

                word_a1 = words_a1[-1] if words_a1 else None
                word_b1 = words_b1[-1] if words_b1 else None
                word_a2 = words_a2[-1] if words_a2 else None
                word_b2 = words_b2[-1] if words_b2 else None

                rhyme_check_failed = False # Flag within stanza check

                # Check A lines (1st and 3rd) using check_rhyme_via_part
                if not check_rhyme_via_part(word_a1, word_a2):
                    msg = f"Stanza {stanza_num}: Line {i+1} ('...{word_a1}') and Line {i+3} ('...{word_a2}') do not rhyme (ABAB)."
                    error_messages.append(msg)
                    detailed_errors.append({
                        "type": "rhyme", "stanza": stanza_num, "scheme": "ABAB",
                        "lines": (i+1, i+3), "words": (word_a1, word_a2), "message": msg
                    })
                    # Add subtype based on why check_rhyme_via_part might fail
                    if not word_a1 or not word_a2:
                        detailed_errors[-1]["subtype"] = "missing_word"
                    elif not pronouncing.phones_for_word(word_a1) or not pronouncing.phones_for_word(word_a2):
                         detailed_errors[-1]["subtype"] = "dict_lookup_failed"
                    rhyme_check_failed = True

                # Check B lines (2nd and 4th) using check_rhyme_via_part
                if not check_rhyme_via_part(word_b1, word_b2):
                    msg = f"Stanza {stanza_num}: Line {i+2} ('...{word_b1}') and Line {i+4} ('...{word_b2}') do not rhyme (ABAB)."
                    error_messages.append(msg)
                    detailed_errors.append({
                        "type": "rhyme", "stanza": stanza_num, "scheme": "ABAB",
                        "lines": (i+2, i+4), "words": (word_b1, word_b2), "message": msg
                    })
                     # Add subtype based on why check_rhyme_via_part might fail
                    if not word_b1 or not word_b2:
                        detailed_errors[-1]["subtype"] = "missing_word"
                    elif not pronouncing.phones_for_word(word_b1) or not pronouncing.phones_for_word(word_b2):
                         detailed_errors[-1]["subtype"] = "dict_lookup_failed"
                    rhyme_check_failed = True

                # If any rhyme check within the stanza failed, mark overall validation as failed
                if rhyme_check_failed:
                    validation_passed = False

            except IndexError: # Handle case where stanza isn't complete (lines missing)
                msg = f"Stanza {stanza_num} appears incomplete. Cannot check rhyme."
                error_messages.append(msg)
                detailed_errors.append({"type": "structure", "stanza": stanza_num, "message": msg})
                validation_passed = False
            except Exception as e: # Catch potential errors from regex/logic
                msg = f"Error checking rhyme in stanza {stanza_num}: {e}"
                logger.error(msg)
                error_messages.append(msg)
                detailed_errors.append({"type": "rhyme_check_error", "stanza": stanza_num, "message": msg})
                validation_passed = False # Fail validation if rhyme check itself errors

    else:
        msg = f"Poem has {num_lines} lines, not divisible by 4. Cannot validate ABAB rhyme scheme per stanza."
        error_messages.append(msg)
        # Don't necessarily fail validation just for this if line count check already failed
        if validation_passed: # Only add if line count check *didn't* already catch it
            detailed_errors.append({"type": "structure", "message": msg})
        logger.warning(msg)

    # --- Construct Output ---
    final_error_message = None
    if not validation_passed:
        final_error_message = "Validation FAILED:\n" + "\n".join([f"- {e}" for e in error_messages])
        logger.warning(final_error_message)
        # Log retry/fail status
        if current_retry < max_retries_allowed:
            logger.warning(f"---VALIDATION FAILED - RETRYING DRAFT ({current_retry}/{max_retries_allowed})---")
        else:
            logger.error(f"---VALIDATION FAILED - MAX RETRIES ({max_retries_allowed}) REACHED - FINISHING WITH ERROR---")
    else:
        logger.info("---VALIDATION PASSED---")

    # Return updated state
    return {
        "validated_poem": draft_poem if validation_passed else None,
        "validation_passed": validation_passed,
        "error_message": final_error_message,
        "validation_errors": detailed_errors,
        # IMPORTANT: Increment retry_count if validation failed
        "retry_count": current_retry + (1 if not validation_passed else 0)
    }

# --- Conditional Edge Logic ---

def should_retry_drafting(state: PoetAgentState) -> str:
    """Determines the next step after validation.
    Returns 'retry' to retry or 'end' if validation passed or max retries reached.
    """
    validation_passed = state["validation_passed"]
    retry_count = state["retry_count"]
    max_retries = state["max_retries"]
    error_message = state.get("error_message", "") # Get error message if present

    if validation_passed:
        logger.info("---VALIDATION PASSED - FINISHING---")
        return "end"
    elif retry_count < max_retries:
        logger.warning(f"---VALIDATION FAILED - RETRYING DRAFT ({retry_count}/{max_retries})---")
        return "retry"
    else:
        logger.error(f"---VALIDATION FAILED - MAX RETRIES ({max_retries}) REACHED - FINISHING WITH ERROR---")
        return "end"

# --- Build the Graph ---

# Initialize the graph
workflow = StateGraph(PoetAgentState)

# Add nodes
workflow.add_node("research_node", research_node)
workflow.add_node("validation_node", validation_node)

# Define edges
workflow.set_entry_point("research_node")
workflow.add_edge("research_node", "validation_node")

# Add conditional edge from validation
workflow.add_conditional_edges(
    "validation_node",
    should_retry_drafting,
    {
        "retry": "research_node",
        "end": END
    }
)

# Compile the graph
poet_agent_graph = workflow.compile()

logger.info("Poet Agent graph compiled successfully.")

# --- Optional: Function to invoke the graph ---
def run_poet_agent(location: str, max_retries: int = 5) -> PoetAgentState:
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
    test_location = "Quirnheim, Deutschland"
    print(f"\nTesting Poet Agent for: {test_location}\n")
    final_state_output = run_poet_agent(test_location)
    print("\n--- Final Output ---")
    if final_state_output.get("validated_poem"):
        print("Generated Poem:")
        print(final_state_output["validated_poem"])
    else:
        print("Failed to generate a valid poem.")
        print(f"Error: {final_state_output.get('error_message', 'Unknown error')}")
    print("--------------------")
