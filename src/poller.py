"""
Long-polling loop — handles all Telegram updates.
Handles: poll_answer, my_chat_member, callback_query (admin), admin commands.
"""
import os, time, threading
from src.logger        import setup_logger
from src.groups        import Groups
from src               import api
from src.quiz_pipeline import on_poll_answer

log      = setup_logger("poller")
ADMIN_ID = os.environ.get("ADMIN_CHAT_ID", "")


class Poller:
    def __init__(self, groups: Groups):
        self.groups               = groups
        self._offset              = 0
        self._bot_id: str         = ""
        self._joined_recently: set = set()
        api.delete_webhook()

    def tick(self):
        updates = api.get_updates(self._offset, timeout=5)
        for upd in updates:
            self._offset = upd["update_id"] + 1
            try:
                self._dispatch(upd)
            except Exception as e:
                log.warning(f"Dispatch error: {e}")

    # ── Router ────────────────────────────────────────────────────────

    def _dispatch(self, upd: dict):
        # Poll answers (quiz responses)
        if "poll_answer" in upd:
            pa   = upd["poll_answer"]
            user = pa.get("user", {})
            name = (
                (user.get("first_name", "") + " " + user.get("last_name", "")).strip()
                or user.get("username", "Unknown")
            )
            on_poll_answer(pa["poll_id"], user["id"], name, pa.get("option_ids", []))
            return

        # Admin inline button presses
        if "callback_query" in upd:
            self._on_callback(upd["callback_query"])
            return

        # Bot added to / removed from a group
        if "my_chat_member" in upd:
            self._on_member(upd["my_chat_member"])
            return

        msg = upd.get("message", {})
        if not msg:
            return

        # Legacy new_chat_members event (some clients still send this)
        for member in msg.get("new_chat_members", []):
            if str(member.get("id")) == self._bot_id_str():
                chat = msg.get("chat", {})
                self._handle_join(str(chat["id"]), chat.get("title", "?"))
                return

        # Private messages from the admin
        chat = msg.get("chat", {})
        text = msg.get("text", "").strip()
        if str(chat.get("id")) == ADMIN_ID and chat.get("type") == "private":
            self._on_admin_cmd(text)

    # ── Join / Leave ──────────────────────────────────────────────────

    def _on_member(self, data: dict):
        chat   = data.get("chat", {})
        cid    = str(chat.get("id", ""))
        title  = chat.get("title", "?")
        status = data.get("new_chat_member", {}).get("status", "")

        if status in ("member", "administrator"):
            log.info(f"Joined: {title} ({cid})")
            self._handle_join(cid, title)
        elif status in ("left", "kicked", "banned", "restricted"):
            log.info(f"Removed from: {title} ({cid})")
            self.groups.remove(cid)

    def _handle_join(self, cid: str, title: str):
        # De-duplicate rapid join events (some groups fire it twice)
        if cid in self._joined_recently:
            log.info(f"Duplicate join ignored: {title} ({cid})")
            return
        self._joined_recently.add(cid)
        threading.Timer(10, lambda: self._joined_recently.discard(cid)).start()

        status  = self.groups.handle_join(cid, title)
        members = self.groups._data.get(cid, {}).get("members", 0)

        time.sleep(1)

        if status == "too_small":
            self.groups.send_small_group(cid)
            self.groups.notify_admin_rejected(cid, title, members)
            time.sleep(2)
            self.groups.leave(cid)

        elif status == "approved":
            self.groups.welcome(cid)
            self.groups.notify_admin_join(cid, title, members)

        elif status == "existing":
            self.groups.welcome(cid)

    # ── Admin inline callbacks ────────────────────────────────────────

    def _on_callback(self, cb: dict):
        sender = str(cb.get("from", {}).get("id", ""))
        if sender != ADMIN_ID:
            self._answer_cb(cb["id"], "⛔ Not authorized")
            return

        data = cb.get("data", "")
        msg  = cb.get("message", {})
        cid  = str(msg.get("chat", {}).get("id", ""))
        mid  = msg.get("message_id")

        if data == "dashboard":
            self._answer_cb(cb["id"], "🔄 Refreshing...")
            self._delete_msg(cid, mid)
            self.groups.send_dashboard()

        elif data.startswith("remove:"):
            gid  = data.split(":", 1)[1]
            info = self.groups._data.get(gid, {})
            if self.groups.remove_by_admin(gid):
                self._answer_cb(cb["id"], "🗑 Removed!")
                self._edit_msg(
                    cid, mid,
                    f"🗑 <b>Removed</b>\n"
                    f"📌 {info.get('title', '')}\n"
                    f"🆔 <code>{gid}</code>",
                )
                time.sleep(1)
                self.groups.leave(gid)
            else:
                self._answer_cb(cb["id"], "⚠️ Group not found")

    # ── Admin text commands ───────────────────────────────────────────

    def _on_admin_cmd(self, text: str):
        parts = text.split()
        cmd   = parts[0].lower() if parts else ""

        if cmd in ("/dashboard", "/groups"):
            self.groups.send_dashboard()

        elif cmd == "/remove" and len(parts) == 2:
            gid = parts[1]
            if self.groups.remove_by_admin(gid):
                self.groups._send(ADMIN_ID, f"🗑 Removed: {gid}")
                self.groups.leave(gid)
            else:
                self.groups._send(ADMIN_ID, "⚠️ Group not found")

        elif cmd == "/help":
            self.groups._send(
                ADMIN_ID,
                "🤖 <b>Admin Commands</b>\n\n"
                "/dashboard — show all active groups\n"
                "/remove [id] — remove group & leave\n",
            )

    # ── Helpers ───────────────────────────────────────────────────────

    def _answer_cb(self, cb_id: str, text: str = ""):
        try:
            api._post("answerCallbackQuery", callback_query_id=cb_id, text=text)
        except Exception:
            pass

    def _edit_msg(self, chat_id: str, msg_id: int, text: str):
        try:
            api._post(
                "editMessageText",
                chat_id=chat_id, message_id=msg_id,
                text=text, parse_mode="HTML",
            )
        except Exception:
            pass

    def _delete_msg(self, chat_id: str, msg_id: int):
        try:
            api._post("deleteMessage", chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass

    def _bot_id_str(self) -> str:
        if not self._bot_id:
            self._bot_id = str(api.get_me().get("id", ""))
        return self._bot_id
