"""Qwen 3.8 Max via OpenAI-compatible Chat Completions. Never sizes trades."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx


def api_key() -> str:
    return (
        os.getenv("BITGET_QWEN_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    ).strip()


def base_url() -> str:
    return (
        os.getenv("BITGET_QWEN_BASE_URL")
        or os.getenv("DASHSCOPE_BASE_URL")
        or "https://hackathon.bitgetops.com/v1"
    ).rstrip("/")


def model() -> str:
    return os.getenv("BITGET_QWEN_MODEL") or os.getenv("DASHSCOPE_MODEL") or "qwen3.8-max"


def configured() -> bool:
    return bool(api_key())


def status() -> dict:
    key = api_key()
    return {
        "configured": bool(key),
        "model": model(),
        "base_url": base_url(),
        "key_tail": ("…" + key[-4:]) if len(key) >= 4 else "",
    }


def complete(messages: list[dict[str, str]], *, temperature: float = 0, timeout: float = 20.0) -> str:
    key = api_key()
    if not key:
        raise RuntimeError("No Qwen key. Set BITGET_QWEN_API_KEY in .env")
    payload = {
        "model": model(),
        "temperature": temperature,
        "messages": messages,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=timeout) as client:
        r = client.post(f"{base_url()}/chat/completions", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    return data["choices"][0]["message"]["content"]


def ping() -> dict:
    text = complete(
        [
            {"role": "system", "content": "Reply with the single word pong."},
            {"role": "user", "content": "ping"},
        ],
        timeout=15.0,
    )
    return {"ok": True, "model": model(), "reply": (text or "").strip()[:200]}


def narrate(decision: dict[str, Any]) -> str | None:
    """Judge-facing English. Must not invent numbers or change the action."""
    if not configured():
        return None
    slim = {
        "action": decision.get("action"),
        "reason": decision.get("reason"),
        "news": (decision.get("news") or {}).get("label"),
        "headline": (decision.get("news") or {}).get("headline"),
        "session": (decision.get("session") or {}).get("kind"),
        "screen": (decision.get("screen") or {}).get("status"),
        "p90": (decision.get("p90") or {}).get("status"),
        "legs": decision.get("legs") or [],
        "fake_hedges": [f.get("note") for f in (decision.get("fake_hedges") or [])],
    }
    try:
        text = complete(
            [
                {
                    "role": "system",
                    "content": (
                        "You are Nightshift's narrator for a Bitget hackathon judge. "
                        "You receive a locked kernel decision. Do not change the action. "
                        "Do not invent prices, percents, or fills. Use only the JSON. "
                        "Write 2-3 short sentences: what the frozen-index illusion is, "
                        "what Monday p90 does, and what the kernel did (including HOLD)."
                    ),
                },
                {"role": "user", "content": json.dumps(slim)},
            ],
            timeout=18.0,
        )
        return (text or "").strip()[:600] or None
    except Exception:
        return None
