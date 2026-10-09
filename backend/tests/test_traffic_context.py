import pytest
from atlas.traffic_context import normalize_events, parse_toronto_csv


def test_toronto_official_csv_preserves_future_restrictions_without_asserting_active_closure():
    header = "ID,Latitude,Longitude,Expired,Planned,StartTime,EndTime,LastUpdated,Name,Description,Type,CurrImpact\n"
    rows = b"one,43.6,-79.3,0,1,1792000000000,,1791000000000,Future work,Reported work,CONSTRUCTION,None\ntwo,43.6,-79.3,1,1,1792000000000,,1791000000000,Expired work,Reported work,CONSTRUCTION,None\nbroken,43.6\n"
    data = parse_toronto_csv(b"Current road restrictions\n" + header.encode() + rows)
    assert data["malformed_records_omitted"] == 1
    events = normalize_events("toronto", data, "2026-10-08T21:00:00+00:00")
    assert len(events) == 1 and events[0]["id"] == "one"
    assert "planned=1" in events[0]["source_status"]
    assert not events[0]["applied_to_simulation"]


def test_road_events_preserve_reporting_and_source_time_ambiguity():
    data = {
        "Features": [
            {
                "PointCoordinate": [47.6, -122.3],
                "Incidents": [
                    {
                        "Id": "one",
                        "Description": "Reported collision",
                        "Type": "Collision",
                        "StartDateTime": "10/8/2026 1:00:00 PM",
                    }
                ],
            }
        ]
    }
    event = normalize_events("seattle", data, "2026-10-08T21:00:00+00:00")[0]
    assert event["started_at"] == "10/8/2026 1:00:00 PM"
    assert event["source_modified_at"] is None
    assert not event["confirmed_by_atlas"] and not event["applied_to_simulation"]


def test_incident_adapter_rejects_bad_geometry_and_does_not_revive_inactive_reports():
    inactive = {"traffic_report_status": "INACTIVE"}
    assert normalize_events("austin", [inactive], "2026-10-08T21:00:00+00:00") == []
    invalid = {
        "id": "x",
        "geography": {"coordinates": [200, 51]},
        "category": "Works",
        "status": "Active",
    }
    with pytest.raises(ValueError):
        normalize_events("london", [invalid], "2026-10-08T21:00:00+00:00")
    assert normalize_events("london", [{"id": "no-point"}], "2026-10-08T21:00:00+00:00") == []
