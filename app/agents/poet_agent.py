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

try:
    llm = ChatOllama(model="anthropic/claude-3.5-sonnet", base_url=ollama_base_url)
    # Test connection/model availability (optional but good practice)
    # llm.invoke("Ping")
    logger.info(f"ChatOllama initialized with model '{llm.model}' and base URL: {ollama_base_url}")
except Exception as e:
    logger.error(f"Failed to initialize ChatOllama: {e}. Ensure Ollama is running and the model is available.")
    # Consider how to handle this - maybe raise an error or have a fallback?
    llm = None # Set llm to None or raise an exception if initialization fails

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

    Uses ChatOllama with the 'perplexity/llama-3.1-sonar-small-128k-online' model
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
            model="perplexity/llama-3.1-sonar-large-128k-online",
            base_url=ollama_base_url, # Use the same base URL
            temperature=0.1 # Low temperature for factual extraction
        )

        # Define the prompt for the research model
        # Instructs it to browse and extract specific types of keywords
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", "You are an expert researcher tasked with finding specific, distinctive keywords about a location using your web browsing capabilities. Focus on local food specialities, unique local drinks or beverages, famous or characteristic landmarks/natural features, and notable cultural elements (like specific festivals, traditions, or famous local figures/art). Exclude generic terms. Search in the language of the location. Return ONLY the keywords, as a comma-separated list of 10-15. Example answer: keyword1, keyword2, keyword3"),
            ("user", "Find keywords for the location: {location}.")
        ])

        # Simple chain: prompt -> LLM -> string output
        chain = prompt_template | research_llm | StrOutputParser()

        logger.info(f'Querying Ollama model perplexity/llama-3.1-sonar-small-128k-online for: "{location}"')
        raw_keywords_string = chain.invoke({"location": location})
        print("raw_keywords_string:", raw_keywords_string)

        # --- Improved Parsing Logic --- 
        if raw_keywords_string:
            extracted_keywords = set()
            
            # 1. Try finding markdown list items
            markdown_list_items = re.findall(r'^\s*[-*+]\s+(.*)', raw_keywords_string, re.MULTILINE)
            for item in markdown_list_items:
                clean_item = item.strip().lower()
                if len(clean_item) > 2: # Basic length filter
                    extracted_keywords.add(clean_item)
            
            # 2. Split by common delimiters and clean
            potential_keywords = re.split(r'[\n,]+', raw_keywords_string)
            for kw in potential_keywords:
                # Strip punctuation first (like .) before cleaning/checking length
                clean_kw = re.sub(r'[.!?]$', '', kw).strip().lower()
                # Remove potential leading list markers if missed by regex
                clean_kw = re.sub(r'^\s*[-*+]\s*', '', clean_kw)
                
                # Define location parts for broader filtering
                location_parts = [part.strip().lower() for part in location.split(',')]
                
                # Filter out generic phrases, short words, broad locations, etc.
                generic_phrases_to_exclude = [
                    'keywords:', 'here is a list', 'based on', 'distinctive to',
                    'local food', 'unique drinks', 'famous landmarks',
                    'cultural elements', 'cultural festivals', 'notable landmarks',
                    'feelgood restaurant', 'variety of'
                ]
                if (len(clean_kw) > 3 and 
                    len(clean_kw) < 50 and # Avoid overly long strings
                    clean_kw not in location_parts and # Exclude parts of the input location string
                    not any(phrase in clean_kw for phrase in generic_phrases_to_exclude)
                    and clean_kw not in ['and', 'or', 'the', 'for']): 
                    extracted_keywords.add(clean_kw)

            keywords_to_update = sorted(list(extracted_keywords))[:15] # Limit final list
            logger.info(f"Extracted keywords (Ollama Online): {keywords_to_update}")
        else:
            logger.warning(f"Ollama online model returned an empty response for {location}.")
        # --- End of Improved Parsing --- 

    except Exception as e:
        logger.error(f"Error during Ollama online research for {location}: {e}", exc_info=True)
        error_msg = f"Online research failed: {e}"
        keywords_to_update = []

    return {"keywords": keywords_to_update, "error_message": error_msg}

# --- Drafting Node ---

