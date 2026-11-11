import asyncio

import pytest

from ep_engine.main import RequestBoundary


def test_asgi_chunk_limits_and_disconnect():
    async def exercise(chunks, limit):
        output = []
        reached = []

        async def application(scope, receive, send):
            message = await receive()
            reached.append(message["body"])
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        iterator = iter(chunks)

        async def receive():
            return next(iterator)

        async def send(message):
            output.append(message)

        await RequestBoundary(application, limit)({"type": "http"}, receive, send)
        return output, reached

    output, reached = asyncio.run(
        exercise(
            [
                {"type": "http.request", "body": b"ab", "more_body": True},
                {"type": "http.request", "body": b"cd", "more_body": False},
            ],
            3,
        )
    )
    assert output[0]["status"] == 413
    assert reached == []
    output, reached = asyncio.run(
        exercise(
            [
                {"type": "http.request", "body": b"ab", "more_body": True},
                {"type": "http.request", "body": b"cd", "more_body": False},
            ],
            4,
        )
    )
    assert output[0]["status"] == 200
    assert reached == [b"abcd"]
    output, reached = asyncio.run(exercise([{"type": "http.disconnect"}], 4))
    assert output == reached == []


def test_stream_failure_after_headers_is_not_false_success():
    async def application(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("stream interrupted")

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        return None

    with pytest.raises(RuntimeError, match="stream interrupted"):
        asyncio.run(RequestBoundary(application, 10)({"type": "http"}, receive, send))
