import importlib
import os
from pathlib import Path


def load_app(tmp_path: Path):
    os.environ["DATA_DIR"] = str(tmp_path / "data")
    os.environ["SECRET_KEY"] = "test-secret"
    os.environ["ADMIN_USERNAME"] = "martijn"
    os.environ["ADMIN_PASSWORD"] = "test-password"
    os.environ["SESSION_COOKIE_SECURE"] = "false"
    import app as app_module
    importlib.reload(app_module)
    app_module.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app_module


def login(client):
    return client.post("/login", data={"username": "martijn", "password": "test-password"}, follow_redirects=True)


def test_health(tmp_path):
    module = load_app(tmp_path)
    client = module.app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_login_and_save_day(tmp_path):
    module = load_app(tmp_path)
    client = module.app.test_client()
    assert login(client).status_code == 200
    response = client.post(
        "/dag/2026-10-13",
        data={
            "service_number": "12345",
            "start_time": "06:12",
            "end_time": "14:30",
            "overrun_minutes": "15",
            "notes": "Testdienst",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"12345" in response.data
    assert b"Testdienst" in response.data


def test_upload_unique_names(tmp_path):
    from io import BytesIO

    module = load_app(tmp_path)
    client = module.app.test_client()
    login(client)
    response = client.post(
        "/dag/2026-10-13/upload/dienstlijst",
        data={"attachments": [(BytesIO(b"one"), "image.jpg"), (BytesIO(b"two"), "image.jpg")]},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    upload_dir = tmp_path / "data" / "administratie" / "2026" / "42" / "dinsdag"
    files = list(upload_dir.glob("*.jpg"))
    assert len(files) == 2
    assert files[0].name != files[1].name
