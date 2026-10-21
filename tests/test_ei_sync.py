"""EI API smoke tests; run with isolated DATA_DIR and test credentials."""
import importlib
import os
import tempfile
import unittest


class EISyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = cls.temp.name
        os.environ["ADMIN_USERNAME"] = "ei-test"
        os.environ["ADMIN_PASSWORD"] = "test-password-not-for-production"
        os.environ["SECRET_KEY"] = "test-secret-only"
        os.environ["SESSION_COOKIE_SECURE"] = "false"
        cls.module = importlib.import_module("app")
        cls.app = cls.module.app
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        response = self.client.post("/login", data={"username": "ei-test", "password": "test-password-not-for-production"})
        self.assertEqual(response.status_code, 302)

    def payload(self, revision=1):
        return {
            "recordId": "3e67a1f7-6a7b-43a5-985a-cdb9e5e1a905",
            "revision": revision,
            "selected": ["1"],
            "accepted": True,
            "identification": "TEST-123",
            "date": "2026-10-20",
            "time": "12:30",
            "checks": {"1": {}},
            "details": {"1": {}},
        }

    def test_authenticated_page(self):
        response = self.client.get("/ei/new")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"European Instructions", response.data)

    def test_sync_idempotency_and_conflict(self):
        data = self.payload()
        first = self.client.post("/api/ei/sync", json=data)
        self.assertEqual(first.status_code, 200)
        retry = self.client.post("/api/ei/sync", json=data)
        self.assertEqual(retry.status_code, 200)
        changed = dict(data, identification="DIFFERENT")
        conflict = self.client.post("/api/ei/sync", json=changed)
        self.assertEqual(conflict.status_code, 409)
        next_version = self.client.post("/api/ei/sync", json=self.payload(2))
        self.assertEqual(next_version.status_code, 200)

    def test_validation(self):
        bad = self.payload()
        bad["selected"] = ["999"]
        self.assertEqual(self.client.post("/api/ei/sync", json=bad).status_code, 400)

    def test_anonymous_sync_rejected(self):
        self.client.post("/logout")
        response = self.client.post("/api/ei/sync", json=self.payload())
        self.assertNotEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
