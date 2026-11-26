"""LLM client for the reconciliation agent.

Reads the model configuration from environment variables first, then falls back to the
JiuwenSwarm runtime config (`~/.jiuwenswarm/config/config.yaml`, `models.defaults[0]`).
API keys are NEVER hardcoded in source and are never written into proposals, screenshots
or exports.

Environment variables:
  AUTOVAL_LLM_API_KEY   API key (required unless available via the runtime config)
  AUTOVAL_LLM_BASE_URL  OpenAI-compatible base URL (default https://tokendance.space/gateway/v1)
  AUTOVAL_LLM_MODEL     model name (default deepseek-v4-pro-0813)
"""
from __future__ import annotations
import json
import os
import re

import requests

DEFAULT_BASE_URL = "https://tokendance.space/gateway/v1"
DEFAULT_MODEL = "deepseek-v4-pro-0813"
RUNTIME_CONFIG = os.path.expanduser("~/.jiuwenswarm/config/config.yaml")


def _from_runtime_config() -> dict:
    """Best-effort read of the JiuwenSwarm default model config (no hardcoded keys).

    Opt-in only: the public/demo build never reads a private runtime config unless
    `AUTOVAL_LLM_USE_RUNTIME_CONFIG=1` is set. This prevents the offline demonstration from
    silently loading a developer's credentials through a config-file fallback.
    """
    cfg: dict = {}
    if os.environ.get("AUTOVAL_LLM_USE_RUNTIME_CONFIG") != "1":
        return cfg
    try:
        txt = open(RUNTIME_CONFIG, encoding="utf-8").read()
    except OSError:
        return cfg
    # The default model is the first model_client_config under `models.defaults`.
    # Its api_key starts with `sk-`; the memory/embedding placeholders use `${...}`.
    m_base = re.search(r"api_base:\s*(\S+)", txt)
    m_model = re.search(r"model_name:\s*(\S+)", txt)
    m_key = re.search(r"api_key:\s*(sk-\S+)", txt)
    if m_base:
        cfg["base_url"] = m_base.group(1)
    if m_model:
        cfg["model"] = m_model.group(1)
    if m_key:
        cfg["api_key"] = m_key.group(1)
    return cfg


def llm_config() -> dict:
    cfg = _from_runtime_config()
    out = {
        "base_url": os.environ.get("AUTOVAL_LLM_BASE_URL", cfg.get("base_url", DEFAULT_BASE_URL)),
        "model": os.environ.get("AUTOVAL_LLM_MODEL", cfg.get("model", DEFAULT_MODEL)),
        "api_key": os.environ.get("AUTOVAL_LLM_API_KEY", cfg.get("api_key", "")),
    }
    return out


def is_configured() -> bool:
    return bool(llm_config()["api_key"])


def chat(messages: list[dict], max_tokens: int = 3000, temperature: float = 0.0,
         json_mode: bool = False) -> str:
    """Send a chat completion request and return the assistant text.

    Raises RuntimeError on a missing key or a non-2xx response. Never returns the key.
    In public-demonstration mode (`AUTOVAL_PUBLIC_DEMO=1`) paid calls are prohibited at the
    backend, even when credentials happen to be configured.
    """
    if os.environ.get("AUTOVAL_PUBLIC_DEMO") == "1":
        raise RuntimeError("Paid LLM calls are disabled in public demonstration mode.")
    cfg = llm_config()
    if not cfg["api_key"]:
        raise RuntimeError("No LLM API key configured (set AUTOVAL_LLM_API_KEY or the runtime config).")
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }
    resp = requests.post(f"{cfg['base_url'].rstrip('/')}/chat/completions",
                         data=json.dumps(payload), headers=headers, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected LLM response shape: {exc}") from exc


def extract_json(text: str) -> dict:
    """Robustly extract a JSON object from an LLM response (code fences tolerated)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise
