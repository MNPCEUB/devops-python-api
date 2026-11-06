import pytest
from fastapi.testclient import TestClient

from app.main import app, tasks

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_tasks() -> None:
    """Isola os testes, limpando o armazenamento em memória."""

    tasks.clear()


def test_root_points_to_docs() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"
    assert "1.1.0" in response.json()["message"]


def test_health_returns_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GIT_SHA", raising=False)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.1.0", "commit": "local"}


def test_health_returns_deployed_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_SHA", "abc1234")

    response = client.get("/health")

    assert response.json()["commit"] == "abc1234"


def test_list_starts_empty() -> None:
    response = client.get("/tasks")

    assert response.status_code == 200
    assert response.json() == []


def test_create_and_list_task() -> None:
    created = client.post("/tasks", json={"title": "Estudar GitHub Actions"})
    listed = client.get("/tasks")

    assert created.status_code == 201
    assert created.json() == {
        "id": 1,
        "title": "Estudar GitHub Actions",
        "done": False,
    }
    assert listed.json() == [created.json()]


def test_rejects_short_title() -> None:
    response = client.post("/tasks", json={"title": "CI"})

    assert response.status_code == 422


def test_complete_task() -> None:
    client.post("/tasks", json={"title": "Executar testes"})

    response = client.patch("/tasks/1/done")

    assert response.status_code == 200
    assert response.json()["done"] is True


def test_complete_unknown_task_returns_404() -> None:
    response = client.patch("/tasks/99/done")

    assert response.status_code == 404
    assert response.json() == {"detail": "Tarefa não encontrada"}