def drafting_node(state: PoetAgentState) -> dict:
    """
    Generates a draft poem using ChatOllama based on location and keywords.
    """
    location = state["location"]
    keywords = state.get("keywords", []) # Use .get for safety
    retry_count = state["retry_count"]
    max_retries = state["max_retries"]
    logger.info(f"---DRAFTING POEM (Attempt {retry_count + 1}/{max_retries}) FOR: {location}---")

    keywords_str = ", ".join(keywords) if keywords else "no specific keywords provided"

    # --- >>> NEW: Get detailed validation errors from previous step <<< ---
    validation_errors = state.get("validation_errors")
    logger.info(f"---DRAFTING POEM (Attempt {retry_count + 1}/{max_retries}) FOR: {location}---")

    # --- >>> NEW: Construct retry instruction based on specific errors <<< ---
    retry_instruction = "" # Default: no retry instruction needed for first attempt
    if retry_count > 0 and validation_errors: # Check retry_count too
        error_details = []
        # Prioritize line length errors
        length_errors = [e for e in validation_errors if e.get("type") == "line_length"]
        if length_errors:
            error_details.append("Your previous attempt had lines that were too long:")
            for err in length_errors[:3]: # Limit feedback
                error_details.append(
                    f"  - Line {err.get('line_number', '?')} was {err.get('actual', '?')} chars (max 30): \"{err.get('content', '')[:40]}...\""
                )
            error_details.append("Please rewrite these lines to be 30 characters or less.")

        # Add rhyme errors if present and limited/no length errors
        rhyme_errors = [e for e in validation_errors if e.get("type") == "rhyme"]
        if rhyme_errors and len(length_errors) < 2:
             error_details.append("Also, some lines failed the ABAB rhyme scheme:")
             for err in rhyme_errors[:2]: # Limit feedback
                 lines = err.get('lines', ('?', '?'))
                 words = err.get('words', ('?', '?'))
                 error_details.append(
                     f"  - Stanza {err.get('stanza', '?')}: Line {lines[0]} ('...{words[0]}') and Line {lines[1]} ('...{words[1]}') didn't rhyme well."
                 )

        # Add structure errors
        structure_errors = [e for e in validation_errors if e.get("type") in ["line_count", "structure"]]
        if structure_errors:
             # Combine message for brevity
             error_details.append("The overall structure (expected 8 lines in 2 stanzas) was also incorrect.")

        if error_details:
             retry_instruction = "\n**Feedback on Previous Attempt:**\n" + "\n".join(error_details) + "\nPlease correct these specific issues while following all original constraints."
        else: # Fallback if errors exist but aren't parsed correctly
            retry_instruction = "\n**Feedback on Previous Attempt:** The previous attempt failed validation. Please review all constraints carefully, especially the 30-character line limit and ABAB rhyme."
    elif retry_count > 0:
        # Fallback if validation_errors field was missing for some reason on a retry
        retry_instruction = "\n**Feedback on Previous Attempt:** The previous attempt failed validation. Please review all constraints carefully, especially the 30-character line limit and ABAB rhyme."


    # Construct the prompt dynamically
    # Base prompt emphasizing constraints
    prompt_template_str = """
Generate a humorous, 2-stanza poem about {location}.

**Follow these steps carefully:**
1.  **Draft Initial Poem:** Write 2 stanzas (4 lines each, 8 total) with an ABAB rhyme scheme, trying to use these keywords: {keywords_str}.
2.  **Self-Correction (CRITICAL):** Review EACH line of your draft internally.
    *   **CHECK LINE LENGTH:** Ensure EVERY line is **30 characters or less**. This is the **MOST IMPORTANT** rule.
    *   **REWRITE IF NEEDED:** If any line exceeds 30 characters, REWRITE IT to be 30 characters or less while preserving meaning and rhyme if possible. Repeat until all lines conform.
    *   **CHECK RHYME/STANZAS:** Briefly confirm ABAB rhyme and 2 stanzas of 4 lines remain.
3.  **Final Output:** Provide ONLY the corrected poem text.

**Constraints Summary (Apply during Self-Correction):**
*   **MAXIMUM LINE LENGTH: 30 CHARACTERS. NO EXCEPTIONS.**
*   Exactly 2 stanzas, 4 lines each (8 lines total).
*   ABAB rhyme scheme per stanza.

**Example ABAB structure (lines ≤ 30 chars):**
A: The stars align above (16 chars)
B: Their light cuts like knives (17 chars)
A: A dance of cosmic love (17 chars)
B: It writes our fleeting lives (18 chars)

{retry_instruction} # Note: This placeholder gets filled dynamically now

**IMPORTANT:** Output ONLY the final, corrected poem text, line by line. Do NOT include your internal thought process, "A:", "B:", character counts, or any other conversational text or explanations.
"""

    prompt = ChatPromptTemplate.from_template(prompt_template_str)
    output_parser = StrOutputParser()

    # Create the generation chain
    chain = prompt | llm | output_parser

    draft_poem = None
    error_msg = None
    try:
        logger.info(f"Generating draft with keywords: {keywords_str}")
        # Add prompt details to log for easier debugging
        logger.debug(f"Prompt passed to LLM:\n{prompt.format(location=location, keywords_str=keywords_str, retry_instruction=retry_instruction)}")
        draft_poem = chain.invoke({
            "location": location,
            "keywords_str": keywords_str,
            "retry_instruction": retry_instruction
        })
        # Basic cleanup: remove leading/trailing whitespace
        draft_poem = draft_poem.strip() if draft_poem else None
        logger.info(f"Draft poem generated:\n---\n{draft_poem}\n---")

        print(f"\n--- Attempt {state['retry_count'] + 1} Draft ---")
        print(draft_poem if draft_poem else "No poem generated.")
        print("----------------------\n")

    except Exception as e:
        logger.error(f"Error during poem drafting for {location}: {e}")
        error_msg = f"Drafting failed: {e}"
        print(f"\n--- Attempt {state['retry_count'] + 1} FAILED ---")
        print(f"Error: {e}")
        print("------------------------\n")

    # Return the partial state update, incrementing retry_count
    return {
        "draft_poem": draft_poem,
        "error_message": error_msg,
        "retry_count": retry_count + 1,
        "validation_passed": False # Reset validation status for the new draft
    }

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
    """
    draft_poem = state.get("draft_poem")
    retry_count = state["retry_count"]
    max_retries = state["max_retries"]
    location = state["location"]
    logger.info(f"---VALIDATING POEM (Attempt {retry_count}/{max_retries}) FOR: {location}---")
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
        if state['retry_count'] < state['max_retries']:
            logger.warning(f"---VALIDATION FAILED - RETRYING DRAFT ({state['retry_count']}/{state['max_retries']})---")
        else:
            logger.error(f"---VALIDATION FAILED - MAX RETRIES ({state['retry_count']}) REACHED - FINISHING WITH ERROR---")
    else:
        logger.info("---VALIDATION PASSED---")

    return {
        "validation_passed": validation_passed,
        "error_message": final_error_message,
        "validated_poem": draft_poem if validation_passed else None,
        "validation_errors": detailed_errors if not validation_passed else None
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
