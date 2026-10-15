"""
TR-2088: Reporting problems (inconsistent data in batch jobs) - local tests.

Put this file in cab-ai-api/ecs/cab_batch/ (next to batch_processor.py) and run:

    uv run --with pytest pytest test_tr2088_batch.py -v

Nothing external is called. ServiceNow, LangGraph, the dedup endpoint and the
notification endpoint are all mocked, so no VPN or deployed services needed.

Covers:
  AC1  Daily batch only processes CRs in New / Assess / Authorize
  AC2  Email only on first store or a forward state move, never on backward moves
  AC3  A failed CR is retried so the agent writes its DB record; if every
       attempt fails, a cr_unrecorded event is logged
  AC5  CRs past review (what month-end processes) never reach the daily batch,
       and dedup-skipped CRs are not reprocessed
"""
import json
import os
import sys

import pytest

os.environ.setdefault("LANGGRAPH_BASE_URL", "http://localhost:2024")
os.environ.setdefault("SERVICE_NOW_USERNAME", "test")
os.environ.setdefault("SERVICE_NOW_PASSWORD", "test")
os.environ.setdefault("API_KEY", "test")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import batch_processor as bp  # noqa: E402


# ---------------------------------------------------------------- helpers

class FakeResp:
    def __init__(self, status, payload):
        self.status = status
        self.data = json.dumps(payload).encode("utf-8")


def snow_item(number, state, updated="2026-10-15 10:00:00"):
    """Shape ServiceNow returns with sysparm_display_value=all."""
    return {
        "number": {"display_value": number, "value": number},
        "state": {"display_value": state, "value": state},
        "sys_updated_on": {"display_value": updated, "value": updated},
    }


@pytest.fixture
def snow(monkeypatch):
    def _install(items):
        monkeypatch.setattr(
            bp.http, "request",
            lambda *a, **k: FakeResp(200, {"result": items}),
        )
    return _install


def daily_fetch():
    return bp.get_crs_from_snow("daily", "2026-10-15", "2026-10-15", "major")


# ---------------------------------------------------------------- AC1

def test_ac1_daily_keeps_only_new_assess_authorize(snow):
    snow([
        snow_item("CHG001", "New"),
        snow_item("CHG002", "Assess"),
        snow_item("CHG003", "Authorize"),
        snow_item("CHG004", "Scheduled"),
        snow_item("CHG005", "Implement"),
        snow_item("CHG006", "Review"),
        snow_item("CHG007", "Closed"),
        snow_item("CHG008", "Cancelled"),
    ])
    assert sorted(c["number"] for c in daily_fetch()) == ["CHG001", "CHG002", "CHG003"]


def test_ac1_review_state_is_excluded(snow):
    # Old code used a blocklist without 'Review', so these slipped through.
    snow([snow_item("CHG100", "Review")])
    assert daily_fetch() == []


def test_ac1_unknown_state_is_excluded(snow):
    # Allowlist means a state nobody planned for is skipped, not processed.
    snow([snow_item("CHG101", "Some New ServiceNow State")])
    assert daily_fetch() == []


def test_ac1_state_match_tolerates_case_and_whitespace(snow):
    snow([snow_item("CHG102", " assess "), snow_item("CHG103", "AUTHORIZE")])
    assert sorted(c["number"] for c in daily_fetch()) == ["CHG102", "CHG103"]


def test_ac1_keeps_sys_updated_on_for_dedup(snow):
    snow([snow_item("CHG104", "New", updated="2026-10-14 09:30:00")])
    assert daily_fetch() == [{"number": "CHG104", "sys_updated_on": "2026-10-14 09:30:00"}]


# ---------------------------------------------------------------- AC2 (pure rule)

