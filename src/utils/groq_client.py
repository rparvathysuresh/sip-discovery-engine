"""
Groq API client wrapper for the SIP Discovery Engine.

Provides:
- Initialization with API key from env
- Chat completion with retry and rate-limit handling
- JSON extraction mode
- Token usage tracking
- Fallback model support
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

from groq import AuthenticationError, Groq, RateLimitError, APIError
from dotenv import load_dotenv

from src.utils.logging import get_logger

# Ensure environment variables are loaded
load_dotenv()

logger = get_logger(__name__)


class GroqClientError(Exception):
    """Raised when the Groq client encounters an unrecoverable error."""
    pass


class GroqClient:
    """
    Wrapper around the Groq SDK with retry logic, rate limiting,
    and token usage tracking.
    """

    # Default models (configurable via extraction.yaml)
    DEFAULT_PRIMARY_MODEL = "openai/gpt-oss-120b"
    DEFAULT_FALLBACK_MODEL = "openai/gpt-oss-20b"

    def __init__(
        self,
        api_key: Optional[str] = None,
        primary_model: Optional[str] = None,
        fallback_model: Optional[str] = None,
        max_retries: int = 3,
        base_retry_delay: float = 1.0,
    ):
        """
        Initialize the Groq client.
        
        Args:
            api_key: Groq API key. Defaults to GROQ_API_KEY env var.
            primary_model: Primary model ID. Defaults to llama-3.3-70b-versatile.
            fallback_model: Fallback model ID. Defaults to mixtral-8x7b-32768.
            max_retries: Maximum number of retry attempts per request.
            base_retry_delay: Base delay in seconds for exponential backoff.
        
        Raises:
            GroqClientError: If no API key is provided or found in environment.
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise GroqClientError(
                "Groq API key not provided. Set GROQ_API_KEY in your .env file "
                "or pass it directly to GroqClient()."
            )
        
        self.primary_model = primary_model or self.DEFAULT_PRIMARY_MODEL
        self.fallback_model = fallback_model or self.DEFAULT_FALLBACK_MODEL
        self.max_retries = max_retries
        self.base_retry_delay = base_retry_delay
        
        # Token usage tracking
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_requests = 0
        self.failed_requests = 0
        
        # Initialize the Groq SDK client
        self.client = Groq(api_key=self.api_key)
        
        logger.info(
            "GroqClient initialized | primary_model=%s | fallback_model=%s",
            self.primary_model, self.fallback_model
        )

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        response_format: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Send a chat completion request to Groq with retry and fallback.
        
        Args:
            messages: List of message dicts [{"role": "system", "content": "..."}, ...]
            model: Model to use. Defaults to primary_model.
            temperature: Sampling temperature (0.0–2.0). Default 0.1 for determinism.
            max_tokens: Maximum tokens in the response.
            response_format: Optional response format (e.g. {"type": "json_object"}).
        
        Returns:
            Dict with:
                - "content": The response text
                - "model": Model that was actually used
                - "usage": {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
        
        Raises:
            GroqClientError: If all retries and fallback are exhausted.
        """
        model = model or self.primary_model
        last_error: Optional[Exception] = None
        
        # Try primary model with retries
        for attempt in range(self.max_retries):
            try:
                return self._make_request(
                    messages, model, temperature, max_tokens, response_format
                )
            except RateLimitError as e:
                delay = self.base_retry_delay * (2 ** attempt)
                logger.warning(
                    "Rate limited (attempt %d/%d). Waiting %.1fs before retry. Error: %s",
                    attempt + 1, self.max_retries, delay, str(e)
                )
                time.sleep(delay)
                last_error = e
            except APIError as e:
                # Fast fail if sandbox policy blocks network access to avoid delaying offline fallback
                if "not allowed by policy" in str(e).lower() or "policy" in str(e).lower():
                    logger.warning("Network policy blocked outbound API call: %s", e)
                    raise GroqClientError(f"Network policy blocked API call: {e}")

                # Model not found or server error — try fallback
                if "model" in str(e).lower() and "not found" in str(e).lower():
                    logger.warning(
                        "Model '%s' not found. Switching to fallback '%s'.",
                        model, self.fallback_model
                    )
                    model = self.fallback_model
                    last_error = e
                    continue
                
                delay = self.base_retry_delay * (2 ** attempt)
                logger.warning(
                    "API error (attempt %d/%d). Waiting %.1fs. Error: %s",
                    attempt + 1, self.max_retries, delay, str(e)
                )
                time.sleep(delay)
                last_error = e
        
        # Try fallback model as last resort (if not already trying it)
        if model != self.fallback_model:
            logger.warning(
                "Primary model '%s' failed after %d attempts. Trying fallback '%s'.",
                self.primary_model, self.max_retries, self.fallback_model
            )
            try:
                return self._make_request(
                    messages, self.fallback_model, temperature, max_tokens, response_format
                )
            except Exception as e:
                last_error = e
        
        self.failed_requests += 1
        raise GroqClientError(
            f"All retry attempts exhausted for Groq API. Last error: {last_error}"
        )

    def _make_request(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        response_format: Optional[dict],
    ) -> dict[str, Any]:
        """Make a single API request to Groq."""
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            if isinstance(response_format, str):
                kwargs["response_format"] = {"type": response_format}
            else:
                kwargs["response_format"] = response_format
        
        response = self.client.chat.completions.create(**kwargs)
        
        # Track usage
        usage = response.usage
        if usage:
            self.total_prompt_tokens += usage.prompt_tokens
            self.total_completion_tokens += usage.completion_tokens
        self.total_requests += 1
        
        content = response.choices[0].message.content or ""
        
        return {
            "content": content,
            "model": model,
            "usage": {
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
            },
        }

    def extract_json(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """
        Send a chat completion request expecting a JSON response.
        
        Attempts to parse the response as JSON. If parsing fails,
        tries to extract JSON from markdown code fences or preamble text.
        
        Args:
            messages: Chat messages.
            model: Model override.
            temperature: Sampling temperature.
            max_tokens: Max response tokens.
        
        Returns:
            Dict with:
                - "parsed": The parsed JSON object (dict)
                - "raw": The raw response text
                - "model": Model used
                - "usage": Token usage dict
        
        Raises:
            GroqClientError: If JSON cannot be extracted from the response.
        """
        result = self.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        
        raw_content = result["content"]
        parsed = self._parse_json_response(raw_content)
        
        return {
            "parsed": parsed,
            "raw": raw_content,
            "model": result["model"],
            "usage": result["usage"],
        }

    @staticmethod
    def _parse_json_response(text: str) -> dict:
        """
        Attempt to parse JSON from LLM response text.
        
        Handles common issues:
        - Markdown code fences (```json ... ```)
        - Preamble text before JSON
        - Trailing text after JSON
        """
        text = text.strip()
        
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Strip markdown code fences
        if "```" in text:
            lines = text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.strip().startswith("```"):
                    in_block = not in_block
                    continue
                if in_block:
                    json_lines.append(line)
            if json_lines:
                try:
                    return json.loads("\n".join(json_lines))
                except json.JSONDecodeError:
                    pass
        
        # Find first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        
        raise GroqClientError(
            f"Failed to parse JSON from Groq response. Raw text: {text[:200]}..."
        )

    def test_connection(self) -> dict[str, Any]:
        """
        Test the Groq API connection with a simple request.
        
        Returns:
            Dict with model, response text, and usage stats.
        
        Raises:
            GroqClientError: If connection test fails.
        """
        try:
            result = self.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a test assistant."},
                    {"role": "user", "content": "Respond with exactly: CONNECTION_OK"},
                ],
                max_tokens=20,
            )
            logger.info(
                "Groq connection test successful | model=%s | tokens=%d",
                result["model"], result["usage"]["total_tokens"]
            )
            return result
        except AuthenticationError:
            raise GroqClientError(
                "Groq authentication failed. Check your GROQ_API_KEY."
            )

    def get_usage_stats(self) -> dict[str, int]:
        """Return cumulative token usage statistics."""
        return {
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
        }
