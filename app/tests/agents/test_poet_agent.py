# # app/tests/agents/test_poet_agent.py
# import pytest
# from unittest.mock import patch, MagicMock, ANY, call

# # Import the function to test and the state definition
# from app.agents.poet_agent import run_poet_agent, PoetAgentState, SUPPORTED_RHYME_LANGUAGES

# # --- Mock Data ---
# MOCK_ENGLISH_KEYWORDS = ["Big Ben", "Tea", "Rain", "Tube", "Palace"]
# MOCK_VALID_ENGLISH_POEM = """London town, a foggy day,
# Big Ben tolls the time away,
# Red buses splash along the street,
# A royal guard, can't be beat.
# In pubs they gather, warm inside,
# With pints of ale, nowhere hide,
# Fish and chips, a tasty treat,
# London's charm just can't fleet.
# """
# MOCK_GERMAN_KEYWORDS = ["Brandenburg Gate", "Beer", "Currywurst", "Techno", "Ampelmann"]
# MOCK_VALID_GERMAN_POEM = """Berlin, die Stadt, so grau,
# Das Tor steht stolz zur Schau,
# Currywurst auf die Hand, schnell,
# Im Berghain tanzt man hell.
# Die Spree fliesst ruhig hin,
# Ein Bär hat hier Gewinn,
# Ampelmännchen, grün und rot,
# Die Mauer fiel, kein Tod.
# """
# MOCK_LONG_LINE_POEM = MOCK_VALID_ENGLISH_POEM.replace("London's charm just can't fleet.", "London's undeniable historical charm just can't possibly ever fleet away.")
# MOCK_BAD_RHYME_POEM = MOCK_VALID_ENGLISH_POEM.replace("fleet.", "done.") # AABB rhyme

# EXPECTED_RHYME_PATTERN = [1, 2, 1, 2, 3, 4, 3, 4]
# BAD_RHYME_PATTERN = [1, 1, 2, 2, 3, 3, 4, 4] # Example incorrect pattern

# # --- Helper for Mocking ---
# def create_mock_chat_ollama():
#     mock_llm = MagicMock()
#     # Use side_effect to allow different returns based on input later if needed
#     mock_llm.invoke.return_value = "Default mock LLM response"
#     return mock_llm

# def create_mock_rhyme_tagger():
#     mock_rt = MagicMock()
#     mock_rt.tag.return_value = EXPECTED_RHYME_PATTERN
#     # Simulate successful model loading by default
#     mock_rt.load_model.return_value = None
#     return mock_rt

# # --- Test Cases ---

# @pytest.fixture(autouse=True)
# def mock_dependencies():
#     mock_research_llm = MagicMock(name="MockResearchLLM")
#     mock_drafting_llm = MagicMock(name="MockDraftingLLM")
#     mock_rt_instance = create_mock_rhyme_tagger()

#     def ollama_side_effect(*args, **kwargs):
#         model_name = kwargs.get('model', '')
#         if 'perplexity' in model_name or 'sonar' in model_name:
#              return mock_research_llm
#         else:
#              return mock_drafting_llm

#     with patch('app.agents.poet_agent.ChatOllama', side_effect=ollama_side_effect) as mock_chat_ollama_class, \
#          patch('app.agents.poet_agent.RhymeTagger', return_value=mock_rt_instance) as mock_rt_class, \
#          patch('app.agents.poet_agent.rt', new=mock_rt_instance) as mock_rt_module_instance:
#         yield {
#             "ResearchLLM": mock_research_llm,
#             "DraftingLLM": mock_drafting_llm,
#             "RTModuleInstance": mock_rt_module_instance
#         }

# # --- Test Cases (adjust mock configuration) ---

# def test_poet_agent_success_english(mock_dependencies):
#     location = "London, United Kingdom"
#     max_retries = 3
#     # Configure the return value of the invoke *method*
#     mock_dependencies["ResearchLLM"].invoke.return_value = ", ".join(MOCK_ENGLISH_KEYWORDS)
#     mock_dependencies["DraftingLLM"].invoke.return_value = MOCK_VALID_ENGLISH_POEM
#     mock_dependencies["RTModuleInstance"].tag.return_value = EXPECTED_RHYME_PATTERN
#     # Reset mocks
#     mock_dependencies["ResearchLLM"].invoke.reset_mock()
#     mock_dependencies["DraftingLLM"].invoke.reset_mock()
#     mock_dependencies["RTModuleInstance"].tag.reset_mock()
#     mock_dependencies["RTModuleInstance"].load_model.reset_mock()

#     final_state = run_poet_agent(location=location, max_retries=max_retries)

