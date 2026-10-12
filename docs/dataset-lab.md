# Dataset Lab

Dataset Lab accepts historical CSV and JSON files through `POST /api/v1/datasets?filename=<name>` as a raw request body. Files are parsed in memory, limited by `TWINVOLT_DATASET_MAX_UPLOAD_BYTES` (default 20 MiB), bounded to 100,000 rows, 200 columns, and 500,000 cells, and retained for up to one hour of inactivity. The temporary registry allows up to 10 files / 100 MiB total. It is process-local and is cleared when the server restarts. There is no permanent file storage.

Supported JSON shapes are an array of row objects or an object with `data` or `rows` containing row objects. CSV and JSON must decode as UTF-8. XLSX, XLS, and Parquet are reported as unavailable because this environment does not have `openpyxl`, `xlrd`, or `pyarrow`. A previously downloaded Kaggle CSV/JSON can be uploaded; there is no Kaggle API integration and no credential handling.

## API

- `POST /api/v1/datasets?filename=...` — bounded raw upload; MIME type is not trusted.
- `GET /api/v1/datasets` — list temporary uploads.
- `GET /api/v1/datasets/{dataset_id}` — profile and quality report.
- `GET /api/v1/datasets/{dataset_id}/preview?offset=0&limit=25` — bounded raw rows (maximum 100).
- `PUT /api/v1/datasets/{dataset_id}/mappings` — explicitly map columns and units.
- `GET /api/v1/datasets/{dataset_id}/series?columns=...&columns=...&limit=1500` — mapped series; repeat `columns` for each selection; maximum 2,000 points, deterministic row stride, final row retained, skipped gaps marked, raw rows unchanged.
- `DELETE /api/v1/datasets/{dataset_id}` — remove the temporary dataset.

Known conversions are V/mV to V, A/mA to A, °F to °C, and SOC/SOH fraction to percent. Numeric timestamps require an explicit ns/ms/s unit; timezone-aware ISO timestamps are accepted directly. No column mapping or unit is automatically confirmed. Calculated power requires explicitly mapped voltage and current and uses `P = V × I`; its sign is preserved without assigning charge/discharge meaning.

## Replay and security limits

Uploads do not enter the live telemetry repository and do not cause a Twin step. Dataset replay is deliberately not wired to the existing CSV replay API: `ReplayService.replay_csv` resolves the selected Twin instance and the replay configuration defaults to `auto_reset_instance=True`. A separate reviewed replay sandbox is required to guarantee live state isolation.

The repository has no existing API authentication or authorization layer. Dataset endpoints currently inherit that repository-wide state. Do not expose this service to an untrusted network until an authentication/session design, authorization boundary, rate limiting, and deployment storage policy are reviewed and implemented. The upload registry is process-local and not multi-worker shared.

Start locally with:

```powershell
python -m src.server --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000/ui`. Set `TWINVOLT_DATASET_MAX_UPLOAD_BYTES` on the server to change the per-upload byte cap.
