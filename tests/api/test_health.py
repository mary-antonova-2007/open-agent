from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.api.main import create_app


async def test_health() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
