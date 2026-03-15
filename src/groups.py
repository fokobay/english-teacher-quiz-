"""
Group registry — all groups require admin approval before the bot starts posting.
Admin selects the daily start hour (0-23 UTC) when approving a group.
The bot posts every 6 hours starting from that hour.
Persists to DATA_DIR/groups.json

Cycle per group (every 6h):
  next_step=0 → lesson
  next_step=1 → quiz
"""
import json, os, re, time, requests
from pathlib import Path
from src.logger import setup_logger

log      = setup_logger("groups")
DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
DB       = DATA_DIR / "groups.json"
BASE     = f"https://api.telegram.org/bot{os.environ.get('TELEGRAM_BOT_TOKEN','')}"
ADMIN_ID = os.environ.get("ADMIN_CHAT_ID", "")

INTERVAL_HOURS    = 6
PENDING_TIMEOUT_H = 24   # auto-reject pending groups after 24h with no admin response

PENDING_MSG = (
    "⏳ <b>Thanks for adding me!</b>\n\n"
    "I'm waiting for admin approval before I start posting.\n"
    "I'll leave automatically if there's no response within 24 hours. 📚"
)

REJECTED_MSG = (
    "🚫 <b>Access denied by admin.</b>\n\n"
    "I wasn't approved for this group.\n"
    "Goodbye! 👋"
)

def welcome_msg(start_hour: int) -> str:
    return (
        f"👋 <b>Hello! I'm your English Teacher & Quiz Bot 📚🎯</b>\n\n"
        f"Every <b>6 hours</b> I alternate between:\n\n"
        f"📖 <b>English Lesson</b> — vocabulary, grammar, idioms & more\n"
        f"🧠 <b>English Quiz</b>  — 20 questions to test what you learned\n\n"
        f"🏆 Leaderboard after every quiz!\n\n"
        f"⏰ Posting schedule starts at <b>{start_hour:02d}:00 UTC</b> "
        f"(every 6h: {start_hour:02d}h, {(start_hour+6)%24:02d}h, "
        f"{(start_hour+12)%24:02d}h, {(start_hour+18)%24:02d}h)\n\n"
        f"<i>Let's improve your English together! 🚀</i>"
    )

WELCOME = welcome_msg(8)