@pytest.mark.parametrize(
    "case, prev, had_prior, cur, det, expected",
    [
        ("first store in New, PASS",          "",          False, "New",       "PASS",    True),
        ("first store in New, FAIL",          "",          False, "New",       "FAIL",    True),
        ("first store in Assess",             "",          False, "Assess",    "PASS",    True),
        ("first store in Authorize",          "",          False, "Authorize", "PASS",    True),
        ("first store in Scheduled",          "",          False, "Scheduled", "PASS",    False),
        ("New -> Assess",                     "New",       True,  "Assess",    "PASS",    True),
        ("Assess -> Authorize",               "Assess",    True,  "Authorize", "PASS",    True),
        ("New -> Authorize (skipped a step)", "New",       True,  "Authorize", "PASS",    True),
        ("Assess -> New (backward)",          "Assess",    True,  "New",       "PASS",    False),
        ("Authorize -> Assess (backward)",    "Authorize", True,  "Assess",    "PASS",    False),
        ("New -> New (no change)",            "New",       True,  "New",       "PASS",    False),
        ("Assess -> Assess (no change)",      "Assess",    True,  "Assess",    "FAIL",    False),
        ("Authorize -> Scheduled",            "Authorize", True,  "Scheduled", "PASS",    False),
        ("legacy record, no prev state",      "",          True,  "Assess",    "PASS",    False),
        ("unknown determination",             "",          False, "New",       "unknown", False),
        ("case/whitespace tolerant",          " new ",     True,  "ASSESS",    "PASS",    True),
    ],
)
def test_ac2_notification_rule(case, prev, had_prior, cur, det, expected):
    assert bp._should_notify(prev, had_prior, cur, det) is expected, case


def test_ac2_back_and_forth_sequence():
    """Exact scenario from the ticket: forward, back, forward again."""
    seq = ["New", "Assess", "New", "Assess", "Authorize"]
    expected = [True, True, False, True, True]
    prev, had_prior = "", False
    got = []
    for state in seq:
        got.append(bp._should_notify(prev, had_prior, state, "PASS"))
        prev, had_prior = state, True
    assert got == expected


# ---------------------------------------------------------------- wiring through the batch loop

def _wait_data(state, determination="PASS"):
    return {
        "summary": {"overall_determination": determination},
        "main_cr_data": {"cr_state": state},
    }


@pytest.fixture
def harness(monkeypatch):
    calls = {"notified": [], "processed": []}
    history = {}   # cr -> (prev_state, had_prior_record), what the DB says
    current = {}   # cr -> (state, determination), what this run produces
    skip = set()   # crs the dedup check says to skip

    monkeypatch.setattr(bp, "get_assistant_id", lambda: "eta_cab_v2")

    def fake_skip(cr, _updated, _run_type="daily"):
        prev, had = history.get(cr, ("", False))
        return cr in skip, prev, had
    monkeypatch.setattr(bp, "_should_skip_cr_batch", fake_skip)

    def fake_single(cr_info, _assistant_id, *_):
        cr = cr_info["number"]
        calls["processed"].append(cr)
        state, det = current[cr]
        mapping = {cr: {
            "thread_id": f"t-{cr}",
            "run_id": f"r-{cr}",
            "response_body": _wait_data(state, det),
            "run_status": "success",
        }}
        return cr, mapping, 0.01
    monkeypatch.setattr(bp, "_process_single_cr", fake_single)
    monkeypatch.setattr(bp, "_notify_cr_owner", lambda tid: calls["notified"].append(tid))
    return calls, history, current, skip


def run_batch(crs, run_type="daily"):
    bp.processing_and_store_helper(
        [{"number": c, "sys_updated_on": "2026-10-15 10:00:00"} for c in crs],
        "2026-10-15", run_type, "2026-10-15",
    )


def test_ac2_batch_emails_only_the_right_crs(harness):
    calls, history, current, _ = harness
    history.update({
        "CHG_FWD":  ("New", True),
        "CHG_BACK": ("Assess", True),
        "CHG_SAME": ("Assess", True),
    })
    current.update({
        "CHG_FWD":  ("Assess", "PASS"),
        "CHG_BACK": ("New", "PASS"),
        "CHG_SAME": ("Assess", "PASS"),
        "CHG_NEW":  ("New", "PASS"),
    })
    run_batch(["CHG_FWD", "CHG_BACK", "CHG_SAME", "CHG_NEW"])
    assert sorted(calls["notified"]) == ["t-CHG_FWD", "t-CHG_NEW"]
    assert sorted(calls["processed"]) == ["CHG_BACK", "CHG_FWD", "CHG_NEW", "CHG_SAME"]


# ---------------------------------------------------------------- AC5

def test_ac5_month_end_crs_never_reach_daily(snow):
    # Month-end pulls review_status=3, i.e. CRs already past implementation.
    # Those sit in Review/Closed, which the daily allowlist now rejects.
    snow([snow_item("CHG_ME1", "Review"), snow_item("CHG_ME2", "Closed")])
    assert daily_fetch() == []


@pytest.fixture
def last_run(monkeypatch):
    """Mock GET /cr/{cr}/last-run with whatever record the test wants."""
    def _install(record):
        monkeypatch.setattr(bp.http, "request", lambda *a, **k: FakeResp(200, record))
    return _install


