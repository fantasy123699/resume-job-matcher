import asyncio

import httpx

from resume_job_matcher.api.app import app


def get(path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path)

    return asyncio.run(request())


def test_liveness_endpoint() -> None:
    response = get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_endpoint() -> None:
    response = get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