#     assert final_state["validation_passed"] is True
#     assert final_state["validated_poem"] == MOCK_VALID_ENGLISH_POEM
#     assert final_state["language_code"] == "en"
#     assert final_state["language_name"] == "English"
#     assert final_state["error_message"] is None
#     assert final_state["retry_count"] == 1 # Should succeed on first try
#     mock_dependencies["ResearchLLM"].invoke.assert_called_once()
#     mock_dependencies["DraftingLLM"].invoke.assert_called_once()
#     mock_dependencies["RTModuleInstance"].tag.assert_called_once()
#     mock_dependencies["RTModuleInstance"].load_model.assert_called_once_with('en')


# def test_poet_agent_success_german(mock_dependencies):
#     location = "Berlin, Germany"
#     max_retries = 3
#     # Configure mocks
#     mock_dependencies["ResearchLLM"].invoke.return_value = ", ".join(MOCK_GERMAN_KEYWORDS)
#     mock_dependencies["DraftingLLM"].invoke.return_value = MOCK_VALID_GERMAN_POEM
#     mock_dependencies["RTModuleInstance"].tag.return_value = EXPECTED_RHYME_PATTERN
#     # Reset
#     mock_dependencies["ResearchLLM"].invoke.reset_mock()
#     mock_dependencies["DraftingLLM"].invoke.reset_mock()
#     mock_dependencies["RTModuleInstance"].tag.reset_mock()
#     mock_dependencies["RTModuleInstance"].load_model.reset_mock()

#     final_state = run_poet_agent(location=location, max_retries=max_retries)

#     assert final_state["validation_passed"] is True
#     assert final_state["validated_poem"] == MOCK_VALID_GERMAN_POEM
#     assert final_state["language_code"] == "de"
#     assert final_state["language_name"] == "German"
#     assert final_state["error_message"] is None
#     assert final_state["retry_count"] == 1
#     mock_dependencies["ResearchLLM"].invoke.assert_called_once()
#     mock_dependencies["DraftingLLM"].invoke.assert_called_once()
#     mock_dependencies["RTModuleInstance"].tag.assert_called_once()
#     mock_dependencies["RTModuleInstance"].load_model.assert_called_once_with('de')


# def test_poet_agent_failure_line_length(mock_dependencies):
#     location = "London, UK"
#     max_retries = 2
#     # Configure mocks
#     mock_dependencies["ResearchLLM"].invoke.return_value = ", ".join(MOCK_ENGLISH_KEYWORDS)
#     mock_dependencies["DraftingLLM"].invoke.return_value = MOCK_LONG_LINE_POEM
#     mock_dependencies["RTModuleInstance"].tag.return_value = EXPECTED_RHYME_PATTERN
#     # Reset
#     mock_dependencies["ResearchLLM"].invoke.reset_mock()
#     mock_dependencies["DraftingLLM"].invoke.reset_mock()
#     mock_dependencies["RTModuleInstance"].tag.reset_mock()
#     mock_dependencies["RTModuleInstance"].load_model.reset_mock()

#     final_state = run_poet_agent(location=location, max_retries=max_retries)

#     assert final_state["validation_passed"] is False
#     assert final_state["validated_poem"] is None
#     assert final_state["error_message"] is not None
#     assert "exceeds 30 characters" in final_state["error_message"]
#     assert final_state["retry_count"] == max_retries
#     mock_dependencies["ResearchLLM"].invoke.assert_called_once()
#     assert mock_dependencies["DraftingLLM"].invoke.call_count == max_retries


# def test_poet_agent_failure_rhyme(mock_dependencies):
#     location = "Paris, France"
#     max_retries = 2
#     # Configure mocks
#     mock_dependencies["ResearchLLM"].invoke.return_value = "french,keywords"
#     mock_dependencies["DraftingLLM"].invoke.return_value = MOCK_BAD_RHYME_POEM
#     mock_dependencies["RTModuleInstance"].tag.return_value = BAD_RHYME_PATTERN
#     # Reset
#     mock_dependencies["ResearchLLM"].invoke.reset_mock()
#     mock_dependencies["DraftingLLM"].invoke.reset_mock()
#     mock_dependencies["RTModuleInstance"].tag.reset_mock()
#     mock_dependencies["RTModuleInstance"].load_model.reset_mock()

#     final_state = run_poet_agent(location=location, max_retries=max_retries)

