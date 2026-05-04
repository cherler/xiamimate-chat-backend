"""Billing package catalog helpers for the billing domain."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

try:
	import psycopg2.extras
except ImportError:
	pass

from data_platform.chat_backend.infra.settings import DEFAULT_BILLING_PACKAGES
from data_platform.chat_backend.infra.postgres import _fetch_optional_one, _run_pg_dict_query


_LEGACY_BILLING_PACKAGE_CODES = (
	"credit_pack_s",
	"credit_pack_m",
	"credit_pack_l",
	"monthly_basic",
)


def _seed_billing_packages(conn) -> None:
	for package in DEFAULT_BILLING_PACKAGES:
		_run_pg_dict_query(
			conn,
			"""
			INSERT INTO app.billing_package (
				package_code, package_name, product_type, price_cents, points_amount,
				period_days, status, display_order, meta_json, created_at, updated_at
			) VALUES (%s, %s, %s, %s, %s, %s, 'active', %s, %s, NOW(), NOW())
			ON CONFLICT (package_code) DO UPDATE SET
				package_name = EXCLUDED.package_name,
				product_type = EXCLUDED.product_type,
				price_cents = EXCLUDED.price_cents,
				points_amount = EXCLUDED.points_amount,
				period_days = EXCLUDED.period_days,
				status = 'active',
				display_order = EXCLUDED.display_order,
				meta_json = EXCLUDED.meta_json,
				updated_at = NOW()
			RETURNING package_code
			""",
			[
				package["package_code"],
				package["package_name"],
				package["product_type"],
				package["price_cents"],
				package["points_amount"],
				package["period_days"],
				package["display_order"],
				psycopg2.extras.Json(package.get("meta_json") or {}),
			],
		)
	_run_pg_dict_query(
		conn,
		"""
		UPDATE app.billing_package
		SET status = 'disabled',
			updated_at = NOW()
		WHERE package_code = ANY(%s)
		RETURNING package_code
		""",
		[list(_LEGACY_BILLING_PACKAGE_CODES)],
	)


def _fetch_billing_package(conn, package_code: str) -> dict[str, Any]:
	row = _fetch_optional_one(
		conn,
		"""
		SELECT package_code, package_name, product_type, price_cents, points_amount,
			   period_days, status, display_order, meta_json, created_at, updated_at
		FROM app.billing_package
		WHERE package_code = %s
		LIMIT 1
		""",
		[package_code],
	)
	if row is None:
		raise HTTPException(status_code=404, detail=f"billing package not found: {package_code}")
	if row["status"] != "active":
		raise HTTPException(status_code=409, detail=f"billing package is not active: {package_code}")
	return row


def _list_billing_packages(conn) -> list[dict[str, Any]]:
	return _run_pg_dict_query(
		conn,
		"""
		SELECT package_code, package_name, product_type, price_cents, points_amount,
			   period_days, status, display_order, meta_json, created_at, updated_at
		FROM app.billing_package
		WHERE status = 'active'
		ORDER BY display_order ASC, created_at ASC, package_code ASC
		""",
	)
