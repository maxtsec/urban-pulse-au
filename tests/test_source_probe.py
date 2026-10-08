"""Public source probes are bounded and replay from retained bytes only."""

import json

import httpx
import pytest

from scripts import source_probe as probe


def weather():
    return {
        "utc_offset_seconds": 0,
        "latitude": -37.8,
        "longitude": 144.96,
        "current": {
            "time": 1791421200,
            "interval": 900,
            "temperature_2m": 18,
            "precipitation": 0,
            "rain": 0,
            "weather_code": 3,
            "cloud_cover": 100,
            "wind_speed_10m": 2,
            "is_day": 1,
        },
        "current_units": {
            "time": "unixtime",
            "temperature_2m": "°C",
            "precipitation": "mm",
            "rain": "mm",
            "weather_code": "wmo code",
            "cloud_cover": "%",
            "wind_speed_10m": "m/s",
            "is_day": "",
        },
    }


def row(key="one", area="Southbank"):
    return {
        "development_key": key,
        "clue_small_area": area,
        "status": "Under Construction",
        "geopoint": {"lat": -37.82, "lon": 144.96},
        "year_completed": None,
    }


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.time, "sleep", lambda _: None)
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.host == "api.open-meteo.com":
            assert request.url.params["timeformat"] == "unixtime"
            assert request.url.params["current"].split(",") == list(probe.VARIABLES)
            return httpx.Response(200, json=weather())
        if request.url.path.endswith("/records"):
            area = "Southbank" if "Southbank" in request.url.params["where"] else "Melbourne (CBD)"
            offset = int(request.url.params["offset"])
            return httpx.Response(
                200,
                json={
                    "total_count": 101,
                    "results": [row(str(i), area) for i in range(offset, min(offset + 100, 101))],
                },
            )
        return httpx.Response(
            200,
            json={
                "metas": {
                    "default": {
                        "modified": "2026-09-24T00:00:00Z",
                        "records_count": 1450,
                        "license": "CC BY",
                    }
                }
            },
        )

    directory = tmp_path / "probe"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        probe.capture(directory, client)
    return directory, calls


def test_capture_and_offline_replay_keep_source_times_and_all_pages(saved):
    folder, calls = saved
    result = probe.replay(folder)
    assert len(calls) == 8
    assert result["requests"] == 8
    assert result["dam_metadata_stable"]
    for area in probe.AREAS:
        assert result["areas"][area]["planning"]["pages_complete"]
        assert result["areas"][area]["planning"]["records"] == 101
        reading = result["areas"][area]["weather"]
        assert reading["interval_seconds"] == 900
        assert reading["resolved_model"] is None
        assert reading["warning_coverage"] == "not_evaluated"
    assert result["public_live_enabled"] is False
    assert probe.replay(folder) == result


def test_replay_rejects_tampered_bytes_and_incomplete_capture(saved):
    folder, _ = saved
    original = (folder / "00.json").read_bytes()
    (folder / "00.json").write_bytes(original + b" ")
    with pytest.raises(ValueError, match="integrity"):
        probe.replay(folder)
    (folder / "00.json").write_bytes(original)
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["complete"] = False
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Incomplete"):
        probe.replay(folder)


def test_replay_refuses_reference_outside_capture_directory(saved):
    folder, _ = saved
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["entries"][0]["file"] = "../other.json"
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="reference"):
        probe.replay(folder)


def test_planning_preserves_missing_location_and_detects_incomplete_or_duplicate_pages():
    unlocated = {**row(), "geopoint": None}
    summary = probe.planning_summary([{"total_count": 1, "results": [unlocated]}], "Southbank")
    assert summary["missing_positions"] == 1
    assert summary["pages_complete"]
    for total, rows in [(2, [row()]), (2, [row(), row()])]:
        assert not probe.planning_summary([{"total_count": total, "results": rows}], "Southbank")[
            "pages_complete"
        ]
    with pytest.raises(ValueError, match="unrequested"):
        probe.planning_summary([{"total_count": 1, "results": [row(area="Carlton")]}], "Southbank")
    for invalid in [
        None,
        {**row(), "status": None, "geopoint": None},
        {**row(), "geopoint": {"lat": None, "lon": 144}},
    ]:
        with pytest.raises(ValueError):
            probe.planning_summary([{"total_count": 1, "results": [invalid]}], "Southbank")


def test_weather_missing_is_not_zero_and_wrong_units_or_time_are_rejected():
    data = weather()
    data["current"]["rain"] = None
    assert probe.weather_summary(data)["missing"] == ["rain"]
    assert probe.weather_summary(data)["values"]["rain"] is None
    for mutate in [
        lambda d: d.update(utc_offset_seconds=3600),
        lambda d: d["current_units"].update(wind_speed_10m="km/h"),
        lambda d: d["current"].update(time="2026-10-08T00:00:00"),
        lambda d: d["current"].update(rain=float("nan")),
    ]:
        data = weather()
        mutate(data)
        with pytest.raises(ValueError):
            probe.weather_summary(data)
    with pytest.raises(ValueError):
        probe.decode(b'{"rain":NaN}')


def test_http_failure_and_bounds_do_not_retry_or_claim_complete(tmp_path, monkeypatch):
    for code in [301, 403, 429, 503]:
        calls = []

        def handler(request, calls=calls, code=code):
            calls.append(request)
            return httpx.Response(code, headers={"Location": probe.DAM})

        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
            folder = tmp_path / str(code)
            with pytest.raises(httpx.HTTPStatusError):
                probe.capture(folder, client)
            assert len(calls) == 1
            assert json.loads((folder / "manifest.json").read_text())["complete"] is False
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 100))
    ) as client:
        monkeypatch.setattr(probe, "MAX_BYTES", 20)
        with pytest.raises(ValueError, match="budget"):
            probe.capture(tmp_path / "oversize", client)
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: pytest.fail("Unexpected network request"))
    ) as client:
        monkeypatch.setattr(probe, "MAX_REQUESTS", 0)
        with pytest.raises(ValueError, match="budget"):
            probe.capture(tmp_path / "limit", client)
        monkeypatch.setattr(probe, "MAX_REQUESTS", 16)
        monkeypatch.setattr(probe, "MAX_SECONDS", 0)
        with pytest.raises(ValueError, match="budget"):
            probe.capture(tmp_path / "deadline", client)


@pytest.mark.parametrize("total", [1000, 1001])
def test_both_areas_can_use_ten_pages_within_global_budget(tmp_path, monkeypatch, total):
    monkeypatch.setattr(probe.time, "sleep", lambda _: None)
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.host == "api.open-meteo.com":
            return httpx.Response(200, json=weather())
        if request.url.path.endswith("/records"):
            area = "Southbank" if "Southbank" in request.url.params["where"] else "Melbourne (CBD)"
            offset = int(request.url.params["offset"])
            return httpx.Response(
                200,
                json={
                    "total_count": total,
                    "results": [row(str(i), area) for i in range(offset, offset + 100)],
                },
            )
        return httpx.Response(200, json={"metas": {"default": {"records_count": total}}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        probe.capture(tmp_path / "pages", client)
    result = probe.replay(tmp_path / "pages")
    assert len(calls) == probe.MAX_REQUESTS == 24
    for area in probe.AREAS:
        planning = result["areas"][area]["planning"]
        assert planning["records"] == 1000
        assert planning["pages_complete"] is (total == 1000)
