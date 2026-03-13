"""
Generates English quiz questions via Groq.
Question types (all as Telegram Quiz Polls):
  - mcq         : 4-option multiple choice
  - tf          : True / False
  - fill_blank  : fill in the blank (4 options)
  - odd_one_out : which word doesn't belong (4 options)
  - match_def   : match word to definition (4 options)
  - error_spot  : spot the grammar error (4 options)
  - complete_sent: complete the sentence (4 options)
  - word_form   : correct word form (4 options)
Covers easy / medium / hard — wide topic variety.
"""
import os, re, json, random
from groq import Groq
from src.logger import setup_logger

log = setup_logger("generator")

SYSTEM = (
    "You are an expert English quiz maker for Telegram. "
    "Return ONLY a valid JSON array — no markdown, no extra text."
)

# ── Per-type prompts ──────────────────────────────────────────────────

PROMPTS = {

"mcq": """Create {n} English multiple-choice questions.
Topics: vocabulary, grammar, idioms, phrasal verbs, collocations, prepositions, synonyms, spelling.
Mix: easy, medium, hard.

Return ONLY this JSON array:
[{{"type":"mcq","question":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},"correct":"B","difficulty":"medium","explanation":"✅ [answer]\\n💡 [reason, max 150 chars]"}}]

Rules: type=mcq, correct in A-D, all 4 options plausible, no repeated topics.""",

"tf": """Create {n} English True/False questions.
Topics: grammar rules, vocabulary facts, idiom meanings, spelling, pronunciation facts.
Make roughly half True and half False. Mix: easy, medium, hard.

Return ONLY this JSON array:
[{{"type":"tf","question":"TRUE or FALSE: ...","correct":"True","difficulty":"easy","explanation":"✅ [True/False]\\n💡 [reason, max 150 chars]"}}]

Rules: type=tf, question starts with "TRUE or FALSE:", correct is exactly "True" or "False".""",

"fill_blank": """Create {n} fill-in-the-blank English questions. A sentence with ONE blank.
4 options — only one is correct. Topics: grammar, vocabulary, prepositions, articles, collocations.
Mix: easy, medium, hard.

Return ONLY this JSON array:
[{{"type":"fill_blank","question":"Choose the correct word: \\"She was ___ to the party.\\"","options":{{"A":"invite","B":"invited","C":"inviting","D":"invitation"}},"correct":"B","difficulty":"medium","explanation":"✅ invited\\n💡 [reason, max 150 chars]"}}]

Rules: type=fill_blank, blank shown as ___, correct in A-D, all options same word family or related.""",

"odd_one_out": """Create {n} "odd one out" English vocabulary questions.
Give 4 words — 3 share a category/theme, 1 doesn't belong.
Topics: word categories, parts of speech, register, connotation, word families.
Mix: easy, medium, hard.

Return ONLY this JSON array:
[{{"type":"odd_one_out","question":"Which word does NOT belong?\\nA) happy  B) joyful  C) content  D) angry","options":{{"A":"happy","B":"joyful","C":"content","D":"angry"}},"correct":"D","difficulty":"easy","explanation":"✅ angry\\n💡 [reason, max 150 chars]"}}]

Rules: type=odd_one_out, exactly one odd word, clear logical reason.""",

"match_def": """Create {n} "match the definition" questions.
Give a definition or explanation, ask which word matches.
Topics: advanced vocabulary, idioms, phrasal verbs, formal words.
Mix: easy, medium, hard.

Return ONLY this JSON array:
[{{"type":"match_def","question":"Which word means: \\"feeling worried and nervous\\"?","options":{{"A":"anxious","B":"furious","C":"content","D":"bored"}},"correct":"A","difficulty":"easy","explanation":"✅ anxious\\n💡 [reason, max 150 chars]"}}]

Rules: type=match_def, definition is clear and unambiguous, only one option fits.""",

"error_spot": """Create {n} error-spotting questions.
Show a sentence, ask which version has the correct grammar (or which has the error).
Topics: subject-verb agreement, tense, articles, prepositions, word order.
Mix: easy, medium, hard.

Return ONLY this JSON array:
[{{"type":"error_spot","question":"Which sentence is CORRECT?","options":{{"A":"She don't like coffee.","B":"She doesn't likes coffee.","C":"She doesn't like coffee.","D":"She not like coffee."}},"correct":"C","difficulty":"easy","explanation":"✅ She doesn't like coffee.\\n💡 [reason, max 150 chars]"}}]

Rules: type=error_spot, only ONE option is fully correct, errors in others must be clear.""",

"complete_sent": """Create {n} sentence completion questions.
Give the beginning of a sentence, ask which ending is correct or most natural.
Topics: conditionals, reported speech, collocations, linking words, formal phrases.
Mix: easy, medium, hard.

Return ONLY this JSON array:
[{{"type":"complete_sent","question":"If I had more time, I ___ travel the world.","options":{{"A":"will","B":"would","C":"can","D":"shall"}},"correct":"B","difficulty":"medium","explanation":"✅ would\\n💡 [reason, max 150 chars]"}}]

Rules: type=complete_sent, only one option makes the sentence grammatically and naturally correct.""",

"word_form": """Create {n} word form questions.
Give a base word and a sentence with a blank — choose the correct word form.
Topics: nouns/verbs/adjectives/adverbs, suffixes, prefixes, word families.
Mix: easy, medium, hard.

Return ONLY this JSON array:
[{{"type":"word_form","question":"Use the correct form of \\"create\\":\\n\\"She showed great ___ in her work.\\"","options":{{"A":"create","B":"creative","C":"creation","D":"creativity"}},"correct":"D","difficulty":"medium","explanation":"✅ creativity\\n💡 [reason, max 150 chars]"}}]

Rules: type=word_form, base word clearly stated, blank fits only one form grammatically.""",

}

