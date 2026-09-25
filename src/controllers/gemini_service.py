import os
import time
import json
import random
import logging
from typing import List, Optional, Any, Callable, Dict
from google import genai
from google.genai import types
from google.genai import errors
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()
parent_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", ".env")
if os.path.exists(parent_env):
    load_dotenv(parent_env)

logger = logging.getLogger("gemini_service")
logging.basicConfig(level=logging.INFO)

# Default fallback models in priority order.
# If a model experiences high demand (503) or rate limits (429), the service cascades to the next.
DEFAULT_FALLBACK_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
]


class ExtractedQuestion(BaseModel):
    question_number: str = Field(description="The number or letter of the question (e.g., '1', 'a', '2.1')")
    question_text: str = Field(description="The exact or faithfully transcribed text of the question")
    question_type: str = Field(description="Type of question: e.g., 'math', 'multiple-choice', 'short-answer', etc.")
    answer: Optional[str] = Field(description="The final answer to the question, if it can be determined")
    steps: List[str] = Field(description="A step-by-step educational explanation on how to solve it")


class DocumentAnalysisResult(BaseModel):
    document_title: str = Field(description="A short descriptive title for the document")
    questions: List[ExtractedQuestion]


def is_high_demand_or_transient_error(exc: Exception) -> bool:
    """
    Detects whether an error is a temporary 503 / Service Unavailable / High Demand spike
    where waiting and retrying is appropriate.
    """
    if isinstance(exc, (errors.ServerError, errors.APIError)):
        code = getattr(exc, 'code', None)
        if code in (408, 500, 502, 503, 504):
            return True
        status = getattr(exc, 'status', None)
        if status in ('UNAVAILABLE', 'DEADLINE_EXCEEDED'):
            return True

    err_str = str(exc).lower()
    high_demand_indicators = [
        "503",
        "service unavailable",
        "high demand",
        "spikes in demand",
        "overloaded",
        "unavailable",
        "deadline exceeded",
        "try again later",
        "temporarily unavailable",
        "connection reset",
        "timed out",
        "timeout",
    ]
    return any(indicator in err_str for indicator in high_demand_indicators)


def is_quota_exhausted_error(exc: Exception) -> bool:
    """
    Detects whether an error is a 429 Resource Exhausted / Rate Limit error
    for a specific model, which should immediately trigger fallback to another model/port
    rather than waiting out a long quota window.
    """
    if isinstance(exc, (errors.ClientError, errors.APIError)):
        code = getattr(exc, 'code', None)
        if code == 429:
            return True
        status = getattr(exc, 'status', None)
        if status == 'RESOURCE_EXHAUSTED':
            return True

    err_str = str(exc).lower()
    quota_indicators = [
        "429",
        "resource has been exhausted",
        "resource_exhausted",
        "quota exceeded",
        "rate limit",
        "free_tier_requests",
    ]
    return any(indicator in err_str for indicator in quota_indicators)


def get_candidate_models() -> List[str]:
    """
    Returns the ordered list of Gemini models to use, starting with the primary model,
    followed by fallback models.
    """
    configured_primary = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
    configured_fallbacks_str = os.getenv("GEMINI_FALLBACK_MODELS", "")

    if configured_fallbacks_str:
        user_fallbacks = [m.strip() for m in configured_fallbacks_str.split(",") if m.strip()]
    else:
        user_fallbacks = DEFAULT_FALLBACK_MODELS

    models = [configured_primary]
    for m in user_fallbacks:
        if m not in models:
            models.append(m)

    return models


