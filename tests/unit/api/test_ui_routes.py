"""Unit tests for UI Static Asset Serving and Route Integrity."""

import unittest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import create_default_services


class TestUiRoutes(unittest.TestCase):
    """Test suite verifying UI static file serving and non-interference with REST and WebSocket APIs."""

    def setUp(self) -> None:
        self.services = create_default_services()
        self.app = create_app(services=self.services)
        self.client = TestClient(self.app)

    def test_root_serves_html_dashboard(self) -> None:
        """GET / returns the TwinVolt index.html single-page dashboard."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers.get("content-type", ""))
        self.assertIn("TwinVolt", res.text)
        self.assertIn("app-shell", res.text)

    def test_ui_static_assets_serve_correctly(self) -> None:
        """Static assets under /ui/ (css, js, assets) serve with valid content."""
        # CSS variables
        res_css = self.client.get("/ui/css/variables.css")
        self.assertEqual(res_css.status_code, 200)
        self.assertIn("--bg-primary", res_css.text)

        # JS app module
        res_js = self.client.get("/ui/js/app.js")
        self.assertEqual(res_js.status_code, 200)
        self.assertIn("TwinVoltApp", res_js.text)

        # SVG logo asset
        res_svg = self.client.get("/ui/assets/logo.svg")
        self.assertEqual(res_svg.status_code, 200)
        self.assertIn("<svg", res_svg.text)

    def test_api_routes_unaffected_by_static_mount(self) -> None:
        """Core REST routes retain priority and functionality."""
        res_health = self.client.get("/health")
        self.assertEqual(res_health.status_code, 200)
        self.assertEqual(res_health.json()["status"], "healthy")

        res_packs = self.client.get("/api/v1/packs")
        self.assertEqual(res_packs.status_code, 200)
        self.assertIn("packs", res_packs.json())

        res_twins = self.client.get("/api/v1/twins")
        self.assertEqual(res_twins.status_code, 200)
        self.assertIn("twins", res_twins.json())

    def test_websocket_routes_unaffected_by_static_mount(self) -> None:
        """WebSocket routes continue to function normally with static mount active."""
        with self.client.websocket_connect("/api/v1/ws") as ws:
            welcome = ws.receive_json()
            self.assertEqual(welcome["type"], "connected")
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            self.assertEqual(pong["type"], "pong")


if __name__ == "__main__":
    unittest.main()
