# ESP32 Wi-Fi to existing TwinVolt dashboard

The existing dashboard UI is preserved. FastAPI serves the UI and API together.

## 1. Install and start backend (Windows PowerShell)

```powershell
cd "DIGITAL TWIN"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m src.server --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000/ui` on the backend computer.

## 2. Configure ESP32

Open `firmware/esp32/TwinVolt_ESP32_WiFi.ino` in Arduino IDE. Fill in `WIFI_SSID`, `WIFI_PASSWORD`, and `TWINVOLT_SERVER_HOST`. The server host must be the backend computer's LAN IPv4 address (find it with `ipconfig`), not `localhost` or `127.0.0.1`. Allow inbound TCP port 8000 through Windows Firewall on a trusted private network if prompted.

The sketch posts to `/api/v1/telemetry/ingest` every 3 seconds. Keep `TARGET_SYSTEM_ID` aligned with a twin shown in the dashboard selector; the default in this project is `twin_prototype_3s1p`.

## 3. Live dashboard

Open the dashboard at the same server origin (`http://<computer-LAN-IP>:8000/ui` from another device). Select the same twin ID as the firmware. HTTP telemetry ingestion is broadcast to the existing WebSocket subscribers, so the dashboard's measured voltage/current/power/temperature strip and charts update without changing the UI layout.

## Notes

- This project ZIP intentionally excludes the local `.env` file, Git history, and generated Python caches. Copy any required local environment values from `.env.example` into your own `.env` file.
- Check sensor calibration before relying on readings. The provided SOC/SOH calculations are estimates, not validated battery-management algorithms.
