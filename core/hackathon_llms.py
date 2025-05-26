print("DEBUG: hackathon_llms.py: Script execution started.")
import requests
import json
import logging
from typing import Any, List, Optional, Dict

print("DEBUG: hackathon_llms.py: Basic imports done.")

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.llms import LLM
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from pydantic import BaseModel, Field, HttpUrl # HttpUrl might still be in settings.py for type validation

print("DEBUG: hackathon_llms.py: LangChain and Pydantic imports done.")

from config.settings import settings # To get API key and base URL

print("DEBUG: hackathon_llms.py: Imported 'settings' from config.settings.")

logger = logging.getLogger(__name__)
print(f"DEBUG: hackathon_llms.py: Logger '{__name__}' configured.")

class SyngentaHackathonEmbeddings(Embeddings, BaseModel):
    """Custom LangChain Embeddings class for Syngenta Hackathon API."""
    client: Any = None 
    api_key: str = Field(default_factory=lambda: settings.SYNGENTA_HACKATHON_API_KEY)
    base_url: str = Field(default_factory=lambda: str(settings.SYNGENTA_HACKATHON_API_BASE_URL))
    model_id: str = "amazon-embedding-v2" # As per the hackathon doc for embeddings

    def _call_api(self, text: str) -> List[float]:
        payload = {
            "api_key": self.api_key,
            "prompt": text, # The hackathon doc uses "prompt" for text to embed
            "model_id": self.model_id
        }
        headers = {"Content-Type": "application/json"}
        
        logger.debug(f"Calling Syngenta Embedding API. URL: {self.base_url}, Model: {self.model_id}, Text snippet: {text[:50]}...")
        try:
            response = requests.post(self.base_url, headers=headers, data=json.dumps(payload), timeout=300)
            response.raise_for_status()
            result = response.json()

            if "error" in result:
                logger.error(f"Embedding API error: {result['error']}")
                raise ValueError(f"Embedding API error: {result['error']}")
            
            embedding_vector = result.get("response", {}).get("embedding")
            if embedding_vector is None:
                logger.error(f"Embedding vector not found or is null in API response: {result}")
                raise ValueError("Embedding vector not found or is null in API response")
            
            token_count = result.get("response", {}).get("inputTextTokenCount")
            logger.debug(f"Embedding generated. Token count: {token_count}, Dimension: {len(embedding_vector)}")
            return embedding_vector
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for Syngenta Embedding API: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error calling Syngenta Embedding API: {e}")
            raise

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        embeddings_list = []
        for i, text in enumerate(texts):
            logger.debug(f"Embedding document {i+1}/{len(texts)}")
            try:
                embeddings_list.append(self._call_api(text))
            except Exception as e:
                logger.error(f"Failed to embed document chunk {i+1}: {text[:100]}... Error: {e}")
                raise
        return embeddings_list

    def embed_query(self, text: str) -> List[float]:
        logger.debug(f"Embedding query: {text[:100]}...")
        return self._call_api(text)


print("DEBUG: hackathon_llms.py: SyngentaHackathonEmbeddings class defined.")

