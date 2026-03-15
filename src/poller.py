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
        # BUG FIX: _joined_recently was accessed from multiple threads without a lock.
        # Added _joined_lock to prevent race conditions when many groups add the bot
        # simultaneously (e.g. after a bot restart or viral share).
        self._joined_recently: set  = set()
        self._joined_lock           = threading.Lock()
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
            threading.Thread(
                target=self._handle_join,
                args=(cid, title),
                daemon=True,
                name=f"join-{cid}",
            ).start()
        elif status in ("left", "kicked", "banned", "restricted"):
            log.info(f"Removed from: {title} ({cid})")
            self.groups.remove(cid)

    def _handle_join(self, cid: str, title: str):
        with self._joined_lock:
            if cid in self._joined_recently:
                log.info(f"Duplicate join ignored: {title} ({cid})")
                return
            self._joined_recently.add(cid)

        threading.Timer(10, self._discard_joined, args=(cid,)).start()

        status  = self.groups.handle_join(cid, title)
        members = self.groups._data.get(cid, {}).get("members", 0)

        time.sleep(1)

        if status == "too_small":
            self.groups.send_small_group(cid)
            self.groups.notify_admin_rejected(cid, title, members)
            time.sleep(2)
            self.groups.leave(cid)

        elif status == "pending":
            # New group — send pending message and ask admin
            self.groups.send_pending(cid)
            self.groups.notify_admin_pending(cid, title, members)
            log.info(f"[{cid}] Awaiting admin approval")

        elif status == "existing":
            # Previously approved — start directly
            self.groups.welcome(cid)

        elif status == "unknown":
            log.warning(f"Join for {title} ({cid}) skipped — member count unknown")

    def _discard_joined(self, cid: str):
        """Remove cid from _joined_recently after the dedup window expires."""
        with self._joined_lock:
            self._joined_recently.discard(cid)

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

        elif data.startswith("approve:"):
            gid   = data.split(":", 1)[1]
            info  = self.groups._data.get(gid, {})
            title = info.get("title", gid)
            if self.groups.approve(gid):
                self._answer_cb(cb["id"], "✅ Approved!")
                self._edit_msg(
                    cid, mid,
                    f"✅ <b>Approved</b>\n"
                    f"📌 {title}\n"
                    f"🆔 <code>{gid}</code>\n"
                    f"Bot is now active in this group.",
                )
                threading.Thread(
                    target=self._start_approved,
                    args=(gid, info.get("members", 0), title),
                    daemon=True,
                ).start()
            else:
                self._answer_cb(cb["id"], "⚠️ Group not found")

        elif data.startswith("reject:"):
            gid   = data.split(":", 1)[1]
            info  = self.groups._data.get(gid, {})
            title = info.get("title", gid)
            if self.groups.reject_pending(gid):
                self._answer_cb(cb["id"], "❌ Rejected")
                self._edit_msg(
                    cid, mid,
                    f"❌ <b>Rejected</b>\n"
                    f"📌 {title}\n"
                    f"🆔 <code>{gid}</code>\n"
                    f"Bot will leave the group.",
                )
                time.sleep(1)
                self.groups.send_rejected(gid)
                time.sleep(1)
                self.groups.leave(gid)
            else:
                self._answer_cb(cb["id"], "⚠️ Group not found")

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

    def _start_approved(self, gid: str, members: int, title: str):
        """Called after admin approves — welcome and notify."""
        time.sleep(1)
        self.groups.welcome(gid)
        self.groups.notify_admin_join(gid, title, members)
        log.info(f"[{gid}] Bot started after admin approval")

    # ── Admin text commands ───────────────────────────────────────────

    def _on_admin_cmd(self, text: str):
        if not ADMIN_ID:
            return
        parts = text.split()
        cmd   = parts[0].lower() if parts else ""

        if cmd in ("/dashboard", "/groups"):
            self.groups.send_dashboard()

        elif cmd == "/pending":
            pending = self.groups.pending_list()
            if not pending:
                self.groups._send(ADMIN_ID, "✅ No groups waiting for approval.")
                return
            self.groups._send(ADMIN_ID, f"⏳ <b>Pending approval: {len(pending)} group(s)</b>")
            for g in pending:
                age_h = (time.time() - g.get("joined_at", 0)) / 3600
                self.groups._send(
                    ADMIN_ID,
                    f"📌 <b>{g['title']}</b>\n"
                    f"🆔 <code>{g['chat_id']}</code>\n"
                    f"👥 {g.get('members', 0):,} members\n"
                    f"⏱ Waiting {age_h:.1f}h",
                    reply_markup={"inline_keyboard": [[
                        {"text": "✅ Approve", "callback_data": f"approve:{g['chat_id']}"},
                        {"text": "❌ Reject",  "callback_data": f"reject:{g['chat_id']}"},
                    ]]},
                )

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
                "/pending   — show groups waiting for approval\n"
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
