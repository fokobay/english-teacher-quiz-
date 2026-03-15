"""
Generates a 4-option quiz poll via Groq based on lesson content.
"""

import os
import re
import json
from typing import Optional
from groq import Groq
from src.logger import setup_logger

logger = setup_logger("quiz")

SYSTEM = (
    "You are an English teacher making a 4-option multiple choice quiz. "
    "Respond with valid JSON ONLY — no markdown, no extra text."
)

TYPE_HINTS = {
    "vocabulary":           "Ask about the word's meaning or correct usage in a sentence.",
    "grammar":              "Ask which sentence correctly applies the grammar rule taught.",
    "idioms":               "Ask what the idiom means in real life.",
    "pronunciation":        "Ask which pronunciation version is correct.",
    "common_mistakes":      "Ask which sentence is grammatically correct.",
    "phrases":              "Ask when or why you would use one of the phrases taught.",
    "fun_fact":             "Ask a factual question directly about the fun fact shared.",
    "slang":                "Ask what the slang expression means or when it should be used.",
    "business_english":     "Ask how to use the business phrase correctly in a professional context.",
    "phrasal_verbs":        "Ask what the phrasal verb means or which sentence uses it correctly.",
    "confusing_words":      "Ask which word correctly completes a given sentence.",
    "writing_tips":         "Ask which sentence is stronger or follows the writing tip taught.",
    "prepositions":         "Ask which preposition correctly completes a sentence.",
    "collocations":         "Ask which word naturally collocates with the key word taught.",
    "american_vs_british":  "Ask which word is American English vs British English.",
    "word_origins":         "Ask a factual question about the word's origin or meaning.",
    "synonyms_nuance":      "Ask which synonym best fits a specific context or sentence.",
    "sentence_starters":    "Ask which sentence starter fits a given communicative function.",
    "linking_words":        "Ask which linking word correctly connects two given ideas.",
    "formal_vs_informal":   "Ask whether a given phrase is formal or informal.",
    "numbers_and_dates":    "Ask how to correctly say a number, date, or time in English.",
    "questions_forms":      "Ask which question form is grammatically correct.",
    "modal_verbs":          "Ask which modal verb is correct for a given context.",
    "passive_voice":        "Ask which sentence correctly uses the passive voice.",
    "conditionals":         "Ask which conditional form correctly completes a sentence.",
    "reported_speech":      "Ask how to correctly report a direct speech sentence.",
    "articles":             "Ask which article (a/an/the/no article) is correct in a sentence.",
    "punctuation":          "Ask which sentence uses the punctuation mark correctly.",
    "word_families":        "Ask which word form (noun/verb/adjective/adverb) fits a blank.",
    "expressions_with_time":"Ask what a time expression means or when it is used.",
    "body_language_vocab":  "Ask what a body language word or phrase describes.",
    "food_and_cooking":     "Ask the meaning of a cooking term or food vocabulary word.",
    "travel_english":       "Ask which phrase is appropriate for a given travel situation.",
    "email_phrases":        "Ask which phrase is appropriate for the email function taught.",
    "small_talk":           "Ask which phrase is most natural for the social situation described.",
}


class QuizGenerator:
    def __init__(self):
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])

    def generate(self, post_type: str, content_text: str) -> Optional[dict]:
        hint   = TYPE_HINTS.get(post_type, "Ask a relevant question about the lesson.")
        prompt = (
            f"Based on this English lesson:\n---\n{content_text[:700]}\n---\n\n"
            f"{hint}\n\n"
            'Return ONLY:\n'
            '{"question":"<max 100 chars>","options":["A","B","C","D"],"correct_index":0,"explanation":"<max 80 chars>"}\n\n'
            "Rules: correct_index is 0-3, wrong options must be plausible, all options similar length."
        )
        try:
            res = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.7,
                max_tokens=350,
            )
            raw = res.choices[0].message.content.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
            raw = re.sub(r"```\s*$",          "", raw, flags=re.MULTILINE)
            m   = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                raw = m.group(0)
            quiz = json.loads(raw)
            assert "question" in quiz
            assert len(quiz.get("options", [])) == 4
            assert 0 <= quiz.get("correct_index", -1) <= 3
            logger.info(f"Quiz ready: {quiz['question'][:60]}")
            return quiz
        except Exception as e:
            logger.warning(f"Quiz failed: {e}")
            return None
