from fastapi.testclient import TestClient

from app.main import app


def test_get_grade_rule_with_encoded_slash_value():
    with TestClient(app) as client:
        response = client.get("/api/v1/rules/grade/%E5%88%9D%E4%B8%AD/%E5%B0%8F%E5%AD%A6%E6%9A%91%E6%9C%9F")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["grade"] == "初中/小学暑期"
