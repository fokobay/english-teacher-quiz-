"""
Fetches images: Pexels → Pixabay → Unsplash (round-robin).
Uses AI-generated keywords from lesson content.
"""

import os
import random
import requests
from pathlib import Path
from typing import Optional
from src.logger import setup_logger

logger = setup_logger("images")

FALLBACK_KEYWORDS = {
    "vocabulary":      ["open book reading", "dictionary desk", "student studying"],
    "grammar":         ["writing notebook", "pen paper study", "chalkboard classroom"],
    "idioms":          ["people talking cafe", "speech bubble", "friends conversation"],
    "pronunciation":   ["microphone speaking", "sound waves", "mouth close up"],
    "common_mistakes": ["red pen correction", "editing paper", "writing desk"],
    "phrases":         ["people conversation", "daily communication", "friends talking"],
    "fun_fact":        ["lightbulb idea", "magnifying glass", "brain thinking"],
}

_source_idx = 0


class ImageFetcher:
    def __init__(self):
        self.pexels   = os.environ.get("PEXELS_API_KEY", "")
        self.pixabay  = os.environ.get("PIXABAY_API_KEY", "")
        self.unsplash = os.environ.get("UNSPLASH_ACCESS_KEY", "")

    def fetch(self, post_type: str, save_path: Path, keywords: list = None) -> Optional[Path]:
        global _source_idx
        kw_pool = keywords if keywords else FALLBACK_KEYWORDS.get(post_type, ["education"])
        kw      = random.choice(kw_pool)
        sources = [self._pexels, self._pixabay, self._unsplash]

        # Try from current source index first, then rotate
        for i in range(3):
            idx = (_source_idx + i) % 3
            url = sources[idx](kw)
            if url and self._download(url, save_path):
                _source_idx = (idx + 1) % 3
                logger.info(f"Image ok [{['Pexels','Pixabay','Unsplash'][idx]}] '{kw}'")
                return save_path

        # Fallback keyword
        fb = random.choice(FALLBACK_KEYWORDS.get(post_type, ["nature"]))
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
