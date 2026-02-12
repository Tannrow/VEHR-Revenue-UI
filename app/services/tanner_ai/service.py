from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI


TRANSCRIPTION_MODEL = "whisper-1"
GENERATION_MODEL = "gpt-4o"
GENERATION_FALLBACK_MODEL = "gpt-4o-mini"
ALLOWED_NOTE_TYPES = {"SOAP", "DAP", "CUSTOM"}


class TannerAIConfigurationError(RuntimeError):
    pass


class TannerAIServiceError(RuntimeError):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise TannerAIConfigurationError(f"{name} is not configured")
    return value


def validate_tanner_ai_startup_configuration() -> None:
    _required_env("OPENAI_API_KEY")


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    parts.append(text_value.strip())
                continue

            item_text = getattr(item, "text", None)
            if isinstance(item_text, str) and item_text.strip():
                parts.append(item_text.strip())
        return "\n".join(parts).strip()

    return ""


def _parse_json_object(raw_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw_text[start : end + 1])
            except json.JSONDecodeError as exc:
                raise TannerAIServiceError("structured_note_invalid_json", status_code=502) from exc
        else:
            raise TannerAIServiceError("structured_note_invalid_json", status_code=502)

    if not isinstance(parsed, dict):
        raise TannerAIServiceError("structured_note_invalid_json", status_code=502)
    return parsed


class TannerAIService:
    def __init__(self, *, api_key: str | None = None, client: OpenAI | None = None) -> None:
        key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        if not key:
            raise TannerAIConfigurationError("OPENAI_API_KEY is not configured")
        self._client = client or OpenAI(api_key=key)

    def _chat_completion(self, *, messages: list[dict[str, str]], temperature: float) -> str:
        model_candidates = [GENERATION_MODEL, GENERATION_FALLBACK_MODEL]
        seen_models: set[str] = set()
        last_error: Exception | None = None

        for model_name in model_candidates:
            normalized = model_name.strip()
            if not normalized or normalized in seen_models:
                continue
            seen_models.add(normalized)
            try:
                response = self._client.chat.completions.create(
                    model=normalized,
                    messages=messages,
                    temperature=temperature,
                )
            except Exception as exc:
                last_error = exc
                continue

            if not response.choices:
                continue

            message = response.choices[0].message
            text = _extract_text_content(getattr(message, "content", ""))
            if text:
                return text

        if last_error is not None:
            raise TannerAIServiceError("tanner_ai_generation_failed", status_code=503) from last_error
        raise TannerAIServiceError("tanner_ai_empty_response", status_code=502)

    def transcribe_audio(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise TannerAIServiceError("audio_file_not_found", status_code=400)

        try:
            with path.open("rb") as audio_file:
                response = self._client.audio.transcriptions.create(
                    model=TRANSCRIPTION_MODEL,
                    file=audio_file,
                )
        except Exception as exc:
            raise TannerAIServiceError("tanner_ai_transcription_failed", status_code=503) from exc

        transcript = _extract_text_content(getattr(response, "text", ""))
        if not transcript and isinstance(response, dict):
            transcript = _extract_text_content(response.get("text", ""))

        cleaned = " ".join(transcript.split())
        if not cleaned:
            raise TannerAIServiceError("tanner_ai_transcription_empty", status_code=502)
        return cleaned

    def generate_text(self, prompt: str, temperature: float = 0.2) -> str:
        cleaned_prompt = prompt.strip()
        if not cleaned_prompt:
            raise TannerAIServiceError("prompt_required", status_code=400)
        if temperature < 0.0 or temperature > 2.0:
            raise TannerAIServiceError("temperature_out_of_range", status_code=400)

        system_prompt = (
            "You are Tanner AI for VEHR staff support. "
            "Be concise, practical, and avoid fabricating details."
        )
        return self._chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": cleaned_prompt},
            ],
            temperature=temperature,
        )

    def generate_structured_note(self, transcript: str, note_type: str) -> dict[str, str]:
        cleaned_transcript = transcript.strip()
        normalized_type = note_type.strip().upper()
        if not cleaned_transcript:
            raise TannerAIServiceError("transcript_required", status_code=400)
        if normalized_type not in ALLOWED_NOTE_TYPES:
            raise TannerAIServiceError("invalid_note_type", status_code=400)

        format_instruction = {
            "SOAP": (
                '{"S":"subjective summary","O":"objective findings","A":"assessment","P":"plan"}'
            ),
            "DAP": (
                '{"D":"data summary","A":"assessment","P":"plan"}'
            ),
            "CUSTOM": (
                '{"content":"custom clinical note"}'
            ),
        }[normalized_type]

        system_prompt = (
            "You are Tanner AI. Return ONLY valid JSON with no markdown, code fences, or commentary."
        )
        user_prompt = (
            f"Create a {normalized_type} clinical note from the transcript below.\n"
            f"Output must match exactly this JSON shape: {format_instruction}\n\n"
            f"Transcript:\n{cleaned_transcript}"
        )

        raw = self._chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
        parsed = _parse_json_object(raw)

        if normalized_type == "SOAP":
            required = ("S", "O", "A", "P")
            return {key: str(parsed.get(key, "")).strip() for key in required}

        if normalized_type == "DAP":
            required = ("D", "A", "P")
            return {key: str(parsed.get(key, "")).strip() for key in required}

        content = str(parsed.get("content", "")).strip()
        if not content:
            raise TannerAIServiceError("structured_note_invalid_json", status_code=502)
        return {"content": content}

    def assistant_reply(self, message: str, context: str | None = None) -> str:
        cleaned_message = message.strip()
        if not cleaned_message:
            raise TannerAIServiceError("message_required", status_code=400)

        system_prompt = (
            "You are Tanner AI for VEHR staff support. "
            "Do not assume missing facts. Ask clarifying questions when needed."
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if context and context.strip():
            messages.append({"role": "system", "content": f"Context: {context.strip()}"})
        messages.append({"role": "user", "content": cleaned_message})
        return self._chat_completion(messages=messages, temperature=0.2)


_service_instance: TannerAIService | None = None


def get_tanner_ai_service() -> TannerAIService:
    global _service_instance
    if _service_instance is None:
        _service_instance = TannerAIService()
    return _service_instance
