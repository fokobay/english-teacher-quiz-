"""
Group registry — auto-join if >= 10,000 members, else leave immediately.
No manual approval needed.
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
MIN_MEMBERS       = 10_000
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

WELCOME = (
    "👋 <b>Hello! I'm your English Teacher & Quiz Bot 📚🎯</b>\n\n"
    "Every <b>6 hours</b> I alternate between:\n\n"
    "📖 <b>English Lesson</b> — vocabulary, grammar, idioms & more\n"
    "🧠 <b>English Quiz</b>  — 20 questions to test what you learned\n\n"
    "🏆 Leaderboard after every quiz!\n\n"
    "<i>Let's improve your English together! 🚀</i>"
)

SMALL_GROUP_MSG = (
    "⚠️ <b>Minimum 10,000 members required.</b>\n\n"
    "This group doesn't meet the requirement.\n"
    "I'll leave now. Goodbye! 👋"
)


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
        """شيل الـ groups الـ inactive من الـ RAM لو عدى عليها أكتر من 30 يوم."""
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
        """
        Returns member count (int), or None if the API call failed.

        BUG FIX: previously returned 0 on any failure, which caused the bot
        to treat unreachable-but-valid groups as 'too small' and leave them.
        Now returns None on failure so handle_join can skip rather than reject.
        """
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
        """Return username (without @) or '' if the group has none."""
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
        """Return a clickable HTML anchor for the group."""
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
        # Deep-link fallback for private/no-username supergroups.
        # Supergroup IDs look like -100XXXXXXXXXX; strip prefix to get plain digits.
        # BUG FIX: replaced .removeprefix() (Python 3.9+ only) with re.sub
        # so the bot runs correctly on Python 3.8 environments too.
        numeric = re.sub(r"^-100", "", chat_id).lstrip("-")
        return f'<a href="tg://openmessage?chat_id={numeric}">{safe}</a>'

    # ── Join / Leave ──────────────────────────────────────────────────

    def handle_join(self, chat_id: str, title: str) -> str:
        """Returns: 'pending' | 'too_small' | 'existing' | 'unknown'

        New groups always go to pending and wait for admin approval.
        Previously approved groups that rejoin are reactivated directly.
        """
        gid      = str(chat_id)
        count    = self.get_member_count(gid)
        username = self.get_chat_username(gid)

        if count is None:
            log.warning(f"Could not verify member count for {title} ({gid}) — skipping join")
            return "unknown"

        if count < MIN_MEMBERS:
            log.info(f"Too small: {title} ({gid}) — {count} members < {MIN_MEMBERS:,}")
            # Store count so notify_admin_rejected shows real number
            self._data.setdefault(gid, {}).update({"title": title, "members": count, "active": False})
            return "too_small"

        # Previously approved group rejoining — reactivate directly, no re-approval needed
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

        # Brand new group — set pending, wait for admin
        self._data[gid] = {
            "chat_id":    gid,
            "title":      title,
            "username":   username,
            "joined_at":  time.time(),
            "last_post":  0,
            "next_step":  0,
            "quiz_count": 0,
            "active":     False,
            "pending":    True,
            "members":    count,
        }
        self._save()
        log.info(f"Pending approval: {title} ({gid}) — {count:,} members")
        return "pending"

    def approve(self, chat_id: str) -> bool:
        """Admin approved a pending group. Returns True if found."""
        gid = str(chat_id)
        if gid not in self._data:
            return False
        self._data[gid]["active"]      = True
        self._data[gid]["pending"]     = False
        self._data[gid]["approved_at"] = time.time()
        self._save()
        log.info(f"Approved: {gid}")
        return True

    def reject_pending(self, chat_id: str) -> bool:
        """Admin rejected a pending group. Returns True if found."""
        gid = str(chat_id)
        if gid not in self._data:
            return False
        self._data[gid]["active"]  = False
        self._data[gid]["pending"] = False
        self._save()
        log.info(f"Rejected: {gid}")
        return True

    def expire_pending(self) -> list:
        """Auto-reject pending groups older than PENDING_TIMEOUT_H. Returns expired IDs."""
        now, expired = time.time(), []
        for gid, info in self._data.items():
            if not info.get("pending"):
                continue
            if (now - info.get("joined_at", now)) / 3600 >= PENDING_TIMEOUT_H:
                expired.append(gid)
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
        """Called when the bot is kicked/left from the group."""
        gid = str(chat_id)
        if gid in self._data:
            self._data[gid]["active"] = False
            self._save()
            log.info(f"Deactivated: {gid}")

    def mark_done(self, chat_id: str, step: int):
        """Record that a step finished; toggle next_step (0↔1)."""
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
        """0 = lesson due next, 1 = quiz due next."""
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
        """Return [(chat_id, step), ...] for groups whose next step is due."""
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

    def send_pending(self, chat_id: str):
        self._send(chat_id, PENDING_MSG)

    def send_rejected(self, chat_id: str):
        self._send(chat_id, REJECTED_MSG)

    def welcome(self, chat_id: str):
        self._send(chat_id, WELCOME)

    def send_small_group(self, chat_id: str):
        self._send(chat_id, SMALL_GROUP_MSG)

    def notify_admin_pending(self, chat_id: str, title: str, members: int):
        """Ask admin to approve or reject a new group."""
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
            f"Do you want me to join this group?",
            reply_markup={"inline_keyboard": [[
                {"text": "✅ Approve", "callback_data": f"approve:{chat_id}"},
                {"text": "❌ Reject",  "callback_data": f"reject:{chat_id}"},
            ]]},
        )

    def notify_admin_join(self, chat_id: str, title: str, members: int):
        if not ADMIN_ID:
            return
        g    = self._data.get(str(chat_id), {"chat_id": chat_id, "title": title})
        link = self._group_link(g)
        self._send(
            ADMIN_ID,
            f"✅ <b>New group joined</b>\n\n"
            f"📌 {link}\n"
            f"🆔 <code>{chat_id}</code>\n"
            f"👥 {members:,} members",
            reply_markup={"inline_keyboard": [[
                {"text": "🗑 Remove & Leave", "callback_data": f"remove:{chat_id}"},
            ]]},
        )

    def notify_admin_rejected(self, chat_id: str, title: str, members: int):
        if not ADMIN_ID:
            return
        self._send(
            ADMIN_ID,
            f"🚫 <b>Left small group</b>\n\n"
            f"📌 <b>{title}</b>\n"
            f"🆔 <code>{chat_id}</code>\n"
            f"👥 {members:,} members (< {MIN_MEMBERS:,} required)",
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
            link    = self._group_link(g)
            nxt     = "📖 lesson" if g.get("next_step", 0) == 0 else "🎯 quiz"
            quizzes = g.get("quiz_count", 0)
            joined  = time.strftime(
                "%d %b %Y", time.localtime(g.get("joined_at", 0))
            )
            text = (
                f"📌 {link}\n"
                f"🆔 <code>{g['chat_id']}</code>\n"
                f"👥 {g.get('members', 0):,} members\n"
                f"🗓 Joined: {joined}\n"
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
