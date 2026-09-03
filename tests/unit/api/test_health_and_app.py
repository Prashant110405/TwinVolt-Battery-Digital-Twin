"""Unit tests for FastAPI App and Health routes."""

import unittest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import create_default_services


class TestAppAndHealth(unittest.TestCase):
    """Test suite verifying FastAPI initialization, OpenAPI docs, and health endpoints."""

    def setUp(self) -> None:
        self.services = create_default_services()
        self.app = create_app(services=self.services)
        self.client = TestClient(self.app)

    def test_health_endpoint(self) -> None:
        """GET /health returns 200 OK and service metadata."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["service"], "twinvolt-api")
        self.assertEqual(data["version"], "1.0.0")

    def test_openapi_json(self) -> None:
        """OpenAPI schema generation succeeds and exposes defined route paths."""
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertIn("paths", schema)
        self.assertIn("/health", schema["paths"])
        self.assertIn("/api/v1/packs", schema["paths"])
        self.assertIn("/api/v1/twins", schema["paths"])
        self.assertIn("/api/v1/telemetry/ingest", schema["paths"])
        self.assertIn("/api/v1/replay/{system_id}/profile", schema["paths"])


if __name__ == "__main__":
    unittest.main()
