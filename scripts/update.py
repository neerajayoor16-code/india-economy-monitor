"""The update pipeline: fetch -> check -> signal -> text -> save -> report -> build.

Plain-English summary
---------------------
1. Read what the site shows now (data/latest.json).
2. Ask every source for new numbers. A source that fails keeps its old number.
3. Check each new number (rules.validate_reading). A failed check keeps the old number.
4. Recompute every signal and the economic phase from the numbers.
5. Write card text for numbers that changed: AI text if enabled and it passes all checks,
   otherwise plain fill-in text. Unchanged numbers keep their text.
6. Save data files, add new points to data/history/, write logs/run-<time>.json and
   reports/last-run.md (the "what changed" report), then rebuild the site.

Exit codes: 0 = all fine, 2 = finished but something needs a human look (alerts), 1 = crashed.

Run:  python scripts/update.py                 (all sources, AI text if ANTHROPIC_API_KEY is set)
      python scripts/update.py --no-ai         (fill-in text only)
      python scripts/update.py --light         (skip the slow survey search; used on most runs)
      python scripts/update.py --offline       (no fetching; recompute and rebuild from saved data)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import rules  # noqa: E402
import textgen  # noqa: E402
from fetchers import GROUP_INDICATORS, GROUPS, INDICATOR_IDS, FetchError, NoNewRelease  # noqa: E402

DATA = ROOT / "data"
HISTORY = DATA / "history"
LOGS = ROOT / "logs"
REPORTS = ROOT / "reports"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# Days after the end of a reading's period before the card is marked stale and an alert is raised.
MAX_AGE_DAYS = {
    "cpi": 50, "wpi": 50, "unemployment": 50, "bank_credit": 35, "repo_rate": 10, "core_industries": 55,
    "iip": 75, "rail_freight": 40, "gst": 40, "vehicles": 50, "gdp": 160, "nifty": 10, "yield_spread": 10,
    "consumer_confidence": 100, "industrial_outlook": 130, "oecd_cli": 70,
}
SLOW_GROUPS = {"rbi_consumer_confidence", "rbi_industrial_outlook"}  # they search many pages when the feed misses


def load(name, default):
    p = DATA / name
    return json.loads(p.read_text("utf8")) if p.exists() else default


def save(name, obj):
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf8")


def read_history(key: str) -> list[tuple[str, float]]:
    p = HISTORY / f"{key}.csv"
    if not p.exists():
        return []
    with p.open(newline="") as f:
        return [(row["period_end"], float(row["value"])) for row in csv.DictReader(f)]


def append_history(key: str, reading: dict) -> None:
    HISTORY.mkdir(parents=True, exist_ok=True)
    p = HISTORY / f"{key}.csv"
    rows = {}
    if p.exists():
        with p.open(newline="") as f:
            rows = {r["period_end"]: r for r in csv.DictReader(f)}
    rows[reading["period_end"]] = {"period_end": reading["period_end"], "value": reading["value"],
                                   "period_label": reading["period_label"]}
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["period_end", "value", "period_label"])
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])


def fingerprint(r: dict) -> str:
    return f"{r['value']}|{r['period_end']}|{r.get('previous')}"


# --------------------------------------------------------------------------- steps
def fetch_all(state: dict, light: bool, log: list) -> dict[str, dict]:
    """Return new readings by indicator. Records every group's outcome in log."""
    found = {}
    for name, fn in GROUPS.items():
        try:
            if light and name in SLOW_GROUPS:
                os.environ["IEM_SKIP_PROBE"] = "1"  # light runs only read the feed; the full search runs once a day
            readings = fn(state.get("readings", {}))
            for k, r in readings.items():
                found[k] = r.to_dict()
            log.append({"group": name, "outcome": "ok", "indicators": sorted(readings)})
        except NoNewRelease as e:
            log.append({"group": name, "outcome": "no_new_release", "message": str(e)})
        except FetchError as e:
            log.append({"group": name, "outcome": "error", "message": str(e)})
        except Exception as e:  # a bug, not a source problem: record it loudly
            log.append({"group": name, "outcome": "bug", "message": f"{type(e).__name__}: {e}",
                        "trace": traceback.format_exc(limit=3)})
        finally:
            os.environ.pop("IEM_SKIP_PROBE", None)
    return found


