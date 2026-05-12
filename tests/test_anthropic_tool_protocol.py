import json
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_platform.llm_client import (  # noqa: E402
    anthropic_response_to_openai_chat_completion,
    build_anthropic_messages_payload,
)
from data_platform.chat_backend.domains.provider_proxy.service import _format_theme_api_tool_result  # noqa: E402


class AnthropicToolProtocolTests(unittest.TestCase):
    def test_openai_tool_messages_convert_to_anthropic_tool_use_and_result(self) -> None:
        payload = build_anthropic_messages_payload(
            model="MiniMax-M2.7-highspeed",
            messages=[
                {"role": "system", "content": "system instructions"},
                {"role": "user", "content": "resolve humidifier"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "resolve_candidates",
                                "arguments": json.dumps(
                                    {"product_query": "humidifier", "marketplace": "US"},
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": '{"candidate_asins":["B001"]}'},
            ],
            temperature=0,
            response_format=None,
            extra_body={
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "resolve_candidates",
                            "description": "Resolve candidate ASINs.",
                            "parameters": {
                                "type": "object",
                                "properties": {"product_query": {"type": "string"}},
                            },
                        },
                    }
                ],
                "tool_choice": "auto",
                "max_tokens": 1024,
            },
            default_max_tokens=4096,
        )

        self.assertEqual(payload["system"], "system instructions")
        self.assertEqual(payload["tool_choice"], {"type": "auto"})
        self.assertEqual(payload["tools"][0]["name"], "resolve_candidates")
        self.assertEqual(payload["tools"][0]["input_schema"]["properties"]["product_query"]["type"], "string")

        assistant_blocks = payload["messages"][1]["content"]
        self.assertEqual(assistant_blocks[0]["type"], "tool_use")
        self.assertEqual(assistant_blocks[0]["id"], "call_1")
        self.assertEqual(assistant_blocks[0]["name"], "resolve_candidates")
        self.assertEqual(assistant_blocks[0]["input"]["product_query"], "humidifier")

        tool_result_blocks = payload["messages"][2]["content"]
        self.assertEqual(tool_result_blocks[0]["type"], "tool_result")
        self.assertEqual(tool_result_blocks[0]["tool_use_id"], "call_1")
        self.assertIn("candidate_asins", tool_result_blocks[0]["content"])

    def test_anthropic_tool_use_response_converts_to_openai_tool_calls(self) -> None:
        completion = anthropic_response_to_openai_chat_completion(
            {
                "id": "msg_1",
                "content": [
                    {"type": "text", "text": ""},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "asin_history_timeseries",
                        "input": {"asins": "B001", "marketplace": "US"},
                    },
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
            model="MiniMax-M2.7-highspeed",
        )

        message = completion["choices"][0]["message"]
        self.assertEqual(completion["choices"][0]["finish_reason"], "tool_calls")
        self.assertEqual(message["tool_calls"][0]["id"], "toolu_1")
        self.assertEqual(message["tool_calls"][0]["function"]["name"], "asin_history_timeseries")
        self.assertEqual(json.loads(message["tool_calls"][0]["function"]["arguments"])["asins"], "B001")

    def test_opportunity_discovery_tool_result_is_presentation_first(self) -> None:
        formatted = _format_theme_api_tool_result(
            "opportunity_discovery",
            {
                "success": True,
                "data": {
                    "opportunity_count": 1,
                    "opportunity_cards_text": "| 排名 | 机会主题 | 样本ASIN数 |\n| 1 | Golf Balls | 12 |\n\n### 字段解释\n- Offer 不是供应商数量。",
                    "opportunities_for_llm": [{"title": "Golf Balls", "candidate_count": 12, "row_count": 120}],
                    "metric_definitions": {"offer_count_avg": {"meaning": "Offer 不是供应商数量"}},
                    "diagnostics": {"window_days": 30},
                },
                "meta": {"endpoint": "/api/product-theme/opportunity-discovery"},
            },
        )

        payload = json.loads(formatted)
        self.assertIn("工具证据块", payload["instruction"])
        self.assertIn("不要改写成平铺列表", payload["instruction"])
        self.assertIn("样本ASIN数", payload["opportunity_cards_text"])
        self.assertEqual(payload["opportunities_for_llm"][0]["candidate_count"], 12)
        self.assertIn("Offer 不是供应商数量", json.dumps(payload["metric_definitions"], ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()