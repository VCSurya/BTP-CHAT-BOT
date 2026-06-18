"""OpenAI access layer for the two pipeline stages.

Uses Chat Completions with JSON mode (response_format=json_object) and
temperature 0 for deterministic, parseable output.
"""
import json
import logging

from openai import OpenAI

log = logging.getLogger("procura.llm")


class LLMError(Exception):
    pass


class LLMService:
    def __init__(self, config):
        self.cfg = config
        self.client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            timeout=config.OPENAI_TIMEOUT,
        )

    def _chat_json(self, system_prompt: str, messages: list) -> dict:
        try:
            response = self.client.chat.completions.create(
                model=self.cfg.OPENAI_MODEL,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system_prompt}] + messages,
            )
        except Exception as error:  # network / auth / rate limit
            log.exception("OpenAI request failed")
            raise LLMError(str(error)) from error

        content = response.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError as error:
            log.error("Model returned non-JSON content: %s", content[:500])
            raise LLMError("The model returned malformed output.") from error

    def plan(self, system_prompt: str, history: list, user_message: str) -> dict:
        """Stage 1: classify + (optionally) generate SQL."""
        messages = list(history) + [{"role": "user", "content": user_message}]
        return self._chat_json(system_prompt, messages)

    def analyze(self, system_prompt: str, user_message: str, sql: str,
                result: dict, schema_summary: str = "",
                enhanced_question: str = "") -> dict:
        """Stage 2: turn real rows into an insight + chart spec.

        The enhanced_question (produced by the planner) is the user's short
        message expanded into a detailed analytical question. The analyst uses
        it to deliver a thorough answer that addresses the full inferred intent.
        """
        # Send a bounded preview of the rows to keep the prompt small.
        preview = result.get("rows", [])[:60]
        payload = {
            "original_question": user_message,
            "enhanced_question": enhanced_question or user_message,
            "columns": result.get("columns", []),
            "data": preview,
            "found_count": len(result.get("rows", [])),
            "available_information": schema_summary,
        }
        messages = [{"role": "user", "content": json.dumps(payload, default=str)}]
        return self._chat_json(system_prompt, messages)