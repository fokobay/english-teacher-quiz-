"""
Posts photos, videos, text, and polls to Telegram.
Adds a header label per lesson type.
"""

import os
import re
import requests
from pathlib import Path
from typing import Optional
from src.logger import setup_logger

logger    = setup_logger("poster")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BASE_URL  = f"https://api.telegram.org/bot{BOT_TOKEN}"

TYPE_LABELS = {
    "vocabulary":            "📖 Word of the Day",
    "grammar":               "📐 Grammar Lesson",
    "idioms":                "🗣 English Idiom",
    "pronunciation":         "🎤 Pronunciation Fix",
    "common_mistakes":       "⚠️ Common Mistake",
    "phrases":               "💬 Daily Phrases",
    "fun_fact":              "🤯 English Fun Fact",
    "slang":                 "😎 English Slang",
    "business_english":      "💼 Business English",
    "phrasal_verbs":         "🔗 Phrasal Verb",
    "confusing_words":       "🤔 Confusing Words",
    "writing_tips":          "✍️ Writing Tip",
    "prepositions":          "📌 Prepositions",
    "collocations":          "🔤 Collocations",
    "american_vs_british":   "🌍 American vs British",
    "word_origins":          "🏛 Word Origin",
    "synonyms_nuance":       "🎨 Synonyms & Nuance",
    "sentence_starters":     "🚀 Sentence Starters",
    "linking_words":         "🔗 Linking Words",
    "formal_vs_informal":    "👔 Formal vs Informal",
    "numbers_and_dates":     "🔢 Numbers & Dates",
    "questions_forms":       "❓ Question Forms",
    "modal_verbs":           "🎯 Modal Verbs",
    "passive_voice":         "🔄 Passive Voice",
    "conditionals":          "🔀 Conditionals",
    "reported_speech":       "💬 Reported Speech",
    "articles":              "📎 Articles",
    "punctuation":           "✏️ Punctuation",
    "word_families":         "🌳 Word Families",
    "expressions_with_time": "⏰ Time Expressions",
    "body_language_vocab":   "🤸 Body Language",
    "food_and_cooking":      "🍽 Food & Cooking",
    "travel_english":        "✈️ Travel English",
    "email_phrases":         "📧 Email Phrases",
    "small_talk":            "💬 Small Talk",
}


def _build_caption(text: str, post_type: str, max_len: int = 1024) -> str:
    label   = TYPE_LABELS.get(post_type, "📚 English Lesson")
    divider = "─" * 28
    text    = re.sub(r"\*(.+?)\*",             r"<b>\1</b>", text)
    text    = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", text)
    return f"<b>{label}</b>\n{divider}\n\n{text}"[:max_len]


class TelegramPoster:

    def post_photo(self, caption: str, image_path: Path,
                   chat_id: str, post_type: str = "") -> str:
        logger.info(f"Posting photo → {chat_id}")
        with open(image_path, "rb") as f:
            r = requests.post(
                f"{BASE_URL}/sendPhoto",
                data={"chat_id": chat_id,
                      "caption": _build_caption(caption, post_type, max_len=1024),
                      "parse_mode": "HTML"},
                files={"photo": f},
                timeout=40,
            )
        r.raise_for_status()
        msg_id = str(r.json()["result"]["message_id"])
        logger.info(f"Photo posted ✓ id={msg_id}")
        return msg_id

    def post_video(self, caption: str, video_path: Path,
                   chat_id: str, post_type: str = "") -> str:
        logger.info(f"Posting video → {chat_id}")
        with open(video_path, "rb") as f:
            r = requests.post(
                f"{BASE_URL}/sendVideo",
                data={"chat_id": chat_id,
                      "caption": _build_caption(caption, post_type, max_len=1024),
                      "parse_mode": "HTML",
                      "supports_streaming": "true"},
                files={"video": f},
                timeout=120,
            )
        r.raise_for_status()
        msg_id = str(r.json()["result"]["message_id"])
        logger.info(f"Video posted ✓ id={msg_id}")
        return msg_id

    def post_text(self, caption: str, chat_id: str, post_type: str = "") -> str:
        logger.info(f"Posting text → {chat_id}")
        r = requests.post(
            f"{BASE_URL}/sendMessage",
            json={"chat_id": chat_id,
                  "text": _build_caption(caption, post_type, max_len=4096),
                  "parse_mode": "HTML"},
            timeout=20,
        )
        r.raise_for_status()
        msg_id = str(r.json()["result"]["message_id"])
        logger.info(f"Text posted ✓ id={msg_id}")
        return msg_id

    def post_poll(self, quiz: dict, chat_id: str) -> Optional[str]:
        try:
            r = requests.post(
                f"{BASE_URL}/sendPoll",
                json={
                    "chat_id":                 chat_id,
                    "question":                ("🧠 " + quiz["question"])[:300],
                    "options":                 quiz["options"],
                    "type":                    "quiz",
                    "correct_option_id":       quiz["correct_index"],
                    "explanation":             ("✅ " + quiz.get("explanation", ""))[:200],
                    "is_anonymous":            True,
                    "allows_multiple_answers": False,
                },
                timeout=20,
            )
            r.raise_for_status()
            msg_id = str(r.json()["result"]["message_id"])
            logger.info(f"Poll posted ✓ id={msg_id}")
            return msg_id
        except Exception as e:
            logger.warning(f"Poll failed: {e}")
            return None
