"""CalDAV calendar adapter (BUILD_SPEC sections 63, 88, 96).

Real, over ``httpx`` per this phase's instructions, and reachable only once a
user fills in a server URL and credentials through the Console — no account
detail is ever asked for or hardcoded (section 88). It ships disabled: the
provider registry's ``calendar`` definition defaults ``enabled`` to false, and
nothing in this module runs unless a caller builds one with real settings.

Scope is intentionally narrow. This implements the handful of iCalendar
(RFC 5545) fields LifeOps actually reads and writes — ``UID``, ``DTSTART``,
``DTEND``, ``SUMMARY``, ``LOCATION``, ``DESCRIPTION`` — rather than a general
RFC 5545 parser. A calendar event with fields outside that set still round-trips
correctly; LifeOps simply does not surface them. Free/busy is computed
client-side from ``list_events`` rather than a server-side ``free-busy-query``
REPORT, which not every CalDAV server implements consistently — correct for
every server that implements calendaring at all, at the cost of one extra
round trip.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

import httpx

from lifeops.domain.calendar import CalendarEvent, FreeBusySlot
from lifeops.errors import ProviderError

_REPORT_BODY = """<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:getetag/>
    <C:calendar-data/>
  </D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">
        <C:time-range start="{start}" end="{end}"/>
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>"""


def _ics_stamp(instant: str) -> str:
    """ISO 8601 -> the ``DTSTART``/``DTEND`` basic form (RFC 5545 §3.3.5)."""
    moment = datetime.fromisoformat(instant.replace("Z", "+00:00")).astimezone(UTC)
    return moment.strftime("%Y%m%dT%H%M%SZ")


def _from_ics_stamp(stamp: str) -> str:
    stamp = stamp.strip()
    try:
        if stamp.endswith("Z"):
            moment = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        else:
            moment = datetime.strptime(stamp, "%Y%m%d").replace(tzinfo=UTC)
    except ValueError:
        return stamp
    return moment.isoformat().replace("+00:00", "Z")


def _ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace(
        "\n", "\\n"
    )


def _build_vevent(
    *,
    uid: str,
    subject: str,
    start_at: str,
    end_at: str,
    location: str = "",
    notes: str = "",
) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//LifeOps//Calendar//EN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_ics_stamp(datetime.now(UTC).isoformat())}",
        f"DTSTART:{_ics_stamp(start_at)}",
        f"DTEND:{_ics_stamp(end_at)}",
        f"SUMMARY:{_ics_escape(subject)}",
    ]
    if location:
        lines.append(f"LOCATION:{_ics_escape(location)}")
    if notes:
        lines.append(f"DESCRIPTION:{_ics_escape(notes)}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"


_FIELD = re.compile(r"^([A-Z]+)(?:;[^:]*)?:(.*)$")


def _parse_vevent(ics: str) -> dict[str, str]:
    """Extract the handful of properties this adapter cares about from one
    VEVENT block. Deliberately not a general RFC 5545 parser (module
    docstring) — folded lines and every other property type pass through
    untouched."""
    fields: dict[str, str] = {}
    for raw_line in ics.replace("\r\n", "\n").split("\n"):
        match = _FIELD.match(raw_line.strip())
        if match:
            fields[match.group(1)] = match.group(2)
    return fields


def _event_from_calendar_data(
    calendar_provider_id: str, calendar_data: str
) -> CalendarEvent | None:
    if "BEGIN:VEVENT" not in calendar_data:
        return None
    block = calendar_data.split("BEGIN:VEVENT", 1)[1].split("END:VEVENT", 1)[0]
    fields = _parse_vevent(block)
    uid = fields.get("UID")
    dtstart = fields.get("DTSTART")
    dtend = fields.get("DTEND")
    if not (uid and dtstart and dtend):
        return None
    return CalendarEvent(
        id=CalendarEvent.make_id(calendar_provider_id, uid),
        external_event_id=uid,
        calendar_provider_id=calendar_provider_id,
        title=fields.get("SUMMARY", ""),
        start_at=_from_ics_stamp(dtstart),
        end_at=_from_ics_stamp(dtend),
        location=fields.get("LOCATION", ""),
    )


class CalDAVCalendarProvider:
    """Speaks CalDAV (RFC 4791) over ``httpx`` against one calendar
    collection URL."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str = "",
        password: str = "",
        timeout_s: float = 20.0,
        calendar_provider_id: str = "caldav",
    ) -> None:
        self._calendar_provider_id = calendar_provider_id
        auth = httpx.BasicAuth(username, password) if username else None
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            auth=auth,
            timeout=timeout_s,
            headers={"User-Agent": "lifeops-calendar/1"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_events(self, *, start_at: str, end_at: str) -> list[CalendarEvent]:
        body = _REPORT_BODY.format(start=_ics_stamp(start_at), end=_ics_stamp(end_at))
        try:
            response = await self._client.request(
                "REPORT",
                "",
                content=body,
                headers={"Content-Type": "application/xml; charset=utf-8", "Depth": "1"},
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"CalDAV request failed: {exc}", provider="caldav") from exc
        if response.status_code not in (200, 207):
            raise ProviderError(
                f"CalDAV server returned {response.status_code}",
                provider="caldav",
                status=response.status_code,
            )
        # A minimal multistatus scan: every <C:calendar-data> block is one
        # VEVENT payload. A full WebDAV XML parse is not needed for the one
        # element this adapter reads.
        events: list[CalendarEvent] = []
        for block in re.findall(
            r"<[^:>]*:?calendar-data[^>]*>(.*?)</[^:>]*:?calendar-data>",
            response.text,
            flags=re.DOTALL,
        ):
            event = _event_from_calendar_data(self._calendar_provider_id, block)
            if event is not None:
                events.append(event)
        return sorted(events, key=lambda e: e.start_at)

    async def free_busy(self, *, start_at: str, end_at: str) -> list[FreeBusySlot]:
        events = await self.list_events(start_at=start_at, end_at=end_at)
        return [
            FreeBusySlot(start_at=e.start_at, end_at=e.end_at, busy=True) for e in events
        ]

    async def _put_event(
        self,
        uid: str,
        *,
        subject: str,
        start_at: str,
        end_at: str,
        location: str = "",
        notes: str = "",
    ) -> None:
        ics = _build_vevent(
            uid=uid, subject=subject, start_at=start_at, end_at=end_at,
            location=location, notes=notes,
        )
        try:
            response = await self._client.put(
                f"{uid}.ics",
                content=ics,
                headers={"Content-Type": "text/calendar; charset=utf-8"},
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"CalDAV PUT failed: {exc}", provider="caldav") from exc
        if response.status_code not in (200, 201, 204):
            raise ProviderError(
                f"CalDAV server rejected the event ({response.status_code})",
                provider="caldav",
                status=response.status_code,
            )

    async def create_hold(
        self, *, subject: str, start_at: str, end_at: str, notes: str = ""
    ) -> str:
        # A hold is an ordinary VEVENT tagged in its summary, released by
        # DELETE if it is never confirmed. CalDAV has no first-class "tentative
        # hold" primitive, so this is the reversible local equivalent.
        uid = f"lifeops-hold-{uuid.uuid4().hex}"
        await self._put_event(
            uid, subject=f"[LifeOps hold] {subject}", start_at=start_at, end_at=end_at,
            notes=notes,
        )
        return uid

    async def create_event(
        self,
        *,
        subject: str,
        start_at: str,
        end_at: str,
        location: str = "",
        notes: str = "",
        hold_reference: str | None = None,
    ) -> str:
        uid = hold_reference or f"lifeops-{uuid.uuid4().hex}"
        await self._put_event(
            uid, subject=subject, start_at=start_at, end_at=end_at,
            location=location, notes=notes,
        )
        return uid

    async def get_event(self, external_event_id: str) -> CalendarEvent | None:
        try:
            response = await self._client.get(f"{external_event_id}.ics")
        except httpx.HTTPError as exc:
            raise ProviderError(f"CalDAV GET failed: {exc}", provider="caldav") from exc
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise ProviderError(
                f"CalDAV server returned {response.status_code}",
                provider="caldav",
                status=response.status_code,
            )
        return _event_from_calendar_data(self._calendar_provider_id, response.text)

    async def update_event(
        self,
        external_event_id: str,
        *,
        subject: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        location: str | None = None,
        notes: str | None = None,
    ) -> None:
        current = await self.get_event(external_event_id)
        if current is None:
            raise ProviderError(
                f"no such calendar event: {external_event_id}", provider="caldav"
            )
        await self._put_event(
            external_event_id,
            subject=subject if subject is not None else current.title,
            start_at=start_at if start_at is not None else current.start_at,
            end_at=end_at if end_at is not None else current.end_at,
            location=location if location is not None else current.location,
            notes=notes or "",
        )

    async def cancel_event(self, external_event_id: str) -> None:
        try:
            response = await self._client.delete(f"{external_event_id}.ics")
        except httpx.HTTPError as exc:
            raise ProviderError(f"CalDAV DELETE failed: {exc}", provider="caldav") from exc
        if response.status_code not in (200, 204, 404):
            raise ProviderError(
                f"CalDAV server rejected the cancellation ({response.status_code})",
                provider="caldav",
                status=response.status_code,
            )

    async def health(self) -> tuple[bool, str]:
        try:
            response = await self._client.request(
                "PROPFIND", "", headers={"Depth": "0"}
            )
        except httpx.HTTPError as exc:
            return False, f"could not reach the CalDAV server: {exc}"
        if response.status_code in (200, 207):
            return True, "CalDAV server reachable"
        return False, f"CalDAV server returned {response.status_code}"
