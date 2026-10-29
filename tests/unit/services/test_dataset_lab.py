import pytest

from src.services.dataset_lab import DatasetError, DatasetLabStore, parse_dataset


def test_csv_profile_mappings_and_calculated_power_preserve_source_rows():
    store = DatasetLabStore()
    dataset = store.add("../cycles.csv", b"time,pack_v,pack_i,temp,soc\n2025-01-01T00:00:00Z,12,2,25,0.5\n2025-01-01T00:00:01Z,11,-1,26,0.49\n")
    assert dataset["filename"] == "../cycles.csv"  # Display metadata only; never used as a path.
    saved = store.map_columns(dataset["dataset_id"], {
        "timestamp": {"column": "time", "unit": None},
        "voltage": {"column": "pack_v", "unit": "V"},
        "current": {"column": "pack_i", "unit": "A"},
        "temperature": {"column": "temp", "unit": "°C"},
        "soc": {"column": "soc", "unit": "fraction"},
    })
    assert saved["profile"]["timestamp"]["monotonic_non_decreasing"] is True
    series = store.series(dataset["dataset_id"], ["pack_v", "pack_i", "calculated_power_w"], 10)
    assert [point["calculated_power_w"] for point in series["points"]] == [24.0, -11.0]
    assert series["points"][0]["pack_v"] == 12.0
    assert series["derived"]["calculated_power_w"]["formula"] == "P = V × I"
    assert store.preview(dataset["dataset_id"], 0, 10)["rows"][0]["pack_v"] == "12"


def test_mapping_requires_explicit_compatible_units_and_existing_columns():
    store = DatasetLabStore()
    dataset = store.add("x.csv", b"voltage\n12\n")
    with pytest.raises(DatasetError, match="unit"):
        store.map_columns(dataset["dataset_id"], {"voltage": {"column": "voltage", "unit": None}})
    with pytest.raises(DatasetError, match="does not exist"):
        store.map_columns(dataset["dataset_id"], {"voltage": {"column": "other", "unit": "V"}})


def test_unordered_and_duplicate_timestamps_are_reported_without_sorting():
    store = DatasetLabStore()
    dataset = store.add("x.json", b'{"data":[{"t":"2025-01-01T00:00:02Z"},{"t":"2025-01-01T00:00:01Z"},{"t":"2025-01-01T00:00:01Z"}]}')
    profile = store.map_columns(dataset["dataset_id"], {"timestamp": {"column": "t", "unit": None}})["profile"]
    assert profile["timestamp"]["monotonic_non_decreasing"] is False
    assert profile["timestamp"]["duplicate_count"] == 1
    assert [row["t"] for row in store.preview(dataset["dataset_id"], 0, 10)["rows"]] == [
        "2025-01-01T00:00:02Z", "2025-01-01T00:00:01Z", "2025-01-01T00:00:01Z"]


def test_non_finite_values_and_custom_numeric_series_are_reported():
    store = DatasetLabStore()
    dataset = store.add("x.csv", b"signal\nNaN\nInfinity\n3\n")
    column = dataset["profile"]["columns"][0]
    assert column["non_finite_count"] == 2
    store.map_columns(dataset["dataset_id"], {"series:custom_signal": {"column": "signal", "unit": "raw"}})
    assert store.series(dataset["dataset_id"], ["signal"], 10)["points"][-1]["signal"] == 3.0


def test_downsampling_marks_skipped_missing_samples_as_gaps():
    store = DatasetLabStore()
    dataset = store.add("x.csv", b"v\n1\nNaN\n3\n4\n5\n")
    store.map_columns(dataset["dataset_id"], {"voltage": {"column": "v", "unit": "V"}})
    series = store.series(dataset["dataset_id"], ["v"], 2)
    assert series["raw_row_count"] == 5
    assert series["rendered_point_count"] <= 3
    assert any("v" in point["gap_before"] for point in series["points"])


@pytest.mark.parametrize("filename,payload,match", [
    ("x.csv", b'a,b\n"unterminated,2\n', "Malformed CSV"),
    ("x.json", b"{not valid", "Malformed JSON"),
    ("x.csv", b"\xff\xfe", "UTF-8"),
    ("x.xlsx", b"PK\x03\x04", "XLSX is unavailable"),
    ("x.xls", b"legacy", "XLS is unsupported"),
    ("x.parquet", b"PAR1", "Parquet is unavailable"),
    ("x.json", b"[]", "no data rows"),
])
def test_malformed_empty_encoding_and_unsupported_files(filename, payload, match):
    with pytest.raises(DatasetError, match=match):
        parse_dataset(filename, payload)


def test_unsupported_series_requires_mapping_and_power_requires_voltage_current():
    store = DatasetLabStore()
    dataset = store.add("x.csv", b"x\n1\n")
    with pytest.raises(DatasetError, match="explicitly mapped"):
        store.series(dataset["dataset_id"], ["x"], 10)
    with pytest.raises(DatasetError, match="requires explicitly mapped"):
        store.series(dataset["dataset_id"], ["calculated_power_w"], 10)


def test_dataset_delete_is_isolated_and_generated_id_is_path_safe():
    store = DatasetLabStore()
    first = store.add("../../traverse.csv", b"x\n1\n")
    second = store.add("other.csv", b"y\n2\n")
    assert "/" not in first["dataset_id"] and ".." not in first["dataset_id"]
    store.delete(first["dataset_id"])
    assert [item["dataset_id"] for item in store.list()] == [second["dataset_id"]]
    with pytest.raises(KeyError):
        store.get("../../traverse.csv")


def test_dataset_api_upload_profile_preview_map_series_delete_and_error_responses(monkeypatch):
    from fastapi.testclient import TestClient
    from src.api.app import create_app
    from src.config.settings import AppSettings

    app = create_app(settings=AppSettings(seed_defaults=False))
    with TestClient(app) as client:
        telemetry_count_before = app.state.services.telemetry_repo.count()
        response = client.post("/api/v1/datasets?filename=../test.csv", content=b"t,v,i\n2025-01-01T00:00:00Z,4,2\n", headers={"content-type": "text/plain"})
        assert response.status_code == 201
        body = response.json()
        assert body["filename"] == "test.csv"
        dataset_id = body["dataset_id"]
        assert body["profile"]["row_count"] == 1
        assert app.state.services.telemetry_repo.count() == telemetry_count_before

        mapped = client.put(f"/api/v1/datasets/{dataset_id}/mappings", json={"mappings": {
            "timestamp": {"column": "t"}, "voltage": {"column": "v", "unit": "V"},
            "current": {"column": "i", "unit": "A"},
        }})
        assert mapped.status_code == 200
        series = client.get(f"/api/v1/datasets/{dataset_id}/series?columns=v&columns=i&columns=calculated_power_w")
        assert series.status_code == 200
        assert series.json()["points"][0]["calculated_power_w"] == 8
        assert client.get(f"/api/v1/datasets/{dataset_id}/preview").json()["rows"][0]["v"] == "4"
        assert client.delete(f"/api/v1/datasets/{dataset_id}").status_code == 204
        assert client.get(f"/api/v1/datasets/{dataset_id}").status_code == 404
        assert client.post("/api/v1/datasets?filename=x.csv", content=b"a\n", headers={"content-type": "text/plain"}).status_code == 422

    monkeypatch.setenv("TWINVOLT_DATASET_MAX_UPLOAD_BYTES", "3")
    app = create_app(settings=AppSettings(seed_defaults=False))
    with TestClient(app) as client:
        oversized = client.post("/api/v1/datasets?filename=x.csv", content=b"a\n123\n")
        assert oversized.status_code == 413
