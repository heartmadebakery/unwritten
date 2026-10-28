"""
RETIRED (Oct 27, 2026): the blind-apprentice design was cut. Not called by
the core pipeline; kept in the tree as a retired experiment.

Apprentice commitment parsing and gap analysis for Unwritten Craft.

The apprentice (see prompts/apprentice.md) replies with a JSON object of
per-step mechanical commitments. A parameter that comes back as the
geometric-neutral default — or that diverges across fresh runs, or that
a run fails to commit at all — marks a silence in the card: knowledge
the teacher has but never wrote down.

Hardened after the Muse Wonder full-code review (Oct 26): values are
canonicalised once (90 == 90.0 == "90", "Moderate" == "moderate") so a
parameter can never be both default and divergent; steps are keyed by
their `step` number, not position; a step attempted by a minority of
runs counts its unattempted parameters as missing, never as specified;
None/empty commitments count as missing; the wisdom strip is
case/level-insensitive and bounded to its own section.
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

WISDOM_HEADING = re.compile(r"^\s*#{2,}\s+what\b.*\bknow", re.IGNORECASE)


def canon(param, value):
    """Canonical form of a committed value, used for BOTH the default
    test and divergence detection so the two can never disagree."""
    if value is None:
        return None
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    try:
        return float(text)
    except ValueError:
        return text


def is_missing_value(value):
    return value is None or (isinstance(value, str) and value.strip() == "")


def parse_commitments(raw):
    """Extract the commitment object from a raw model response.

    Tries each fenced block, then the outermost brace span; the first
    candidate that parses to an object with a 'steps' list of dicts
    wins. Raises ValueError if none does.
    """
    candidates = []
    for block in re.findall(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL):
        s, e = block.find("{"), block.rfind("}")
        if s != -1 and e > s:
            candidates.append(block[s:e + 1])
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start:end + 1])
    last_err = None
    for cand in candidates:
        try:
            data = json.loads(cand)
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
            continue
        if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
            last_err = ValueError("response JSON has no 'steps' list")
            continue
        for s in data["steps"]:
            if not isinstance(s, dict):
                raise ValueError("a step is not an object")
        return data["steps"]
    raise ValueError(f"no parseable commitment object ({last_err})")


def is_default(param, value):
    """True if a committed value equals the geometric-neutral default."""
    if is_missing_value(value):
        return False
    return canon(param, value) == canon(param, DEFAULTS[param])


def _step_key(step_dict, idx):
    n = step_dict.get("step")
    if isinstance(n, int) and not isinstance(n, bool) and n >= 1:
        return n
    return idx + 1


def analyze(runs):
    """Compare parsed runs (list of step-lists) step by step.

    Steps are aligned by their `step` number. Returns per-step dicts:
      {step, n_present, n_runs, defaults, missing, divergences, sentences}
    - defaults: params at default in every run that attempted the step
    - missing: params absent/null/empty in some attempting run, plus
      every param for runs that never attempted the step at all
    - divergences: params whose canonical values differ across runs
    A step with many defaults/divergences/missing is where the card
    is silent. "Fully specified" is impossible unless every run
    attempted the step and committed every parameter consistently.
    """
    if not runs:
        return []
    keyed = []
    for run in runs:
        d = {}
        for idx, s in enumerate(run):
            d[_step_key(s, idx)] = s
        keyed.append(d)
    all_steps = sorted({k for d in keyed for k in d})
    report = []
    for step_no in all_steps:
        present = [d[step_no] for d in keyed if step_no in d]
        n_present = len(present)
        defaults, divergences, missing = [], {}, []
        for param in PARAMETERS:
            absent_runs = n_present < len(runs)
            values, has_missing = [], False
            for s in present:
                if param not in s or is_missing_value(s.get(param)):
                    has_missing = True
                else:
                    values.append(s[param])
            if has_missing or absent_runs:
                missing.append(param)
            if values and all(is_default(param, v) for v in values):
                defaults.append(param)
            distinct = {json.dumps(canon(param, v), sort_keys=True) for v in values}
            if len(distinct) > 1:
                divergences[param] = sorted({str(v) for v in values})
        report.append({
            "step": step_no,
            "n_present": n_present,
            "n_runs": len(runs),
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


def strip_wisdom(card_text):
    """Remove the card's wisdom section ('## What ... knows').

    Matching is case- and level-insensitive. The cut runs from the
    wisdom heading to the next level-2 heading or end of card, so
    anything filed after the wisdom section survives.
    """
    lines = card_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if WISDOM_HEADING.match(line):
            start = i
            break
    if start is None:
        return card_text
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^\s*##\s+", lines[j]):
            end = j
            break
    return "\n".join(lines[:start] + lines[end:]).rstrip() + "\n"


def has_wisdom_section(card_text):
    return any(WISDOM_HEADING.match(line) for line in card_text.splitlines())


def render_report(card_title, runs, analysis, notes=""):
    lines = [
        f"# Gap report — {card_title}",
        "",
        f"Fresh apprentice runs analyzed: {len(runs)}",
    ]
    if notes:
        lines.append(notes)
    lines += [
        "",
        "A parameter at its default in every run, diverging across runs, "
        "or missing from a run marks a place where the card is silent — "
        "a candidate technique.",
        "",
    ]
    ranked = sorted(analysis, key=gap_score, reverse=True)
    for s in ranked:
        lines.append(f"## Step {s['step']} — silence score {gap_score(s)}"
                     f" (attempted by {s.get('n_present', len(runs))} of {s.get('n_runs', len(runs))} runs)")
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
