from uuid import uuid4

from fastapi.testclient import TestClient

from jayai.main import app, repository


def test_permissions_can_be_scoped_expired_and_revoked_per_user(monkeypatch):
    user = uuid4()
    key = "p" * 32
    monkeypatch.setenv("JAYAI_ENV", "development")
    monkeypatch.setenv("JAYAI_DEV_API_KEY", key)
    monkeypatch.setenv("JAYAI_DEV_USER_ID", str(user))

    class Store:
        def __init__(self):
            self.permissions = []

        def set_permission(self, owner, resource, actions, mode, expires):
            assert owner == user
            row = {"id": uuid4(), "resource": resource, "actions": actions,
                   "mode": mode, "expires_in_seconds": expires}
            self.permissions.append(row)
            return row["id"]

        def list_permissions(self, owner):
            assert owner == user
            return self.permissions

        def revoke_permission(self, owner, permission_id):
            assert owner == user
            before = len(self.permissions)
            self.permissions[:] = [p for p in self.permissions if p["id"] != permission_id]
            return len(self.permissions) != before

    store = Store()
    app.dependency_overrides[repository] = lambda: store
    headers = {"X-JayAI-Key": key}
    try:
        with TestClient(app) as client:
            created = client.post("/permissions", headers=headers, json={
                "resource": "text.analysis", "actions": ["count"],
                "mode": "APPROVE_SCOPE", "expires_in_seconds": 600,
            })
            assert created.status_code == 201
            permission_id = created.json()["id"]
            assert client.get("/permissions", headers=headers).json()[0]["actions"] == ["count"]
            assert client.delete(f"/permissions/{permission_id}", headers=headers).json() == {"revoked": True}
            assert client.delete(f"/permissions/{permission_id}", headers=headers).status_code == 404
            assert client.post("/permissions", headers=headers, json={
                "resource": "*", "actions": ["count"], "mode": "APPROVE_SCOPE",
            }).status_code == 422
            assert client.post("/permissions", headers=headers, json={
                "resource": "text.analysis", "actions": ["count", "count"],
                "mode": "APPROVE_SCOPE",
            }).status_code == 422
            assert client.post("/permissions", headers=headers, json={
                "resource": "text.analysis", "actions": ["count"],
                "mode": "APPROVE_SCOPE", "expires_in_seconds": 90000,
            }).status_code == 422
    finally:
        app.dependency_overrides.clear()
