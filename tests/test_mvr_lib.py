"""Unit tests for scripts/mvr_lib.py: real flows become emulator-shaped records the frozen checks can read."""

import json
import urllib.request

from grader import checks as chk
from scripts.mvr_lib import Recorder, agreement, classify

FLAG = "join_button_trial_1_1"


def flow(method, path, req=None, resp=None, t=100.0, status=200):
    return {"t": t, "method": method, "host": "edge.api.flagsmith.com", "path": path,
            "req_body": json.dumps(req) if req is not None else "", "status": status,
            "resp_body": json.dumps(resp) if resp is not None else ""}  # fmt: skip


def test_identities_response_reads_the_trial_flag_among_others():
    resp = {"flags": [{"feature": {"name": "other"}, "feature_state_value": "x"},
                      {"feature": {"name": FLAG}, "feature_state_value": "Join free"}]}  # fmt: skip
    r = classify(flow("POST", "/api/v1/identities/", {"identifier": "u1"}, resp), FLAG)
    assert (r["kind"], r["identifier"], r["returned_value"]) == ("flags", "u1", "Join free")
    r = classify(flow("GET", "/api/v1/identities/?identifier=u2", None, resp), FLAG)
    assert r["identifier"] == "u2"


def test_events_and_environment_document():
    ev = {"events": [{"event": "$flag_exposure", "feature_name": FLAG, "identifier": "u1", "timestamp": 1}]}
    r = classify(flow("POST", "/api/v1/events", ev), FLAG)
    assert r["kind"] == "events" and r["events"][0]["identifier"] == "u1"
    assert classify(flow("GET", "/api/v1/environment-document/"), FLAG)["kind"] == "environment"
    assert classify(flow("OPTIONS", "/api/v1/events"), FLAG)["kind"] == "preflight"


def test_phase_is_taken_at_request_start_and_checks_read_records():
    rec = Recorder(FLAG)
    rec.set_phase("load", 10.0)
    rec.set_phase("click", 20.0)
    resp = {"flags": [{"feature": {"name": FLAG}, "feature_state_value": "Join"}]}
    rec.add_flow(flow("POST", "/api/v1/identities/", {"identifier": "u1"}, resp, t=11.0))
    rec.add_flow(flow("POST", "/api/v1/events", {"events": [{"event": "join_clicked", "identifier": "u1"}]}, t=21.0))
    assert [r["phase"] for r in rec.records] == ["load", "click"]
    assert chk.phase_identity(rec.records, "load", FLAG) == "u1"
    assert chk.expected_value(rec.records, "load", "u1") == "Join"


def test_recorder_http_endpoints():
    rec = Recorder(FLAG)
    rec.start()
    try:
        urllib.request.urlopen(f"{rec.url}/__grader/phase?name=load", timeout=5).read()
        body = json.dumps(flow("POST", "/api/v1/identities/", {"identifier": "u9"}, {"flags": []}, t=1e12)).encode()
        req = urllib.request.Request(f"{rec.url}/__grader/flow", data=body, method="POST")
        urllib.request.urlopen(req, timeout=5).read()
    finally:
        rec.stop()
    assert rec.records[0]["phase"] == "load" and rec.records[0]["identifier"] == "u9"


def test_agreement_counts_and_disagreements():
    sel = {"failing": [{"trial_id": "a", "stage": "primary", "variant": "skill", "stack": "react"}],
           "passing_sample": [{"trial_id": "b", "stage": "replication", "variant": "prompt", "stack": "node"},
                              {"trial_id": "c", "stage": "primary", "variant": "prompt", "stack": "node"}]}  # fmt: skip
    real = {"a": {"passed": True, "failed_checks": []}, "b": {"passed": True, "failed_checks": ["C7"]}}
    mock = {"a": {"passed": False, "failed_checks": ["C2"]}, "b": {"passed": True, "failed_checks": []},
            "c": {"passed": True, "failed_checks": []}}  # fmt: skip
    t = agreement(sel, real, mock)
    assert t["by"]["overall"] == {"n": 2, "agree": 1, "checks_agree": 0}
    assert [x["trial_id"] for x in t["disagreements"]] == ["a"]
    assert [x["trial_id"] for x in t["check_differences"]] == ["b"]
    assert t["not_compared"] == [{"trial_id": "c", "why": "no real verdict"}]
