"""CalDAV adapter parsing and round-trip rules (BUILD_SPEC sections 63, 96).

Pinned after the 2026-08-18 audit: the old parser handled only ``...Z`` and
bare-date stamps and returned every other RFC 5545 form *raw* — poisoning
``start_at`` ordering, shifting events on update (the raw stamp re-parsed as
naive local time), truncating folded lines, double-encoding XML entities,
dropping recurrence entirely, and erasing DESCRIPTION on every update.

The transport-level tests use ``httpx.MockTransport``, the same technique the
Twilio and ElevenLabs adapters are tested with — no live CalDAV server.
"""

from __future__ import annotations

import httpx

from lifeops.calendar.caldav import (
    CalDAVCalendarProvider,
    _events_from_calendar_data,
    _from_ics_stamp,
    _parse_vevent,
)

_MULTISTATUS = """<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:response>
    <D:propstat><D:prop><C:calendar-data>{ics}</C:calendar-data></D:prop></D:propstat>
  </D:response>
</D:multistatus>"""


def _vevent(body: str) -> str:
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
        f"BEGIN:VEVENT\r\n{body}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    )


class TestStampParsing:
    def test_utc_form(self) -> None:
        assert _from_ics_stamp("20260818T120000Z") == "2026-08-18T12:00:00Z"

    def test_tzid_form_converts_through_the_named_zone(self) -> None:
        """The normal form Google/Apple/Nextcloud clients write. The old
        parser returned it raw."""
        assert (
            _from_ics_stamp("20260818T120000", tzid="America/New_York")
            == "2026-08-18T16:00:00Z"  # EDT is UTC-4 in August
        )

    def test_floating_time_falls_back_to_utc_not_raw(self) -> None:
        assert _from_ics_stamp("20260818T120000") == "2026-08-18T12:00:00Z"

    def test_an_unknown_tzid_falls_back_to_utc_not_raw(self) -> None:
        assert (
            _from_ics_stamp("20260818T120000", tzid="Not/AZone")
            == "2026-08-18T12:00:00Z"
        )

    def test_all_day_value(self) -> None:
        assert _from_ics_stamp("20260818") == "2026-08-18T00:00:00Z"

    def test_garbage_still_passes_through_as_a_last_resort(self) -> None:
        assert _from_ics_stamp("not-a-date") == "not-a-date"


class TestVeventParsing:
    def test_folded_lines_are_unfolded(self) -> None:
        """RFC 5545 section 3.1: a line starting with a space continues the
        previous one. The old parser truncated a long SUMMARY at the fold."""
        fields = _parse_vevent(
            "SUMMARY:Electrical panel inspection with th\r\n e county inspector\r\n"
        )
        assert fields["SUMMARY"][1] == (
            "Electrical panel inspection with the county inspector"
        )

    def test_property_parameters_are_captured(self) -> None:
        fields = _parse_vevent("DTSTART;TZID=Europe/Berlin:20260818T090000\r\n")
        params, value = fields["DTSTART"]
        assert "TZID=Europe/Berlin" in params
        assert value == "20260818T090000"

    def test_every_vevent_block_is_read_not_only_the_first(self) -> None:
        """A server-expanded recurring event is one block per occurrence
        sharing a UID; each needs its own distinct event."""
        ics = (
            "BEGIN:VCALENDAR\r\n"
            "BEGIN:VEVENT\r\nUID:standup\r\nRECURRENCE-ID:20260818T090000Z\r\n"
            "DTSTART:20260818T090000Z\r\nDTEND:20260818T091500Z\r\n"
            "SUMMARY:Stand-up\r\nEND:VEVENT\r\n"
            "BEGIN:VEVENT\r\nUID:standup\r\nRECURRENCE-ID:20260825T090000Z\r\n"
            "DTSTART:20260825T090000Z\r\nDTEND:20260825T091500Z\r\n"
            "SUMMARY:Stand-up\r\nEND:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        events = _events_from_calendar_data("caldav", ics)
        assert len(events) == 2
        assert events[0].id != events[1].id  # occurrences must not collapse
        assert {e.start_at for e in events} == {
            "2026-08-18T09:00:00Z",
            "2026-08-25T09:00:00Z",
        }

    def test_escaped_text_is_unescaped(self) -> None:
        ics = _vevent(
            "UID:x\r\nDTSTART:20260818T090000Z\r\nDTEND:20260818T100000Z\r\n"
            "SUMMARY:Lunch\\, then errands\\; maybe\r\n"
        )
        (event,) = _events_from_calendar_data("caldav", ics)
        assert event.title == "Lunch, then errands; maybe"


def _provider(handler) -> CalDAVCalendarProvider:
    return CalDAVCalendarProvider(
        base_url="https://cal.example.test/user/calendar",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://cal.example.test/user/calendar/",
        ),
    )


class TestListEvents:
    async def test_xml_entities_are_decoded_and_expand_is_requested(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = request.content.decode()
            ics = _vevent(
                "UID:x\r\nDTSTART;TZID=America/New_York:20260818T120000\r\n"
                "DTEND;TZID=America/New_York:20260818T130000\r\n"
                "SUMMARY:Tom &amp; Jerry\r\n"
            )
            return httpx.Response(207, text=_MULTISTATUS.format(ics=ics))

        provider = _provider(handler)
        try:
            events = await provider.list_events(
                start_at="2026-08-18T00:00:00Z", end_at="2026-08-19T00:00:00Z"
            )
        finally:
            await provider.aclose()

        (event,) = events
        assert event.title == "Tom & Jerry"  # not "Tom &amp; Jerry"
        assert event.start_at == "2026-08-18T16:00:00Z"  # EDT -> UTC
        # RFC 4791 section 9.6.5: the server expands recurrences for us.
        assert "expand" in seen["body"]


class TestUpdatePreservesNotes:
    async def test_updating_a_time_keeps_the_description(self) -> None:
        """The old ``notes or \"\"`` erased confirmation numbers whenever a
        reschedule touched any other field."""
        put_bodies: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                ics = _vevent(
                    "UID:appt\r\nDTSTART:20260818T090000Z\r\n"
                    "DTEND:20260818T100000Z\r\nSUMMARY:Electrician\r\n"
                    "DESCRIPTION:Confirmation no. 4711\r\n"
                )
                return httpx.Response(200, text=ics)
            put_bodies.append(request.content.decode())
            return httpx.Response(204)

        provider = _provider(handler)
        try:
            await provider.update_event("appt", start_at="2026-08-18T11:00:00Z")
        finally:
            await provider.aclose()

        (body,) = put_bodies
        assert "DESCRIPTION:Confirmation no. 4711" in body
        assert "DTSTART:20260818T110000Z" in body
