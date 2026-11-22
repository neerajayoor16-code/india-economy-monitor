"""AI writer tests with a fake Claude client (no network, no cost).

The plan's "try to break it" cases: a made-up number, buy advice, and a wrong direction must
all be rejected. Also: the second check, a refusal, and a cut-off answer.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import write_text  # noqa: E402

EX = {"name": "CPI Retail Inflation", "plainEnglishDefinition": "How fast household prices rise."}
READING = {"indicator": "cpi", "value": 6.09, "previous": 5.54, "unit": "%", "display": "6.09% YoY",
           "period_label": "Oct 2026", "previous_label": "Sep 2026", "period_end": "2026-10-31",
           "source_name": "MoSPI", "details": {}}
SIGNAL = {"signal": "warn", "reason": "RBI target 4%, tolerance band 2% to 6%"}
GOOD = {
    "summary": "Retail inflation rose to 6.09% in Oct 2026, up from 5.54% in Sep 2026.",
    "goodOrBadVerdict": "Warning sign: inflation is above the RBI tolerance band of 2% to 6%.",
    "everydayIndianExample": "A basket that cost Rs. 10,000 a year ago now costs Rs. 10,609. Families feel this in groceries and rent.",
}


class FakeClient:
    """Returns queued answers in order: first the writer, then the checker."""
    def __init__(self, *answers, stop_reason="end_turn"):
        self.answers, self.stop_reason, self.calls = list(answers), stop_reason, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        body = self.answers.pop(0)
        blocks = [SimpleNamespace(type="thinking", text=None), SimpleNamespace(type="text", text=json.dumps(body))]
        return SimpleNamespace(stop_reason=self.stop_reason, content=blocks)


def run(*answers, **kw):
    w = write_text.AIWriter(client=FakeClient(*answers, **kw))
    return w.write("cpi", EX, READING, SIGNAL), w.client


def test_good_text_passes_both_checks():
    (texts, problems), client = run(GOOD, {"consistent": True, "problems": []})
    assert problems == [] and texts == GOOD
    assert len(client.calls) == 2
    assert client.calls[0]["model"] == "claude-opus-5-5"
    assert client.calls[0]["fallbacks"] == "default"


def test_illustration_amount_is_computed_in_code():
    assert write_text.illustrations("cpi", READING) == {"basket_last_year_rs": 10000, "same_basket_now_rs": 10609}


def test_made_up_number_is_rejected_before_the_second_call():
    (_, problems), client = run({**GOOD, "summary": "Inflation rose to 6.09%, with food at 8.94%."})
    assert any("8.94" in p for p in problems)
    assert len(client.calls) == 1


def test_buy_advice_is_rejected():
    (_, problems), _ = run({**GOOD, "everydayIndianExample": "Investors should buy gold now."})
    assert any("advice" in p for p in problems)


def test_wrong_direction_is_rejected():
    (_, problems), _ = run({**GOOD, "summary": "Retail inflation fell to 6.09% in Oct 2026."})
    assert any("fell" in p for p in problems)


def test_wrong_signal_label_is_rejected():
    (_, problems), _ = run({**GOOD, "goodOrBadVerdict": "Good: prices are calm."})
    assert any("signal label" in p for p in problems)


def test_second_check_can_reject():
    (_, problems), _ = run(GOOD, {"consistent": False, "problems": ["says food prices drove it; data has no such fact"]})
    assert problems == ["second check: says food prices drove it; data has no such fact"]


def test_refusal_raises():
    with pytest.raises(RuntimeError, match="declined"):
        run(GOOD, stop_reason="refusal")


def test_cut_off_answer_raises():
    with pytest.raises(RuntimeError, match="cut off"):
        run(GOOD, stop_reason="max_tokens")