class SyngentaHackathonLLM(LLM, BaseModel):
    """Custom LangChain LLM class for Syngenta Hackathon API (Claude models)."""
    api_key: str = Field(default_factory=lambda: settings.SYNGENTA_HACKATHON_API_KEY)
    base_url: str = ""  # Will be set in __init__ to a string
    
    # This is the model_id that OUR _call method will use in the payload to the hackathon API
    model_id: str = "claude-3.5-sonnet" 
    temperature: float = 0.7
    max_tokens: int = 1024

    # --- Fields to make LiteLLM (via CrewAI) think this is an OpenAI-compatible custom endpoint ---
    # This 'model_name' will be what LiteLLM receives as the 'model' parameter.
    # Prefixing with "openai/" tells LiteLLM to use its OpenAI client logic,
    # which will then respect the 'api_base' parameter.
    model_name: str = "" # Will be set in __init__
    # This reinforces to LiteLLM that it's an "openai" type of custom provider.
    custom_llm_provider: str = "openai" 

    def __init__(self, **data: Any):
        super().__init__(**data)
        
        self.base_url = str(settings.SYNGENTA_HACKATHON_API_BASE_URL)
        if not isinstance(self.base_url, str):
            logger.critical(f"CRITICAL: self.base_url in SyngentaHackathonLLM is NOT a string after init! Type: {type(self.base_url)}")
            raise TypeError("SyngentaHackathonLLM.base_url must be a string.")

        # Set the model_name that LiteLLM will see.
        # If 'model_name' was explicitly passed during instantiation use that.
        # Otherwise, construct one based on self.model_id (the actual model for our API payload).
        passed_model_name = data.get("model_name") 
        # We use the actual model_id (e.g., "claude-3.5-sonnet") and prefix it with "openai/"
        # The 'openai/' part is the important hint for LiteLLM's provider routing.
        self.model_name = passed_model_name if passed_model_name else f"openai/{self.model_id}"
        
        logger.debug(
            f"SyngentaHackathonLLM initialized. "
            f"LiteLLM effective 'model' (self.model_name): {self.model_name}, "
            f"Custom Provider for LiteLLM (self.custom_llm_provider): {self.custom_llm_provider}, "
            f"API Base for LiteLLM (self.base_url): {self.base_url}, "
            f"Actual model_id for payload (self.model_id): {self.model_id}" # The model_id for our API
        )

    @property
    def _llm_type(self) -> str:
        """Return type of llm for LangChain internal use."""
        return "syngenta_hackathon_custom_claude" # A unique type for LangChain

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None, # Note: Hackathon API doc doesn't show stop sequence support for Claude
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """
        This method makes the ACTUAL HTTP call to the Syngenta Hackathon API endpoint.
        It correctly formats the payload including the api_key in the body.
        """
        
        # The model_id for the payload should be what our custom API expects (e.g., "claude-3.5-sonnet")
        # Allow overriding via kwargs if needed for flexibility during a call.
        payload_model_id = kwargs.get("model_id_override", self.model_id)

        payload = {
            "api_key": self.api_key, # Key in body, as required by hackathon API
            "prompt": prompt,
            "model_id": payload_model_id, 
            "model_params": {
                "max_tokens": kwargs.get("max_tokens", self.max_tokens),
                "temperature": kwargs.get("temperature", self.temperature),
            }
        }
        
        headers = {"Content-Type": "application/json"}
        logger.debug(
            f"Calling Syngenta LLM API (via _call). URL: {self.base_url}, "
            f"Model in PAYLOAD: {payload['model_id']}, Temp: {payload['model_params']['temperature']}, "
            f"MaxTokens: {payload['model_params']['max_tokens']}, Prompt snippet: {prompt[:100]}..."
        )
        
        try:
            response = requests.post(self.base_url, headers=headers, data=json.dumps(payload), timeout=120)
            response.raise_for_status() 
            result = response.json()

            if "error" in result:
                error_message = result['error']
                logger.error(f"LLM API (via _call) error for model {payload['model_id']}: {error_message}")
                return f"Error from API: {error_message}" # Return error string

            content_list = result.get("response", {}).get("content", [])
            if content_list and isinstance(content_list, list) and len(content_list) > 0:
                if content_list[0].get("type") == "text":
                    text_response = content_list[0].get("text", "")
                    logger.debug(f"LLM API (via _call) response text snippet: {text_response[:100]}...")
                    return text_response # Successful response
            
            logger.warning(f"Generated text not found in API response (via _call) for model {payload['model_id']}: {json.dumps(result, indent=2)}")
            return "Error: Could not parse LLM response structure."
        except requests.exceptions.Timeout:
            logger.error(f"Request timed out for Syngenta LLM API (via _call) (model {payload['model_id']}).")
            return "Error: API request timed out."
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for Syngenta LLM API (via _call) (model {payload['model_id']}): {str(e)}")
            return f"Error: API request failed - {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error calling Syngenta LLM API (via _call) (model {payload['model_id']}): {e}", exc_info=True)
            return f"Error: Unexpected issue - {str(e)}"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        """
        Get the identifying parameters for LangChain.
        These are also used by CrewAI's LlmAdapter to construct parameters for LiteLLM.
        """
        return {
            "model": self.model_name,  # This is what LiteLLM sees as 'model' (e.g., "openai/claude-3.5-sonnet")
            "custom_llm_provider": self.custom_llm_provider, # Should be "openai"
            "api_base": self.base_url, # The hackathon API endpoint
            "api_key": self.api_key,   # The hackathon API key (LiteLLM will try to use this for its OpenAI client)
            
            # Parameters specific to our SyngentaHackathonLLM instance, not directly for LiteLLM's call:
            "actual_model_id_for_custom_api": self.model_id, 
            "temperature_custom_api": self.temperature, # Naming to avoid collision if LiteLLM also uses 'temperature'
            "max_tokens_custom_api": self.max_tokens,
        }

print("DEBUG: hackathon_llms.py: SyngentaHackathonLLM class defined.") 




