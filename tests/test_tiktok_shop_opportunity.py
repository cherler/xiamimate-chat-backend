from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from data_platform.chat_backend.api.models import InternalTikTokOpportunityRequest
from data_platform.chat_backend.domains.tiktok_shop_opportunity.normalizer import normalize_keywords, normalize_search_products
from data_platform.chat_backend.domains.tiktok_shop_opportunity.scoring import score_opportunity
from data_platform.chat_backend.domains.tiktok_shop_opportunity.service import run_tiktok_opportunity


class TikTokShopOpportunityTests(unittest.TestCase):
    def test_request_model_normalizes_market_and_keywords(self) -> None:
        payload = InternalTikTokOpportunityRequest(
            query="portable blender",
            target_market="us",
            keywords="portable blender, personal blender, portable blender",
        )

        self.assertEqual(payload.target_market, "US")
        self.assertEqual(payload.keywords, ["portable blender", "personal blender"])

    def test_missing_credentials_degrades_without_network_or_database(self) -> None:
        env = {
            "THIRD_PARTY_MARKET_ENABLED": "true",
            "TIKTOK_OPPORTUNITY_ENABLED": "true",
            "TIKTOK_PROVIDER": "tikhub",
            "TIKTOK_API_KEY": "",
        }
        with patch.dict(os.environ, env, clear=False):
            result = run_tiktok_opportunity({"query": "portable blender", "target_market": "US", "limit": 5})

        self.assertEqual(result["provider"], "tikhub")
        self.assertEqual(result["capability"], "tiktok_opportunity")
        self.assertEqual(result["degradation"]["status"], "missing_credentials")
        self.assertIn("TikTok Shop 实时增强", result["result_text"])

    def test_normalizer_extracts_keywords_and_products_from_nested_payload(self) -> None:
        keywords = normalize_keywords({"data": {"suggestions": [{"word": "portable blender"}, {"keyword": "mini blender"}]}})
        products = normalize_search_products(
            {
                "data": {
                    "products": [
                        {"product_id": "p1", "title": "Mini Blender", "shop_name": "Shop A", "sold_count": 120},
                    ]
                }
            }
        )

        self.assertEqual(keywords, ["portable blender", "mini blender"])
        self.assertEqual(products[0]["product_id"], "p1")
        self.assertEqual(products[0]["shop_name"], "Shop A")

    def test_scoring_returns_directional_summary(self) -> None:
        scored = score_opportunity(
            query_terms=["portable blender"],
            expanded_keywords=["portable blender", "mini blender"],
            trend_keywords=["portable blender"],
            hot_products=[{"shop_name": "A"}, {"shop_name": "B"}],
            search_products=[{"shop_name": "A"}, {"shop_name": "B"}, {"shop_name": "C"}],
            product_details=[{"product_id": "p1"}],
            trending_posts=[{"post_id": "v1"}, {"post_id": "v2"}],
        )

        self.assertIn(scored["summary"]["opportunity_level"], {"low", "medium", "high"})
        self.assertGreater(scored["summary"]["confidence"], 0)
        self.assertEqual(scored["signals"]["brand_concentration_hint"], "medium")


if __name__ == "__main__":
    unittest.main()