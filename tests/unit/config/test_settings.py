"""Unit tests for 12-factor operational configuration."""

import os
import unittest
from src.config.settings import AppSettings, get_settings
from src.gateway.base import GatewayOverflowPolicy


class TestAppSettings(unittest.TestCase):
    """Test suite verifying AppSettings defaults, environment variable overrides, and boundary validation."""

    def test_default_settings(self) -> None:
        """AppSettings initializes with deterministic, safe defaults."""
        settings = AppSettings()
        self.assertEqual(settings.host, "0.0.0.0")
        self.assertEqual(settings.port, 8000)
        self.assertEqual(settings.log_level, "INFO")
        self.assertFalse(settings.gateway_autostart)
        self.assertEqual(settings.gateway_queue_size, 1000)
        self.assertEqual(settings.gateway_overflow_policy, GatewayOverflowPolicy.DROP_OLDEST)
        self.assertEqual(settings.storage_dir, "data/storage")

    def test_env_variable_overrides(self) -> None:
        """AppSettings correctly parses TWINVOLT_* and legacy API_* environment variables."""
        env = {
            "TWINVOLT_HOST": "127.0.0.1",
            "TWINVOLT_PORT": "9090",
            "TWINVOLT_LOG_LEVEL": "debug",
            "TWINVOLT_GATEWAY_AUTOSTART": "true",
            "TWINVOLT_GATEWAY_QUEUE_SIZE": "5000",
            "TWINVOLT_GATEWAY_OVERFLOW_POLICY": "DROP_NEWEST",
            "TWINVOLT_STORAGE_DIR": "/tmp/twinvolt_data",
        }
        settings = AppSettings.from_env(env)
        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.port, 9090)
        self.assertEqual(settings.log_level, "DEBUG")
        self.assertTrue(settings.gateway_autostart)
        self.assertEqual(settings.gateway_queue_size, 5000)
        self.assertEqual(settings.gateway_overflow_policy, GatewayOverflowPolicy.DROP_NEWEST)
        self.assertEqual(settings.storage_dir, "/tmp/twinvolt_data")

    def test_legacy_env_fallbacks(self) -> None:
        """AppSettings supports API_HOST and API_PORT as legacy fallbacks."""
        env = {
            "API_HOST": "192.168.1.50",
            "API_PORT": "8080",
        }
        settings = AppSettings.from_env(env)
        self.assertEqual(settings.host, "192.168.1.50")
        self.assertEqual(settings.port, 8080)

    def test_invalid_settings_rejected(self) -> None:
        """AppSettings rejects invalid port numbers, invalid log levels, and bad overflow policies."""
        with self.assertRaises(Exception):
            AppSettings(port=70000)

        with self.assertRaises(Exception):
            AppSettings(port=0)

        with self.assertRaises(Exception):
            AppSettings(log_level="INVALID_LEVEL")

        with self.assertRaises(Exception):
            AppSettings(gateway_overflow_policy="UNKNOWN_POLICY")  # type: ignore

    def test_get_settings_helper(self) -> None:
        """get_settings returns consistent settings instance or reloads on demand."""
        s1 = get_settings(reload=True)
        s2 = get_settings()
        self.assertIs(s1, s2)

        s3 = get_settings(env={"TWINVOLT_PORT": "8888"}, reload=True)
        self.assertEqual(s3.port, 8888)


if __name__ == "__main__":
    unittest.main()
