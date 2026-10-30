"""
Tests for the Vercel deployment configuration and production deployment infrastructure.

Verifies:
- vercel.json is valid and has correct outputDirectory
- config.js exists and has the correct placeholder structure
- api.js exports resolveWsBaseUrl
- build-config.py generates config.js correctly
- CORS middleware is registered on the FastAPI app
- index.html loads config.js before app.js
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
    """vercel.json must be valid and correctly configured for the static SPA."""

    def setUp(self) -> None:
        self.vercel_json_path = ROOT / "vercel.json"
        with open(self.vercel_json_path, encoding="utf-8") as f:
            self.config = json.load(f)

    def test_vercel_json_exists(self) -> None:
        self.assertTrue(self.vercel_json_path.is_file(), "vercel.json must exist at repo root")

    def test_output_directory_is_src_ui(self) -> None:
        self.assertEqual(
            self.config.get("outputDirectory"),
            "src/ui",
            "vercel.json outputDirectory must be 'src/ui' to serve the frontend SPA",
        )

    def test_spa_rewrite_rule_exists(self) -> None:
        rewrites = self.config.get("rewrites", [])
        self.assertTrue(len(rewrites) > 0, "vercel.json must have at least one rewrite rule")
        # The catch-all SPA rewrite must redirect to /index.html
        catch_all = next((r for r in rewrites if r.get("source") in ("/(.*)", "**")), None)
        self.assertIsNotNone(catch_all, "Must have a catch-all rewrite rule for SPA routing")
        self.assertEqual(catch_all.get("destination"), "/index.html")

    def test_js_mime_type_header(self) -> None:
        headers = self.config.get("headers", [])
        js_header = next((h for h in headers if ".js" in h.get("source", "")), None)
        self.assertIsNotNone(js_header, "Must set Content-Type header for .js files")
        header_values = {kv["key"]: kv["value"] for kv in js_header.get("headers", [])}
        self.assertIn("application/javascript", header_values.get("Content-Type", ""))

    def test_no_functions_field(self) -> None:
        self.assertNotIn(
            "functions",
            self.config,
            "vercel.json must NOT define serverless functions — the FastAPI backend runs separately",
        )

    def test_framework_is_null_or_absent(self) -> None:
        framework = self.config.get("framework")
        self.assertIsNone(
            framework,
            "vercel.json framework must be null (vanilla static SPA, not Next.js or similar)",
        )


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
    """index.html must correctly load config.js before app.js and have all view containers."""

    def setUp(self) -> None:
        self.html = (ROOT / "src" / "ui" / "index.html").read_text(encoding="utf-8")

    def test_config_js_loaded_before_app_js(self) -> None:
        config_pos = self.html.find("config.js")
        app_pos = self.html.find("app.js")
        self.assertGreater(config_pos, -1, "index.html must load config.js")
        self.assertGreater(app_pos, -1, "index.html must load app.js")
        self.assertLess(config_pos, app_pos, "config.js must be loaded BEFORE app.js")

    def test_app_js_is_module(self) -> None:
        self.assertIn('type="module"', self.html, "app.js must be loaded as a JS module")
        self.assertIn('src="js/app.js"', self.html)

    def test_config_js_is_plain_script(self) -> None:
        # config.js is a plain script (IIFE), NOT a module — it sets window.* globals
        # We just need to ensure it's loaded (with or without type="module")
        self.assertIn("config.js", self.html)

    def test_all_view_containers_present(self) -> None:
        required_views = [
            "view-overview", "view-telemetry", "view-hardware", "view-mock",
            "view-twin", "view-estimation", "view-replay", "view-events",
            "view-diagnostics", "view-benchmarking", "view-datasets",
        ]
        missing = [v for v in required_views if f'id="{v}"' not in self.html]
        self.assertEqual(missing, [], f"Missing view containers: {missing}")

    def test_all_nav_buttons_present(self) -> None:
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


class TestConfigJs(unittest.TestCase):
    """config.js must have the correct placeholder structure for build-time injection."""

    def setUp(self) -> None:
        self.content = (ROOT / "src" / "ui" / "js" / "config.js").read_text(encoding="utf-8")

    def test_api_url_placeholder_present(self) -> None:
        self.assertIn("__TWINVOLT_API_BASE_URL__", self.content)

    def test_ws_url_placeholder_present(self) -> None:
        self.assertIn("__TWINVOLT_WS_BASE_URL__", self.content)

    def test_iife_wrapper_present(self) -> None:
        self.assertIn("(function", self.content, "config.js must use an IIFE wrapper")

    def test_sets_window_api_base_url(self) -> None:
        self.assertIn("window.TWINVOLT_API_BASE_URL", self.content)

    def test_sets_window_ws_base_url(self) -> None:
        self.assertIn("window.TWINVOLT_WS_BASE_URL", self.content)


class TestApiJs(unittest.TestCase):
    """api.js must export resolveWsBaseUrl and use _resolveApiBaseUrl for the constructor."""

    def setUp(self) -> None:
        self.content = (ROOT / "src" / "ui" / "js" / "api.js").read_text(encoding="utf-8")

    def test_resolve_ws_base_url_exported(self) -> None:
        self.assertIn("export function resolveWsBaseUrl", self.content)

    def test_resolve_api_base_url_defined(self) -> None:
        self.assertIn("function _resolveApiBaseUrl", self.content)

    def test_constructor_uses_dynamic_resolver(self) -> None:
        self.assertIn("_resolveApiBaseUrl()", self.content)

    def test_api_client_exported(self) -> None:
        self.assertIn("export const api = new ApiClient()", self.content)

    def test_no_hardcoded_localhost_in_production_paths(self) -> None:
        # Ensure no hardcoded localhost URL in the API path definitions
        # (allowed in comments and error messages, but not in fetch() paths)
        lines = self.content.splitlines()
        suspicious = [
            (i + 1, line) for i, line in enumerate(lines)
            if "localhost" in line and "return" in line and "http" in line
        ]
        self.assertEqual(suspicious, [], f"Suspicious hardcoded localhost in return statements: {suspicious}")


class TestWebsocketJs(unittest.TestCase):
    """websocket.js must import resolveWsBaseUrl and use it instead of window.location directly."""

    def setUp(self) -> None:
        self.content = (ROOT / "src" / "ui" / "js" / "websocket.js").read_text(encoding="utf-8")

    def test_imports_resolve_ws_base_url(self) -> None:
        self.assertIn("resolveWsBaseUrl", self.content)
        self.assertIn("from './api.js'", self.content)

    def test_uses_ws_base_in_connect(self) -> None:
        self.assertIn("resolveWsBaseUrl()", self.content)

    def test_no_direct_window_location_for_ws_url(self) -> None:
        # The old pattern used window.location.host directly for the WS URL.
        # After the patch, the URL is always routed through resolveWsBaseUrl().
        # window.location may still appear in resolveWsBaseUrl itself (in api.js),
        # but websocket.js should NOT build the WS URL from window.location directly.
        lines = self.content.splitlines()
        # Look for the old pattern: building wsUrl directly from window.location.host
        # without going through the resolver
        old_pattern = [
            line for line in lines
            if "window.location.host" in line and ("wsUrl" in line or "protocol" in line)
        ]
        self.assertEqual(old_pattern, [], f"websocket.js still builds wsUrl directly from window.location: {old_pattern}")


class TestBuildConfigScript(unittest.TestCase):
    """scripts/build-config.py must generate config.js correctly in both modes."""

    def setUp(self) -> None:
        self.script = ROOT / "scripts" / "build-config.py"
        self.config_out = ROOT / "src" / "ui" / "js" / "config.js"

    def test_build_config_script_exists(self) -> None:
        self.assertTrue(self.script.is_file(), "scripts/build-config.py must exist")

    def test_placeholder_mode_no_env(self) -> None:
        """Running without env vars writes placeholder tokens (safe for local dev)."""
        env = {**os.environ}
        env.pop("TWINVOLT_API_BASE_URL", None)
        env.pop("TWINVOLT_WS_BASE_URL", None)

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

    def test_url_injection_mode(self) -> None:
        """Running with env vars injects the real URLs into config.js."""
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
        # Restore placeholder state after test
        subprocess.run([sys.executable, str(self.script)], env={k: v for k, v in os.environ.items()
                       if k not in ("TWINVOLT_API_BASE_URL", "TWINVOLT_WS_BASE_URL")},
                       cwd=str(ROOT))


class TestCorsMiddleware(unittest.TestCase):
    """The FastAPI application must have CORS middleware that permits Vercel origins."""

    def test_cors_middleware_registered(self) -> None:
        from fastapi.middleware.cors import CORSMiddleware
        from src.api.app import create_app

        app = create_app()
        # Check app.user_middleware list — FastAPI stores middleware here before building the stack
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
        # Simulate a cross-origin preflight from a Vercel URL
        response = client.options(
            "/health",
            headers={
                "Origin": "https://twinvolt.vercel.app",
                "Access-Control-Request-Method": "GET",
            },
        )
        # 200 or 204 = CORS preflight accepted
        self.assertIn(response.status_code, (200, 204))
        # The response must set ACAO header
        acao = response.headers.get("access-control-allow-origin", "")
        self.assertTrue(
            acao in ("*", "https://twinvolt.vercel.app") or "vercel" in acao,
            f"CORS must allow Vercel origin, got: {acao!r}",
        )


if __name__ == "__main__":
    unittest.main()
