"""Health endpoint smoke tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_ok(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_root_ok(client: AsyncClient) -> None:
    r = await client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "pi-backend"
    assert "version" in data
