"""
Tests for the Vercel deployment configuration and production deployment infrastructure.

Verifies:
- vercel.json is valid and uses @vercel/python with api/index.py
- api/index.py exists and exports the initialized FastAPI app
- config.js exists and has the correct placeholder structure supporting both TWINVOLT_* and VITE_*
- api.js exports resolveWsBaseUrl and supports both TWINVOLT_* and VITE_* variables
- build-config.py generates config.js correctly in both modes
- CORS middleware is registered on the FastAPI app and allows Vercel origins
- index.html loads config.js before app.js and contains all 11 views
- All frontend JS modules and CSS assets exist
"""

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root


class TestVercelJsonConfig(unittest.TestCase):
    """vercel.json must be valid and configured for the unified FastAPI Vercel Serverless deployment."""

    def setUp(self) -> None:
        self.vercel_json_path = ROOT / "vercel.json"
        with open(self.vercel_json_path, encoding="utf-8") as f:
            self.config = json.load(f)

    def test_vercel_json_exists(self) -> None:
        self.assertTrue(self.vercel_json_path.is_file(), "vercel.json must exist at repo root")

    def test_builds_uses_vercel_python(self) -> None:
        builds = self.config.get("builds", [])
        self.assertTrue(len(builds) > 0, "vercel.json must define builds")
        python_build = next((b for b in builds if b.get("use") == "@vercel/python"), None)
        self.assertIsNotNone(python_build, "vercel.json must use @vercel/python builder")
        self.assertEqual(python_build.get("src"), "api/index.py")

    def test_routes_maps_to_api_index(self) -> None:
        routes = self.config.get("routes", [])
        self.assertTrue(len(routes) > 0, "vercel.json must define routes")
        catch_all = next((r for r in routes if r.get("src") in ("/(.*)", "/.*", "**")), None)
        self.assertIsNotNone(catch_all, "vercel.json must have a catch-all route")
        self.assertEqual(catch_all.get("dest"), "api/index.py")

    def test_no_invalid_comment_property(self) -> None:
        self.assertNotIn(
            "comment",
            self.config,
            "vercel.json must NOT contain a 'comment' property as it fails Vercel's schema validator",
        )


class TestApiIndexEntrypoint(unittest.TestCase):
    """api/index.py must exist and export the initialized FastAPI app."""

    def test_api_index_exists(self) -> None:
        index_py = ROOT / "api" / "index.py"
        self.assertTrue(index_py.is_file(), "api/index.py must exist for @vercel/python")

    def test_api_index_exports_app(self) -> None:
        import api.index as entry
        from fastapi import FastAPI
        self.assertTrue(hasattr(entry, "app"), "api/index.py must export 'app'")
        self.assertIsInstance(entry.app, FastAPI)


class TestFrontendAssets(unittest.TestCase):
    """All frontend JS modules and CSS assets required by the SPA must exist."""

    UI_DIR = ROOT / "src" / "ui"

    REQUIRED_JS = [
        "js/app.js",
        "js/api.js",
        "js/websocket.js",
        "js/state.js",
        "js/ble.js",
        "js/serial.js",
        "js/telemetry_pipeline.js",
        "js/config.js",
        "js/views/hardware.js",
        "js/views/mock.js",
        "js/views/overview.js",
        "js/views/telemetry.js",
        "js/views/twin.js",
        "js/views/estimation.js",
        "js/views/replay.js",
        "js/views/events.js",
        "js/views/diagnostics.js",
        "js/views/benchmarking.js",
        "js/views/dataset_lab.js",
    ]

    REQUIRED_CSS = [
        "css/variables.css",
        "css/layout.css",
        "css/components.css",
        "css/charts.css",
    ]

    def test_index_html_exists(self) -> None:
        self.assertTrue((self.UI_DIR / "index.html").is_file())

    def test_all_required_js_modules_exist(self) -> None:
        missing = [p for p in self.REQUIRED_JS if not (self.UI_DIR / p).is_file()]
        self.assertEqual(missing, [], f"Missing JS modules: {missing}")

    def test_all_required_css_files_exist(self) -> None:
        missing = [p for p in self.REQUIRED_CSS if not (self.UI_DIR / p).is_file()]
        self.assertEqual(missing, [], f"Missing CSS files: {missing}")

    def test_logo_svg_exists(self) -> None:
        self.assertTrue((self.UI_DIR / "assets" / "logo.svg").is_file())


