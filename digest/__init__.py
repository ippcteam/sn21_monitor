"""
Digest framework — pluggable daily digests over JSON stores.

A digest = (source → composer → channel) executed on a schedule.
- source: pure function that gathers structured inputs from on-disk JSON.
- composer: turns inputs into a markdown/plain-text message (LLM or fallback).
- channel: ships the message somewhere (Telegram today; email/Slack later).

To add a new digest, drop a source module under `digest/sources/`, add a prompt
under `digest/prompts/`, and append a `DigestConfig` to `REGISTERED_DIGESTS`.
"""

from .core import DigestConfig, run_digest, REGISTERED_DIGESTS

__all__ = ["DigestConfig", "run_digest", "REGISTERED_DIGESTS"]
