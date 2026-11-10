import json
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.integrations.apns import ApnsSender

TOKEN = "ab" * 32
NOW = datetime(2027, 3, 10, 12, 0, tzinfo=UTC)


def _key_pem() -> tuple[str, object]:
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return pem, key.public_key()


def _sender(handler, clock=lambda: NOW):
    pem, pub = _key_pem()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sender = ApnsSender("KEYID12345", "TEAMID1234", pem, "com.example.mc", client, clock=clock)
    return sender, pub


async def test_request_shape_and_jwt():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    sender, pub = _sender(handler)
    result = await sender.send(TOKEN, "sandbox", "MC-1", "MC-1: прибыл в Поти", {"ref": "MC-1"})
    assert result == "ok"
    req = seen[0]
    assert str(req.url) == f"https://api.sandbox.push.apple.com/3/device/{TOKEN}"
    assert req.headers["apns-topic"] == "com.example.mc"
    assert req.headers["apns-push-type"] == "alert"
    auth = req.headers["authorization"]
    assert auth.startswith("bearer ")
    claims = jwt.decode(auth[7:], pub, algorithms=["ES256"], options={"verify_iat": False})
    assert claims["iss"] == "TEAMID1234"
    assert jwt.get_unverified_header(auth[7:])["kid"] == "KEYID12345"
    assert json.loads(req.content) == {
        "aps": {"alert": {"title": "MC-1", "body": "MC-1: прибыл в Поти"}, "sound": "default"},
        "ref": "MC-1",
    }


async def test_production_host():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200)

    sender, _ = _sender(handler)
    await sender.send(TOKEN, "production", "t", "b", {})
    assert seen[0].url.host == "api.push.apple.com"


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (410, {"reason": "Unregistered"}, "gone"),
        (400, {"reason": "BadDeviceToken"}, "gone"),
        (400, {"reason": "Unregistered"}, "gone"),
        (400, {"reason": "PayloadEmpty"}, "error"),
        (500, {"reason": "InternalServerError"}, "error"),
        (429, {}, "error"),
    ],
)
async def test_status_mapping(status, body, expected):
    sender, _ = _sender(lambda r: httpx.Response(status, json=body))
    assert await sender.send(TOKEN, "sandbox", "t", "b", {}) == expected


async def test_transport_error_is_error():
    def handler(request):
        raise httpx.ConnectError("boom")

    sender, _ = _sender(handler)
    assert await sender.send(TOKEN, "sandbox", "t", "b", {}) == "error"


async def test_jwt_cached_50_minutes():
    tokens: list[str] = []
    now = [NOW]

    def handler(request):
        tokens.append(request.headers["authorization"])
        return httpx.Response(200)

    sender, _ = _sender(handler, clock=lambda: now[0])
    await sender.send(TOKEN, "sandbox", "t", "b", {})
    now[0] = NOW + timedelta(minutes=49)
    await sender.send(TOKEN, "sandbox", "t", "b", {})
    assert tokens[0] == tokens[1]
    now[0] = NOW + timedelta(minutes=51)
    await sender.send(TOKEN, "sandbox", "t", "b", {})
    assert tokens[2] != tokens[0]
