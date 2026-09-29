from datetime import datetime

import pytest

from voicedesk.domain import DomainError, validate_local_instant


def test_dst_fold_requires_explicit_offset_and_preserves_distinct_instants() -> None:
    first = validate_local_instant(
        datetime.fromisoformat("2026-11-01T01:30:00-04:00"), "America/New_York"
    )
    second = validate_local_instant(
        datetime.fromisoformat("2026-11-01T01:30:00-05:00"), "America/New_York"
    )
    assert first.isoformat() == "2026-11-01T05:30:00+00:00"
    assert second.isoformat() == "2026-11-01T06:30:00+00:00"


def test_dst_gap_and_mismatched_zone_fail_closed() -> None:
    with pytest.raises(DomainError, match="do not agree"):
        validate_local_instant(
            datetime.fromisoformat("2027-03-14T02:30:00-05:00"), "America/New_York"
        )
    with pytest.raises(DomainError, match="do not agree"):
        validate_local_instant(
            datetime.fromisoformat("2026-10-05T08:00:00-07:00"), "America/New_York"
        )


def test_google_freebusy_reads_one_range_and_fails_closed_on_calendar_error(monkeypatch) -> None:
    from voicedesk.calendar import CalendarError, GoogleCalendar

    class FreebusyClient:
        def __init__(self):
            self.calls = []
            self.response = {"calendars": {"test-calendar": {
                "busy": [{"start": "2026-10-01T14:00:00Z", "end": "2026-10-01T15:00:00Z"}],
            }}}

        def freebusy(self):
            return self

        def query(self, body):
            self.calls.append(body)
            return self

        def execute(self, num_retries):
            assert num_retries == 0
            return self.response

    client = FreebusyClient()
    calendar = GoogleCalendar.__new__(GoogleCalendar)
    calendar.calendar_id = "test-calendar"
    monkeypatch.setattr(calendar, "_client", lambda: client)
    start = datetime.fromisoformat("2026-10-01T13:00:00+00:00")
    end = datetime.fromisoformat("2026-10-01T18:00:00+00:00")
    assert calendar.busy_intervals(start, end) == [
        (datetime.fromisoformat("2026-10-01T14:00:00+00:00"),
         datetime.fromisoformat("2026-10-01T15:00:00+00:00"))
    ]
    assert len(client.calls) == 1
    client.response = {"calendars": {"test-calendar": {"errors": [{"reason": "notFound"}]}}}
    with pytest.raises(CalendarError, match="could not be verified"):
        calendar.busy_intervals(start, end)


def test_explicit_handoff_outranks_an_unrelated_ambiguous_date(monkeypatch) -> None:
    from voicedesk import graphs

    phrase = "Please pass this to a person; I can provide details later."
    monkeypatch.setattr(
        graphs, "_demo_extract", lambda _text, _workspace: graphs.ExtractedTurn(
            intent="handoff", ambiguous_date=True,
        ),
    )
    result = graphs.build_semantic_graph(checkpointer=None).invoke({
        "workspace_id": "cedar-demo", "session_id": "handoff-regression",
        "turn_id": "last-turn", "text": phrase, "mode": "demo",
        "stable_slots": {"exact_date": "2026-12-08", "exact_time": "08:00"},
        "timezone": "America/New_York", "observable_events": [],
    })
    assert result["route"] == "handoff"
    assert "human operator" in result["reply_text"]
    assert result["stable_slots"]["exact_date"] == "2026-12-08"


def test_demo_policy_today_and_booking_customer_named_price(monkeypatch) -> None:
    from types import SimpleNamespace

    from voicedesk import graphs
    from voicedesk.models import Service, ServiceZone

    class CatalogSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def query(self, model):
            entries = ([SimpleNamespace(id="boiler-service", name="Boiler service"),
                        SimpleNamespace(id="drain-clearing", name="Drain clearing")]
                       if model is Service else
                       [SimpleNamespace(id="central", name="Central Maple County"),
                        SimpleNamespace(id="south", name="South Maple County")]
                       if model is ServiceZone else [])

            class Query:
                def filter(self, *_args):
                    return entries

            return Query()

    monkeypatch.setattr(graphs, "SessionLocal", CatalogSession)
    phrase = (
        "Hello, What is the starting price and visit policy for boiler service "
        "in Central Maple County? I am asking about the policy, not booking today."
    )
    extracted = graphs._demo_extract(phrase, "cedar-demo")
    assert extracted.intent == "policy"
    assert extracted.ambiguous_date is True
    assert extracted.service_id == "boiler-service"

    result = graphs.build_semantic_graph(checkpointer=None).invoke({
        "workspace_id": "cedar-demo", "session_id": "policy-date-regression",
        "turn_id": "last-turn", "text": phrase, "mode": "demo",
        "stable_slots": {}, "timezone": "America/New_York", "observable_events": [],
    })
    assert result["route"] == "policy"
    assert "$189" in result["reply_text"]
    assert "Source: kb:boiler-service." in result["reply_text"]
    assert "exact date" not in result["reply_text"].lower()

    booking_phrase = (
        "Hello, I'd like to book a drain clearing in South Maple County on Monday, "
        "October 19 at 11:00 AM. I'm Noah Price; my email is "
        "customer0006.cedar-demo@example.com."
    )
    booking = graphs._demo_extract(booking_phrase, "cedar-demo")
    assert booking.intent == "booking"
    assert booking.customer_name == "Noah Price"
    assert booking.service_id == "drain-clearing"
    assert booking.zone_id == "south"
    assert booking.exact_date.isoformat() == "2026-10-19"