def apply_readings(state: dict, found: dict, now_iso: str, changes: list, alerts: list) -> None:
    readings, status = state.setdefault("readings", {}), state.setdefault("status", {})
    for key, new in found.items():
        st = status.setdefault(key, {})
        st["last_checked"] = now_iso
        old = readings.get(key)
        verdict = rules.validate_reading(new, old)
        if not verdict.accept:
            st["last_error"] = f"rejected: {verdict.reason}"
            alerts.append(f"{key}: new value rejected ({verdict.reason}); the old value stays on the site")
            continue
        st.pop("last_error", None)
        if old and fingerprint(old) == fingerprint(new):
            continue  # nothing new
        readings[key] = new
        st["last_updated"] = now_iso
        append_history(key, new)
        what = "revised" if verdict.revised else ("new" if not old else "updated")
        changes.append({"indicator": key, "kind": what, "from": old and old["display"], "to": new["display"],
                        "period": new["period_label"]})


def compute_signals(state: dict) -> dict[str, dict]:
    readings, out = state["readings"], {}
    previous = state.get("signals", {})
    for key in INDICATOR_IDS:
        r = readings.get(key)
        if not r:
            continue
        sig, reason = rules.signal_for(key, r, readings, read_history(key))
        if sig is None:
            keep = previous.get(key)
            if keep:
                sig, reason = keep["signal"], keep["reason"].split(" (kept")[0] + f" (kept from the last run: {reason})"
            else:
                sig, reason = "watch", f"{reason}; shown as watch closely until it can be judged"
        out[key] = {"signal": sig, "reason": reason}
    return out


def stale_flags(state: dict, today: dt.date, alerts: list) -> dict[str, str]:
    flags = {}
    for key in INDICATOR_IDS:
        r = state["readings"].get(key)
        if not r:
            flags[key] = "no data yet"
            alerts.append(f"{key}: no reading at all")
            continue
        age = (today - dt.date.fromisoformat(r["period_end"])).days
        if age > MAX_AGE_DAYS[key]:
            flags[key] = f"older than expected ({age} days since the period ended)"
            alerts.append(f"{key}: stale, last period ended {r['period_end']} ({age} days ago); "
                          f"last error: {state['status'].get(key, {}).get('last_error', 'none')}")
    return flags


def write_texts(state: dict, explainers: dict, signals: dict, use_ai: bool, alerts: list, changes: list) -> None:
    texts = state.setdefault("texts", {})
    writer = None
    if use_ai:
        try:
            import write_text
            writer = write_text.AIWriter()
        except Exception as e:
            alerts.append(f"AI text is on but could not start ({type(e).__name__}: {e}); fill-in text used")
    for key in INDICATOR_IDS:
        r = state["readings"].get(key)
        if not r:
            continue
        fp = fingerprint(r) + "|" + signals[key]["signal"] + "|" + textgen.TEXT_VERSION + ("|ai" if writer else "")
        if texts.get(key, {}).get("fingerprint") == fp:
            continue
        ex = explainers[key]
        result, source = None, "template"
        if writer:
            try:
                result, problems = writer.write(key, ex, r, signals[key])
                if problems:
                    alerts.append(f"{key}: AI text rejected ({'; '.join(problems)}); fill-in text used")
                    result = None
                else:
                    source = "ai"
            except Exception as e:
                alerts.append(f"{key}: AI text failed ({type(e).__name__}: {e}); fill-in text used")
                result = None
        if result is None:
            result = textgen.template_texts(key, ex["name"], r, signals[key]["signal"], signals[key]["reason"], ex["exampleGeneric"])
        texts[key] = {**result, "fingerprint": fp, "writer": source}
        changes.append({"indicator": key, "kind": f"text ({source})", "to": result["summary"]})


def compose_page_data(state: dict, explainers: dict, signals: dict, stale: dict) -> list[dict]:
    """The list the page script uses (same fields as before, plus a few new ones)."""
    out = []
    for key in INDICATOR_IDS:
        ex, r, t, s = explainers[key], state["readings"].get(key), state["texts"].get(key, {}), signals.get(key)
        if not r or not s:
            raise SystemExit(f"cannot build: {key} has no reading or signal")
        out.append({
            "id": ex["id"], "key": key, "step": ex["step"], "stepLabel": textgen.STEP_LABEL[ex["step"]],
            "name": ex["name"], "value": r["display"], "period": r["period_label"],
            "signal": s["signal"], "signalLabel": rules.LABEL[s["signal"]],
            "summary": t["summary"], "officialSource": r["source_name"], "sourceUrl": r["source_url"],
            "plainEnglishDefinition": ex["plainEnglishDefinition"], "whyItMatters": ex["whyItMatters"],
            "everydayIndianExample": t["everydayIndianExample"], "goodOrBadVerdict": t["goodOrBadVerdict"],
            "periodEnd": r["period_end"], "lastChecked": state["status"].get(key, {}).get("last_checked", ""),
            "stale": stale.get(key, ""),
        })
    return out


