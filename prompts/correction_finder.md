# Correction finder — prompt

You are given the timestamped transcript of a lesson: a mentor teaching a
beginner a hands-on craft. There are no speaker labels. The mentor's
speech dominates; the beginner asks questions and narrates their attempts.

Your job: find the **correction moments** — every moment where the mentor
corrects how the beginner is performing the craft, or corrects a wrong
belief the beginner states about how it is done. A correction is about the
work itself: a movement, a force, a sequence, a stopping condition, a
handling choice.

Do NOT report:
- Answers to the beginner's questions that correct a fact about objects,
  ingredients, or logistics (which bowl, shopping, schedules).
- The mentor correcting their own wording or quantities as they speak.
- The beginner's self-talk, including when they say they have got it now.
- General instruction that is not a response to something the beginner did
  or said they would do.

For each correction, output one object:
- "start": the timestamp, exactly as it appears in the transcript, of the
  segment where the correction begins.
- "quote": the mentor's exact words of correction, copied from the
  transcript (the key sentence or two, not the whole segment).
- "correcting": one short phrase naming what they were doing or believing
  that the mentor corrected.
- "segment": a short noun phrase naming the visible subject of the
  correction for the camera — the hands, tool, or material the viewer
  should watch (e.g. "person's hands", "knife", "dough"). Use ""
  when the correction has no visible subject.

Output ONLY a JSON array of these objects, in transcript order. No prose,
no code fences. If there are no corrections, output [].
