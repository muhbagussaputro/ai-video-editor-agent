from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from shared.settings import settings


class RouterClientError(RuntimeError):
    pass


class RouterClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or settings.router_base_url).rstrip("/")
        self.api_key = api_key or settings.router_api_key
        self.model = model or settings.llm_model

    def _extract_chat_content(self, response: httpx.Response) -> str:
        content_type = (response.headers.get("content-type") or "").lower()
        text = response.text or ""
        if "text/event-stream" in content_type or text.lstrip().startswith("data:"):
            parts: list[str] = []
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                for choice in chunk.get("choices", []) or []:
                    delta = choice.get("delta") or {}
                    piece = delta.get("content")
                    if piece:
                        parts.append(str(piece))
            content = "".join(parts).strip()
            if content:
                return content
            raise RouterClientError(f"Router returned SSE without content: {text[:300]}")

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise RouterClientError(
                f"Router returned non-JSON response: status={response.status_code} content_type={content_type} body={text[:300]}"
            ) from exc
        return data["choices"][0]["message"]["content"]

    def _api_key(self) -> str:
        for value in (self.api_key, settings.router_api_key):
            if value and value != "***" and not value.lower().startswith("your_"):
                return value
        return ""

    def _auth_headers(self) -> dict[str, str]:
        api_key = self._api_key()
        if not self.base_url or not api_key:
            raise RouterClientError("Router base_url atau api_key belum diset")
        return {"Authorization": f"Bearer {api_key}"}

    def _join_url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def config(self) -> dict[str, Any]:
        return {
            "configured": bool(self.base_url and self._api_key()),
            "base_url": self.base_url,
            "model": self.model,
            "reasoning_effort": settings.llm_reasoning_effort,
            "transcription_model": settings.transcription_model,
            "transcription_path": settings.transcription_path,
            "transcription_ready": settings.transcription_ready,
            "local_asr_ready": settings.local_asr_ready,
            "local_transcription_model": settings.local_transcription_model,
            "local_transcription_device": settings.local_transcription_device,
            "local_transcription_compute_type": settings.local_transcription_compute_type,
            "min_highlight_duration": settings.min_highlight_duration,
            "max_highlight_duration": settings.max_highlight_duration,
            "highlight_count": settings.highlight_count,
            "highlight_score_threshold": settings.highlight_score_threshold,
            "min_output_count": settings.min_output_count,
            "threshold_backoff_step": settings.threshold_backoff_step,
            "min_score_threshold_floor": settings.min_score_threshold_floor,
        }

    def ping(self) -> dict[str, Any]:
        url = self._join_url("models")
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url, headers=self._auth_headers())
        return {
            "status_code": response.status_code,
            "ok": response.is_success,
            "base_url": self.base_url,
            "response_preview": response.text[:200],
        }

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        response_format: dict[str, str] | None = None,
        extra_payload: dict[str, Any] | None = None,
    ) -> str:
        url = self._join_url("chat/completions")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if extra_payload:
            payload.update(extra_payload)
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=self._auth_headers(), json=payload)
        if response.status_code >= 400:
            raise RouterClientError(f"Router chat request failed: {response.status_code} {response.text}")
        return self._extract_chat_content(response)

    def transcribe_audio(
        self,
        audio_path: Path,
        *,
        model: str | None = None,
        language: str | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        url = self._join_url(settings.transcription_path)
        payload: dict[str, Any] = {
            "model": model or settings.transcription_model,
            "response_format": "verbose_json",
        }
        if language:
            payload["language"] = language
        if prompt:
            payload["prompt"] = prompt
        with audio_path.open("rb") as fh:
            files = {"file": (audio_path.name, fh, "audio/wav")}
            with httpx.Client(timeout=180.0) as client:
                response = client.post(url, headers=self._auth_headers(), data=payload, files=files)
        if response.status_code >= 400:
            raise RouterClientError(f"Router transcription failed: {response.status_code} {response.text}")
        return response.json()
