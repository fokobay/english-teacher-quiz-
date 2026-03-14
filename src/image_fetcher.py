"""
Fetches images: Pexels → Pixabay → Unsplash (round-robin).
Uses AI-generated keywords from lesson content.
"""

import os
import requests
from pathlib import Path
from typing import Optional
from src.logger import setup_logger

logger = setup_logger("images")

FALLBACK_KEYWORDS = {
    "vocabulary":           ["open book reading", "dictionary desk", "student studying words"],
    "grammar":              ["writing notebook pen", "chalkboard grammar", "editing paper red pen"],
    "idioms":               ["people talking cafe", "speech bubble conversation", "friends laughing"],
    "pronunciation":        ["microphone speaking mouth", "sound waves audio", "person speaking close"],
    "common_mistakes":      ["red pen correction paper", "editing writing desk", "mistake correction"],
    "phrases":              ["people conversation daily", "friends talking coffee", "communication scene"],
    "fun_fact":             ["lightbulb idea bright", "magnifying glass discovery", "brain thinking"],
    "slang":                ["young people talking", "casual friends street", "youth culture chat"],
    "business_english":     ["professional office meeting", "business people laptop", "corporate workplace"],
    "phrasal_verbs":        ["action movement person", "daily activity scene", "people doing things"],
    "confusing_words":      ["two similar objects", "choice decision crossroads", "comparison side by side"],
    "writing_tips":         ["person writing journal", "laptop writing coffee", "notebook pen creative"],
    "prepositions":         ["map location direction", "arrows path movement", "spatial relationship"],
    "collocations":         ["words connection link", "language pattern book", "vocabulary combination"],
    "american_vs_british":  ["usa uk flag together", "american british comparison", "two countries culture"],
    "word_origins":         ["ancient history book", "etymology dictionary old", "historical manuscript"],
    "synonyms_nuance":      ["color shades gradient", "subtle difference detail", "spectrum variation"],
    "sentence_starters":    ["person beginning speech", "opening paragraph writing", "start line runner"],
    "linking_words":        ["chain links connected", "bridge connection path", "flow diagram arrows"],
    "formal_vs_informal":   ["suit casual clothes comparison", "formal informal dress", "professional vs casual"],
    "numbers_and_dates":    ["calendar numbers desk", "clock time date", "digits numbers close"],
    "questions_forms":      ["question mark large", "curious person thinking", "interview microphone"],
    "modal_verbs":          ["possibility choice doors", "permission sign allowed", "obligation duty"],
    "passive_voice":        ["action object focus", "passive scene observation", "receiving action"],
    "conditionals":         ["fork road decision", "if then scenario", "cause effect domino"],
    "reported_speech":      ["person relaying message", "telephone conversation relay", "gossip whisper"],
    "articles":             ["specific object spotlight", "the vs a comparison", "singular unique item"],
    "punctuation":          ["punctuation marks close", "editing document symbols", "comma period text"],
    "word_families":        ["tree branches growth", "family tree roots", "words transform change"],
    "expressions_with_time":["clock face close", "hourglass time passing", "calendar deadline rush"],
    "body_language_vocab":  ["person facial expression", "body language gesture", "nonverbal communication"],
    "food_and_cooking":     ["kitchen cooking food", "chef preparing meal", "restaurant food close"],
    "travel_english":       ["airport travel suitcase", "tourist map exploring", "travel adventure scene"],
    "email_phrases":        ["laptop email typing", "professional email office", "person writing computer"],
    "small_talk":           ["people chatting casually", "friendly conversation smile", "social gathering talk"],
}

_source_idx = 0


class ImageFetcher:
    def __init__(self):
        self.pexels   = os.environ.get("PEXELS_API_KEY", "")
        self.pixabay  = os.environ.get("PIXABAY_API_KEY", "")
        self.unsplash = os.environ.get("UNSPLASH_ACCESS_KEY", "")

    def fetch(self, post_type: str, save_path: Path, keywords: list = None) -> Optional[Path]:
        global _source_idx
        kw_pool = keywords if keywords else FALLBACK_KEYWORDS.get(post_type, ["education learning"])
        sources = [self._pexels, self._pixabay, self._unsplash]

        # جرب كل keyword من الـ 3 على التوالي (من الأكثر تحديداً للأقل)
        for kw in kw_pool:
            for i in range(3):
                idx = (_source_idx + i) % 3
                url = sources[idx](kw)
                if url and self._download(url, save_path):
                    _source_idx = (idx + 1) % 3
                    logger.info(f"Image ok [{['Pexels','Pixabay','Unsplash'][idx]}] '{kw}'")
                    return save_path

        # Fallback: keywords عامة للنوع
        fallback_pool = FALLBACK_KEYWORDS.get(post_type, ["education learning", "student study"])
        for fb in fallback_pool:
            for src in sources:
                url = src(fb)
                if url and self._download(url, save_path):
                    logger.info(f"Image fallback '{fb}'")
                    return save_path

        logger.warning("All image sources failed")
        return None

    # ── Sources ──────────────────────────────────────────────────────

    def _pexels(self, q: str) -> Optional[str]:
        if not self.pexels:
            return None
        try:
            r = requests.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": self.pexels},
                params={"query": q, "per_page": 15, "orientation": "square"},
                timeout=10,
            )
            r.raise_for_status()
            photos = r.json().get("photos", [])
            return random.choice(photos)["src"]["large"] if photos else None
        except Exception as e:
            logger.warning(f"Pexels error: {e}")
            return None

    def _pixabay(self, q: str) -> Optional[str]:
        if not self.pixabay:
            return None
        try:
            r = requests.get(
                "https://pixabay.com/api/",
                params={"key": self.pixabay, "q": q, "image_type": "photo",
                        "per_page": 15, "safesearch": "true"},
                timeout=10,
            )
            r.raise_for_status()
            hits = r.json().get("hits", [])
            return random.choice(hits)["largeImageURL"] if hits else None
        except Exception as e:
            logger.warning(f"Pixabay error: {e}")
            return None

    def _unsplash(self, q: str) -> Optional[str]:
        if not self.unsplash:
            return None
        try:
            r = requests.get(
                "https://api.unsplash.com/search/photos",
                headers={"Authorization": f"Client-ID {self.unsplash}"},
                params={"query": q, "per_page": 15},
                timeout=10,
            )
            r.raise_for_status()
            results = r.json().get("results", [])
            return random.choice(results)["urls"]["regular"] if results else None
        except Exception as e:
            logger.warning(f"Unsplash error: {e}")
            return None

    def _download(self, url: str, dest: Path) -> bool:
        try:
            r = requests.get(url, timeout=20, stream=True)
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return dest.exists() and dest.stat().st_size > 0
        except Exception as e:
            logger.warning(f"Download failed: {e}")
            return False
