from __future__ import annotations

import respx
from httpx import Response

from app.infrastructure.llm import ChatMessage, OpenAICompatibleLLMClient


async def test_openai_compatible_llm_client_posts_chat_completion() -> None:
    client = OpenAICompatibleLLMClient(
        base_url="http://llm.test/v1",
        api_key="test-key",
        model="gpt-oss-20b:latest",
        timeout_seconds=1,
    )
    with respx.mock(assert_all_called=True) as router:
        route = router.post("http://llm.test/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "choices": [
                        {"message": {"role": "assistant", "content": "Работает"}}
                    ]
                },
            )
        )

        answer = await client.chat([ChatMessage(role="user", content="ping")])

    assert answer == "Работает"
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer test-key"
    assert request.content
