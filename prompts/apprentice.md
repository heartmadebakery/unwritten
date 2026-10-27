# Apprentice — the blind learner contract (Step 2)

The apprentice is a fresh model call. Its **entire** context is the card
text plus the instruction below. No interview, no photo, no hints. This
boundary is the product: the apprentice must fail where the card is silent,
and it must fail *honestly* — so it is never told to play dumb, be clumsy,
or imagine it is a beginner.

What keeps the failure honest: the apprentice must **commit** to
concrete mechanical parameters for every action, derived *only* from what
the card explicitly states. Any parameter the card does not specify must be
filled with the **geometric-neutral default** listed below — not with
learned domain intuition. A model following this contract literally will
produce expert-sounding prose nowhere; it can only produce the card, plus
defaults. Where its commitments look wrong to the teacher, the card was
silent — that silence is a technique waiting to be taught.

## Instruction given to the apprentice (verbatim)

> You will be given a short instruction card written by a teacher for one
> hands-on task. It is the only information you may use. Do not use any
> prior knowledge of this craft, even if you have it.
>
> For each numbered step on the card, state exactly what you would
> physically do, committing to concrete values for every parameter below.
> If the card does not specify a parameter, use the DEFAULT — do not
> substitute experience or common practice.
>
> Parameters and defaults:
> - `tool` — the tool or implement used for this step.
>   DEFAULT: `unspecified`.
> - `angle_deg` — angle of the tool or hand relative to the work surface.
>   DEFAULT: 90 (perpendicular).
> - `force` — one of `light`, `moderate`, `firm`, `maximum`.
>   DEFAULT: `moderate`, applied uniformly.
> - `force_location` — where the force is applied (e.g. center, edge,
>   heel of hand). DEFAULT: `center`.
> - `duration_s` — how long the action lasts, in seconds.
>   DEFAULT: 10.
> - `repetitions` — how many times the action repeats. DEFAULT: 1.
> - `size` — any size the action targets (e.g. pea-sized, 2 cm), in your
>   own words. DEFAULT: `unspecified-medium`.
> - `amount` — how much material the step uses (per piece, per batch,
>   per pass). DEFAULT: `unspecified-amount`.
> - `temperature` — heat the step works at, in the card's own terms or
>   numbers (e.g. shimmering oil, 350 degrees, cold hands).
>   DEFAULT: `ambient`.
> - `stopping_condition` — how you know the step is done.
>   DEFAULT: `when the step's motion is complete`.
>
> The card may include a "What the teacher knows" section of notes and
> judgment. Anything written anywhere on the card is yours to use —
> written knowledge transfers. Only what is NOT written is missing;
> never fill a gap in the notes with prior knowledge either.
>
> Also write one sentence, `in_my_words`, saying what you are doing in
> this step and why — using only ideas present on the card.
>
> Reply with a single JSON object, no other text:
> `{"steps": [{"step": 1, "tool": ..., "angle_deg": ..., "force": ..., "force_location": ..., "duration_s": ..., "repetitions": ..., "size": ..., "amount": ..., "temperature": ..., "stopping_condition": "...", "in_my_words": "..."}]}`
>
> The card follows:
> ---
> <CARD TEXT>
> ---

## Why defaults, not intuition

If the apprentice were allowed its training, it would autocomplete the
teacher's tacit knowledge (it has read every bread forum on the internet)
and the gap would never show. Defaults make the boundary *mechanical*:
correctness can only come from the card. This also makes runs comparable —
a parameter that comes back as the default, or that diverges across fresh
runs, marks a silence in the card.
