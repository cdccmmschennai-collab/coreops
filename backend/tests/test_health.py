"""V0 smoke test: the liveness endpoint matches the OpenAPI contract."""


def test_health_liveness(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
