"""Normalize Onebound 1688 payloads into supplier offer records."""
from __future__ import annotations

import re
from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_text(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _first_number(item: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = item.get(key)
        number = _to_float(value)
        if number is not None:
            return number
    return None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    return int(number) if number is not None else None


def _recursive_find_first_list(value: Any, candidate_keys: set[str]) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return []
    for key, child in value.items():
        if key in candidate_keys and isinstance(child, list):
            return child
        if key in candidate_keys and isinstance(child, dict):
            for nested_key in ("item", "items", "list", "data"):
                nested = child.get(nested_key)
                if isinstance(nested, list):
                    return nested
    for child in value.values():
        found = _recursive_find_first_list(child, candidate_keys)
        if found:
            return found
    return []


def _recursive_find_first_dict(value: Any, candidate_keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    for key, child in value.items():
        if key in candidate_keys and isinstance(child, dict):
            return child
    for child in value.values():
        if isinstance(child, dict):
            found = _recursive_find_first_dict(child, candidate_keys)
            if found:
                return found
        elif isinstance(child, list):
            for item in child:
                found = _recursive_find_first_dict(item, candidate_keys)
                if found:
                    return found
    return {}


def _normalize_batch_price(value: Any) -> list[dict[str, Any]]:
    entries = _as_list(value)
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        item = _as_dict(entry)
        if not item:
            continue
        price = _first_number(item, ("price", "discountPrice", "batchPrice", "value"))
        start_quantity = _to_int(_first_text(item, ("beginAmount", "startQuantity", "quantity", "num", "amount")))
        normalized.append({"price_cny": price, "start_quantity": start_quantity, "raw": item})
    return normalized


def _infer_moq(source: dict[str, Any], batch_price: list[dict[str, Any]]) -> int | None:
    for key in ("moq", "min_num", "minOrderQuantity", "min_order_quantity", "minQuantity", "beginAmount"):
        value = _to_int(source.get(key))
        if value is not None:
            return value
    quantities = [item.get("start_quantity") for item in batch_price if item.get("start_quantity") is not None]
    return min(quantities) if quantities else None


def normalize_search_items(payload: dict[str, Any], *, supplier_query: str) -> list[dict[str, Any]]:
    items = _recursive_find_first_list(payload, {"item", "items", "list", "data", "results"})
    offers: list[dict[str, Any]] = []
    for raw in _as_list(items):
        source = _as_dict(raw)
        if not source:
            continue
        offers.append(_normalize_offer_base(source, supplier_query=supplier_query, raw_source="item_search"))
    return offers


def normalize_item_detail(payload: dict[str, Any], *, supplier_query: str) -> dict[str, Any]:
    source = _recursive_find_first_dict(payload, {"item", "data", "product"}) or payload
    offer = _normalize_offer_base(source, supplier_query=supplier_query, raw_source="item_get")
    batch_price = _normalize_batch_price(source.get("batch_price") or source.get("priceRange") or source.get("priceRangeOriginal"))
    offer.update(
        {
            "desc_short": _first_text(source, ("desc_short", "subtitle", "sub_title")),
            "batch_price": batch_price,
            "moq": _infer_moq(source, batch_price),
            "sales_30d": _to_int(source.get("sales_data") or source.get("sales") or source.get("monthSales")),
            "sku_count": len(_as_list(_as_dict(source.get("skus")).get("sku"))),
            "raw_keys": sorted(source.keys())[:40],
        }
    )
    seller_info = _as_dict(source.get("seller_info"))
    if seller_info:
        offer["seller_id"] = offer.get("seller_id") or _first_text(seller_info, ("seller_id", "sid", "nick"))
        offer["shop_name"] = offer.get("shop_name") or _first_text(seller_info, ("shop_name", "title", "nick", "name"))
    return offer


def normalize_seller_info(payload: dict[str, Any]) -> dict[str, Any]:
    source = _recursive_find_first_dict(payload, {"seller", "seller_info", "shop", "data", "item"}) or payload
    return {
        "seller_id": _first_text(source, ("sid", "seller_id", "sellerId", "nick")),
        "shop_id": _first_text(source, ("shop_id", "shopId", "company_id")),
        "shop_name": _first_text(source, ("shop_name", "title", "nick", "company_dj", "company", "name")),
        "company_name": _first_text(source, ("company_dj", "company", "company_name", "name")),
        "tpservice_year": _to_int(source.get("tpservice_year") or source.get("credit_year") or source.get("tp_year")),
        "scores": {
            "fh_score": _to_float(source.get("fh_score")),
            "hm_score": _to_float(source.get("hm_score")),
            "xy_score": _to_float(source.get("xy_score")),
            "ht_score": _to_float(source.get("ht_score")),
            "qe_score": _to_float(source.get("qe_score")),
        },
        "raw_keys": sorted(source.keys())[:40],
    }


def merge_offer_detail(base: dict[str, Any], detail: dict[str, Any] | None, seller: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    if detail:
        for key, value in detail.items():
            if value not in (None, "", [], {}):
                merged[key] = value
    if seller:
        merged["seller_info"] = seller
        merged["seller_id"] = merged.get("seller_id") or seller.get("seller_id")
        merged["shop_id"] = merged.get("shop_id") or seller.get("shop_id")
        merged["shop_name"] = merged.get("shop_name") or seller.get("shop_name")
    return merged


def _normalize_offer_base(source: dict[str, Any], *, supplier_query: str, raw_source: str) -> dict[str, Any]:
    price = _first_number(source, ("price", "sale_price", "current_price", "orginal_price", "total_price"))
    sales = _to_int(source.get("sales") or source.get("sold") or source.get("sale_count") or source.get("month_sales"))
    image_url = _first_text(source, ("pic_url", "image", "image_url", "img", "pic"))
    return {
        "supplier_query": supplier_query,
        "num_iid": _first_text(source, ("num_iid", "item_id", "itemId", "offer_id", "id")),
        "title": _first_text(source, ("title", "name", "subject", "offer_title")),
        "detail_url": _first_text(source, ("detail_url", "url", "item_url", "link")),
        "image_url": image_url,
        "pic_url": image_url,
        "price_cny": price,
        "price_cny_min": price,
        "price_cny_max": price,
        "moq": _to_int(source.get("moq") or source.get("min_num") or source.get("beginAmount")),
        "sales_30d": sales,
        "seller_id": _first_text(source, ("seller_id", "sellerId", "sid", "memberId", "seller_nick")),
        "shop_id": _first_text(source, ("shop_id", "shopId")),
        "shop_name": _first_text(source, ("shop_name", "seller_nick", "nick", "company", "seller_name")),
        "batch_price": [],
        "raw_source": raw_source,
        "raw_keys": sorted(source.keys())[:40],
    }
