from __future__ import annotations

import json
import logging
import os
import subprocess
from functools import lru_cache

import requests

from gemini_config import gemini_endpoint, resolve_gemini_model

DEFAULT_LITELLM_API_BASE = "https://litellm.iaiai.ai/v1"
DEFAULT_LITELLM_MODEL = "gpt-5.4"
DEFAULT_LITELLM_CURATOR_MODEL = "gpt-5-mini"
DEFAULT_LITELLM_SUMMARIZER_MODEL = "gpt-5.4"
LITELLM_KEYCHAIN_SERVICE = "codex-litellm-iaiai"
LITELLM_KEYCHAIN_ACCOUNT = "LITELLM_API_KEY"

_TASK_PROVIDER_ENV_VARS = {
    "curator": "LLM_CURATOR_PROVIDER",
    "summarizer": "LLM_SUMMARIZER_PROVIDER",
}
_TASK_LITELLM_MODEL_ENV_VARS = {
    "curator": "LITELLM_CURATOR_MODEL",
    "summarizer": "LITELLM_SUMMARIZER_MODEL",
}
_TASK_LITELLM_DEFAULTS = {
    "curator": DEFAULT_LITELLM_CURATOR_MODEL,
    "summarizer": DEFAULT_LITELLM_SUMMARIZER_MODEL,
}


def _task_key(task: str) -> str:
    return str(task or "").strip().lower()


def resolve_provider(task: str) -> str:
    task_key = _task_key(task)
    provider = os.getenv(_TASK_PROVIDER_ENV_VARS.get(task_key, ""), "").strip().lower()
    if provider:
        return provider

    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider:
        return provider
    return "gemini"


def credential_env_name(provider: str) -> str:
    return "LITELLM_API_KEY" if provider == "litellm" else "GEMINI_API_KEY"


@lru_cache(maxsize=1)
def _litellm_keychain_secret() -> str:
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                LITELLM_KEYCHAIN_SERVICE,
                "-a",
                LITELLM_KEYCHAIN_ACCOUNT,
                "-w",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def resolve_api_key(provider: str) -> str:
    if provider == "litellm":
        return os.getenv("LITELLM_API_KEY", "").strip() or _litellm_keychain_secret()
    return os.getenv("GEMINI_API_KEY", "").strip()


def credentials_available(task: str) -> bool:
    provider = resolve_provider(task)
    return bool(resolve_api_key(provider))


def resolve_model(task: str) -> str:
    task_key = _task_key(task)
    provider = resolve_provider(task)

    if provider == "litellm":
        task_value = os.getenv(_TASK_LITELLM_MODEL_ENV_VARS.get(task_key, ""), "").strip()
        if task_value:
            return task_value

        shared_value = os.getenv("LITELLM_MODEL", "").strip()
        if shared_value:
            return shared_value
        return _TASK_LITELLM_DEFAULTS.get(task_key, DEFAULT_LITELLM_MODEL)

    return resolve_gemini_model(task_key)


def resolve_api_base(provider: str) -> str | None:
    if provider == "litellm":
        return os.getenv("LITELLM_API_BASE", "").strip() or DEFAULT_LITELLM_API_BASE
    return None


def call_json_text(
    *,
    task: str,
    prompt: str,
    logger: logging.Logger,
    max_output_tokens: int,
    temperature: float,
) -> str:
    provider = resolve_provider(task)
    api_key = resolve_api_key(provider)
    if not api_key:
        raise RuntimeError(f"Missing credentials for provider={provider} ({credential_env_name(provider)})")

    model_name = resolve_model(task)
    logger.info(
        "LLM request started (task=%s provider=%s model=%s prompt chars=%d)",
        task,
        provider,
        model_name,
        len(prompt),
    )

    if provider == "litellm":
        return _call_litellm(
            task=task,
            prompt=prompt,
            api_key=api_key,
            model_name=model_name,
            logger=logger,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )

    return _call_gemini(
        task=task,
        prompt=prompt,
        api_key=api_key,
        model_name=model_name,
        logger=logger,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
    )


def _call_gemini(
    *,
    task: str,
    prompt: str,
    api_key: str,
    model_name: str,
    logger: logging.Logger,
    max_output_tokens: int,
    temperature: float,
) -> str:
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
            "responseMimeType": "application/json",
        },
    }
    response = requests.post(
        gemini_endpoint(task),
        headers={"x-goog-api-key": api_key},
        json=payload,
        timeout=60,
    )
    logger.info("LLM response status=%s (task=%s provider=gemini model=%s)", response.status_code, task, model_name)
    if response.status_code >= 400:
        logger.error("LLM error body=%s", response.text)
    response.raise_for_status()

    data = response.json()
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text_chunks = [part.get("text", "") for part in parts if isinstance(part, dict) and part.get("text")]
    if text_chunks:
        return "".join(text_chunks)
    raise RuntimeError(f"Gemini returned no text parts: {json.dumps(data, ensure_ascii=False)[:800]}")


def _call_litellm(
    *,
    task: str,
    prompt: str,
    api_key: str,
    model_name: str,
    logger: logging.Logger,
    max_output_tokens: int,
    temperature: float,
) -> str:
    api_base = resolve_api_base("litellm")
    endpoint = (api_base or DEFAULT_LITELLM_API_BASE).rstrip("/") + "/chat/completions"
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": "Return only valid JSON. Do not wrap the JSON in markdown fences.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": temperature,
        "max_tokens": max_output_tokens,
    }
    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    logger.info("LLM response status=%s (task=%s provider=litellm model=%s)", response.status_code, task, model_name)
    if response.status_code >= 400:
        logger.error("LLM error body=%s", response.text)
    response.raise_for_status()

    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"LiteLLM returned no choices: {json.dumps(data, ensure_ascii=False)[:800]}")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text_value = item.get("text")
                if text_value:
                    text_parts.append(str(text_value))
            elif item:
                text_parts.append(str(item))
        content = "\n".join(text_parts)

    if isinstance(content, str) and content.strip():
        return content
    raise RuntimeError(f"LiteLLM returned no text content: {json.dumps(data, ensure_ascii=False)[:800]}")
