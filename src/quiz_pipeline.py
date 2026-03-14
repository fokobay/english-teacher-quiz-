"""
Full quiz session for one group — 20 questions, 8 types.
"""
import time
import threading
from src.logger    import setup_logger
from src.generator import Generator
from src.scores    import Scores
from src           import api

log          = setup_logger("quiz")
POLL_SECONDS = 180
MCQ_LETTERS  = ["A", "B", "C", "D"]
DIFF_STARS   = {"easy": "⭐", "medium": "⭐⭐", "hard": "⭐⭐⭐"}
TYPE_LABEL   = {
    "mcq":           "📝",
    "tf":            "✔️",
    "fill_blank":    "📝",
    "odd_one_out":   "🔍",
    "match_def":     "🔤",
    "error_spot":    "⚠️",
    "complete_sent": "💬",
    "word_form":     "🔤",
}

# Shared state — protected by _poll_lock
_poll_lock:  threading.Lock = threading.Lock()
poll_answers: dict          = {}   # poll_id → state dict

# Per-group Scores instances
_scores_instances: dict        = {}
_scores_lock:      threading.Lock = threading.Lock()


def _get_scores(chat_id: str) -> Scores:
    with _scores_lock:
        if chat_id not in _scores_instances:
            _scores_instances[chat_id] = Scores()
        return _scores_instances[chat_id]


# ── Public entry point ────────────────────────────────────────────────

def run_quiz(chat_id: str, quiz_num: int) -> bool:
    log.info(f"[{chat_id}] Quiz #{quiz_num} starting")
    try:
        questions = Generator().generate()
    except Exception as e:
        log.error(f"[{chat_id}] Generator error: {e}")
        api.send(chat_id, "⚠️ Could not generate quiz. Will try next session.")
        return False

    if not questions:
        log.error(f"[{chat_id}] Empty questions list")
        return False

    scores = _get_scores(chat_id)
    scores.start(chat_id)

    # Announce
    msg = api.send(chat_id, api.txt_announce(quiz_num, len(questions)))
    if msg:
        api.pin(chat_id, msg["message_id"])
    time.sleep(10)

    # Questions
    for i, q in enumerate(questions, 1):
        _run_one(chat_id, i, q, len(questions), scores)
        if i == 10:
            time.sleep(1)
            api.send(chat_id, api.txt_halfway(scores.session_board(chat_id)))
        time.sleep(3)

    # Final results
    board = scores.session_board(chat_id)
    total = scores.count(chat_id)
    scores.commit(chat_id, quiz_num)

    msg = api.send(chat_id, api.txt_final(board, quiz_num, total, len(questions)))
    if msg:
        api.pin(chat_id, msg["message_id"])

    # All-time leaderboard every 5 quizzes
    if quiz_num % 5 == 0:
        time.sleep(2)
        api.send(chat_id, api.txt_alltime(scores.alltime_board(chat_id)))

    log.info(f"[{chat_id}] Quiz #{quiz_num} done — {total} players")
    return True


# ── Single question ───────────────────────────────────────────────────

def _run_one(chat_id: str, number: int, q: dict, total_q: int, scores: Scores):
    qtype  = q.get("type", "mcq")
    diff   = DIFF_STARS.get(q.get("difficulty", ""), "")
    icon   = TYPE_LABEL.get(qtype, "📝")
    q_text = f"Q{number}/{total_q} {diff} {icon}\n{q['question']}"

    if qtype == "tf":
        options_list  = ["✅ True", "❌ False"]
        correct_index = 0 if q["correct"] == "True" else 1
    else:
        opts          = q["options"]
        options_list  = [opts["A"], opts["B"], opts["C"], opts["D"]]
        correct_index = MCQ_LETTERS.index(q["correct"])

    # api.send_poll returns the full Message object (dict) from Telegram,
    # which has "message_id" at the top level and "poll" nested inside.
    result = api.send_poll(
        chat_id       = chat_id,
        question      = q_text,
        options       = options_list,
        correct_index = correct_index,
        explanation   = q.get("explanation", ""),
    )

    poll_id = None
    msg_id  = None

    if result:
        msg_id  = result.get("message_id")
        poll    = result.get("poll", {})
        poll_id = poll.get("id")

        if poll_id:
            with _poll_lock:
                poll_answers[poll_id] = {
                    "chat_id":     str(chat_id),
                    "correct_idx": correct_index,
                    "q_num":       number,
                    "msg_id":      msg_id,
                    "answered":    set(),
                }

    # لو الـ poll ما اتبعتش، متستناش 3 دقايق عبثاً
    if not poll_id:
        log.warning(f"[{chat_id}] Q{number} poll failed — skipping wait")
        return

    # Wait for the poll to expire
    time.sleep(POLL_SECONDS)

    # Close the poll on Telegram and clean up state كاملاً من الـ memory
    with _poll_lock:
        state = poll_answers.pop(poll_id, None)
    if state and state.get("msg_id"):
        api.stop_poll(chat_id, state["msg_id"])


# ── Poll answer callback (called from Poller thread) ──────────────────

def on_poll_answer(poll_id: str, user_id: int, name: str, option_ids: list):
    with _poll_lock:
        state = poll_answers.get(poll_id)
        if not state:
            return
        if user_id in state["answered"]:
            return
        state["answered"].add(user_id)
        correct = bool(option_ids) and option_ids[0] == state["correct_idx"]
        chat_id = state["chat_id"]
        q_num   = state["q_num"]

    scores = _get_scores(chat_id)
    scores.record(chat_id, user_id, name, correct)
    log.info(f"[{chat_id}] Q{q_num} {name}: {'✓' if correct else '✗'}")
