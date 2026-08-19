"""API contract tests. No server, no network — TestClient drives the app directly."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from panel.api.app import SESSIONS, app
from panel.demo_answers import DEMO_ANSWERS, NO_MORE


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Each test gets its own store; the lifespan opens it on client entry.
    monkeypatch.setenv("PANEL_DB", str(tmp_path / "panel.db"))
    SESSIONS.clear()
    with TestClient(app) as c:
        yield c
    SESSIONS.clear()


def _start(client, **overrides):
    body = {"role": "Backend Engineer", "interview_type": "behavioral", "minutes": 20}
    body.update(overrides)
    response = client.post("/api/sessions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _answer_for(step: dict) -> str:
    """Answer whatever competency the API says it just asked about."""
    bank = DEMO_ANSWERS.get(step.get("competency_id") or "", [])
    return bank[0] if bank else NO_MORE


def _run_to_completion(client, session_id, first_step):
    step = first_step
    guard = 0
    while not step["done"]:
        response = client.post(
            f"/api/sessions/{session_id}/answer", json={"text": _answer_for(step)}
        )
        assert response.status_code == 200, response.text
        step = response.json()
        guard += 1
        assert guard < 60, "interview did not terminate"
    return step


class TestHealth:
    def test_reports_which_reasoner_is_live(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["reasoner"] in {"heuristic", "anthropic"}
        assert body["demo_mode"] == (body["model"] is None)

    def test_states_the_in_memory_caveat(self, client):
        assert "memory" in client.get("/api/health").json()["note"].lower()


class TestSessionCreation:
    def test_returns_frozen_plan_and_opening_question(self, client):
        body = _start(client)
        assert body["plan"]["plan_hash"]
        assert body["plan"]["competencies"]
        assert body["step"]["decision"] == "ask"
        assert not body["step"]["done"]
        assert body["step"]["utterance"]
        assert body["step"]["progress"]["competency_total"] == len(body["plan"]["competencies"])

    def test_same_inputs_produce_the_same_rubric_version(self, client):
        a, b = _start(client), _start(client)
        assert a["session_id"] != b["session_id"]
        assert a["plan"]["plan_hash"] == b["plan"]["plan_hash"]

    def test_rejects_out_of_range_duration(self, client):
        assert client.post("/api/sessions", json={"role": "X", "minutes": 500}).status_code == 422

    def test_rejects_unknown_interview_type(self, client):
        response = client.post("/api/sessions", json={"role": "X", "interview_type": "vibes"})
        assert response.status_code == 422


class TestAnswering:
    def test_progress_advances_with_each_answer(self, client):
        body = _start(client)
        sid = body["session_id"]
        before = body["step"]["progress"]["exchanges"]

        step = client.post(
            f"/api/sessions/{sid}/answer", json={"text": _answer_for(body["step"])}
        ).json()
        assert step["progress"]["exchanges"] == before + 1

    def test_rejects_empty_answer(self, client):
        sid = _start(client)["session_id"]
        assert client.post(f"/api/sessions/{sid}/answer", json={"text": ""}).status_code == 422

    def test_unknown_session_is_404(self, client):
        response = client.post("/api/sessions/nope/answer", json={"text": "hello"})
        assert response.status_code == 404
        assert "restart" in response.json()["detail"].lower()

    def test_answering_a_finished_interview_is_409(self, client):
        body = _start(client)
        sid = body["session_id"]
        _run_to_completion(client, sid, body["step"])

        response = client.post(f"/api/sessions/{sid}/answer", json={"text": "more"})
        assert response.status_code == 409


class TestReport:
    def test_report_is_409_while_the_interview_is_running(self, client):
        sid = _start(client)["session_id"]
        assert client.get(f"/api/sessions/{sid}/report").status_code == 409

    def test_full_run_yields_a_cited_report(self, client):
        body = _start(client, mode="screening")
        sid = body["session_id"]
        final = _run_to_completion(client, sid, body["step"])
        assert final["decision"] == "close"

        report = client.get(f"/api/sessions/{sid}/report").json()
        assert report["plan_hash"] == body["plan"]["plan_hash"]
        assert report["recommendation"]
        assert 0.0 <= report["coverage"] <= 1.0
        assert len(report["competencies"]) == len(body["plan"]["competencies"])

        transcript = "\n".join(t["text"] for t in report["transcript"]["turns"])
        for entry in report["competencies"]:
            if entry["level"] is None:
                assert not entry["supporting"]
            else:
                assert entry["supporting"], "a scored competency must cite evidence"
                for item in entry["supporting"]:
                    assert item["quote"] in transcript

    def test_practice_mode_attaches_coaching_screening_does_not(self, client):
        practice = _start(client, mode="practice")
        _run_to_completion(client, practice["session_id"], practice["step"])
        practice_report = client.get(
            f"/api/sessions/{practice['session_id']}/report"
        ).json()

        screening = _start(client, mode="screening")
        _run_to_completion(client, screening["session_id"], screening["step"])
        screening_report = client.get(
            f"/api/sessions/{screening['session_id']}/report"
        ).json()

        assert any(e["coaching"] for e in practice_report["competencies"])
        assert all(e["coaching"] is None for e in screening_report["competencies"])


class TestHistory:
    def test_history_is_empty_before_anything_finishes(self, client):
        assert client.get("/api/history").json()["interviews"] == []

    def test_a_finished_interview_is_recorded_without_being_asked_for(self, client):
        body = _start(client)
        _run_to_completion(client, body["session_id"], body["step"])

        # Note: no call to /report here — finishing is what records it.
        interviews = client.get("/api/history").json()["interviews"]
        assert len(interviews) == 1
        assert interviews[0]["plan_hash"] == body["plan"]["plan_hash"]
        assert interviews[0]["role"] == "Backend Engineer"

    def test_an_abandoned_interview_is_not_recorded(self, client):
        body = _start(client)
        client.post(
            f"/api/sessions/{body['session_id']}/answer",
            json={"text": _answer_for(body["step"])},
        )
        client.delete(f"/api/sessions/{body['session_id']}")

        assert client.get("/api/history").json()["interviews"] == []

    def test_past_report_round_trips_with_citations(self, client):
        body = _start(client, mode="screening")
        _run_to_completion(client, body["session_id"], body["step"])
        interview_id = client.get("/api/history").json()["interviews"][0]["id"]

        report = client.get(f"/api/history/{interview_id}").json()
        assert report["plan_hash"] == body["plan"]["plan_hash"]
        transcript = "\n".join(t["text"] for t in report["transcript"]["turns"])
        for entry in report["competencies"]:
            for item in entry["supporting"]:
                assert item["quote"] in transcript

    def test_unknown_interview_is_404(self, client):
        assert client.get("/api/history/9999").status_code == 404

    def test_history_can_be_filtered_by_role(self, client):
        a = _start(client, role="Backend Engineer")
        _run_to_completion(client, a["session_id"], a["step"])
        b = _start(client, role="Data Scientist")
        _run_to_completion(client, b["session_id"], b["step"])

        filtered = client.get("/api/history", params={"role": "Data Scientist"}).json()
        assert [i["role"] for i in filtered["interviews"]] == ["Data Scientist"]
        assert len(client.get("/api/history").json()["interviews"]) == 2


class TestTrends:
    def test_trend_accumulates_across_runs_of_one_rubric(self, client):
        first = _start(client)
        _run_to_completion(client, first["session_id"], first["step"])
        second = _start(client)
        _run_to_completion(client, second["session_id"], second["step"])

        plan_hash = first["plan"]["plan_hash"]
        assert second["plan"]["plan_hash"] == plan_hash

        trends = client.get(f"/api/trends/{plan_hash}").json()
        assert trends["runs"] == 2
        assert trends["competencies"]
        assert all(len(c["points"]) == 2 for c in trends["competencies"])

    def test_a_different_rubric_is_excluded_from_the_trend(self, client):
        behavioral = _start(client, interview_type="behavioral")
        _run_to_completion(client, behavioral["session_id"], behavioral["step"])
        technical = _start(client, interview_type="technical_verbal")
        _run_to_completion(client, technical["session_id"], technical["step"])

        hash_a = behavioral["plan"]["plan_hash"]
        assert technical["plan"]["plan_hash"] != hash_a

        trends = client.get(f"/api/trends/{hash_a}").json()
        assert trends["runs"] == 1
        assert "not comparable" in trends["note"]

    def test_unknown_rubric_returns_an_empty_trend_not_an_error(self, client):
        trends = client.get("/api/trends/deadbeefdeadbeef").json()
        assert trends["runs"] == 0
        assert trends["competencies"] == []


class TestSessionState:
    def test_state_survives_a_page_reload(self, client):
        body = _start(client)
        sid = body["session_id"]
        client.post(f"/api/sessions/{sid}/answer", json={"text": _answer_for(body["step"])})

        state = client.get(f"/api/sessions/{sid}").json()
        assert state["plan"]["plan_hash"] == body["plan"]["plan_hash"]
        assert len(state["transcript"]["turns"]) >= 3
        assert not state["has_report"]

    def test_delete_removes_the_session(self, client):
        sid = _start(client)["session_id"]
        assert client.delete(f"/api/sessions/{sid}").status_code == 204
        assert client.get(f"/api/sessions/{sid}").status_code == 404
