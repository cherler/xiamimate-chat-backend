from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from data_platform.chat_backend.api.models import InternalOnebound1688SupplierDiscoveryRequest
from data_platform.chat_backend.domains.onebound_1688_sourcing import service as onebound_service
from data_platform.chat_backend.domains.onebound_1688_sourcing.client import Onebound1688CallResult
from data_platform.chat_backend.domains.onebound_1688_sourcing.normalizer import normalize_item_detail, normalize_search_items, normalize_seller_info
from data_platform.chat_backend.domains.onebound_1688_sourcing.service import run_onebound_1688_supplier_discovery


class Onebound1688SourcingTests(unittest.TestCase):
    def test_request_model_normalizes_market_and_supplier_queries(self) -> None:
        payload = InternalOnebound1688SupplierDiscoveryRequest(
            query="portable blender",
            marketplace="us",
            supplier_queries="便携式榨汁机, 榨汁杯, 便携式榨汁机",
        )

        self.assertEqual(payload.marketplace, "US")
        self.assertEqual(payload.supplier_queries, ["便携式榨汁机", "榨汁杯"])

    def test_missing_credentials_degrades_without_network_or_database(self) -> None:
        class FailingClient:
            def __init__(self, config):
                self.config = config

            def get(self, endpoint, params):
                raise AssertionError("missing credentials should not call Onebound")

        env = {
            "ONEBOUND_1688_ENABLED": "true",
            "ONEBOUND_API_KEY": "",
            "ONEBOUND_API_SECRET": "",
        }
        with patch.dict(os.environ, env, clear=False), patch.object(onebound_service, "Onebound1688Client", FailingClient):
            result = run_onebound_1688_supplier_discovery({"query": "portable blender", "marketplace": "US", "limit": 5})

        self.assertEqual(result["provider"], "onebound")
        self.assertEqual(result["capability"], "onebound_1688_supplier_discovery")
        self.assertEqual(result["degradation"]["status"], "missing_credentials")
        self.assertEqual(result["source_meta"]["endpoint_count"], 0)
        self.assertEqual(result["agent_tool_policy"]["action"], "call_onebound_1688")
        self.assertIn("1688 供应商发现结果", result["result_text"])

    def test_agent_policy_skips_broad_query_before_network(self) -> None:
        class FailingClient:
            def __init__(self, config):
                self.config = config

            def get(self, endpoint, params):
                raise AssertionError("broad queries should not call Onebound")

        env = {
            "ONEBOUND_1688_ENABLED": "true",
            "ONEBOUND_API_KEY": "test-key",
            "ONEBOUND_API_SECRET": "test-secret",
        }
        with patch.dict(os.environ, env, clear=False), patch.object(onebound_service, "Onebound1688Client", FailingClient):
            result = run_onebound_1688_supplier_discovery({"query": "beauty", "marketplace": "US", "limit": 5})

        self.assertEqual(result["degradation"]["status"], "skipped")
        self.assertEqual(result["agent_tool_policy"]["action"], "skip_realtime")
        self.assertEqual(result["agent_tool_policy"]["reason"], "query_too_broad")

    def test_onebound_calls_use_p0_endpoints_and_redacted_params(self) -> None:
        calls = []

        class FakeOneboundClient:
            def __init__(self, config):
                self.config = config

            def get(self, api_name, params):
                calls.append((api_name, params))
                if api_name == "item_search":
                    return Onebound1688CallResult(
                        api_name=api_name,
                        endpoint="/1688/item_search/",
                        params=params,
                        ok=True,
                        status_code=200,
                        data={
                            "code": "0000",
                            "items": [
                                {
                                    "num_iid": "offer-1",
                                    "title": "便携式榨汁杯",
                                    "price": "18.8",
                                    "sales": "320",
                                    "seller_id": "seller-1",
                                    "shop_name": "源头工厂A",
                                    "detail_url": "https://detail.1688.com/offer/offer-1.html",
                                }
                            ],
                        },
                    )
                if api_name == "item_get":
                    return Onebound1688CallResult(
                        api_name=api_name,
                        endpoint="/1688/item_get/",
                        params=params,
                        ok=True,
                        status_code=200,
                        data={
                            "code": "0000",
                            "item": {
                                "num_iid": "offer-1",
                                "title": "便携式榨汁杯",
                                "price": "18.8",
                                "batch_price": [{"beginAmount": "2", "price": "18.8"}],
                                "sales_data": "320",
                                "seller_id": "seller-1",
                            },
                        },
                    )
                if api_name == "seller_info":
                    return Onebound1688CallResult(
                        api_name=api_name,
                        endpoint="/1688/seller_info/",
                        params=params,
                        ok=True,
                        status_code=200,
                        data={
                            "code": "0000",
                            "seller_info": {
                                "sid": "seller-1",
                                "shop_name": "源头工厂A",
                                "company": "深圳源头工厂有限公司",
                                "tpservice_year": "6",
                                "fh_score": "4.8",
                                "hm_score": "4.7",
                                "xy_score": "4.9",
                                "ht_score": "4.6",
                            },
                        },
                    )
                raise AssertionError(f"unexpected api: {api_name}")

        env = {
            "ONEBOUND_1688_ENABLED": "true",
            "ONEBOUND_API_KEY": "test-key",
            "ONEBOUND_API_SECRET": "test-secret",
            "ONEBOUND_1688_ITEM_SEARCH_PAGE_SIZE": "5",
            "ONEBOUND_1688_MAX_ITEM_GET": "1",
            "ONEBOUND_1688_MAX_SELLER_INFO": "1",
        }
        with patch.dict(os.environ, env, clear=False), patch.object(onebound_service, "Onebound1688Client", FakeOneboundClient):
            result = run_onebound_1688_supplier_discovery(
                {"query": "portable blender", "marketplace": "US", "supplier_queries": ["便携式榨汁机"], "limit": 5}
            )

        self.assertEqual(result["degradation"]["status"], "ok")
        self.assertEqual([api_name for api_name, _ in calls], ["item_search", "item_get", "seller_info"])
        self.assertEqual(calls[0][1]["q"], "便携式榨汁机")
        self.assertEqual(calls[1][1], {"num_iid": "offer-1", "sales_data": 1})
        self.assertEqual(calls[2][1], {"sid": "seller-1"})
        self.assertEqual(result["signals"]["offer_count"], 1)
        self.assertGreater(result["summary"]["supplier_score"], 0)
        self.assertNotIn("key", result["vendor_endpoints"][0]["params"])
        self.assertNotIn("secret", result["vendor_endpoints"][0]["params"])

    def test_normalizer_extracts_search_detail_and_seller_info(self) -> None:
        offers = normalize_search_items(
            {"items": [{"num_iid": "1", "title": "榨汁杯", "price": "12.5", "sales": "20", "seller_id": "s1"}]},
            supplier_query="榨汁杯",
        )
        detail = normalize_item_detail(
            {"item": {"num_iid": "1", "batch_price": [{"beginAmount": "3", "price": "11.8"}], "sales_data": "30"}},
            supplier_query="榨汁杯",
        )
        seller = normalize_seller_info({"seller_info": {"sid": "s1", "shop_name": "工厂店", "fh_score": "4.8"}})

        self.assertEqual(offers[0]["num_iid"], "1")
        self.assertEqual(offers[0]["price_cny"], 12.5)
        self.assertEqual(detail["moq"], 3)
        self.assertEqual(detail["sales_30d"], 30)
        self.assertEqual(seller["seller_id"], "s1")
        self.assertEqual(seller["scores"]["fh_score"], 4.8)


if __name__ == "__main__":
    unittest.main()