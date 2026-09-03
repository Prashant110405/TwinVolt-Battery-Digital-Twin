"""Unit tests for Gateway REST API Routes."""

import unittest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import create_default_services
from src.gateway.serial_source import SerialConfig, SerialUartSource


class TestGatewayRoutes(unittest.TestCase):
    """Test suite verifying Gateway monitoring REST endpoints."""

    def setUp(self) -> None:
        self.services = create_default_services()
        self.app = create_app(services=self.services)
        self.client = TestClient(self.app)

        # Register a test source in the app's gateway manager
        self.source = SerialUartSource(
            source_id="bench_serial_01",
            config=SerialConfig(port="COM_TEST", auto_reconnect=False),
        )
        self.app.state.gateway_manager.register_source(self.source)

    def test_get_gateway_status(self) -> None:
        """GET /api/v1/gateway/status returns operational statistics and queue depth."""
        res = self.client.get("/api/v1/gateway/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("is_running", data)
        self.assertIn("sources_count", data)
        self.assertIn("queue_depth", data)
        self.assertIn("overflow_policy", data)
        self.assertEqual(data["sources_count"], 1)

    def test_get_gateway_sources(self) -> None:
        """GET /api/v1/gateway/sources returns dictionary of registered sources."""
        res = self.client.get("/api/v1/gateway/sources")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("sources", data)
        self.assertIn("bench_serial_01", data["sources"])

    def test_get_gateway_source_detail(self) -> None:
        """GET /api/v1/gateway/sources/{id} returns status for existing source, 404 for unknown."""
        # Existing source
        res_ok = self.client.get("/api/v1/gateway/sources/bench_serial_01")
        self.assertEqual(res_ok.status_code, 200)
        data = res_ok.json()
        self.assertEqual(data["source_id"], "bench_serial_01")
        self.assertEqual(data["transport_type"], "SERIAL")

        # Unknown source
        res_404 = self.client.get("/api/v1/gateway/sources/unknown_source")
        self.assertEqual(res_404.status_code, 404)


if __name__ == "__main__":
    unittest.main()