# How many of each type per quiz (total = 20)
DISTRIBUTION = [
    ("mcq",          5),
    ("tf",           3),
    ("fill_blank",   3),
    ("odd_one_out",  2),
    ("match_def",    2),
    ("error_spot",   2),
    ("complete_sent",2),
    ("word_form",    1),
]


class Generator:
    def __init__(self):
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])

    def generate(self) -> list:
        log.info("Generating 20 questions (8 types)...")
        all_questions = []

        for qtype, count in DISTRIBUTION:
            batch = self._batch(qtype, count)
            all_questions.extend(batch)
            log.info(f"  {qtype}: {len(batch)}/{count} ✓")

        random.shuffle(all_questions)
        log.info(f"Total ready: {len(all_questions)} questions")
        return all_questions[:20]

    def _batch(self, qtype: str, n: int) -> list:
        prompt = PROMPTS[qtype].format(n=n)
        for attempt in range(3):
            try:
                res = self.client.chat.completions.create(
                    model       = "llama-3.3-70b-versatile",
                    messages    = [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    temperature = 0.85,
                    max_tokens  = 2000,
                )
                raw = res.choices[0].message.content.strip()
                raw = re.sub(r"```(?:json)?\s*", "", raw)
                raw = re.sub(r"```", "", raw)
                m   = re.search(r"\[.*\]", raw, re.DOTALL)
                if m:
                    raw = m.group(0)

                questions = json.loads(raw)
                valid     = [q for q in questions if self._valid(q, qtype)]

                if len(valid) >= max(n - 1, 1):
                    return valid[:n]

                log.warning(f"  {qtype} attempt {attempt+1}: {len(valid)} valid — retrying")

            except Exception as e:
                log.warning(f"  {qtype} attempt {attempt+1} failed: {e}")

        return []

    def _valid(self, q: dict, qtype: str) -> bool:
        if q.get("type") != qtype:
            return False
        if not isinstance(q.get("question"), str) or len(q["question"]) < 5:
            return False
        if q.get("difficulty") not in ("easy", "medium", "hard"):
            return False
        if qtype == "tf":
            return (
                q.get("correct") in ("True", "False")
                and "TRUE OR FALSE" in q.get("question","").upper()
            )
        # All other types use A/B/C/D options
        return (
            isinstance(q.get("options"), dict)
            and len(q["options"]) == 4
            and all(k in q["options"] for k in ("A","B","C","D"))
            and q.get("correct") in ("A","B","C","D")
        )