def get_client_configs() -> List[Dict[str, Any]]:
    """
    Returns client configurations in priority order:
    1. Primary Gemini client (standard API key, default base_url or GEMINI_PORT/GEMINI_BASE_URL)
    2. Fallback port / URL client (if GEMINI_FALLBACK_PORT or GEMINI_FALLBACK_URL is configured)
    3. Fallback API key client (if GEMINI_FALLBACK_API_KEY is configured and distinct)
    """
    configs = []
    primary_key = os.getenv("GEMINI_API_KEY")
    if not primary_key or primary_key == "your_gemini_api_key_here":
        raise ValueError("GEMINI_API_KEY environment variable is not set correctly.")

    primary_port = os.getenv("GEMINI_PORT")
    primary_base_url = os.getenv("GEMINI_BASE_URL")
    if not primary_base_url and primary_port:
        primary_base_url = f"http://localhost:{primary_port}"

    configs.append({
        "name": f"primary{f' (port {primary_port})' if primary_port else ''}",
        "api_key": primary_key,
        "base_url": primary_base_url,
    })

    # Check for configured fallback port or URL (e.g. secondary proxy or port)
    fallback_port = os.getenv("GEMINI_FALLBACK_PORT")
    fallback_url = os.getenv("GEMINI_FALLBACK_URL") or os.getenv("GEMINI_FALLBACK_BASE_URL")
    fallback_api_key = os.getenv("GEMINI_FALLBACK_API_KEY") or os.getenv("GEMINI_API_KEY_BACKUP") or primary_key

    if fallback_port and not fallback_url:
        fallback_url = f"http://localhost:{fallback_port}"

    if fallback_url:
        configs.append({
            "name": f"fallback_port_or_url ({fallback_url})",
            "api_key": fallback_api_key,
            "base_url": fallback_url,
        })

    # Dedicated fallback API key if specified without custom fallback port
    if fallback_api_key and fallback_api_key != primary_key and not fallback_url:
        configs.append({
            "name": "fallback_api_key",
            "api_key": fallback_api_key,
            "base_url": None,
        })

    return configs


def create_gemini_client(config: Dict[str, Any]) -> genai.Client:
    """Creates a genai.Client with configured http_options and SDK retry parameters."""
    http_opts_kwargs: Dict[str, Any] = {
        "retry_options": types.HttpRetryOptions(
            attempts=int(os.getenv("GEMINI_HTTP_ATTEMPTS", "2")),
            initial_delay=float(os.getenv("GEMINI_INITIAL_DELAY", "1.0")),
            http_status_codes=[502, 503, 504],
        )
    }
    if config.get("base_url"):
        http_opts_kwargs["base_url"] = config["base_url"]

    return genai.Client(
        api_key=config["api_key"],
        http_options=types.HttpOptions(**http_opts_kwargs)
    )


