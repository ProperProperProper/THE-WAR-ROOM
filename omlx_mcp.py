#!/usr/bin/env python3
"""Clean oMLX integration for War Room - no old bridge dependencies."""
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger('war-room.omlx')

OMLX_HOST = os.environ.get("OMLX_HOST", "127.0.0.1")
OMLX_PORT = int(os.environ.get("OMLX_PORT", "8000"))

def _get_loaded_model():
    """Detect which model is actually loaded in oMLX."""
    try:
        base = f"http://{OMLX_HOST}:{OMLX_PORT}/v1"
        key = os.environ.get("OMLX_KEY", "omlx")
        req = urllib.request.Request(
            base + "/models",
            headers={"Authorization": "Bearer " + key}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.load(response)
            models = [m.get("id") for m in data.get("data", [])]
            if models:
                logger.debug(f"Available oMLX models: {models}")
                return models[0]
    except Exception as e:
        logger.warning(f"Could not detect oMLX model: {e}")
    return os.environ.get("OMLX_MODEL", "mlx-community/Qwen2.5-Coder-7B-Instruct-8bit")

MODEL = _get_loaded_model()


def _get_api_key():
    """Get API key from environment or settings file."""
    # Try environment first
    if os.environ.get("OMLX_KEY"):
        return os.environ.get("OMLX_KEY")

    # Try settings file
    try:
        settings_file = Path.home() / ".omlx" / "settings.json"
        if settings_file.exists():
            data = json.loads(settings_file.read_text())
            key = data.get("auth", {}).get("api_key")
            if key:
                logger.debug(f"Got API key from settings.json")
                return key
    except Exception as e:
        logger.warning(f"Could not read API key from settings: {e}")

    # Fallback
    logger.debug("Using default API key 'omlx'")
    return "omlx"


def config():
    """Return oMLX API endpoint and auth key."""
    base = f"http://{OMLX_HOST}:{OMLX_PORT}/v1"
    key = _get_api_key()
    logger.debug(f"oMLX config: {base}, auth key exists={bool(key)}")
    return base, key


def local_response(prompt, max_thinking_length=32000, model_override=None):
    """Call oMLX local model via /v1/responses endpoint."""
    base, key = config()
    model = model_override or MODEL

    # oMLX times out on long prompts; enforce hard cap
    if len(prompt) > 500:
        logger.warning(f"Prompt length {len(prompt)} exceeds 500 char limit; truncating")
        prompt = prompt[:500] + "...(truncated)"

    body = json.dumps({
        "model": model,
        "input": prompt,
        "max_output_tokens": 2000
    }).encode()

    req = urllib.request.Request(
        base + "/responses", body,
        {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key
        },
        method="POST",
    )

    result = None
    try:
        logger.info(f"Calling oMLX /responses with model={model}")
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.load(response)
            logger.info(f"oMLX response received, status={response.status}")
    except urllib.error.HTTPError as e:
        logger.error(f"oMLX HTTP error {e.code}: {e.reason}")
        raise
    except urllib.error.URLError as e:
        logger.error(f"oMLX connection failed: {e}")
        raise
    except Exception as e:
        logger.error(f"oMLX error: {type(e).__name__}: {e}")
        raise

    if result is None:
        logger.error("oMLX returned None response")
        raise ValueError("oMLX returned no response")

    # Extract text from oMLX response format
    try:
        output = result.get("output", []) if isinstance(result, dict) else []
        if output and len(output) > 0:
            message = output[0]
            content = message.get("content", []) if isinstance(message, dict) else []
            if content and len(content) > 0:
                text = content[0].get("text", "") if isinstance(content[0], dict) else ""
                if text:
                    logger.info(f"oMLX returned {len(text)} chars")
                    return text
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        logger.warning(f"Error parsing oMLX response: {e}")

    logger.warning(f"oMLX response had no text content: {result}")
    raise ValueError(f"oMLX returned no text: {json.dumps(result)}")
