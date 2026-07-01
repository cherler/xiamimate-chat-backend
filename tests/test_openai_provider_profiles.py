from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_platform import llm_client  # noqa: E402
from data_platform.chat_backend.domains.provider_proxy import service  # noqa: E402


class FakeResponse:
    ok = True
    status_code = 200
    reason = "OK"
    url = "https://api.apiyi.com/v1/chat/completions"
    text = "{}"

    def json(self) -> dict:
        return {"choices": [{"message": {"content": "ok"}}]}


class OpenAIProviderProfileTests(unittest.TestCase):
    def test_apiyi_profile_uses_profiled_env_and_removes_gpt5_sampling_params(self) -> None:
        observed = {}

        def fake_post(url, headers, json, timeout):
            observed.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
            return FakeResponse()

        with patch.dict(
            os.environ,
            {
                "AGENT_OPENAI_BASE_URL": "https://api.deepseek.com",
                "AGENT_OPENAI_MODEL": "deepseek-v4-pro",
                "AGENT_OPENAI_API_KEY": "deepseek-key",
                "AGENT_OPENAI_APIYI_ENABLED": "true",
                "AGENT_OPENAI_APIYI_BASE_URL": "https://api.apiyi.com/v1",
                "AGENT_OPENAI_APIYI_MODEL": "gpt-5.5",
                "AGENT_OPENAI_APIYI_API_KEY": "apiyi-key",
                "AGENT_OPENAI_APIYI_TIMEOUT_SECONDS": "180",
            },
            clear=True,
        ), patch.object(llm_client.requests, "post", side_effect=fake_post):
            response = service._proxy_openai_chat_completion(
                payload={
                    "model": "ignored-client-model",
                    "messages": [{"role": "user", "content": "用一句话介绍你自己"}],
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "tools": [{"type": "function", "function": {"name": "resolve_candidates"}}],
                    "tool_choice": "auto",
                },
                provider_profile="apiyi",
            )

        self.assertEqual(response["choices"][0]["message"]["content"], "ok")
        self.assertEqual(observed["url"], "https://api.apiyi.com/v1/chat/completions")
        self.assertEqual(observed["headers"]["Authorization"], "Bearer apiyi-key")
        self.assertEqual(observed["json"]["model"], "gpt-5.5")
        self.assertNotIn("temperature", observed["json"])
        self.assertNotIn("top_p", observed["json"])
        self.assertEqual(observed["json"]["reasoning_effort"], "medium")
        self.assertEqual(observed["json"]["tool_choice"], "auto")
        self.assertEqual(observed["timeout"], 180.0)

    def test_openai_provider_retries_once_on_incomplete_transfer(self) -> None:
        calls = []

        def flaky_post(url, headers, json, timeout):
            calls.append({"url": url, "json": json})
            if len(calls) == 1:
                raise llm_client.requests.exceptions.ChunkedEncodingError("incomplete transfer")
            return FakeResponse()

        with patch.dict(
            os.environ,
            {
                "AGENT_OPENAI_APIYI_ENABLED": "true",
                "AGENT_OPENAI_APIYI_BASE_URL": "https://api.apiyi.com/v1",
                "AGENT_OPENAI_APIYI_MODEL": "gpt-5.5",
                "AGENT_OPENAI_APIYI_API_KEY": "apiyi-key",
            },
            clear=True,
        ), patch.object(llm_client.requests, "post", side_effect=flaky_post):
            response = service._proxy_openai_chat_completion(
                payload={"messages": [{"role": "user", "content": "hi"}]},
                provider_profile="apiyi",
            )

        self.assertEqual(response["choices"][0]["message"]["content"], "ok")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["json"]["model"], "gpt-5.5")


if __name__ == "__main__":
    unittest.main()