def test_dedup_changed_cr_is_processed(last_run):
    last_run({"processed": True, "cr_state": "New",
              "snow_sys_updated_on": "OLD", "determination": "PASS"})
    skip, prev, had = bp._should_skip_cr_batch("CHG501", "NEW_TIMESTAMP")
    assert (skip, prev, had) == (False, "New", True)


def test_dedup_unchanged_cr_is_skipped(last_run):
    last_run({"processed": True, "cr_state": "Assess",
              "snow_sys_updated_on": "SAME", "determination": "FAIL"})
    skip, _, _ = bp._should_skip_cr_batch("CHG503", "SAME")
    assert skip is True


def test_dedup_never_processed_cr_is_not_skipped(last_run):
    last_run({"processed": False, "change_number": "CHG504"})
    skip, prev, had = bp._should_skip_cr_batch("CHG504", "ANY")
    assert (skip, prev, had) == (False, "", False)


def test_ac5_dedup_skipped_crs_are_not_reprocessed(harness):
    calls, history, current, skip = harness
    skip.add("CHG_DONE")
    history["CHG_DONE"] = ("Assess", True)
    current.update({"CHG_DONE": ("Assess", "PASS"), "CHG_OTHER": ("New", "PASS")})
    run_batch(["CHG_DONE", "CHG_OTHER"])
    assert calls["processed"] == ["CHG_OTHER"]


# ---------------------------------------------------------------- AC3 (retry so the DB record gets written)

def _ok(cr):
    return {cr: {"thread_id": "t", "run_id": "r", "response_body": {}, "run_status": "success"}}


def _errored(cr):
    return {cr: {"thread_id": "t", "run_id": "r", "response_body": {}, "run_status": "error"}}


@pytest.fixture
def agent(monkeypatch):
    """Script what each attempt against the agent returns.

    Each outcome is: a builder like _ok/_errored, None (thread/run creation failed),
    or an Exception instance (raised, e.g. network error).
    """
    monkeypatch.setattr(bp, "_CR_RETRY_BACKOFF", 0)
    monkeypatch.setattr(bp, "_CR_MAX_ATTEMPTS", 2)
    calls = []

    def _install(outcomes):
        def fake(crs, _assistant_id, snow_sys_updated_on=""):
            calls.append(crs[0])
            out = outcomes[len(calls) - 1]
            if isinstance(out, Exception):
                raise out
            return out(crs[0]) if callable(out) else out
        monkeypatch.setattr(bp, "process_change_requests_with_stateful_wait", fake)
        return calls
    return _install


def run_single(cr="CHG900"):
    return bp._process_single_cr({"number": cr, "sys_updated_on": "x"}, "eta_cab_v2")


def test_ac3_success_first_try_is_not_retried(agent):
    calls = agent([_ok])
    _, mapping, _ = run_single()
    assert len(calls) == 1
    assert mapping["CHG900"]["run_status"] == "success"


def test_ac3_errored_run_is_retried_and_succeeds(agent):
    calls = agent([_errored, _ok])
    _, mapping, _ = run_single()
    assert len(calls) == 2
    assert mapping["CHG900"]["run_status"] == "success"


def test_ac3_failed_thread_creation_is_retried(agent):
    calls = agent([None, _ok])
    _, mapping, _ = run_single()
    assert len(calls) == 2
    assert mapping["CHG900"]["run_status"] == "success"


def test_ac3_exception_is_retried_not_fatal(agent):
    calls = agent([RuntimeError("502 Bad Gateway"), _ok])
    _, mapping, _ = run_single()
    assert len(calls) == 2
    assert mapping["CHG900"]["run_status"] == "success"


def test_ac3_all_attempts_fail_logs_cr_unrecorded(agent, caplog):
    calls = agent([None, _errored])
    with caplog.at_level("ERROR"):
        _, mapping, _ = run_single()
    assert len(calls) == 2
    assert mapping["CHG900"]["run_status"] != "success"
    events = [r.getMessage() for r in caplog.records if "cr_unrecorded" in r.getMessage()]
    assert len(events) == 1 and "CHG900" in events[0]


def test_ac3_attempt_count_is_configurable(agent, monkeypatch):
    calls = agent([None, None, _ok])
    monkeypatch.setattr(bp, "_CR_MAX_ATTEMPTS", 3)
    _, mapping, _ = run_single()
    assert len(calls) == 3
    assert mapping["CHG900"]["run_status"] == "success"