GAUGES = [  # the four "key health gauges": scale, healthy zone, reference line
    {"key": "gdp", "min": 3, "max": 10, "zone": [6.5, 7.0], "ref": 6.75, "refTitle": "Long-term trend 6.5% to 7.0%",
     "axis": ["3%", "Trend: 6.5% to 7.0%", "10%"]},
    {"key": "cpi", "min": 0, "max": 8, "zone": [2, 6], "ref": 6, "refTitle": "RBI upper limit 6.0%",
     "axis": ["0%", "RBI limit: 6.0%", "8%"]},
    {"key": "bank_credit", "min": 5, "max": 25, "zone": [12, 16], "ref": 16, "refTitle": "Upper healthy limit 16%",
     "axis": ["5%", "Healthy: 12% to 16%", "25%"]},
    {"key": "oecd_cli", "min": 98, "max": 103, "zone": [100, 103], "ref": 100, "refTitle": "Normal trend line 100.0",
     "axis": ["98.0", "Normal line: 100.0", "103.0"]},
]
# "You are here" marker: a point on the wave drawing for each phase (midpoints of each curve segment;
# late expansion sits near the peak).
MARKER = {"recovery": (160, 195), "expansion": (334, 81), "late_expansion": (386, 68), "slowdown": (510, 81),
          "contraction": (684, 195)}
STEP_HEAD = {"past": "🔎 *Past / lagging:*", "present": "⚡ *Present / coincident:*", "future": "🔦 *Future / leading:*"}


def compose_site(state: dict, explainers: dict, signals: dict, calendar: dict, today: dt.date, alerts: list) -> dict:
    readings, phase = state["readings"], state["phase"]
    names = {k: explainers[k]["name"] for k in INDICATOR_IDS}
    by = {s: [k for k in INDICATOR_IDS if signals.get(k, {}).get("signal") == s] for s in ("good", "watch", "warn")}
    counts = {"good": len(by["good"]), "watch": len(by["watch"]), "warn": len(by["warn"]), "total": len(INDICATOR_IDS)}
    summary = (f"{phase['reason'][0].upper() + phase['reason'][1:]}. {counts['good']} of {counts['total']} indicators are in good shape."
               + (f" Warning signs: {', '.join(names[k] for k in by['warn'])}." if by["warn"] else "")
               + (f" Watch closely: {', '.join(names[k] for k in by['watch'])}." if by["watch"] else ""))

    def pct(x, g):
        return round(min(max((x - g["min"]) / (g["max"] - g["min"]) * 100, 0), 100), 1)
    gauges = []
    for g in GAUGES:
        r, s = readings[g["key"]], signals[g["key"]]["signal"]
        gauges.append({
            "id": explainers[g["key"]]["id"], "name": names[g["key"]], "signal": s, "signalLabel": rules.LABEL[s],
            "period": f"{r['period_label']} ({r['source_name'].split(' ')[0]})", "display": r["display"].replace(" YoY", ""),
            "zoneLeft": pct(g["zone"][0], g), "zoneWidth": round(pct(g["zone"][1], g) - pct(g["zone"][0], g), 1),
            "refLeft": pct(g["ref"], g), "refTitle": g["refTitle"], "dotLeft": pct(r["value"], g), "axis": g["axis"],
        })

    upcoming = [e for e in calendar["events"] if dt.date.fromisoformat(e["end"]) >= today - dt.timedelta(days=2)]
    if len(upcoming) < 4:
        alerts.append(f"calendar: only {len(upcoming)} upcoming events left in data/calendar.json; add the next official release dates")
    signposts = []
    for e in upcoming[:4]:
        s, en = dt.date.fromisoformat(e["start"]), dt.date.fromisoformat(e["end"])
        label = s.strftime("%b %-d, %Y") if s == en else f"{s.strftime('%b %-d')} to {en.strftime('%-d, %Y')}"
        signposts.append({**e, "dateLabel": label})

    mk = "late_expansion" if phase["headline"] == "Late-stage expansion" else phase["key"]
    mx, my = MARKER[mk]
    pill_x = min(max(mx - 71, 60), 640)
    as_of = today.strftime("%B %-d, %Y")
    wa = [f"🇮🇳 *India Economic Health Monitor* ({today.strftime('%b %-d, %Y')})", "",
          f"📍 *Verdict: {phase['headline']}*", phase["reason"][0].upper() + phase["reason"][1:] + ".", "",
          f"📊 *Scorecard:* {counts['good']} Good | {counts['watch']} Watch closely | {counts['warn']} Warning signs"]
    for step in ("past", "present", "future"):
        wa += ["", STEP_HEAD[step]]
        wa += [f"- {names[k]}: {readings[k]['display']} ({rules.LABEL[signals[k]['signal']]})"
               for k in INDICATOR_IDS if explainers[k]["step"] == step and k in readings]
    if signposts:
        wa += ["", "🗓️ *Watch next:* " + " | ".join(f"{p['dateLabel']} {p['title']}" for p in signposts)]
    return {
        "asOf": as_of, "phaseKey": phase["key"], "phaseHeadline": phase["headline"], "verdictSummary": summary,
        "counts": counts, "gauges": gauges, "signposts": signposts, "whatsapp": "\n".join(wa),
        "marker": {"x": mx, "y": my, "pillX": pill_x, "lineX": pill_x + 71, "label": f"You are here: {phase['headline']}"},
        "youAreHereBadge": f"You are here ({today.strftime('%b %Y')})",
    }


