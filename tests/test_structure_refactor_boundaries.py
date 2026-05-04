from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_repo_file(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class StructureRefactorBoundaryTests(unittest.TestCase):
    def test_app_uses_router_aggregators(self) -> None:
        source = read_repo_file("data_platform/chat_backend/app.py")

        self.assertIn("data_platform.chat_backend.api.internal.router", source)
        self.assertIn("data_platform.chat_backend.api.portal.router", source)
        self.assertNotIn("data_platform.chat_backend.api.internal_routes import router as internal_router", source)
        self.assertNotIn("data_platform.chat_backend.api.portal_routes import router as portal_router", source)

    def test_service_script_uses_new_app_entrypoint(self) -> None:
        source = read_repo_file("scripts/manage_chat_backend.sh")

        self.assertIn('APP_ENTRYPOINT="data_platform.chat_backend.app:app"', source)
        self.assertIn("data_platform.chat_backend.app:app", source)
        self.assertIn('"$PYTHON_BIN" -m uvicorn "$APP_ENTRYPOINT"', source)
        self.assertIn('--app-dir "$ROOT_DIR"', source)
        self.assertNotIn("uvicorn data_platform.api.chat_backend:app", source)

    def test_tiktok_native_tool_route_is_registered_in_new_tool_router(self) -> None:
        from data_platform.chat_backend.app import app

        paths = [route.path for route in app.routes if hasattr(route, "methods")]
        self.assertIn("/internal/provider/external-market/tiktok/opportunity", paths)

    def test_onebound_1688_supplier_route_is_registered_in_new_tool_router(self) -> None:
        from data_platform.chat_backend.app import app

        paths = [route.path for route in app.routes if hasattr(route, "methods")]
        self.assertIn("/internal/provider/sourcing/1688/supplier-discovery", paths)

    def test_legacy_internal_routes_no_longer_owns_provider_proxy_routes(self) -> None:
        source = read_repo_file("data_platform/chat_backend/api/internal_routes.py")

        self.assertNotIn('@router.post("/internal/provider/', source)
        self.assertNotIn("domains.provider_proxy.service", source)

    def test_billing_facade_delegates_extracted_helpers(self) -> None:
        from data_platform.chat_backend.domains.billing import service

        self.assertEqual(service._seed_billing_packages.__module__, "data_platform.chat_backend.domains.billing.catalog")
        self.assertEqual(service._fetch_billing_package.__module__, "data_platform.chat_backend.domains.billing.catalog")
        self.assertEqual(service._list_billing_packages.__module__, "data_platform.chat_backend.domains.billing.catalog")
        self.assertEqual(service._fetch_daily_credit_quota_state.__module__, "data_platform.chat_backend.domains.billing.quotas")
        self.assertEqual(service._is_guest_daily_quota_user.__module__, "data_platform.chat_backend.domains.billing.quotas")
        self.assertEqual(service._normalize_redeem_code.__module__, "data_platform.chat_backend.domains.billing.redeem_codes")

    def test_new_tiktok_provider_code_must_not_land_in_legacy_files(self) -> None:
        legacy_files = [
            "data_platform/chat_backend/api/internal_routes.py",
            "data_platform/chat_backend/api/portal_routes.py",
            "data_platform/chat_backend/domains/billing/service.py",
        ]

        for relative_path in legacy_files:
            source = read_repo_file(relative_path).lower()
            self.assertNotIn("tikhub", source, relative_path)
            self.assertNotIn("tiktok_shop_opportunity", source, relative_path)

    def test_onebound_provider_code_must_not_land_in_legacy_files(self) -> None:
        legacy_files = [
            "data_platform/chat_backend/api/internal_routes.py",
            "data_platform/chat_backend/api/portal_routes.py",
            "data_platform/chat_backend/domains/billing/service.py",
        ]

        for relative_path in legacy_files:
            source = read_repo_file(relative_path).lower()
            self.assertNotIn("onebound_1688", source, relative_path)
            self.assertNotIn("supplier-discovery", source, relative_path)


if __name__ == "__main__":
    unittest.main()