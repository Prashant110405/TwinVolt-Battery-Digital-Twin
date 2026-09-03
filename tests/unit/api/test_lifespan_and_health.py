"""Unit tests for Application Lifespan, Health Probes, and Deployment Packaging."""

from pathlib import Path
import unittest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import ServiceContainer, create_default_services
from src.config.settings import AppSettings


class TestLifespanAndHealth(unittest.TestCase):
    """Test suite verifying FastAPI lifespan lifecycle, health/liveness/readiness probes, and deployment artifacts."""

    def setUp(self) -> None:
        self.services = create_default_services()

    def test_lifespan_startup_and_shutdown_without_autostart(self) -> None:
        """Lifespan initializes start_time_ns, reuses existing gateway_manager, and keeps gateway stopped when autostart=False."""
        settings = AppSettings(gateway_autostart=False)
        app = create_app(services=self.services, settings=settings)

        # Before entering client, start_time_ns is not set
        self.assertFalse(hasattr(app.state, "start_time_ns"))

        with TestClient(app) as client:
            self.assertTrue(hasattr(app.state, "start_time_ns"))
            self.assertIsNotNone(app.state.start_time_ns)
            self.assertIsNotNone(app.state.gateway_manager)
            self.assertFalse(app.state.gateway_manager.is_running)

            res = client.get("/health/live")
            self.assertEqual(res.status_code, 200)

        # After exiting client (shutdown), gateway manager remains stopped
        self.assertFalse(app.state.gateway_manager.is_running)

    def test_lifespan_autostarts_and_stops_gateway(self) -> None:
        """Lifespan automatically starts GatewayDaemonManager when gateway_autostart=True and stops it upon shutdown."""
        settings = AppSettings(gateway_autostart=True)
        app = create_app(services=self.services, settings=settings)

        with TestClient(app) as client:
            self.assertTrue(app.state.gateway_manager.is_running)

            res = client.get("/health/ready")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["gateway_ready"])

        # After shutdown, gateway must be stopped
        self.assertFalse(app.state.gateway_manager.is_running)

    def test_health_endpoints(self) -> None:
        """Verifies /health, /health/live, /health/ready, and /health/details endpoints."""
        app = create_app(services=self.services)

        with TestClient(app) as client:
            # 1. /health
            res_general = client.get("/health")
            self.assertEqual(res_general.status_code, 200)
            self.assertEqual(res_general.json()["status"], "healthy")

            # 2. /health/live
            res_live = client.get("/health/live")
            self.assertEqual(res_live.status_code, 200)
            self.assertEqual(res_live.json()["status"], "alive")

            # 3. /health/ready (with 0 active twins, system must still be ready)
            res_ready = client.get("/health/ready")
            self.assertEqual(res_ready.status_code, 200)
            data_ready = res_ready.json()
            self.assertEqual(data_ready["status"], "ready")
            self.assertTrue(data_ready["services_initialized"])
            self.assertTrue(data_ready["event_bus_ready"])

            # 4. /health/details
            res_details = client.get("/health/details")
            self.assertEqual(res_details.status_code, 200)
            data_details = res_details.json()
            self.assertIn("uptime_seconds", data_details)
            self.assertEqual(data_details["active_twins_count"], 0)
            self.assertIn("gateway", data_details)
            self.assertTrue(data_details["event_bus_ready"])

    def test_health_ready_unready_when_services_missing(self) -> None:
        """GET /health/ready returns 503 when services or event bus is not available."""
        app = create_app(services=self.services)
        app.state.services = None  # Simulate infrastructure failure

        with TestClient(app) as client:
            res = client.get("/health/ready")
            self.assertEqual(res.status_code, 503)
            data = res.json()["detail"]
            self.assertEqual(data["status"], "not_ready")
            self.assertFalse(data["services_initialized"])

    def test_deployment_artifacts_integrity(self) -> None:
        """Validates that systemd service unit, Dockerfile, and docker-compose files exist and contain required directives."""
        root_dir = Path(__file__).resolve().parent.parent.parent.parent

        # 1. Systemd Service Unit
        systemd_path = root_dir / "deploy" / "systemd" / "twinvolt.service"
        self.assertTrue(systemd_path.is_file())
        systemd_content = systemd_path.read_text(encoding="utf-8")
        self.assertIn("Description=TwinVolt", systemd_content)
        self.assertIn("ExecStart=", systemd_content)
        self.assertIn("Restart=always", systemd_content)
        self.assertIn("SupplementaryGroups=dialout", systemd_content)

        # 2. Dockerfile
        dockerfile_path = root_dir / "deploy" / "docker" / "Dockerfile"
        self.assertTrue(dockerfile_path.is_file())
        docker_content = dockerfile_path.read_text(encoding="utf-8")
        self.assertIn("python:3.10", docker_content)
        self.assertIn("HEALTHCHECK", docker_content)
        self.assertIn("/health/live", docker_content)

        # 3. Docker Compose
        compose_path = root_dir / "deploy" / "docker" / "docker-compose.yml"
        self.assertTrue(compose_path.is_file())
        compose_content = compose_path.read_text(encoding="utf-8")
        self.assertIn("twinvolt_edge_server", compose_content)
        self.assertIn("8000:8000", compose_content)


if __name__ == "__main__":
    unittest.main()
