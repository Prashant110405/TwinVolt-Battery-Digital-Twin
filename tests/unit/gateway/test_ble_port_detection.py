"""Unit tests for Hardware Port Detection and Bluetooth RFCOMM Discrimination.

Verifies that list_available_ports correctly discriminates between physical
USB-UART bridges (CP210x, CH340, FTDI, etc.) and virtual Bluetooth RFCOMM ports.
"""

from unittest.mock import MagicMock, patch
import pytest

from src.gateway.arduino.serial_transport import list_available_ports


def _make_mock_comport(
    device: str = "COM3",
    description: str = "Standard Serial over Bluetooth link (COM3)",
    manufacturer: str = "Microsoft",
    hwid: str = "BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0000\\8&37D4507&0&000000000000_00000000",
):
    mock = MagicMock()
    mock.device = device
    mock.name = device
    mock.description = description
    mock.manufacturer = manufacturer
    mock.hwid = hwid
    return mock


class TestPortDetectionAndBluetoothDiscrimination:
    """Test suite verifying serial port discrimination between USB-UART and Bluetooth RFCOMM."""

    @patch("serial.tools.list_ports.comports")
    def test_bluetooth_rfcomm_ports_flagged_correctly(self, mock_comports):
        # Emulate Windows Bluetooth standard serial port
        mock_comports.return_value = [
            _make_mock_comport(
                device="COM3",
                description="Standard Serial over Bluetooth link (COM3)",
                manufacturer="Microsoft",
                hwid="BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0000",
            ),
            _make_mock_comport(
                device="COM4",
                description="Standard Serial over Bluetooth link (COM4)",
                manufacturer="Microsoft",
                hwid="BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0000",
            ),
        ]

        ports = list_available_ports()
        assert len(ports) == 2
        for p in ports:
            assert p.is_bluetooth_link is True
            assert p.is_arduino_candidate is False

    @patch("serial.tools.list_ports.comports")
    def test_cp210x_and_ch340_usb_uart_identified_as_candidates(self, mock_comports):
        # Emulate real Silicon Labs CP2102 and CH340 USB bridges
        mock_comports.return_value = [
            _make_mock_comport(
                device="COM5",
                description="Silicon Labs CP210x USB to UART Bridge (COM5)",
                manufacturer="Silicon Labs",
                hwid="USB\\VID_10C4&PID_EA60\\0001",
            ),
            _make_mock_comport(
                device="COM6",
                description="USB-SERIAL CH340 (COM6)",
                manufacturer="wch.cn",
                hwid="USB\\VID_1A86&PID_7523\\5&2A1C9A4B&0&1",
            ),
        ]

        ports = list_available_ports()
        assert len(ports) == 2
        for p in ports:
            assert p.is_bluetooth_link is False
            assert p.is_arduino_candidate is True

    @patch("serial.tools.list_ports.comports")
    def test_mixed_environment_segregation(self, mock_comports):
        # Emulate both BT RFCOMM ports and a real ESP32 UART bridge present simultaneously
        mock_comports.return_value = [
            _make_mock_comport(
                device="COM3",
                description="Standard Serial over Bluetooth link (COM3)",
                hwid="BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}",
            ),
            _make_mock_comport(
                device="COM7",
                description="USB JTAG/serial debug unit (COM7)",
                manufacturer="Espressif Systems",
                hwid="USB\\VID_303A&PID_1001",
            ),
        ]

        ports = list_available_ports()
        assert len(ports) == 2

        bt_port = next(p for p in ports if p.device == "COM3")
        assert bt_port.is_bluetooth_link is True
        assert bt_port.is_arduino_candidate is False

        esp_port = next(p for p in ports if p.device == "COM7")
        assert esp_port.is_bluetooth_link is False
        assert esp_port.is_arduino_candidate is True
