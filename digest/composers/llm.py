"""
LLM composer using the Anthropic API. Default model: Claude Haiku 4.5.

The prompt template is a markdown file with a `---` divider separating system
prompt and user prompt template. The user template gets the structured inputs
appended as JSON; the model returns the digest text.

If `ANTHROPIC_API_KEY` is missing or the call errors, the orchestrator falls
back to the deterministic composer.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("DIGEST_LLM_MODEL", "claude-haiku-4-5-20251001")
DEFAULT_MAX_TOKENS = int(os.environ.get("DIGEST_LLM_MAX_TOKENS", "1024"))


def _split_prompt(template: str) -> tuple[str, str]:
    """
    Split the prompt template on the first '---' divider.
    Above is the system prompt, below is the user-prompt template.
    If no divider, the whole text is the system prompt.
    """
    if "\n---\n" in template:
        sys, _, user = template.partition("\n---\n")
        return sys.strip(), user.strip()
    return template.strip(), ""


def compose(inputs: dict[str, Any], prompt_template: str, title: str) -> str:
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    # Imported lazily so missing dep doesn't break the module load.
    try:
        from anthropic import Anthropic
    except ImportError as e:
        raise RuntimeError(f"anthropic package not installed: {e}")

    system_prompt, user_template = _split_prompt(prompt_template)
    if not system_prompt:
        system_prompt = (
            f"You are a concise risk analyst for the {title}. "
            "Produce a tight markdown digest from the structured JSON below."
        )

    inputs_json = json.dumps(inputs, indent=2, default=str, sort_keys=True)
    user_msg = (
        (user_template + "\n\n" if user_template else "")
        + f"Today's data:\n```json\n{inputs_json}\n```"
    )

    client = Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=DEFAULT_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
    )

    parts: list[str] = []
    for block in resp.content or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    out = "\n".join(parts).strip()
    if not out:
        raise RuntimeError("Anthropic returned no text content")
    return out