class Groups:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict:
        try:
            if DB.exists():
                return json.loads(DB.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save(self):
        try:
            self._trim()
            DB.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            log.warning(f"Save failed: {e}")

    def _trim(self):
        MAX_INACTIVE_DAYS = 30
        cutoff = time.time() - MAX_INACTIVE_DAYS * 86400
        to_remove = [
            gid for gid, info in self._data.items()
            if not info.get("active")
            and info.get("joined_at", 0) < cutoff
        ]
        for gid in to_remove:
            del self._data[gid]
        if to_remove:
            log.info(f"Trimmed {len(to_remove)} old inactive groups from RAM")

    def reload(self):
        self._data = self._load()

    # ── Telegram helpers ──────────────────────────────────────────────

    def get_member_count(self, chat_id: str):
        try:
            r = requests.get(
                f"{BASE}/getChatMemberCount",
                params={"chat_id": chat_id},
                timeout=10,
            )
            result = r.json()
            if result.get("ok"):
                return result.get("result", 0)
            log.warning(f"getChatMemberCount error for {chat_id}: {result.get('description')}")
            return None
        except Exception as e:
            log.warning(f"getChatMemberCount failed for {chat_id}: {e}")
            return None

    def get_chat_username(self, chat_id: str) -> str:
        try:
            r = requests.get(
                f"{BASE}/getChat",
                params={"chat_id": chat_id},
                timeout=10,
            )
            return r.json().get("result", {}).get("username", "") or ""
        except Exception:
            return ""

    def _group_link(self, g: dict) -> str:
        title    = g.get("title", "Group")
        username = g.get("username", "")
        chat_id  = g.get("chat_id", "")
        safe     = (
            title.replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;")
        )
        if username:
            return f'<a href="https://t.me/{username}">{safe}</a>'
        numeric = re.sub(r"^-100", "", chat_id).lstrip("-")
        return f'<a href="tg://openmessage?chat_id={numeric}">{safe}</a>'

    # ── Join / Leave ──────────────────────────────────────────────────

    def handle_join(self, chat_id: str, title: str) -> str:
        gid      = str(chat_id)
        count    = self.get_member_count(gid)
        username = self.get_chat_username(gid)

        if count is None:
            log.warning(f"Could not verify member count for {title} ({gid}) — skipping join")
            return "unknown"

        if gid in self._data and self._data[gid].get("approved_at"):
            self._data[gid]["active"]   = True
            self._data[gid]["title"]    = title
            self._data[gid]["username"] = username
            self._data[gid]["members"]  = count
            if time.time() - self._data[gid].get("last_post", 0) > 86400:
                self._data[gid]["last_post"] = 0
            self._save()
            log.info(f"Reactivated: {title} ({gid}) — {count} members")
            return "existing"

        self._data[gid] = {
            "chat_id":       gid,
            "title":         title,
            "username":      username,
            "joined_at":     time.time(),
            "last_post":     0,
            "next_step":     0,
            "quiz_count":    0,
            "active":        False,
            "pending":       True,
            "members":       count,
            "start_hour":    None,
            "awaiting_hour": True,
        }
        self._save()
        log.info(f"Pending approval: {title} ({gid}) — {count:,} members")
        return "pending"

    def approve(self, chat_id: str) -> bool:
        gid = str(chat_id)
        if gid not in self._data:
            return False
        if self._data[gid].get("start_hour") is None:
            log.warning(f"Approve attempted but no start_hour set yet for {gid}")
            return False
        self._data[gid]["active"]      = True
        self._data[gid]["pending"]     = False
        self._data[gid]["approved_at"] = time.time()
        self._data[gid]["last_post"]   = 0
        self._save()
        start_hour = self._data[gid]["start_hour"]
        log.info(f"Approved: {gid} — start_hour={start_hour:02d}:00 UTC")
        return True

    def reject_pending(self, chat_id: str) -> bool:
        gid = str(chat_id)
        if gid not in self._data:
            return False
        self._data[gid]["active"]  = False
        self._data[gid]["pending"] = False
        self._save()
        log.info(f"Rejected: {gid}")
        return True

    def expire_pending(self) -> list:
        """Auto-reject pending groups older than PENDING_TIMEOUT_H.
        BUG FIX: original iterated self._data.items() while potentially
        modifying _data inside the loop body (via _save → _trim).  Now
        we collect expired IDs first, then mutate.
        """
        now = time.time()
        # Snapshot keys to avoid modifying dict during iteration
        expired = [
            gid for gid, info in list(self._data.items())
            if info.get("pending")
            and (now - info.get("joined_at", now)) / 3600 >= PENDING_TIMEOUT_H
        ]
        for gid in expired:
            self._data[gid]["pending"] = False
            self._data[gid]["active"]  = False
        if expired:
            self._save()
        return expired

    def pending_list(self) -> list:
        return [v for v in self._data.values() if v.get("pending")]

    def remove_by_admin(self, chat_id: str) -> bool:
        gid = str(chat_id)
        if gid in self._data:
            self._data[gid]["active"] = False
            self._save()
            log.info(f"Removed by admin: {gid}")
            return True
        return False

    def remove(self, chat_id: str):
        gid = str(chat_id)
        if gid in self._data:
            self._data[gid]["active"] = False
            self._save()
            log.info(f"Deactivated: {gid}")

    def mark_done(self, chat_id: str, step: int):
        gid = str(chat_id)
        if gid in self._data:
            self._data[gid]["last_post"] = time.time()
            self._data[gid]["next_step"] = 1 - step
            if step == 1:
                self._data[gid]["quiz_count"] = (
                    self._data[gid].get("quiz_count", 0) + 1
                )
            self._save()

    def quiz_count(self, chat_id: str) -> int:
        return self._data.get(str(chat_id), {}).get("quiz_count", 0)

    def next_step(self, chat_id: str) -> int:
        return self._data.get(str(chat_id), {}).get("next_step", 0)

    def leave(self, chat_id: str):
        try:
            requests.post(
                f"{BASE}/leaveChat",
                json={"chat_id": chat_id},
                timeout=10,
            )
            log.info(f"Left group: {chat_id}")
        except Exception as e:
            log.warning(f"Leave failed: {e}")

    # ── Scheduler ────────────────────────────────────────────────────

    def due(self, memory: dict, running: set = None) -> list:
        now     = time.time()
        result  = []
        running = running or set()

        for gid, info in self._data.items():
            if not info.get("active"):
                continue
            if gid in running:
                continue

            last    = memory.get(gid, info.get("last_post", 0))
            elapsed = (now - last) / 3600

            if elapsed >= INTERVAL_HOURS:
                result.append((gid, info.get("next_step", 0)))
            else:
                rem  = INTERVAL_HOURS - elapsed
                name = "lesson" if info.get("next_step", 0) == 0 else "quiz"
                log.info(f"⏳ {info['title']} — {rem:.1f}h until {name}")

        return result

    def active_count(self) -> int:
        return sum(1 for v in self._data.values() if v.get("active"))

    def active_list(self) -> list:
        return [v for v in self._data.values() if v.get("active")]

    # ── Messages ─────────────────────────────────────────────────────

    def set_start_hour(self, chat_id: str, hour: int) -> bool:
        gid = str(chat_id)
        if gid not in self._data:
            return False
        self._data[gid]["start_hour"]    = hour
        self._data[gid]["awaiting_hour"] = False
        self._save()
        log.info(f"start_hour set: {gid} → {hour:02d}:00 UTC")
        return True

    def is_awaiting_hour(self, chat_id: str) -> bool:
        return self._data.get(str(chat_id), {}).get("awaiting_hour", False)

    def send_hour_selection(self, chat_id: str):
        hour_rows = []
        for row_start in range(0, 24, 4):
            row = [
                {
                    "text":          f"🕐 {h:02d}:00",
                    "callback_data": f"sethour:{chat_id}:{h}",
                }
                for h in range(row_start, row_start + 4)
            ]
            hour_rows.append(row)
        self._send(
            chat_id,
            "⏰ <b>Choose the daily posting start time (UTC)</b>\n\n"
            "The bot will post every 6 hours starting from the hour you select.\n\n"
            "<i>Example: pick 08:00 → posts at 08:00, 14:00, 20:00, 02:00 daily</i>",
            reply_markup={"inline_keyboard": hour_rows},
        )

    def send_pending(self, chat_id: str):
        self._send(chat_id, PENDING_MSG)

    def send_rejected(self, chat_id: str):
        self._send(chat_id, REJECTED_MSG)

    def welcome(self, chat_id: str):
        start_hour = self._data.get(str(chat_id), {}).get("start_hour", 8)
        self._send(chat_id, welcome_msg(start_hour if start_hour is not None else 8))

    def notify_admin_pending(self, chat_id: str, title: str, members: int):
        if not ADMIN_ID:
            return
        g    = self._data.get(str(chat_id), {"chat_id": chat_id, "title": title})
        link = self._group_link(g)
        self._send(
            ADMIN_ID,
            f"🔔 <b>New group — approval required</b>\n\n"
            f"📌 {link}\n"
            f"🆔 <code>{chat_id}</code>\n"
            f"👥 {members:,} members\n\n"
            f"Do you want me to start posting in this group?",
            reply_markup={"inline_keyboard": [[
                {"text": "✅ Approve", "callback_data": f"approve:{chat_id}"},
                {"text": "❌ Reject",  "callback_data": f"reject:{chat_id}"},
            ]]},
        )

    def notify_admin_join(self, chat_id: str, title: str, members: int):
        if not ADMIN_ID:
            return
        g          = self._data.get(str(chat_id), {"chat_id": chat_id, "title": title})
        link       = self._group_link(g)
        start_hour = self._data.get(str(chat_id), {}).get("start_hour", 8)
        # BUG FIX: start_hour could be None for legacy groups without a stored
        # start_hour, causing TypeError in the f-string format spec :02d.
        start_hour = start_hour if start_hour is not None else 8
        self._send(
            ADMIN_ID,
            f"✅ <b>New group joined</b>\n\n"
            f"📌 {link}\n"
            f"🆔 <code>{chat_id}</code>\n"
            f"👥 {members:,} members\n"
            f"⏰ Posts at {start_hour:02d}:00 UTC (every 6h)",
            reply_markup={"inline_keyboard": [[
                {"text": "🗑 Remove & Leave", "callback_data": f"remove:{chat_id}"},
            ]]},
        )

    def notify_admin_rejected(self, chat_id: str, title: str, members: int):
        if not ADMIN_ID:
            return
        self._send(
            ADMIN_ID,
            f"🚫 <b>Group rejected</b>\n\n"
            f"📌 <b>{title}</b>\n"
            f"🆔 <code>{chat_id}</code>\n"
            f"👥 {members:,} members",
        )

    def send_dashboard(self):
        if not ADMIN_ID:
            return
        groups = self.active_list()
        if not groups:
            self._send(ADMIN_ID, "📊 <b>Dashboard</b>\n\nNo active groups yet.")
            return

        self._send(
            ADMIN_ID,
            f"📊 <b>Active Groups — {len(groups)}</b>\n"
            f"{'═' * 30}\n"
            f"<i>Tap a group name to open it • Tap 🗑 to remove</i>",
        )

        for g in groups:
            link       = self._group_link(g)
            nxt        = "📖 lesson" if g.get("next_step", 0) == 0 else "🎯 quiz"
            quizzes    = g.get("quiz_count", 0)
            start_hour = g.get("start_hour")
            # BUG FIX: start_hour can be None for groups approved before the
            # hour-selection feature was added.  The :02d format spec raises
            # TypeError on None.  Fallback to "—" for those legacy groups.
            if start_hour is not None:
                schedule = (
                    f"{start_hour:02d}h/{(start_hour+6)%24:02d}h/"
                    f"{(start_hour+12)%24:02d}h/{(start_hour+18)%24:02d}h UTC"
                )
            else:
                schedule = "—"
            joined  = time.strftime(
                "%d %b %Y", time.localtime(g.get("joined_at", 0))
            )
            text = (
                f"📌 {link}\n"
                f"🆔 <code>{g['chat_id']}</code>\n"
                f"👥 {g.get('members', 0):,} members\n"
                f"🗓 Joined: {joined}\n"
                f"⏰ Schedule: {schedule}\n"
                f"🎯 Quizzes done: {quizzes}\n"
                f"⏭ Next: {nxt}"
            )
            self._send(
                ADMIN_ID,
                text,
                reply_markup={"inline_keyboard": [[
                    {"text": "🗑 Remove & Leave",
                     "callback_data": f"remove:{g['chat_id']}"},
                ]]},
            )

    def _send(self, chat_id, text, reply_markup=None):
        try:
            payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
            if reply_markup:
                payload["reply_markup"] = reply_markup
            requests.post(f"{BASE}/sendMessage", json=payload, timeout=15)
        except Exception as e:
            log.warning(f"Send failed → {chat_id}: {e}")
