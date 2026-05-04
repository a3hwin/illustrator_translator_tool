"""Translation helpers powered by a structured LLM prompt."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from google import genai
from google.genai import types, errors
import arabic_reshaper
from bidi.algorithm import get_display
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


LOGGER = logging.getLogger(__name__)


class LLMTranslator:
    """Translate extracted SVG text nodes with the Gemini API.

    Uses the ``google-genai`` SDK with ``response_mime_type`` enforcement
    to guarantee structurally valid JSON at the protocol level.
    """

    DEFAULT_BATCH_SIZE: int = 10

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "gemini-2.5-flash",
        batch_size: int | None = None,
    ) -> None:
        """Initialize the Gemini client.

        Args:
            api_key: Google Gemini API key.  Falls back to the
                ``GEMINI_API_KEY`` environment variable when omitted.
            model_name: Gemini model identifier used for translation requests.
            batch_size: Maximum number of nodes per LLM request.  Defaults to
                ``DEFAULT_BATCH_SIZE``.  Set to ``0`` to send all nodes in a
                single request (not recommended for large payloads).

        Raises:
            ValueError: If no API key is available.
        """
        resolved_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not resolved_key:
            raise ValueError(
                "A Gemini API key must be provided either as an argument "
                "or via the GEMINI_API_KEY environment variable."
            )

        self.client = genai.Client(api_key=resolved_key)
        self.model_name = model_name
        self.generation_config = types.GenerateContentConfig(
            response_mime_type="application/json",
        )
        self.batch_size = (
            batch_size if batch_size and batch_size > 0 else self.DEFAULT_BATCH_SIZE
        )

    def translate_nodes(
        self,
        extracted_nodes: list[dict[str, Any]],
        target_language: str,
    ) -> list[dict[str, Any]]:
        """Translate extracted node text and merge results back into the input data.

        When the node count exceeds ``batch_size``, the payload is split into
        sequential batches to avoid context-window truncation and schema
        failure in the LLM response.

        Args:
            extracted_nodes: Extracted SVG text nodes containing at least
                ``node_id`` and ``text`` keys.
            target_language: Target language name such as ``Hindi`` or ``Arabic``.

        Returns:
            A new list of node dictionaries containing the original fields plus
            a ``translated_text`` key for each node.

        Raises:
            ValueError: If ``target_language`` is empty.
            RuntimeError: If the LLM request fails or the response cannot be
                parsed into the expected JSON structure.
        """
        if not target_language:
            raise ValueError("target_language must be provided.")

        payload = [
            {
                "node_id": str(node.get("node_id", "")),
                "text": str(node.get("text", "")),
            }
            for node in extracted_nodes
        ]
        LOGGER.info("Translation payload size: %d node(s).", len(payload))

        batches = self._split_into_batches(payload)
        LOGGER.info(
            "Translating %d node(s) in %d batch(es) of up to %d.",
            len(payload),
            len(batches),
            self.batch_size,
        )

        translations_by_id: dict[str, str] = {}
        for batch_index, batch in enumerate(batches, start=1):
            LOGGER.info(
                "Processing translation batch %d / %d ...",
                batch_index,
                len(batches),
            )
            batch_result = self._translate_batch(batch, target_language)
            translations_by_id.update(batch_result)

        merged_nodes: list[dict[str, Any]] = []
        for node in extracted_nodes:
            merged_node = dict(node)
            node_id = str(node.get("node_id", ""))
            merged_node["translated_text"] = translations_by_id.get(
                node_id,
                str(node.get("text", "")),
            )
            merged_nodes.append(merged_node)

        return merged_nodes

    # ── Internal helpers ────────────────────────────────────────────────

    def _split_into_batches(
        self,
        payload: list[dict[str, str]],
    ) -> list[list[dict[str, str]]]:
        """Split a node payload into sequential batches.

        Args:
            payload: Full list of node dictionaries to translate.

        Returns:
            A list of batches, each containing at most ``batch_size`` items.
        """
        if not payload:
            return []
        return [
            payload[i : i + self.batch_size]
            for i in range(0, len(payload), self.batch_size)
        ]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=10),
        retry=retry_if_exception_type(errors.ServerError),
        reraise=True
    )
    def _translate_batch(
        self,
        batch_payload: list[dict[str, str]],
        target_language: str,
    ) -> dict[str, str]:
        """Translate a single batch of nodes via the LLM.

        Args:
            batch_payload: A batch of node dictionaries containing ``node_id``
                and ``text`` keys.
            target_language: Target language name.

        Returns:
            A dictionary mapping ``node_id`` to ``translated_text``.

        Raises:
            errors.ServerError: If the LLM request fails after retries.
            RuntimeError: If the response is malformed.
        """
        prompt = self._build_translation_prompt(batch_payload, target_language)

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=self.generation_config,
            )
            response_text = response.text or ""
            LOGGER.debug("Raw LLM Response: %s", response_text[:500])
            translated_items = self._parse_translation_response(response_text)
            LOGGER.info("Successfully parsed %d translation(s) from batch.", len(translated_items))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            LOGGER.exception("Failed to parse translation response for batch.")
            raise RuntimeError("Failed to parse translation response.") from exc
        # Note: ServerError is not caught here so tenacity can handle it.

        is_arabic = target_language.strip().lower() in {"arabic", "ar"}
        
        translations: dict[str, str] = {}
        for item in translated_items:
            node_id = str(item["node_id"])
            text = str(item["translated_text"])
            
            if is_arabic:
                # Apply RTL Pre-shaping (Reshaping + BiDi)
                reshaped = arabic_reshaper.reshape(text)
                text = get_display(reshaped)
                
            translations[node_id] = text

        return translations

    def _build_translation_prompt(
        self,
        payload: list[dict[str, str]],
        target_language: str,
    ) -> str:
        """Build a strict localization prompt for structured output.

        The prompt enforces the Context-First Rule: the LLM is instructed to
        treat every string as contextual creative copy (headlines, taglines,
        calls-to-action) rather than isolated dictionary words.

        Args:
            payload: Minimal node payload containing only ``node_id`` and
                ``text``.
            target_language: Requested target language.

        Returns:
            A prompt instructing the LLM to return raw JSON only.
        """
        serialized_payload = json.dumps(payload, ensure_ascii=False)
        return (
            "You are a senior localization expert specializing in creative and "
            "marketing assets such as posters, packaging, banners, and UI copy "
            "for global brands. "
            f"Translate the provided English marketing copy into {target_language}. "
            "These are NOT isolated dictionary words — they are contextual "
            "creative headlines, taglines, and calls-to-action. "
            "Preserve the original tone, impact, and brevity. "
            "Adapt idioms and cultural references for the target locale when "
            "necessary. "
            "Keep each node_id exactly unchanged. "
            "Return ONLY a raw JSON array with no markdown fences, no "
            "commentary, and no explanation. "
            'Each item must be an object with exactly two keys: "node_id" and '
            '"translated_text". '
            "Do not omit any entries. If a source string is empty, return an "
            "empty translated_text. "
            f"Input JSON: {serialized_payload}"
        )

    def _parse_translation_response(self, response_text: str) -> list[dict[str, str]]:
        """Parse and validate the JSON array returned by the LLM.

        Args:
            response_text: Raw text returned by the model.

        Returns:
            A validated list of translation result objects.

        Raises:
            json.JSONDecodeError: If the response is not valid JSON.
            ValueError: If the parsed response does not match the expected shape.
        """
        cleaned_response = self._strip_code_fences(response_text)
        parsed = json.loads(cleaned_response)

        if not isinstance(parsed, list):
            raise ValueError("Translation response must be a JSON array.")

        validated_items: list[dict[str, str]] = []
        for item in parsed:
            if not isinstance(item, dict):
                raise ValueError("Each translation item must be a JSON object.")
            if "node_id" not in item or "translated_text" not in item:
                raise ValueError(
                    "Each translation item must contain node_id and translated_text."
                )

            validated_items.append(
                {
                    "node_id": str(item["node_id"]),
                    "translated_text": str(item["translated_text"]),
                }
            )

        return validated_items

    def _strip_code_fences(self, response_text: str) -> str:
        """Remove optional markdown fences from model output.

        Args:
            response_text: Raw model output.

        Returns:
            Response text with surrounding markdown fences removed when present.
        """
        stripped = response_text.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 2:
                return "\n".join(lines[1:-1]).strip()
        return stripped
