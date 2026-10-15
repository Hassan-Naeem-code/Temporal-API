"""
Applies the TR-2088 changes to batch_processor.py.

Run from cab-ai-api/ecs/cab_batch:

    python apply_tr2088.py

Safe by design:
  - Finds every anchor first. If ANY anchor is missing, nothing is written.
  - Writes a backup to batch_processor.py.bak before changing anything.
  - Compiles the result; if it does not compile, the backup is restored.
  - Running it twice is a no-op (detects the change is already in).
"""
import py_compile
import re
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).with_name("batch_processor.py")
BACKUP = TARGET.with_suffix(".py.bak")

SHOULD_NOTIFY = '''_STATE_RANK = {'New': 0, 'Assess': 1, 'Authorize': 2}


def _should_notify(prev_cr_state: str, had_prior_record: bool, cr_state: str, determination: str) -> bool:
    """TR-2088 AC2: email on first store or a forward state move. Never on backward moves."""
    if (determination or '').strip().upper() == 'UNKNOWN':
        return False
    cur = (cr_state or '').strip().title()
    if cur not in _STATE_RANK:
        return False
    if not had_prior_record:
        return True
    prev = (prev_cr_state or '').strip().title()
    if prev not in _STATE_RANK:
        return False  # legacy record with no stored state: history unknown, do not spam
    return _STATE_RANK[cur] > _STATE_RANK[prev]


'''

NOTIFY_BLOCK = '''prev_cr_state = prev_states.get(cr, '')
had_prior_record = had_prior_records.get(cr, False)
notify = _should_notify(prev_cr_state, had_prior_record, cr_state, determination)
logger.info(json.dumps({
    'event': 'notification_decision',
    'change_number': cr,
    'prev_state': prev_cr_state,
    'had_prior_record': had_prior_record,
    'cr_state': cr_state,
    'determination': determination,
    'notify': notify,
}))
if notify:
    _notify_cr_owner(cr_data.get('thread_id'))'''

PROCESS_SINGLE_CR = '''# TR-2088 AC3: retry a failed CR so the agent completes and writes its DB record
_CR_MAX_ATTEMPTS = int(os.environ.get('BATCH_CR_MAX_ATTEMPTS', '2'))
_CR_RETRY_BACKOFF = int(os.environ.get('BATCH_CR_RETRY_BACKOFF', '30'))


def _process_single_cr(cr_info: dict, assistant_id: str) -> tuple[str, dict | None, float]:
    """Process one CR and return (change_number, thread_mapping, duration_seconds).

    TR-2088 AC3: a failed attempt is retried up to BATCH_CR_MAX_ATTEMPTS times so the
    agent gets to finish and write the processing record. If every attempt fails, a
    cr_unrecorded event is logged so the missing record is visible in Dynatrace.
    """
    cr = cr_info['number']
    sys_updated_on = cr_info.get('sys_updated_on', '')
    cr_start = time.perf_counter()
    thread_mapping = None

    for attempt in range(1, _CR_MAX_ATTEMPTS + 1):
        try:
            thread_mapping = process_change_requests_with_stateful_wait(
                [cr], assistant_id, snow_sys_updated_on=sys_updated_on
            )
        except Exception as e:
            logger.error(f"Attempt {attempt} for {cr} raised {type(e).__name__}: {e}")
            thread_mapping = None

        if thread_mapping and thread_mapping.get(cr, {}).get('run_status') == 'success':
            if attempt > 1:
                logger.info(json.dumps({'event': 'cr_retry_succeeded', 'change_number': cr, 'attempt': attempt}))
            break

        if attempt < _CR_MAX_ATTEMPTS:
            logger.warning(json.dumps({
                'event': 'cr_retry',
                'change_number': cr,
                'attempt': attempt,
                'next_attempt_in_seconds': _CR_RETRY_BACKOFF,
            }))
            time.sleep(_CR_RETRY_BACKOFF)
        else:
            logger.error(json.dumps({
                'event': 'cr_unrecorded',
                'change_number': cr,
                'attempts': attempt,
                'reason': 'all attempts failed, no processing record written',
            }))

    return cr, thread_mapping, round(time.perf_counter() - cr_start, 2)


'''


def fail(msg):
    print(f"ABORTED, nothing written: {msg}")
    sys.exit(1)


def indent(block, prefix):
    return "\n".join(prefix + line if line else line for line in block.splitlines())