# --- MAIN BLOCK FOR TESTING ---
if __name__ == '__main__':
    print("DEBUG: hackathon_llms.py: SUCCESSFULLY ENTERED __main__ block.")
    # logger is already configured at the module level, using __name__ which becomes '__main__' here.
    logger.info("Logger test from __main__ block: Testing direct LLM and Embedding calls...")

    # NO NEED to call load_dotenv() here again.
    # 'settings' is already imported from config.settings and has loaded .env

    logger.info("--- Testing SyngentaHackathonLLM._call directly ---")
    custom_llm = None # Initialize to None
    try:
        logger.info("Initializing SyngentaHackathonLLM for test...")
        custom_llm = SyngentaHackathonLLM(
            model_id="claude-3.5-sonnet", # Or "claude-3-haiku"
            temperature=0.5,
            max_tokens=150
        )
        logger.info("SyngentaHackathonLLM initialized.")

        prompt_text = "What is the capital of France?"
        logger.info(f"Sending prompt: {prompt_text}")
        response_text = custom_llm._call(prompt=prompt_text) # Direct call
        logger.info(f"LLM direct _call response: {response_text}")
        print(f"\nLLM TEST 1 - Capital of France: {response_text}\n") # Added print for clarity

        prompt_text_2 = "Explain quantum computing in simple terms."
        logger.info(f"Sending prompt: {prompt_text_2}")
        # Test overriding model_id and other params in the _call itself
        response_text_2 = custom_llm._call(
            prompt=prompt_text_2,
            model_id_override="claude-3-haiku", # Using the kwarg we defined in _call
            max_tokens=100, # Overriding max_tokens for this call
            temperature=0.2 # Overriding temperature
        )
        logger.info(f"LLM direct _call response (Haiku): {response_text_2}")
        print(f"\nLLM TEST 2 - Quantum Computing (Haiku): {response_text_2}\n")

    except Exception as e:
        logger.error(f"Error during direct LLM _call test: {e}", exc_info=True)
        print(f"\nLLM TEST FAILED: {e}\n")

    logger.info("--- Testing SyngentaHackathonEmbeddings._call_api directly ---")
    custom_embeddings = None # Initialize
    try:
        logger.info("Initializing SyngentaHackathonEmbeddings for test...")
        custom_embeddings = SyngentaHackathonEmbeddings()
        logger.info("SyngentaHackathonEmbeddings initialized.")

        text_to_embed = "This is a test sentence for embeddings."
        logger.info(f"Embedding text: {text_to_embed}")
        vector = custom_embeddings._call_api(text_to_embed)
        logger.info(f"Embedding vector (first 5 dims): {vector[:5]}, Dimension: {len(vector)}")
        print(f"\nEMBEDDING TEST - Vector (first 5): {vector[:5]}, Dimension: {len(vector)}\n")

    except Exception as e:
        logger.error(f"Error during direct embedding test: {e}", exc_info=True)
        print(f"\nEMBEDDING TEST FAILED: {e}\n")

    logger.info("--- Direct tests in hackathon_llms.py finished ---")

# if __name__ == '__main__':
#     # This ensures .env is loaded if script is run directly
#     import os
#     from dotenv import load_dotenv
#     PROJECT_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#     env_path = os.path.join(PROJECT_BASE_DIR, '.env')
#     if os.path.exists(env_path):
#         logger.info(f"Loading .env file from: {env_path} for hackathon_llms test.")
#         load_dotenv(dotenv_path=env_path)
#     else:
#         logger.warning(f".env file not found at {env_path} for test. Relying on system environment variables.")

#     logger.info("--- Testing SyngentaHackathonLLM._call directly ---")
#     try:
#         custom_llm = SyngentaHackathonLLM(
#             model_id="claude-3.5-sonnet", # Or "claude-3-haiku"
#             temperature=0.5,
#             max_tokens=150
#         )
#         prompt_text = "What is the capital of France?"
#         logger.info(f"Sending prompt: {prompt_text}")
#         response_text = custom_llm._call(prompt=prompt_text) # Direct call
#         logger.info(f"LLM direct _call response: {response_text}")

#         prompt_text_2 = "Explain quantum computing in simple terms."
#         logger.info(f"Sending prompt: {prompt_text_2}")
#         response_text_2 = custom_llm._call(prompt=prompt_text_2, model_id_override="claude-3-haiku", max_tokens=50) # Test override
#         logger.info(f"LLM direct _call response (Haiku): {response_text_2}")

#     except Exception as e:
#         logger.error(f"Error during direct _call test: {e}", exc_info=True)

#     logger.info("--- Testing SyngentaHackathonEmbeddings._call_api directly ---")
#     try:
#         custom_embeddings = SyngentaHackathonEmbeddings()
#         text_to_embed = "This is a test sentence for embeddings."
#         logger.info(f"Embedding text: {text_to_embed}")
#         vector = custom_embeddings._call_api(text_to_embed)
#         logger.info(f"Embedding vector (first 5 dims): {vector[:5]}, Dimension: {len(vector)}")
#     except Exception as e:
#         logger.error(f"Error during direct embedding test: {e}", exc_info=True)