"""Apprentice commitment parsing and gap analysis for Unwritten Craft.

The apprentice (see prompts/apprentice.md) replies with a JSON object of
per-step mechanical commitments. A parameter that comes back as the
geometric-neutral default — or that diverges across fresh runs — marks a
silence in the card: knowledge the teacher has but never wrote down.
"""
import json
import re

# Must match prompts/apprentice.md + prompts/apprentice_instruction.txt exactly.
# Craft-agnostic on purpose: motion (angle/force/duration/repetitions),
# material (tool/size/amount), and heat (temperature) — so the same
# contract serves baking, cooking, sewing, gardening, home repair.
DEFAULTS = {
    "tool": "unspecified",
    "angle_deg": 90,
    "force": "moderate",
    "force_location": "center",
    "duration_s": 10,
    "repetitions": 1,
    "size": "unspecified-medium",
    "amount": "unspecified-amount",
    "temperature": "ambient",
    "stopping_condition": "when the step's motion is complete",
}

PARAMETERS = list(DEFAULTS.keys())


def strip_wisdom(card_text):
    """Remove the card's '## What ... knows' wisdom section.

    The apprentice's first attempt runs on the steps only — the wisdom
    section is the teacher's judgment layer, captured AFTER her reaction
    (see the recorder flow), and it is withheld here so that "written
    wisdom transfers" stays a testable claim: run once steps-only, then
    once with --keep-wisdom, and compare. The wisdom section is always
    the card's last section, so everything from its heading on is cut.
    """
    lines = card_text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("## What ") and " know" in line:
            return "\n".join(lines[:i]).rstrip() + "\n"
    return card_text


def parse_commitments(raw):
    """Extract the commitment object from a raw model response.

    Tolerates code fences and surrounding prose by locating the outermost
    JSON object. Raises ValueError if no parseable object with a 'steps'
    list is present.
    """
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object found in response")
        text = text[start:end + 1]
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise ValueError("response JSON has no 'steps' list")
    return data["steps"]


def is_default(param, value):
    """True if a committed value equals the geometric-neutral default."""
    default = DEFAULTS[param]
    if isinstance(default, (int, float)) and isinstance(value, (int, float)):
        return abs(float(value) - float(default)) < 1e-9
    return str(value).strip().lower() == str(default).strip().lower()


def analyze(runs):
    """Compare parsed runs (list of step-lists) step by step.

    Returns a list of per-step dicts:
      {step, defaults: [params at default in EVERY run],
       missing: [params ABSENT from at least one run — the run failed to
                 commit, which is silence too, never "fully specified"],
       divergences: {param: [distinct values across runs]},
       sentences: [in_my_words from each run]}
    A step with many defaults/divergences/missing is where the card is silent.
    """
    if not runs:
        return []
    n_steps = max(len(r) for r in runs)
    report = []
    for idx in range(n_steps):
        step_no = idx + 1
        present = [r[idx] for r in runs if len(r) > idx]
        defaults, divergences, missing = [], {}, []
        for param in PARAMETERS:
            if any(param not in s for s in present):
                missing.append(param)
                continue
            values = [s.get(param) for s in present]
            if values and all(is_default(param, v) for v in values):
                defaults.append(param)
            distinct = {json.dumps(v, sort_keys=True) for v in values}
            if len(distinct) > 1:
                divergences[param] = sorted({str(v) for v in values})
        report.append({
            "step": step_no,
            "defaults": defaults,
            "missing": missing,
            "divergences": divergences,
            "sentences": [s.get("in_my_words", "") for s in present],
        })
    return report


def gap_score(step_report):
    """Silence score: defaults and missing count double, divergences single."""
    return (2 * len(step_report["defaults"]) + 2 * len(step_report.get("missing", []))
            + len(step_report["divergences"]))


def render_report(card_title, runs, analysis):
    lines = [
        f"# Gap report — {card_title}",
        "",
        f"Fresh apprentice runs analyzed: {len(runs)}",
        "",
        "A parameter at its default in every run, or diverging across runs, "
        "marks a place where the card is silent — a candidate Trick.",
        "",
    ]
    ranked = sorted(analysis, key=gap_score, reverse=True)
    for s in ranked:
        lines.append(f"## Step {s['step']} — silence score {gap_score(s)}")
        if s["defaults"]:
            lines.append(f"- At default in every run: {', '.join(s['defaults'])}")
        if s.get("missing"):
            lines.append(f"- Missing from a run (no commitment made): {', '.join(s['missing'])}")
        for param, values in s["divergences"].items():
            lines.append(f"- Diverges across runs — {param}: {' | '.join(values)}")
        if not s["defaults"] and not s["divergences"] and not s.get("missing"):
            lines.append("- Fully specified and consistent: the card carries this step.")
        for sent in s["sentences"]:
            if sent:
                lines.append(f"  > Apprentice: \"{sent}\"")
        lines.append("")
    return "\n".join(lines)