def execute_gemini_call(
    operation: Callable[[genai.Client, str], Any],
    description: str = "Gemini request",
) -> Any:
    """
    Executes a Gemini operation with a comprehensive fallback strategy:
    1. Retries with exponential backoff on 503 ("service unavailable due to high demand").
    2. If retries are exhausted or rate limited (429), cascades immediately to fallback models.
    3. If configured with a fallback port/URL/key, cascades to the alternative port/client.
    """
    client_configs = get_client_configs()
    candidate_models = get_candidate_models()

    max_retries = int(os.getenv("GEMINI_MAX_RETRIES", "3"))
    initial_delay = float(os.getenv("GEMINI_INITIAL_DELAY", "2.0"))
    backoff_factor = float(os.getenv("GEMINI_BACKOFF_FACTOR", "2.0"))
    max_delay = float(os.getenv("GEMINI_MAX_DELAY", "15.0"))

    last_exception = None

    for client_cfg in client_configs:
        try:
            client = create_gemini_client(client_cfg)
        except Exception as e:
            logger.error(f"[Gemini Service] Failed to initialize client '{client_cfg['name']}': {e}")
            last_exception = e
            continue

        for model in candidate_models:
            for attempt in range(max_retries):
                try:
                    logger.info(
                        f"[Gemini Service] Attempting {description} on '{client_cfg['name']}' "
                        f"with model '{model}' (attempt {attempt + 1}/{max_retries})"
                    )
                    result = operation(client, model)
                    logger.info(
                        f"[Gemini Service] SUCCESS for {description} using model '{model}' on '{client_cfg['name']}'"
                    )
                    return result

                except Exception as exc:
                    last_exception = exc
                    err_msg = str(exc)

                    # Check 1: Quota exhausted (429) for this specific model -> cascade immediately to next model/port
                    if is_quota_exhausted_error(exc):
                        logger.warning(
                            f"[Gemini Service] Model '{model}' exceeded quota on '{client_cfg['name']}'. "
                            f"Immediately cascading to next fallback model/port..."
                        )
                        break

                    # Check 2: High demand / 503 / transient server spike -> wait and retry, then cascade
                    if is_high_demand_or_transient_error(exc):
                        if attempt < max_retries - 1:
                            jitter = random.uniform(0.1, 0.5)
                            delay = min(initial_delay * (backoff_factor ** attempt) + jitter, max_delay)
                            logger.warning(
                                f"[Gemini Service] 503 / High Demand detected during {description} on model '{model}'. "
                                f"Waiting {delay:.1f}s before retry {attempt + 2}/{max_retries}... Details: {err_msg[:120]}"
                            )
                            time.sleep(delay)
                            continue
                        else:
                            logger.warning(
                                f"[Gemini Service] Model '{model}' exhausted {max_retries} attempts on '{client_cfg['name']}' "
                                f"due to 503 / High Demand. Passing to next fallback model/port..."
                            )
                            break

                    # Check 3: Model 404 (deprecated / not found) -> cascade to next model
                    if "404" in err_msg or "not_found" in err_msg.lower():
                        logger.warning(
                            f"[Gemini Service] Model '{model}' returned 404 (not found). Falling back to next model..."
                        )
                        break

                    # Non-retryable fatal error (e.g. invalid request structure)
                    logger.error(f"[Gemini Service] Non-retryable error during {description}: {exc}")
                    raise exc

    logger.error(f"[Gemini Service] All models and fallback ports exhausted for {description}.")
    if last_exception:
        raise last_exception
    raise RuntimeError(f"Gemini service failed: no available model or fallback succeeded for {description}.")


