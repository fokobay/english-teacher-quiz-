"""
Tracks scores per session + all-time leaderboard.
Stores user_id for Telegram mention links.
Persists to DATA_DIR/scores.json
"""
import json, os
from pathlib import Path
from src.logger import setup_logger

log      = setup_logger("scores")
DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
DB       = DATA_DIR / "scores.json"


class Scores:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._sessions: dict = {}   # {chat_id: {user_id: {name,user_id,correct,answered}}}
        self._alltime        = self._load()

    def _load(self) -> dict:
        try:
            if DB.exists():
                return json.loads(DB.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save(self):
        try:
            DB.write_text(json.dumps(self._alltime, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.warning(f"Save failed: {e}")

    # ── Session ──────────────────────────────────────────────────────

    def start(self, chat_id: str):
        self._sessions[str(chat_id)] = {}

    def record(self, chat_id: str, user_id: int, name: str, correct: bool):
        cid, uid = str(chat_id), str(user_id)
        sess = self._sessions.setdefault(cid, {})
        if uid not in sess:
            sess[uid] = {"name": name, "user_id": user_id, "correct": 0, "answered": 0}
        sess[uid]["name"]     = name
        sess[uid]["user_id"]  = user_id
        sess[uid]["answered"] += 1
        if correct:
            sess[uid]["correct"] += 1

    def session_board(self, chat_id: str) -> list:
        """Sorted [(name, user_id, correct, answered), ...]"""
        data = self._sessions.get(str(chat_id), {})
        rows = [(v["name"], v.get("user_id",0), v["correct"], v["answered"])
                for v in data.values()]
        return sorted(rows, key=lambda x: (-x[2], -x[3]))

    def count(self, chat_id: str) -> int:
        return len(self._sessions.get(str(chat_id), {}))

    # ── Commit to all-time ───────────────────────────────────────────

    def commit(self, chat_id: str, quiz_num: int):
        cid  = str(chat_id)
        sess = self._sessions.get(cid, {})
        at   = self._alltime.setdefault(cid, {})

        top_uid = max(sess, key=lambda u: sess[u]["correct"], default=None)

        for uid, info in sess.items():
            if uid not in at:
                at[uid] = {
                    "name":      info["name"],
                    "user_id":   info.get("user_id", 0),
                    "total":     0, "answered": 0,
                    "quizzes":   0, "wins":     0,
                    "best":      0, "streak":   0,
                    "last_quiz": 0,
                }
            rec = at[uid]
            rec["name"]      = info["name"]
            rec["user_id"]   = info.get("user_id", 0)
            rec["total"]    += info["correct"]
            rec["answered"] += info["answered"]
            rec["quizzes"]  += 1
            rec["best"]      = max(rec["best"], info["correct"])
            rec["wins"]     += 1 if uid == top_uid and info["correct"] > 0 else 0
            rec["streak"]    = rec["streak"] + 1 if rec["last_quiz"] == quiz_num - 1 else 1
            rec["last_quiz"] = quiz_num

        self._save()
        log.info(f"Committed quiz #{quiz_num} for {cid} — {len(sess)} players")

    def alltime_board(self, chat_id: str) -> list:
        data = self._alltime.get(str(chat_id), {})
        rows = []
        for v in data.values():
            avg = round(v["total"] / v["quizzes"], 1) if v["quizzes"] else 0
            rows.append({
                "name":    v["name"],
                "user_id": v.get("user_id", 0),
                "total":   v["total"],
                "quizzes": v["quizzes"],
                "wins":    v.get("wins",   0),
                "best":    v.get("best",   0),
                "streak":  v.get("streak", 0),
                "avg":     avg,
            })
        return sorted(rows, key=lambda x: (-x["total"], -x["avg"]))
