"""
Telegram Bot API — thin wrapper.
"""
import os, requests
from src.logger import setup_logger

log  = setup_logger("api")
BASE = f"https://api.telegram.org/bot{os.environ.get('TELEGRAM_BOT_TOKEN','')}"
MEDALS = ["🥇","🥈","🥉"]

def mention(name: str, user_id: int) -> str:
    safe = name.replace("<","&lt;").replace(">","&gt;").replace("&","&amp;")
    return f'<a href="tg://user?id={user_id}">{safe}</a>'

def _post(method: str, **kwargs) -> dict | None:
    try:
        r = requests.post(f"{BASE}/{method}", json=kwargs, timeout=20)
        r.raise_for_status()
        return r.json().get("result")
    except Exception as e:
        log.warning(f"{method} failed: {e}")
        return None

def send(chat_id, text, parse_mode="HTML") -> dict | None:
    return _post("sendMessage", chat_id=chat_id, text=text, parse_mode=parse_mode)

def send_poll(chat_id, question, options, correct_index, explanation="") -> dict | None:
    payload = dict(
        chat_id=chat_id, question=question[:300],
        options=[o[:100] for o in options], type="quiz",
        correct_option_id=correct_index, is_anonymous=False, open_period=180,
    )
    if explanation:
        payload["explanation"]            = explanation[:200]
        payload["explanation_parse_mode"] = "HTML"
    return _post("sendPoll", **payload)

def stop_poll(chat_id, message_id):
    _post("stopPoll", chat_id=chat_id, message_id=message_id)

def pin(chat_id, message_id):
    _post("pinChatMessage", chat_id=chat_id,
          message_id=message_id, disable_notification=True)

def unpin(chat_id, message_id):
    _post("unpinChatMessage", chat_id=chat_id, message_id=message_id)

def delete_webhook():
    r = _post("deleteWebhook", drop_pending_updates=False)
    log.info(f"deleteWebhook: {r}")

def get_me() -> dict:
    return _post("getMe") or {}

def get_updates(offset: int, timeout=5) -> list:
    try:
        r = requests.post(
            f"{BASE}/getUpdates",
            json={"offset": offset, "timeout": timeout,
                  "allowed_updates": ["message","my_chat_member","poll_answer","callback_query"]},
            timeout=timeout + 10,
        )
        r.raise_for_status()
        return r.json().get("result", [])
    except requests.exceptions.Timeout:
        return []
    except Exception as e:
        log.warning(f"getUpdates failed: {e}")
        return []

# ── Quiz text builders ────────────────────────────────────────────────

def txt_announce(num: int, total_q: int = 20) -> str:
    return (
        f"🎯 <b>English Quiz #{num} — Starting in 10 seconds!</b>\n\n"
        f"📝 <b>{total_q} questions</b>  •  ⏱ <b>3 minutes</b> each\n"
        f"👆 Tap the correct answer on each poll!\n\n"
        f"<i>Get ready... 🚀</i>"
    )

def txt_halfway(scores: list) -> str:
    if not scores:
        return "📊 <b>Halfway</b>\n\nNo answers yet!"
    lines = ["📊 <b>Halfway — Top 5</b>\n"]
    for i, row in enumerate(scores[:5], 1):
        name, uid, correct, _ = row
        m   = MEDALS[i-1] if i <= 3 else f"{i}."
        tag = mention(name, uid) if uid else f"<b>{name}</b>"
        lines.append(f"{m} {tag} — {correct} pts")
    lines.append("\n<i>10 more questions — keep going! 💪</i>")
    return "\n".join(lines)

def txt_final(scores: list, num: int, total: int, total_q: int = 20) -> str:
    if not scores:
        return "🏆 <b>Quiz Complete!</b>\n\nNo answers recorded."
    lines = [f"🏆 <b>Quiz #{num} — Final Results</b>\n{'═'*30}\n"]
    for i, row in enumerate(scores[:10], 1):
        name, uid, correct, _ = row
        m   = MEDALS[i-1] if i <= 3 else f"{i}."
        pct = int(correct / total_q * 100)
        bar = "█" * (correct // 2) + "░" * (10 - correct // 2)
        tag = "🌟" if correct == total_q else ("🔥" if correct >= total_q * 0.8 else "")
        mnt = mention(name, uid) if uid else f"<b>{name}</b>"
        lines.append(f"{m} {mnt} {tag}\n   {correct}/{total_q} ({pct}%)  {bar}")
    lines.append(f"\n👥 <b>{total}</b> participants")
    lines.append("⏰ Next lesson in <b>6 hours</b>! 📖")
    return "\n".join(lines)

def txt_alltime(scores: list) -> str:
    if not scores:
        return "📈 <b>All-Time Leaderboard</b>\n\nNo data yet."
    lines = ["📈 <b>All-Time Leaderboard</b>\n" + "═"*30 + "\n"]
    for i, s in enumerate(scores[:10], 1):
        m      = MEDALS[i-1] if i <= 3 else f"{i}."
        wins   = f" 👑×{s['wins']}"   if s["wins"]        else ""
        streak = f" 🔥×{s['streak']}" if s["streak"] >= 2 else ""
        mnt    = mention(s["name"], s["user_id"]) if s.get("user_id") else f"<b>{s['name']}</b>"
        lines.append(
            f"{m} {mnt}{wins}{streak}\n"
            f"   {s['total']} pts • avg {s['avg']}/20 • "
            f"best {s['best']}/20 • {s['quizzes']} quizzes"
        )
    return "\n".join(lines)