def analyze_document_with_gemini(file_path: str, mime_type: str) -> DocumentAnalysisResult:
    """
    Uploads the file to Gemini and extracts questions according to the schema,
    with automatic retry and model/port fallback.
    """
    client_configs = get_client_configs()
    candidate_models = get_candidate_models()

    max_retries = int(os.getenv("GEMINI_MAX_RETRIES", "3"))
    initial_delay = float(os.getenv("GEMINI_INITIAL_DELAY", "2.0"))
    backoff_factor = float(os.getenv("GEMINI_BACKOFF_FACTOR", "2.0"))
    max_delay = float(os.getenv("GEMINI_MAX_DELAY", "15.0"))

    prompt = """You are an educational question-paper analysis assistant.
Analyze the uploaded document carefully.
Your first task is to identify every individual question in the document.
Do not merge separate questions. Use numbering, lettering, spacing, visual grouping, page layout, indentation, and semantic context to determine question boundaries.
For example, '1 + 1 =' and '2 + 2 =' must become two separate questions.
Preserve subquestions as children of their parent question when appropriate, or label them clearly like '1a'.

For each question, extract the question number, exact text, question type, the final answer (if solvable), and a step-by-step educational explanation of how to solve it.
Do not skip questions. If the document is unclear, state what is unclear rather than inventing missing content.
"""

    last_exception = None

    for client_cfg in client_configs:
        try:
            client = create_gemini_client(client_cfg)
        except Exception as e:
            logger.error(f"[Gemini Service] Failed to create client '{client_cfg['name']}': {e}")
            last_exception = e
            continue

        uploaded_file = None
        try:
            logger.info(f"[Gemini Service] Uploading file '{file_path}' to Gemini on client '{client_cfg['name']}'...")
            uploaded_file = client.files.upload(file=file_path, config={'mime_type': mime_type})
            logger.info(f"[Gemini Service] File uploaded successfully as '{uploaded_file.name}'")

            for model in candidate_models:
                for attempt in range(max_retries):
                    try:
                        logger.info(
                            f"[Gemini Service] Analyzing document with model '{model}' on '{client_cfg['name']}' "
                            f"(attempt {attempt + 1}/{max_retries})..."
                        )
                        response = client.models.generate_content(
                            model=model,
                            contents=[uploaded_file, prompt],
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                                response_schema=DocumentAnalysisResult,
                                temperature=0.2,
                            ),
                        )
                        result = DocumentAnalysisResult.model_validate_json(response.text)
                        logger.info(
                            f"[Gemini Service] Successfully analyzed document with model '{model}' "
                            f"on '{client_cfg['name']}' ({len(result.questions)} questions detected)"
                        )
                        return result

                    except Exception as exc:
                        last_exception = exc
                        err_str = str(exc)

                        if is_quota_exhausted_error(exc):
                            logger.warning(
                                f"[Gemini Service] Model '{model}' exceeded quota during document analysis. "
                                f"Immediately cascading to next fallback model/port..."
                            )
                            break

                        if is_high_demand_or_transient_error(exc):
                            if attempt < max_retries - 1:
                                jitter = random.uniform(0.1, 0.5)
                                delay = min(initial_delay * (backoff_factor ** attempt) + jitter, max_delay)
                                logger.warning(
                                    f"[Gemini Service] 503 / High Demand on model '{model}' during document analysis. "
                                    f"Waiting {delay:.1f}s before retry {attempt + 2}/{max_retries}... Error: {err_str[:120]}"
                                )
                                time.sleep(delay)
                                continue
                            else:
                                logger.warning(
                                    f"[Gemini Service] Model '{model}' exhausted {max_retries} attempts due to high demand. "
                                    f"Passing to next fallback model or port..."
                                )
                                break

                        if "404" in err_str or "not_found" in err_str.lower():
                            logger.warning(
                                f"[Gemini Service] Model '{model}' returned 404 (not found). Falling back to next model..."
                            )
                            break

                        logger.error(f"[Gemini Service] Non-retryable error during document analysis: {exc}")
                        raise exc

        finally:
            if uploaded_file and client:
                try:
                    client.files.delete(name=uploaded_file.name)
                    logger.info(f"[Gemini Service] Cleaned up temporary Gemini file '{uploaded_file.name}'")
                except Exception as del_err:
                    logger.warning(f"[Gemini Service] Failed to delete temporary file '{uploaded_file.name}': {del_err}")

    if last_exception:
        raise last_exception
    raise RuntimeError("Gemini document analysis failed: all retry attempts and fallback models/ports were exhausted.")


def chat_with_gemini_service(context_prompt: str) -> str:
    """Executes a chat completion with Gemini, with automatic retry and model/port fallback."""
    def op(client: genai.Client, model: str) -> str:
        response = client.models.generate_content(
            model=model,
            contents=context_prompt
        )
        return response.text

    return execute_gemini_call(op, description="Chat completion")


def generate_practice_with_gemini(context_data: str, num_questions: int, difficulty: str) -> list:
    """Generates practice questions based on document context, with automatic retry and model/port fallback."""
    prompt = f"""You are an educational tutor. Based on the following example questions and solutions from a student's document, generate {num_questions} NEW, ORIGINAL practice questions of '{difficulty}' difficulty that test similar concepts. 
Context from original document:
{context_data}

Return ONLY a JSON array of objects. Each object should have:
- "question_text" (string)
- "answer" (string)
- "solution" (string, step-by-step)
- "question_type" (string)
"""

    def op(client: genai.Client, model: str) -> list:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.7,
            )
        )
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())

    return execute_gemini_call(op, description="Practice questions generation")
