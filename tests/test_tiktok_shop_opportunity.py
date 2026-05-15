from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from data_platform.chat_backend.api.models import InternalTikTokOpportunityRequest
from data_platform.chat_backend.domains.tiktok_shop_opportunity.normalizer import normalize_keywords, normalize_search_products
from data_platform.chat_backend.domains.tiktok_shop_opportunity.scoring import score_opportunity
from data_platform.chat_backend.domains.tiktok_shop_opportunity import service as tiktok_service
from data_platform.chat_backend.domains.tiktok_shop_opportunity.service import run_tiktok_opportunity
from data_platform.chat_backend.domains.tiktok_shop_opportunity.tikhub_client import TikHubCallResult, TikHubClient, TikHubConfig


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
            result = run_tiktok_opportunity({"query": "portable blender", "target_market": "US", "keywords": ["portable blender"], "limit": 5})

        self.assertEqual(result["provider"], "tikhub")
        self.assertEqual(result["capability"], "tiktok_opportunity")
        self.assertEqual(result["degradation"]["status"], "missing_credentials")
        self.assertEqual(result["evidence_level"], "insufficient")
        self.assertEqual(result["seller_fit"]["fit_level"], "unknown")
        self.assertIn("TikTok Shop 实时增强", result["result_text"])
        self.assertIn("中小卖家适配结论", result["result_text"])

    def test_tikhub_calls_use_openapi_query_parameters(self) -> None:
        calls = []

        class FakeTikHubClient:
            def __init__(self, config):
                self.config = config

            def get(self, endpoint, params):
                calls.append((endpoint, params))
                data_by_endpoint = {
                    tiktok_service.P0_HOT_PRODUCTS: {"data": {"products": [{"product_id": "hot-1", "shop_name": "Hot Shop"}]}},
                    tiktok_service.P0_SEARCH_SUGGESTIONS: {"data": ["portable blender"]},
                    tiktok_service.P1_TRENDING_SEARCHWORDS: {"data": ["portable blender"]},
                    tiktok_service.P0_SEARCH_PRODUCTS: {"data": {"products": [{"product_id": "p1", "shop_name": "Shop A"}]}},
                    tiktok_service.P0_PRODUCT_DETAIL: {"data": {"product": {"product_id": "p1", "shop_name": "Shop A"}}},
                    tiktok_service.P1_TRENDING_POST: {"data": [{"id": "v1", "play_count": 1000}]},
                    tiktok_service.P2_KEYWORD_INSIGHTS: {"data": []},
                    tiktok_service.P2_TOP_PRODUCTS: {"data": []},
                }
                return TikHubCallResult(endpoint=endpoint, params=params, ok=True, status_code=200, data=data_by_endpoint.get(endpoint, {}))

        env = {
            "THIRD_PARTY_MARKET_ENABLED": "true",
            "TIKTOK_OPPORTUNITY_ENABLED": "true",
            "TIKTOK_PROVIDER": "tikhub",
            "TIKTOK_API_KEY": "test-key",
            "TIKTOK_TOPN": "5",
            "TIKTOK_DETAIL_TOPK": "1",
            "TIKTOK_ENABLE_P1_CONTENT_HEAT": "true",
            "TIKTOK_ENABLE_P2_ADS": "true",
        }
        with patch.dict(os.environ, env, clear=False), patch.object(tiktok_service, "TikHubClient", FakeTikHubClient):
            result = run_tiktok_opportunity({"query": "portable blender", "target_market": "US", "keywords": ["portable blender"], "limit": 5})

        self.assertEqual(result["degradation"]["status"], "ok")
        self.assertEqual(result["evidence_level"], "strong")
        self.assertIn(result["seller_fit"]["fit_level"], {"caution", "good"})
        params_by_endpoint = {endpoint: params for endpoint, params in calls}
        self.assertEqual(params_by_endpoint[tiktok_service.P0_HOT_PRODUCTS], {"region": "US", "count": 5})
        self.assertEqual(params_by_endpoint[tiktok_service.P0_SEARCH_SUGGESTIONS], {"search_word": "portable blender", "lang": "en-US", "region": "US"})
        self.assertEqual(params_by_endpoint[tiktok_service.P0_SEARCH_PRODUCTS], {"search_word": "portable blender", "offset": 0, "region": "US"})
        self.assertEqual(params_by_endpoint[tiktok_service.P0_PRODUCT_DETAIL], {"product_id": "p1", "region": "US"})
        self.assertEqual(params_by_endpoint[tiktok_service.P1_TRENDING_SEARCHWORDS], {})
        self.assertEqual(params_by_endpoint[tiktok_service.P1_TRENDING_POST], {})
        self.assertEqual(params_by_endpoint[tiktok_service.P2_KEYWORD_INSIGHTS]["country_code"], "US")
        self.assertEqual(params_by_endpoint[tiktok_service.P2_TOP_PRODUCTS]["country_code"], "US")

    def test_product_search_retries_original_query_when_expanded_keyword_fails(self) -> None:
        calls = []

        class FakeTikHubClient:
            def __init__(self, config):
                self.config = config

            def get(self, endpoint, params):
                calls.append((endpoint, params))
                if endpoint == tiktok_service.P0_SEARCH_SUGGESTIONS:
                    return TikHubCallResult(endpoint=endpoint, params=params, ok=True, status_code=200, data={"data": ["bad expanded keyword"]})
                if endpoint == tiktok_service.P0_SEARCH_PRODUCTS and params["search_word"] == "bad expanded keyword":
                    return TikHubCallResult(endpoint=endpoint, params=params, ok=False, status_code=400, error="http_400")
                data_by_endpoint = {
                    tiktok_service.P0_HOT_PRODUCTS: {"data": {"products": [{"product_id": "hot-1", "shop_name": "Hot Shop"}]}},
                    tiktok_service.P1_TRENDING_SEARCHWORDS: {"data": []},
                    tiktok_service.P0_SEARCH_PRODUCTS: {"data": {"products": [{"product_id": "p1", "shop_name": "Shop A"}]}},
                    tiktok_service.P0_PRODUCT_DETAIL: {"data": {"product": {"product_id": "p1", "shop_name": "Shop A"}}},
                    tiktok_service.P1_TRENDING_POST: {"data": []},
                }
                return TikHubCallResult(endpoint=endpoint, params=params, ok=True, status_code=200, data=data_by_endpoint.get(endpoint, {}))

        env = {
            "THIRD_PARTY_MARKET_ENABLED": "true",
            "TIKTOK_OPPORTUNITY_ENABLED": "true",
            "TIKTOK_PROVIDER": "tikhub",
            "TIKTOK_API_KEY": "test-key",
            "TIKTOK_TOPN": "5",
            "TIKTOK_DETAIL_TOPK": "1",
            "TIKTOK_ENABLE_P1_CONTENT_HEAT": "true",
            "TIKTOK_ENABLE_P2_ADS": "false",
        }
        with patch.dict(os.environ, env, clear=False), patch.object(tiktok_service, "TikHubClient", FakeTikHubClient):
            result = run_tiktok_opportunity({"query": "portable blender", "target_market": "US", "keywords": ["portable blender"], "limit": 5})

        product_search_params = [params for endpoint, params in calls if endpoint == tiktok_service.P0_SEARCH_PRODUCTS]
        self.assertEqual(product_search_params[0]["search_word"], "bad expanded keyword")
        self.assertEqual(product_search_params[1]["search_word"], "portable blender")
        self.assertEqual(result["degradation"]["status"], "ok")
        self.assertEqual(result["signals"]["product_candidate_count"], 1)

    def test_agent_policy_skips_broad_query_before_network(self) -> None:
        class FailingTikHubClient:
            def __init__(self, config):
                self.config = config

            def get(self, endpoint, params):
                raise AssertionError("broad queries should not call TikHub")

        env = {
            "THIRD_PARTY_MARKET_ENABLED": "true",
            "TIKTOK_OPPORTUNITY_ENABLED": "true",
            "TIKTOK_PROVIDER": "tikhub",
            "TIKTOK_API_KEY": "test-key",
        }
        with patch.dict(os.environ, env, clear=False), patch.object(tiktok_service, "TikHubClient", FailingTikHubClient):
            result = run_tiktok_opportunity({"query": "beauty", "target_market": "US", "limit": 5})

        self.assertEqual(result["degradation"]["status"], "skipped")
        self.assertEqual(result["agent_tool_policy"]["action"], "skip_realtime")
        self.assertEqual(result["agent_tool_policy"]["reason"], "query_too_broad")
        self.assertEqual(result["source_meta"]["endpoint_count"], 0)

    def test_agent_policy_reuses_recent_snapshot_before_network(self) -> None:
        class FakeConn:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        cached = {
            "id": "snap-1",
            "status": "partial",
            "vendor_endpoints": [{"endpoint": tiktok_service.P1_TRENDING_SEARCHWORDS, "ok": True}],
            "vendor_response_raw": {tiktok_service.P1_TRENDING_SEARCHWORDS: {"data": []}},
            "normalized_summary": score_opportunity(
                query_terms=["portable blender"],
                expanded_keywords=[],
                trend_keywords=["portable blender"],
                hot_products=[],
                search_products=[],
                product_details=[],
                trending_posts=[],
                evidence_sources={"tiktok_web_trending_searchwords": True},
            ),
            "result_text": "cached result",
            "created_at": "2026-04-30T00:00:00Z",
        }
        env = {
            "THIRD_PARTY_MARKET_ENABLED": "true",
            "TIKTOK_OPPORTUNITY_ENABLED": "true",
            "TIKTOK_PROVIDER": "tikhub",
            "TIKTOK_API_KEY": "test-key",
        }
        with patch.dict(os.environ, env, clear=False), \
            patch.object(tiktok_service, "_postgres_conn", return_value=FakeConn()), \
            patch.object(tiktok_service, "fetch_recent_tiktok_realtime_query", return_value=cached) as fetch_cached, \
            patch.object(tiktok_service, "TikHubClient") as client_cls:
            result = run_tiktok_opportunity(
                {"report_run_id": "run-1", "query": "portable blender", "target_market": "US", "keywords": ["portable blender"], "limit": 5}
            )

        fetch_cached.assert_called_once()
        client_cls.assert_not_called()
        self.assertEqual(result["result_text"], "cached result")
        self.assertTrue(result["source_meta"]["cache_hit"])
        self.assertEqual(result["agent_tool_policy"]["action"], "reuse_cached")

    def test_shop_web_unavailable_uses_web_ads_fallback_conservatively(self) -> None:
        calls = []

        class FakeTikHubClient:
            def __init__(self, config):
                self.config = config

            def get(self, endpoint, params):
                calls.append(endpoint)
                if "/tiktok/shop/web/" in endpoint:
                    return TikHubCallResult(
                        endpoint=endpoint,
                        params=params,
                        ok=False,
                        status_code=400,
                        error="TikHub Shop Web bad request",
                        request_id="req_shop_400",
                        docs_url=tiktok_service.SHOP_WEB_DOCS_URL,
                    )
                data_by_endpoint = {
                    tiktok_service.P1_TRENDING_SEARCHWORDS: {"data": ["portable blender"]},
                    tiktok_service.P1_TRENDING_POST: {"data": [{"id": "v1", "play_count": 1000}]},
                    tiktok_service.P2_KEYWORD_INSIGHTS: {"data": {"competition_level": "medium"}},
                    tiktok_service.P2_TOP_PRODUCTS: {"data": {"products": [{"product_id": "ads-1", "title": "Portable blender"}]}},
                }
                return TikHubCallResult(endpoint=endpoint, params=params, ok=True, status_code=200, data=data_by_endpoint.get(endpoint, {}))

        env = {
            "THIRD_PARTY_MARKET_ENABLED": "true",
            "TIKTOK_OPPORTUNITY_ENABLED": "true",
            "TIKTOK_PROVIDER": "tikhub",
            "TIKTOK_API_KEY": "test-key",
            "TIKTOK_TOPN": "5",
            "TIKTOK_DETAIL_TOPK": "1",
            "TIKTOK_ENABLE_P1_CONTENT_HEAT": "true",
            "TIKTOK_ENABLE_P2_ADS": "true",
        }
        with patch.dict(os.environ, env, clear=False), patch.object(tiktok_service, "TikHubClient", FakeTikHubClient):
            result = run_tiktok_opportunity({"query": "portable blender", "target_market": "US", "keywords": ["portable blender"], "limit": 5})

        self.assertIn(tiktok_service.P2_TOP_PRODUCTS, calls)
        self.assertEqual(result["degradation"]["status"], "partial")
        self.assertEqual(result["evidence_level"], "medium")
        self.assertFalse(result["evidence_profile"]["shop_supply_verified"])
        self.assertEqual(result["agent_tool_policy"]["action"], "call_tikhub")
        self.assertEqual(result["agent_tool_policy"]["shop_web_replacement_mode"], "shop_web_search_products_v2")
        self.assertEqual(result["supplier_issue"]["issue_type"], "shop_web_endpoint_failure")

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

    def test_normalizer_extracts_tikhub_trending_search_words(self) -> None:
        keywords = normalize_keywords(
            {"data": {"data": {"trending_search_words": [{"trendingSearchWord": "portable blender"}, {"trendingSearchWord": "labubu"}]}}}
        )

        self.assertEqual(keywords, ["portable blender", "labubu"])

    def test_tikhub_client_follows_cache_url(self) -> None:
        class FakeResponse:
            def __init__(self, status_code, payload):
                self.status_code = status_code
                self._payload = payload

            def json(self):
                return self._payload

        class FakeSession:
            def __init__(self):
                self.urls = []

            def get(self, url, **kwargs):
                self.urls.append(url)
                if url == "https://cache.tikhub.test/result":
                    return FakeResponse(200, {"data": {"data": {"trending_search_words": [{"trendingSearchWord": "portable blender"}]}}})
                return FakeResponse(200, {"code": 200, "cache_url": "https://cache.tikhub.test/result"})

        client = TikHubClient(
            config=TikHubConfig(
                enabled=True,
                provider="tikhub",
                base_url="https://api.tikhub.test",
                api_key="test-key",
                target_region="US",
                timeout_seconds=30,
                max_retries=0,
                topn=5,
                detail_topk=1,
                enable_p1_content_heat=True,
                enable_p2_ads=False,
            ),
            session=FakeSession(),
        )

        result = client.get("/api/v1/tiktok/web/fetch_trending_searchwords", {})

        self.assertTrue(result.ok)
        self.assertEqual(normalize_keywords(result.data or {}), ["portable blender"])

    def test_tikhub_client_captures_error_metadata(self) -> None:
        class FakeResponse:
            status_code = 400

            def json(self):
                return {"request_id": "req_123", "docs": "https://api.tikhub.io/#/TikTok-Shop-Web-API", "message": "bad request"}

        class FakeSession:
            def get(self, url, **kwargs):
                return FakeResponse()

        client = TikHubClient(
            config=TikHubConfig(
                enabled=True,
                provider="tikhub",
                base_url="https://api.tikhub.test",
                api_key="test-key",
                target_region="US",
                timeout_seconds=30,
                max_retries=0,
                topn=5,
                detail_topk=1,
                enable_p1_content_heat=True,
                enable_p2_ads=False,
            ),
            session=FakeSession(),
        )

        result = client.get(tiktok_service.P0_HOT_PRODUCTS, {"region": "US", "count": 5})

        self.assertFalse(result.ok)
        self.assertEqual(result.request_id, "req_123")
        self.assertEqual(result.docs_url, "https://api.tikhub.io/#/TikTok-Shop-Web-API")
        self.assertEqual(result.error_payload["message"], "bad request")

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
        self.assertEqual(scored["evidence_profile"]["level"], "strong")
        self.assertIn(scored["seller_fit"]["fit_level"], {"caution", "good"})

    def test_evidence_profile_distinguishes_medium_and_weak_layers(self) -> None:
        ads_only = score_opportunity(
            query_terms=["portable blender"],
            expanded_keywords=[],
            trend_keywords=[],
            hot_products=[{"title": "Portable blender"}],
            search_products=[],
            product_details=[],
            trending_posts=[],
            evidence_sources={"tiktok_ads_top_products": True},
        )
        web_only = score_opportunity(
            query_terms=["portable blender"],
            expanded_keywords=[],
            trend_keywords=["portable blender"],
            hot_products=[],
            search_products=[],
            product_details=[],
            trending_posts=[],
            evidence_sources={"tiktok_web_trending_searchwords": True},
        )

        self.assertEqual(ads_only["evidence_profile"]["level"], "medium")
        self.assertFalse(ads_only["evidence_profile"]["shop_supply_verified"])
        self.assertEqual(web_only["evidence_profile"]["level"], "weak")

    def test_seller_fit_downgrades_ads_only_shop_missing_evidence(self) -> None:
        scored = score_opportunity(
            query_terms=["portable blender"],
            expanded_keywords=[],
            trend_keywords=["portable blender", "mini blender"],
            hot_products=[{"title": "Portable blender"} for _ in range(5)],
            search_products=[],
            product_details=[],
            trending_posts=[],
            ads_keyword_insights={"competition_level": "high"},
        )

        self.assertNotEqual(scored["summary"]["opportunity_level"], "high")
        self.assertIn("shop_evidence_missing", scored["seller_fit"]["risk_flags"])
        self.assertIn("ad_cost_risk", scored["seller_fit"]["risk_flags"])
        self.assertNotEqual(scored["seller_fit"]["fit_level"], "good")

    def test_seller_fit_flags_ip_and_compliance_risks(self) -> None:
        scored = score_opportunity(
            query_terms=["labubu baby toy"],
            expanded_keywords=["labubu baby toy"],
            trend_keywords=["labubu"],
            hot_products=[],
            search_products=[{"title": "Labubu baby toy", "shop_name": "A"}],
            product_details=[{"product_id": "p1", "title": "Labubu baby toy"}],
            trending_posts=[],
        )

        self.assertIn("ip_sensitive", scored["seller_fit"]["risk_flags"])
        self.assertIn("compliance_risk", scored["seller_fit"]["risk_flags"])
        self.assertEqual(scored["seller_fit"]["recommended_action"], "avoid_or_research")


if __name__ == "__main__":
    unittest.main()