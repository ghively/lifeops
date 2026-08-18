"""TwilioTelephonyProvider (BUILD_SPEC sections 68, 69, 88, 97).

Verified against Twilio's documented REST API shape via
``httpx.MockTransport`` — the same technique ``test_voice.py`` uses for
ElevenLabs. Unlike the browser adapter, this is not exercised against a
live account (no Twilio account exists to test against); these tests prove
the request/response handling is correct, not that a real call could be
placed today.
"""

from __future__ import annotations

import base64
from urllib.parse import unquote

import httpx
import pytest

from lifeops.domain.telephony import build_objective
from lifeops.errors import ProviderError
from lifeops.telephony.twilio import TwilioTelephonyProvider

ACCOUNT_SID = "AC" + "0" * 32
AUTH_TOKEN = "test-auth-token"
FROM_NUMBER = "+15551234567"


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.twilio.com",
        auth=(ACCOUNT_SID, AUTH_TOKEN),
    )


def _provider(handler) -> TwilioTelephonyProvider:
    return TwilioTelephonyProvider(
        account_sid=ACCOUNT_SID,
        auth_token=AUTH_TOKEN,
        from_number=FROM_NUMBER,
        client=_mock_client(handler),
    )


def _basic_auth_header(request: httpx.Request) -> str:
    return request.headers["authorization"]


class TestHealth:
    async def test_reports_healthy_for_an_active_account(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["auth"] = _basic_auth_header(request)
            return httpx.Response(200, json={"status": "active", "sid": ACCOUNT_SID})

        provider = _provider(handler)
        healthy, message = await provider.health()
        await provider.aclose()

        assert healthy is True
        assert f"/2010-04-01/Accounts/{ACCOUNT_SID}.json" in captured["url"]
        expected = base64.b64encode(f"{ACCOUNT_SID}:{AUTH_TOKEN}".encode()).decode()
        assert captured["auth"] == f"Basic {expected}"

    async def test_reports_unhealthy_for_a_suspended_account(self) -> None:
        provider = _provider(
            lambda request: httpx.Response(200, json={"status": "suspended"})
        )
        healthy, message = await provider.health()
        await provider.aclose()

        assert healthy is False
        assert "suspended" in message

    async def test_reports_unhealthy_on_rejected_credentials(self) -> None:
        provider = _provider(lambda request: httpx.Response(401))
        healthy, message = await provider.health()
        await provider.aclose()

        assert healthy is False
        assert "rejected" in message

    async def test_reports_unhealthy_on_a_transport_failure(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        provider = _provider(handler)
        healthy, message = await provider.health()
        await provider.aclose()

        assert healthy is False
        assert "could not reach Twilio" in message


class TestDial:
    async def test_raises_because_no_destination_number_is_ever_available(self) -> None:
        # No handler should ever be reached — dial() must refuse before
        # making any request, since it has nothing to call.
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("dial() must not make a request with no destination number")

        provider = _provider(handler)
        objective = build_objective(objective="schedule_electrician", collect=["availability"])
        with pytest.raises(ProviderError, match="no destination phone number"):
            await provider.dial(objective)
        await provider.aclose()


class TestHangup:
    async def test_posts_completed_status_to_the_call_resource(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["body"] = dict(
                item.split("=") for item in request.content.decode().split("&")
            )
            return httpx.Response(200, json={"status": "completed"})

        provider = _provider(handler)
        await provider.hangup("CA123")
        await provider.aclose()

        assert "/Calls/CA123.json" in captured["url"]
        assert captured["body"]["Status"] == "completed"

    async def test_raises_on_an_http_error_status(self) -> None:
        provider = _provider(lambda request: httpx.Response(404, json={"message": "not found"}))
        with pytest.raises(ProviderError, match="HTTP 404"):
            await provider.hangup("CA-unknown")
        await provider.aclose()


class TestSendDtmf:
    async def test_redirects_the_call_with_play_digits_twiml(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = unquote(request.content.decode())
            return httpx.Response(200, json={"status": "in-progress"})

        provider = _provider(handler)
        await provider.send_dtmf("CA123", "1234#")
        await provider.aclose()

        assert 'digits="1234#"' in captured["body"]

    async def test_refuses_characters_that_are_not_valid_dtmf(self) -> None:
        provider = _provider(lambda request: httpx.Response(200))
        with pytest.raises(ProviderError, match="not valid DTMF"):
            await provider.send_dtmf("CA123", "12x34")
        await provider.aclose()


class TestGetStatus:
    async def test_a_connected_call_is_honest_about_having_no_conversation(self) -> None:
        provider = _provider(
            lambda request: httpx.Response(200, json={"status": "in-progress"})
        )
        result = await provider.get_status("CA123")
        await provider.aclose()

        assert result is not None
        assert result.connected is True
        assert result.objective_met is False
        assert result.follow_up_required is True
        assert "cannot yet hold a phone conversation" in result.transcript

    async def test_a_completed_call_is_also_reported_as_connected(self) -> None:
        provider = _provider(
            lambda request: httpx.Response(200, json={"status": "completed"})
        )
        result = await provider.get_status("CA123")
        await provider.aclose()

        assert result is not None
        assert result.connected is True

    async def test_a_call_that_never_connected_is_reported_honestly(self) -> None:
        provider = _provider(lambda request: httpx.Response(200, json={"status": "no-answer"}))
        result = await provider.get_status("CA123")
        await provider.aclose()

        assert result is not None
        assert result.connected is False
        assert result.transcript == "call status: no-answer"

    async def test_an_unknown_reference_returns_none_not_an_error(self) -> None:
        provider = _provider(lambda request: httpx.Response(404, json={"message": "not found"}))
        result = await provider.get_status("CA-unknown")
        await provider.aclose()

        assert result is None