#     assert final_state["validation_passed"] is False
#     assert final_state["validated_poem"] is None
#     assert final_state["error_message"] is not None
#     assert "Rhyme check FAILED" in final_state["error_message"]
#     assert final_state["language_code"] == "fr" # Check language detection
#     assert final_state["retry_count"] == max_retries
#     mock_dependencies["ResearchLLM"].invoke.assert_called_once()
#     assert mock_dependencies["DraftingLLM"].invoke.call_count == max_retries
#     mock_dependencies["RTModuleInstance"].load_model.assert_called_once_with('fr')


# def test_poet_agent_retry_success(mock_dependencies):
#     location = "Rome, Italy"
#     max_retries = 3
#     # Configure mocks
#     mock_dependencies["ResearchLLM"].invoke.return_value = "roman,keywords"
#     # Set side effect directly on the invoke method
#     mock_dependencies["DraftingLLM"].invoke.side_effect = [
#         MOCK_LONG_LINE_POEM,
#         MOCK_VALID_ENGLISH_POEM
#     ]
#     mock_dependencies["RTModuleInstance"].tag.return_value = EXPECTED_RHYME_PATTERN
#     # Reset
#     mock_dependencies["ResearchLLM"].invoke.reset_mock()
#     mock_dependencies["DraftingLLM"].invoke.reset_mock()
#     # Re-apply side effect after reset
#     mock_dependencies["DraftingLLM"].invoke.side_effect = [
#         MOCK_LONG_LINE_POEM,
#         MOCK_VALID_ENGLISH_POEM
#     ]
#     mock_dependencies["RTModuleInstance"].tag.reset_mock()
#     mock_dependencies["RTModuleInstance"].load_model.reset_mock()

#     final_state = run_poet_agent(location=location, max_retries=max_retries)

#     assert final_state["validation_passed"] is True
#     assert final_state["validated_poem"] == MOCK_VALID_ENGLISH_POEM
#     assert final_state["language_code"] == "en" # Defaulted to English
#     assert final_state["error_message"] is None
#     assert final_state["retry_count"] == 2 # Succeeded on the 2nd attempt (count is 1-based for *next* attempt)
#     mock_dependencies["ResearchLLM"].invoke.assert_called_once()
#     assert mock_dependencies["DraftingLLM"].invoke.call_count == 2 # Called twice
#     mock_dependencies["RTModuleInstance"].load_model.assert_called_once_with('en')


# def test_poet_agent_unsupported_language_rhyme_skip(mock_dependencies):
#     location = "Tokyo, Japan"
#     max_retries = 1
#     # Configure mocks
#     mock_dependencies["ResearchLLM"].invoke.return_value = "japanese,keywords"
#     mock_dependencies["DraftingLLM"].invoke.return_value = MOCK_VALID_ENGLISH_POEM
#     # Reset
#     mock_dependencies["ResearchLLM"].invoke.reset_mock()
#     mock_dependencies["DraftingLLM"].invoke.reset_mock()
#     mock_dependencies["RTModuleInstance"].tag.reset_mock()
#     mock_dependencies["RTModuleInstance"].load_model.reset_mock()

#     final_state = run_poet_agent(location=location, max_retries=max_retries)

#     assert final_state["validation_passed"] is True
#     assert final_state["validated_poem"] == MOCK_VALID_ENGLISH_POEM
#     assert final_state["language_code"] == "en" # Defaulted to English
#     assert final_state["error_message"] is None # No validation errors
#     mock_dependencies["RTModuleInstance"].tag.assert_not_called() # Rhyme check skipped
#     mock_dependencies["RTModuleInstance"].load_model.assert_called_once_with('en') # Attempted default


# def test_poet_agent_rhyme_model_load_failure(mock_dependencies):
#     location = "Berlin, Germany"
#     max_retries = 1
#     mock_dependencies["RTModuleInstance"].load_model.side_effect = Exception("Model load failed")
#     # Reset
#     mock_dependencies["ResearchLLM"].invoke.reset_mock()
#     mock_dependencies["DraftingLLM"].invoke.reset_mock()
#     mock_dependencies["RTModuleInstance"].tag.reset_mock()
#     mock_dependencies["RTModuleInstance"].load_model.reset_mock()
#     mock_dependencies["RTModuleInstance"].load_model.side_effect = Exception("Model load failed") # Re-apply

#     final_state = run_poet_agent(location=location, max_retries=max_retries)

#     assert final_state["validation_passed"] is False
#     assert final_state["validated_poem"] is None
#     assert final_state["rhyme_model_ready"] is False
#     assert "Failed to load RhymeTagger model" in final_state["error_message"]
#     mock_dependencies["RTModuleInstance"].load_model.assert_called_once_with('de')
#     mock_dependencies["DraftingLLM"].invoke.assert_not_called()