class TestIndexHtmlStructure(unittest.TestCase):
    """index.html must correctly load config.js before app.js and have all 11 view containers."""

    def setUp(self) -> None:
        self.html = (ROOT / "src" / "ui" / "index.html").read_text(encoding="utf-8")

    def test_config_js_loaded_before_app_js(self) -> None:
        config_pos = self.html.find('src="js/config.js"')
        app_pos = self.html.find('src="js/app.js"')
        self.assertGreater(config_pos, -1, "index.html must load js/config.js")
        self.assertGreater(app_pos, -1, "index.html must load js/app.js")
        self.assertLess(config_pos, app_pos, "config.js script must be loaded BEFORE app.js")

    def test_app_js_is_module(self) -> None:
        self.assertIn('type="module" src="js/app.js"', self.html, "app.js must be loaded as a JS module")

    def test_all_11_view_containers_present(self) -> None:
        required_views = [
            "view-overview", "view-telemetry", "view-hardware", "view-mock",
            "view-twin", "view-estimation", "view-replay", "view-events",
            "view-diagnostics", "view-benchmarking", "view-datasets",
        ]
        missing = [v for v in required_views if f'id="{v}"' not in self.html]
        self.assertEqual(missing, [], f"Missing view containers: {missing}")

    def test_all_11_nav_buttons_present(self) -> None:
        required_nav = [
            "overview", "telemetry", "hardware", "mock",
            "twin", "estimation", "replay", "events",
            "diagnostics", "benchmarking", "datasets",
        ]
        missing = [n for n in required_nav if f'data-view="{n}"' not in self.html]
        self.assertEqual(missing, [], f"Missing nav buttons: {missing}")

    def test_hardware_nav_present(self) -> None:
        self.assertIn('data-view="hardware"', self.html, "Hardware & Arduino nav must be present")

    def test_mock_nav_present(self) -> None:
        self.assertIn('data-view="mock"', self.html, "Mock Generator nav must be present")

    def test_header_mode_badge_present(self) -> None:
        self.assertIn('id="header-mode-badge"', self.html, "Header mode badge must be present")
        self.assertIn('id="header-mode-text"', self.html, "Header mode text must be present")


class TestOverviewHardwareSection(unittest.TestCase):
    """overview.js must contain the live hardware sensor telemetry strip."""

    def setUp(self) -> None:
        self.content = (ROOT / "src" / "ui" / "js" / "views" / "overview.js").read_text(encoding="utf-8")

    def test_live_hardware_sensors_section_present(self) -> None:
        self.assertIn("LIVE HARDWARE SENSORS", self.content)

    def test_test_sample_button_present(self) -> None:
        self.assertIn("overview-btn-test-sample", self.content)


class TestConfigJs(unittest.TestCase):
    """config.js must support both TWINVOLT_* and VITE_* variable styles."""

    def setUp(self) -> None:
        self.content = (ROOT / "src" / "ui" / "js" / "config.js").read_text(encoding="utf-8")

    def test_api_url_placeholder_present(self) -> None:
        self.assertIn("__TWINVOLT_API_BASE_URL__", self.content)

    def test_ws_url_placeholder_present(self) -> None:
        self.assertIn("__TWINVOLT_WS_BASE_URL__", self.content)

    def test_sets_window_twinvolt_and_vite_api_base_url(self) -> None:
        self.assertIn("window.TWINVOLT_API_BASE_URL", self.content)
        self.assertIn("window.VITE_API_BASE_URL", self.content)

    def test_sets_window_twinvolt_and_vite_ws_base_url(self) -> None:
        self.assertIn("window.TWINVOLT_WS_BASE_URL", self.content)
        self.assertIn("window.VITE_WS_BASE_URL", self.content)


class TestApiJs(unittest.TestCase):
    """api.js must export resolveWsBaseUrl and use _resolveApiBaseUrl supporting both naming conventions."""

    def setUp(self) -> None:
        self.content = (ROOT / "src" / "ui" / "js" / "api.js").read_text(encoding="utf-8")

    def test_resolve_ws_base_url_exported(self) -> None:
        self.assertIn("export function resolveWsBaseUrl", self.content)

    def test_supports_twinvolt_and_vite_api_base_url(self) -> None:
        self.assertIn("TWINVOLT_API_BASE_URL", self.content)
        self.assertIn("VITE_API_BASE_URL", self.content)

    def test_supports_twinvolt_and_vite_ws_base_url(self) -> None:
        self.assertIn("TWINVOLT_WS_BASE_URL", self.content)
        self.assertIn("VITE_WS_BASE_URL", self.content)

    def test_constructor_uses_dynamic_resolver(self) -> None:
        self.assertIn("_resolveApiBaseUrl()", self.content)

    def test_api_client_exported(self) -> None:
        self.assertIn("export const api = new ApiClient()", self.content)


