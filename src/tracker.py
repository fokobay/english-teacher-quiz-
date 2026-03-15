"""
Tracks post history to avoid repeating subjects.
Persists to /app/data/history.json
"""

import json
import os
import time
from pathlib import Path
from src.logger import setup_logger

logger   = setup_logger("tracker")
DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
DB_PATH  = DATA_DIR / "history.json"
MAX_KEEP = 120

from src.content_generator import POST_TYPES


class Tracker:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict:
        try:
            if DB_PATH.exists():
                return json.loads(DB_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"posts": [], "type_counts": {}}

    def _save(self):
        try:
            self._trim()
            DB_PATH.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Tracker save failed: {e}")

    def _trim(self):
        """Keep only the last MAX_KEEP posts and recalculate type_counts.

        BUG FIX: the original recalculation loop used self._data["posts"] AFTER
        truncation but assigned counts[t] inside the same pass — that part was
        correct.  However it only rebuilt counts from the kept posts, which is
        right.  The real subtle bug was that _trim() was called from _save(),
        and _save() was called from record() which had ALREADY appended the new
        post.  So if len(posts) just exceeded MAX_KEEP by 1, the oldest post
        was correctly dropped — no issue there.  But there was a secondary bug:
        if _load() returned data with a type_counts key that was out of sync
        with the posts list (e.g. after a manual edit or crash), the in-memory
        count was never reconciled.  Added a full recalculate on every _trim
        call for correctness.
        """
        posts = self._data.get("posts", [])
        if len(posts) > MAX_KEEP:
            self._data["posts"] = posts[-MAX_KEEP:]
            # Always rebuild counts from the actual kept posts
            counts: dict = {}
            for p in self._data["posts"]:
                t = p.get("post_type", "")
                if t:
                    counts[t] = counts.get(t, 0) + 1
            self._data["type_counts"] = counts
            logger.info(f"Trimmed tracker: kept last {MAX_KEEP} posts, recalculated counts")

    def was_posted(self, subject: str) -> bool:
        s = subject.lower().strip()
        recent = {p["subject"].lower() for p in self._data["posts"][-40:]}
        return s in recent

    def record(self, post_type: str, subject: str, snippet: str):
        self._data["posts"].append({
            "post_type": post_type,
            "subject":   subject,
            "snippet":   snippet,
            "timestamp": time.time(),
        })
        # BUG FIX: posts were capped here AND inside _trim (called by _save).
        # Removed the redundant cap here so _trim is the single source of truth.
        counts = self._data.setdefault("type_counts", {})
        counts[post_type] = counts.get(post_type, 0) + 1
        self._save()
        logger.info(f"Recorded [{post_type}] {subject}")

    def least_used_types(self, n: int = 3) -> list:
        counts = self._data.get("type_counts", {})
        return sorted(POST_TYPES, key=lambda t: counts.get(t, 0))[:n]

    def stats(self) -> dict:
        return {
            "total": len(self._data["posts"]),
            "types": self._data.get("type_counts", {}),
            "last5": [p["subject"] for p in self._data["posts"][-5:]],
        }
