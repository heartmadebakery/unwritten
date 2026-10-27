# Correction finder — prompt

You are given the timestamped transcript of a lesson: a teacher teaching a
beginner a hands-on craft. There are no speaker labels. The teacher's
speech dominates; the beginner asks questions and narrates his attempts.

Your job: find the **correction moments** — every moment where the teacher
corrects how the beginner is performing the craft, or corrects a wrong
belief the beginner states about how it is done. A correction is about the
work itself: a movement, a force, a sequence, a stopping condition, a
handling choice.

Do NOT report:
- Answers to the beginner's questions that correct a fact about objects,
  ingredients, or logistics (which bowl, shopping, schedules).
- The teacher correcting her own wording or quantities as she speaks.
- The beginner's self-talk, including when he says he has got it now.
- General instruction that is not a response to something the beginner did
  or said he would do.

For each correction, output one object:
- "start": the timestamp, exactly as it appears in the transcript, of the
  segment where the correction begins.
- "quote": the teacher's exact words of correction, copied from the
  transcript (the key sentence or two, not the whole segment).
- "correcting": one short phrase naming what he was doing or believing
  that she corrected.

Output ONLY a JSON array of these objects, in transcript order. No prose,
no code fences. If there are no corrections, output [].