class TestBuildConfigScript(unittest.TestCase):
    """scripts/build-config.py must support both TWINVOLT_* and VITE_* environment variables."""

    def setUp(self) -> None:
        self.script = ROOT / "scripts" / "build-config.py"
        self.config_out = ROOT / "src" / "ui" / "js" / "config.js"

    def test_build_config_script_exists(self) -> None:
        self.assertTrue(self.script.is_file(), "scripts/build-config.py must exist")

    def test_placeholder_mode_no_env(self) -> None:
        """Running without env vars writes placeholder tokens (safe for local dev)."""
        env = {**os.environ}
        for k in ("TWINVOLT_API_BASE_URL", "TWINVOLT_WS_BASE_URL", "VITE_API_BASE_URL", "VITE_WS_BASE_URL"):
            env.pop(k, None)

        result = subprocess.run(
            [sys.executable, str(self.script)],
            env=env,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(result.returncode, 0, f"build-config.py failed: {result.stderr}")
        content = self.config_out.read_text(encoding="utf-8")
        self.assertIn("__TWINVOLT_API_BASE_URL__", content)
        self.assertIn("__TWINVOLT_WS_BASE_URL__", content)

    def test_twinvolt_url_injection_mode(self) -> None:
        """Running with TWINVOLT_* env vars injects the real URLs into config.js."""
        env = {**os.environ,
               "TWINVOLT_API_BASE_URL": "https://test-backend.railway.app",
               "TWINVOLT_WS_BASE_URL": "wss://test-backend.railway.app"}

        result = subprocess.run(
            [sys.executable, str(self.script)],
            env=env,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(result.returncode, 0, f"build-config.py failed: {result.stderr}")
        content = self.config_out.read_text(encoding="utf-8")
        self.assertIn("test-backend.railway.app", content)
        # Restore placeholder state
        subprocess.run([sys.executable, str(self.script)],
                       env={k: v for k, v in os.environ.items()
                            if k not in ("TWINVOLT_API_BASE_URL", "TWINVOLT_WS_BASE_URL", "VITE_API_BASE_URL", "VITE_WS_BASE_URL")},
                       cwd=str(ROOT))

    def test_vite_url_injection_mode(self) -> None:
        """Running with VITE_* env vars also injects the real URLs into config.js."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("TWINVOLT_API_BASE_URL", "TWINVOLT_WS_BASE_URL")}
        env["VITE_API_BASE_URL"] = "https://vite-test.railway.app"
        env["VITE_WS_BASE_URL"] = "wss://vite-test.railway.app"

        result = subprocess.run(
            [sys.executable, str(self.script)],
            env=env,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(result.returncode, 0, f"build-config.py failed: {result.stderr}")
        content = self.config_out.read_text(encoding="utf-8")
        self.assertIn("vite-test.railway.app", content)
        # Restore placeholder state
        subprocess.run([sys.executable, str(self.script)],
                       env={k: v for k, v in os.environ.items()
                            if k not in ("TWINVOLT_API_BASE_URL", "TWINVOLT_WS_BASE_URL", "VITE_API_BASE_URL", "VITE_WS_BASE_URL")},
                       cwd=str(ROOT))


class TestCorsMiddleware(unittest.TestCase):
    """The FastAPI application must have CORS middleware that permits Vercel origins."""

    def test_cors_middleware_registered(self) -> None:
        from fastapi.middleware.cors import CORSMiddleware
        from src.api.app import create_app

        app = create_app()
        cors_found = any(
            getattr(m, 'cls', None) is CORSMiddleware or
            CORSMiddleware.__name__ in str(getattr(m, 'cls', ''))
            for m in app.user_middleware
        )
        self.assertTrue(cors_found, "CORSMiddleware must be registered on the FastAPI app")

    def test_cors_allows_vercel_origin(self) -> None:
        from fastapi.testclient import TestClient
        from src.api.app import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=True)
        response = client.options(
            "/health",
            headers={
                "Origin": "https://twinvolt.vercel.app",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertIn(response.status_code, (200, 204))
        acao = response.headers.get("access-control-allow-origin", "")
        self.assertTrue(
            acao in ("*", "https://twinvolt.vercel.app") or "vercel" in acao,
            f"CORS must allow Vercel origin, got: {acao!r}",
        )


if __name__ == "__main__":
    unittest.main()
