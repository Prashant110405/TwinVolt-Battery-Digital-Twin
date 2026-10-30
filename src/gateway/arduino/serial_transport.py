"""Asynchronous Serial Transport Layer for Arduino and Physical BMS Hardware.

Provides non-blocking serial I/O over USB Virtual COM ports and physical UARTs.
Detects ports, handles disconnections gracefully, and supports mock injection
for hardware-independent testing.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import time
from typing import Any, Callable, Coroutine, Optional, Sequence

from src.gateway.arduino.models import ArduinoConfig, HardwareConnectionState, HardwarePortInfo

logger = logging.getLogger("twinvolt.gateway.arduino.transport")

# Known Arduino / FTDI / CH340 / CP210x / ESP32 USB Vendor and Product IDs or strings
ARDUINO_SIGNATURES = (
    "arduino", "ch340", "cp210", "ftdi", "usb serial", "ch341", "cdc acm", "wch",
    "usb-serial", "teensy", "esp32", "stmicro", "circuitpython", "silicon labs",
    "usb to uart", "uart", "jtag", "wch.cn", "prolific"
)


def list_available_ports() -> list[HardwarePortInfo]:
    """Enumerates system serial COM ports, identifying physical USB bridges and Bluetooth links."""
    port_list: list[HardwarePortInfo] = []
    try:
        import serial.tools.list_ports
        comports = serial.tools.list_ports.comports()
        for p in comports:
            desc = p.description or ""
            mfg = p.manufacturer or ""
            hwid = p.hwid or ""
            combined = f"{desc} {mfg} {hwid}".lower()

            is_bt = "bthenum" in combined or "bluetooth" in combined
            is_candidate = not is_bt and any(sig in combined for sig in ARDUINO_SIGNATURES)

            port_list.append(
                HardwarePortInfo(
                    device=p.device,
                    name=p.name or p.device,
                    description=desc,
                    hwid=hwid,
                    manufacturer=mfg,
                    is_arduino_candidate=is_candidate,
                    is_bluetooth_link=is_bt,
                )
            )
    except Exception as exc:
        logger.warning("Error enumerating serial ports: %s", exc)
    return port_list


class ArduinoSerialTransport:
    """Asynchronous line reader wrapper over pyserial or mock stream."""

    def __init__(
        self,
        config: ArduinoConfig,
        mock_line_generator: Optional[Callable[[], Coroutine[Any, Any, Optional[str]]]] = None,
    ) -> None:
        self.config = config
        self._mock_generator = mock_line_generator
        self._serial: Any = None
        self._is_open = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="arduino_serial")
        self._buffer = bytearray()

    @property
    def is_open(self) -> bool:
        """Returns True if the underlying serial port or mock stream is active."""
        return self._is_open

    async def open(self) -> None:
        """Opens the configured serial port without blocking the asyncio loop."""
        if self._mock_generator is not None:
            self._is_open = True
            logger.info("Mock serial transport opened for port '%s'", self.config.port)
            return

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(self._executor, self._sync_open)
            self._is_open = True
            logger.info(
                "Serial port '%s' opened at %d baud (format=%s)",
                self.config.port,
                self.config.baud_rate,
                self.config.data_format,
            )
        except Exception as exc:
            self._is_open = False
            logger.error("Failed to open serial port '%s': %s", self.config.port, exc)
            raise

    def _sync_open(self) -> None:
        """Synchronously opens pyserial connection."""
        import serial
        if self._serial is not None and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass

        self._serial = serial.Serial(
            port=self.config.port,
            baudrate=self.config.baud_rate,
            timeout=self.config.read_timeout_s,
            write_timeout=1.0,
        )
        # Flush initial startup junk
        time.sleep(0.05)
        self._serial.reset_input_buffer()

    async def close(self) -> None:
        """Gracefully closes serial connection."""
        self._is_open = False
        if self._mock_generator is not None:
            return

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(self._executor, self._sync_close)
            logger.info("Serial port '%s' closed cleanly.", self.config.port)
        except Exception as exc:
            logger.warning("Error during serial port close: %s", exc)

    def _sync_close(self) -> None:
        """Synchronously closes pyserial object."""
        if self._serial is not None:
            try:
                if self._serial.is_open:
                    self._serial.close()
            except Exception:
                pass
            self._serial = None

    async def readline(self) -> Optional[str]:
        """Reads a single line from the serial connection.

        Returns:
            Decoded line string, or None if timeout / disconnected.
        """
        if not self._is_open:
            return None

        if self._mock_generator is not None:
            return await self._mock_generator()

        loop = asyncio.get_running_loop()
        try:
            line_bytes = await loop.run_in_executor(self._executor, self._sync_readline)
            if not line_bytes:
                return None
            return line_bytes.decode("utf-8", errors="replace")
        except Exception as exc:
            logger.warning("Serial read error on port '%s': %s", self.config.port, exc)
            self._is_open = False
            raise

    def _sync_readline(self) -> Optional[bytes]:
        """Synchronous blocking read until delimiter."""
        if self._serial is None or not self._serial.is_open:
            raise ConnectionError(f"Serial port '{self.config.port}' is closed.")

        try:
            line = self._serial.readline()
            return line if line else None
        except Exception as exc:
            raise ConnectionResetError(f"Port '{self.config.port}' disconnected: {exc}") from exc
