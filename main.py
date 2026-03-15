"""
English Teacher & Quiz Bot
===========================
Cycle per group (every 6 hours):
  Step 0 → 📖 Lesson   (content + image + quick quiz poll)
  Step 1 → 🎯 Quiz     (20-question scored session)

Threads:
  main      : long-polling (Poller)
  scheduler : checks every 5 min which groups need their next step
  per-group : one daemon thread per active step (lesson or quiz)
"""
import os, time, threading
from src.logger          import setup_logger
from src.groups          import Groups
from src.poller          import Poller
from src.lesson_pipeline import run_lesson
from src.quiz_pipeline   import run_quiz
from src                 import api

log      = setup_logger("main")
ADMIN_ID = os.environ.get("ADMIN_CHAT_ID", "")

groups    = Groups()
_last:    dict = {}       # {chat_id: timestamp of last completed step}
_running: set  = set()
_lock          = threading.Lock()


# ── Scheduler ─────────────────────────────────────────────────────────

def scheduler():
    log.info("Scheduler ready — checking every 5 min")
    while True:
        try:
            groups.reload()

            # ── Auto-expire pending groups after 24h ──────────────────
            expired = groups.expire_pending()
            for gid in expired:
                info = groups._data.get(gid, {})
                log.info(f"Auto-rejecting expired pending: {info.get('title', gid)}")
                groups.send_rejected(gid)
                time.sleep(1)
                groups.leave(gid)

            with _lock:
                running_snap = set(_running)

            due = groups.due(_last, running_snap)
            if due:
                log.info(f"⏰ {len(due)} group(s) due")

            for cid, step in due:
                with _lock:
                    if cid in _running:
                        continue
                    _running.add(cid)

                step_name = "lesson" if step == 0 else "quiz"
                quiz_num  = groups.quiz_count(cid) + (1 if step == 1 else 0)

                log.info(
                    f"▶ [{cid}] starting {step_name}"
                    + (f" #{quiz_num}" if step == 1 else "")
                )
                threading.Thread(
                    target=_step_thread,
                    args=(cid, step, quiz_num),
                    daemon=True,
                    name=f"{step_name}-{cid}",
                ).start()

        except Exception as e:
            log.exception(f"Scheduler error: {e}")

        time.sleep(300)   # check every 5 minutes


def _step_thread(cid: str, step: int, quiz_num: int):
    try:
        ok = run_lesson(cid) if step == 0 else run_quiz(cid, quiz_num)

        if ok:
            _last[cid] = time.time()
            groups.mark_done(cid, step)
            label = "lesson" if step == 0 else f"quiz #{quiz_num}"
            log.info(f"✅ [{cid}] {label} complete")
        else:
            log.warning(f"❌ [{cid}] step {step} failed — will retry next cycle")

    except Exception as e:
        log.exception(f"Step error [{cid}] step={step}: {e}")
    finally:
        with _lock:
            _running.discard(cid)


# ── Startup notify ────────────────────────────────────────────────────

def notify_admin(username: str):
    if not ADMIN_ID:
        return
    api.send(
        ADMIN_ID,
        f"🤖 <b>English Teacher & Quiz Bot started</b>\n"
        f"@{username}\n\n"
        f"Groups active : <b>{groups.active_count()}</b>\n"
        f"Min members   : <b>10,000</b>\n"
        f"Cycle         : 📖 Lesson → 🎯 Quiz (every 6h)\n\n"
        f"Send /dashboard to manage groups.",
    )


# ── Entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    me       = api.get_me()
    username = me.get("username", "unknown")

    log.info("=" * 55)
    log.info("  📚🎯  English Teacher & Quiz Bot")
    log.info(f"  @{username}")
    log.info(f"  Groups : {groups.active_count()}")
    log.info("  Cycle  : Lesson → Quiz (every 6h each)")
    log.info("=" * 55)

    notify_admin(username)

    threading.Thread(target=scheduler, daemon=True, name="scheduler").start()

    poller = Poller(groups)
    log.info("Polling started")
    while True:
        try:
            poller.tick()
        except Exception as e:
            log.warning(f"Poll error: {e}")
            time.sleep(5)
        time.sleep(0.5)
