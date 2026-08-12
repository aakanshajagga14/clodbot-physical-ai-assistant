from fastapi.testclient import TestClient

from clodbot.api.server import app


def test_dashboard_state_endpoint_and_reset():
    with TestClient(app) as client:
        state = client.get("/api/state")
        assert state.status_code == 200
        payload = state.json()
        assert payload["machine"]["name"] == "Hydraulic Pump A"
        assert payload["cyberwave"]["status"] in {"MOCK", "CONNECTED"}

        safe = client.post("/api/scenario/correct")
        assert safe.status_code == 200
        assert safe.json()["safety"]["status"] == "SAFE"

        reset = client.post("/api/reset")
        assert reset.status_code == 200
        assert reset.json()["machine"]["pressure_psi"] == 78