def main():
    if not TARGET.exists():
        fail(f"{TARGET.name} not found. Run this from cab-ai-api/ecs/cab_batch.")
    src = TARGET.read_text(encoding="utf-8")
    nl = "\r\n" if "\r\n" in src else "\n"
    src = src.replace("\r\n", "\n")

    if "_ALLOWED_BATCH_STATES" in src or "def _should_notify" in src or "_CR_MAX_ATTEMPTS" in src:
        fail("TR-2088 changes already present (or partially). Restore from git/backup first.")

    # ---- Change 1a: blocklist constant -> allowlist
    m = re.search(r"^([ \t]*)_STATES_PAST_REVIEW\s*=.*$", src, re.M)
    if not m:
        fail("Change 1a: could not find the `_STATES_PAST_REVIEW = ...` line.")
    ind = m.group(1)
    src = src[:m.start()] + (
        f"{ind}# TR-2088 AC1: allowlist. Anything else (Review, Scheduled, unknown states) is skipped.\n"
        f"{ind}_ALLOWED_BATCH_STATES = {{'New', 'Assess', 'Authorize'}}"
    ) + src[m.end():]

    # ---- Change 1b: the filter condition
    m = re.search(r"if\s+state_display\s+in\s+_STATES_PAST_REVIEW\s*:", src)
    if not m:
        fail("Change 1b: could not find `if state_display in _STATES_PAST_REVIEW:`.")
    src = src[:m.start()] + "if (state_display or '').strip().title() not in _ALLOWED_BATCH_STATES:" + src[m.end():]
    if "_STATES_PAST_REVIEW" in src:
        fail("_STATES_PAST_REVIEW is still used somewhere else. Check it by hand.")

    # ---- Change 2b: replace the old notification block (do before 2a so indices are simple)
    start = re.search(r"^([ \t]*)prev_cr_state\s*=\s*prev_states\.get\(cr,\s*''\)\s*$", src, re.M)
    if not start:
        fail("Change 2b: could not find `prev_cr_state = prev_states.get(cr, '')`.")
    end = re.compile(r"^[ \t]*_notify_cr_owner\(cr_data\.get\('thread_id'\)\)\s*$", re.M).search(src, start.end())
    if not end:
        fail("Change 2b: could not find the `_notify_cr_owner(cr_data.get('thread_id'))` call after it.")
    old_block = src[start.start():end.end()]
    if old_block.count("\n") > 40:
        fail("Change 2b: block between the anchors is unexpectedly long. Apply this one by hand.")
    if "had_prior_records" not in src:
        fail("Change 2b: `had_prior_records` is not defined in the file. Apply this one by hand.")
    src = src[:start.start()] + indent(NOTIFY_BLOCK, start.group(1)) + src[end.end():]

    # ---- Change 2a: insert _should_notify above _notify_cr_owner
    m = re.search(r"^def _notify_cr_owner\b", src, re.M)
    if not m:
        fail("Change 2a: could not find `def _notify_cr_owner`.")
    src = src[:m.start()] + SHOULD_NOTIFY + src[m.start():]

    # ---- Change 3: replace _process_single_cr (constants go right above it)
    m = re.search(r"^def _process_single_cr\b", src, re.M)
    if not m:
        fail("Change 3: could not find `def _process_single_cr`.")
    nxt = re.compile(r"^(def |class |@|if __name__)", re.M).search(src, m.end())
    func_end = nxt.start() if nxt else len(src)
    if "process_change_requests_with_stateful_wait" not in src[m.start():func_end]:
        fail("Change 3: _process_single_cr does not look like expected. Apply this one by hand.")
    src = src[:m.start()] + PROCESS_SINGLE_CR + src[func_end:]
    for name in ("import os", "import time", "import json"):
        if not re.search(rf"^{name}\b", src, re.M):
            fail(f"Change 3 needs `{name}` at module level, not found.")

    # ---- write, compile, roll back on failure
    shutil.copy2(TARGET, BACKUP)
    TARGET.write_text(src.replace("\n", nl), encoding="utf-8", newline="")
    try:
        py_compile.compile(str(TARGET), doraise=True)
    except py_compile.PyCompileError as e:
        shutil.copy2(BACKUP, TARGET)
        fail(f"result did not compile, original restored:\n{e}")

    print("TR-2088 applied to batch_processor.py")
    print("  1a/1b  state allowlist (AC1, AC5)")
    print("  2a/2b  _should_notify + notification_decision log (AC2)")
    print("  3      retry + cr_unrecorded in _process_single_cr (AC3)")
    print(f"Backup: {BACKUP.name}   Review with: git diff batch_processor.py")


if __name__ == "__main__":
    main()
