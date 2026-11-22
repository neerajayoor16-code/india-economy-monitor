"""AI card text (Claude API), with three automatic checks before anything is published.

Plain-English summary
---------------------
1. Claude writes three short texts for one card (summary, verdict, everyday example) from the
   numbers only. The model returns a fixed JSON format.
2. Check A (textgen.check_text): every number in the text must be in the data; no advice,
   no certain predictions, no '!'; the direction (up/down) must match the data.
3. Check B: a second, separate Claude call reads the data and the text and must answer
   "consistent". It looks for wrong meaning that a number check cannot catch.
4. If anything fails, the caller uses plain fill-in text instead and raises an alert.

Needs ANTHROPIC_API_KEY in the environment (a GitHub repository secret in production).
Model: claude-opus-5-5 at low effort (short, routine writing). Refusal fallback is on.
"""
from __future__ import annotations

import json

import textgen

MODEL = "claude-opus-5-5"
BETAS = ["server-side-fallback-2026-07-01"]

WRITER_SYSTEM = """You write short card texts for a public dashboard about India's economy. Readers are not economists.

Rules:
- Plain, simple English. Short sentences. Active voice. No jargon without a short explanation.
- Use ONLY numbers that appear in the DATA block (including the ILLUSTRATION amounts). Do not round them differently, do not invent other numbers, dates or facts.
- State facts. Never give investment, buying or selling advice. Never state a prediction as certain.
- No exclamation marks. No hype words.
- "summary": one or two sentences: the latest value, its period, and the change from the previous value if given.
- "goodOrBadVerdict": one or two sentences that start with the signal label given in DATA, then explain the signal using the reason given in DATA.
- "everydayIndianExample": two sentences that show what this means for an ordinary Indian household or small business. If ILLUSTRATION amounts are given, you may use them exactly.
"""

CHECKER_SYSTEM = """You check short dashboard texts against their source data. Answer only from the DATA block.
A text is NOT consistent if it: states a fact or number not supported by the data; describes the direction of change wrongly; gives a different signal than the data; gives investment advice; or makes a certain prediction.
Small wording choices are fine. Be strict about facts."""

TEXT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "goodOrBadVerdict": {"type": "string"},
        "everydayIndianExample": {"type": "string"},
    },
    "required": ["summary", "goodOrBadVerdict", "everydayIndianExample"],
    "additionalProperties": False,
}
CHECK_SCHEMA = {
    "type": "object",
    "properties": {"consistent": {"type": "boolean"}, "problems": {"type": "array", "items": {"type": "string"}}},
    "required": ["consistent", "problems"],
    "additionalProperties": False,
}


def illustrations(key: str, reading: dict) -> dict:
    """Exact rupee examples computed in code, so the model never does arithmetic."""
    v = reading.get("value")
    if key in ("cpi", "wpi") and isinstance(v, (int, float)):
        return {"basket_last_year_rs": 10000, "same_basket_now_rs": round(10000 * (1 + v / 100))}
    if key == "repo_rate" and isinstance(v, (int, float)):
        return {"policy_rate_pct": v}
    return {}


def _data_block(key: str, ex: dict, reading: dict, signal: dict) -> dict:
    return {
        "indicator": ex["name"], "what_it_is": ex["plainEnglishDefinition"],
        "latest": {k: reading.get(k) for k in ("display", "value", "unit", "period_label", "previous", "previous_label")},
        "details": {k: v for k, v in (reading.get("details") or {}).items() if k != "history"},
        "signal_label": textgen.SIGNAL_LABEL[signal["signal"]], "signal_reason": signal["reason"],
        "source": reading.get("source_name"), "ILLUSTRATION": illustrations(key, reading),
    }


class AIWriter:
    def __init__(self, client=None):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.client = client

    def _json_call(self, system: str, user: str, schema: dict) -> dict:
        response = self.client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=BETAS,
            fallbacks="default",
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("the model declined to write this text")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("the response was cut off (max_tokens)")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise RuntimeError("no text block in the response")
        return json.loads(text)

    def write(self, key: str, ex: dict, reading: dict, signal: dict) -> tuple[dict, list[str]]:
        """Return (texts, problems). Texts may only be used when problems is empty."""
        data = _data_block(key, ex, reading, signal)
        data_json = json.dumps(data, ensure_ascii=False, indent=1)
        texts = self._json_call(WRITER_SYSTEM, f"DATA:\n{data_json}\n\nWrite the three texts.", TEXT_SCHEMA)
        texts = {k: texts[k].strip() for k in ("summary", "goodOrBadVerdict", "everydayIndianExample")}

        context = signal["reason"] + " " + json.dumps(data["ILLUSTRATION"])
        problems = textgen.check_text(texts, reading, context)          # check A
        if not texts["goodOrBadVerdict"].lower().startswith(data["signal_label"].lower()):
            problems.append(f"goodOrBadVerdict: does not start with the signal label {data['signal_label']!r}")
        if problems:
            return texts, problems

        verdict = self._json_call(                                       # check B
            CHECKER_SYSTEM,
            f"DATA:\n{data_json}\n\nTEXTS:\n{json.dumps(texts, ensure_ascii=False, indent=1)}\n\nAre the texts consistent with the data?",
            CHECK_SCHEMA,
        )
        if not verdict.get("consistent"):
            return texts, [f"second check: {p}" for p in verdict.get("problems") or ["marked inconsistent"]]
        return texts, []