def write_report(now: dt.datetime, log: list, changes: list, alerts: list, phase: tuple) -> Path:
    REPORTS.mkdir(exist_ok=True)
    lines = [f"# Update run {now.strftime('%d %b %Y, %H:%M IST')}", "",
             f"Phase: **{phase[1]}** ({phase[2]})", ""]
    lines += ["## Changes", ""] + ([f"- {c['indicator']}: {c['kind']}: {c.get('from') or ''} → {c['to']}" for c in changes] or ["- None"])
    lines += ["", "## Alerts (need a human look)", ""] + ([f"- {a}" for a in alerts] or ["- None"])
    lines += ["", "## Sources", ""] + [f"- {x['group']}: {x['outcome']}" + (f" ({x.get('message', '')[:160]})" if x.get("message") else "") for x in log]
    lines += ["", "To undo this run: revert its commit in GitHub (Commits → this commit → Revert)."]
    p = REPORTS / "last-run.md"
    p.write_text("\n".join(lines) + "\n", "utf8")
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--light", action="store_true")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    now = dt.datetime.now(IST)
    today, now_iso = now.date(), now.isoformat(timespec="seconds")
    state = load("latest.json", {"readings": {}, "status": {}, "texts": {}, "signals": {}})
    explainers = load("explainers.json", None)
    if not explainers or set(explainers) != set(INDICATOR_IDS):
        print("FAILED: data/explainers.json must describe exactly the 16 indicators", file=sys.stderr)
        return 1

    log, changes, alerts = [], [], []
    if not args.offline:
        found = fetch_all(state, args.light, log)
        apply_readings(state, found, now_iso, changes, alerts)
        for x in log:
            if x["outcome"] in ("error", "bug"):
                for k in GROUP_INDICATORS[x["group"]]:
                    st = state["status"].setdefault(k, {})
                    st["last_error"], st["last_checked"] = x["message"], now_iso
    signals = compute_signals(state)
    state["signals"] = signals
    stale = stale_flags(state, today, alerts)
    flat_signals = {k: v["signal"] for k, v in signals.items()}
    phase = rules.phase_for(state["readings"].get("oecd_cli"), flat_signals)
    use_ai = not args.no_ai and bool(os.environ.get("ANTHROPIC_API_KEY"))
    write_texts(state, explainers, signals, use_ai, alerts, changes)
    state["phase"] = {"key": phase[0], "headline": phase[1], "reason": phase[2]}
    state["last_run"] = now_iso

    for x in log:
        if x["outcome"] == "bug":
            alerts.append(f"BUG in {x['group']}: {x['message']}")
        elif x["outcome"] == "error" and x["group"] != "siam_vehicles":
            alerts.append(f"{x['group']}: {x['message'][:200]}")
    save("latest.json", state)
    save("indicators.json", compose_page_data(state, explainers, signals, stale))
    save("site.json", compose_site(state, explainers, signals, load("calendar.json", {"events": []}), today, alerts))
    LOGS.mkdir(exist_ok=True)
    (LOGS / f"run-{now.strftime('%Y%m%d-%H%M')}.json").write_text(
        json.dumps({"time": now_iso, "sources": log, "changes": changes, "alerts": alerts}, ensure_ascii=False, indent=1), "utf8")
    report = write_report(now, log, changes, alerts, phase)

    import build
    try:
        build.build(build.OUT)
    except build.BuildError as e:
        print(f"BUILD FAILED: {e}", file=sys.stderr)
        return 1
    print(report.read_text("utf8"))
    return 2 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
