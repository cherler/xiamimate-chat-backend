"""Normalize TikHub raw payloads into compact opportunity inputs."""
from __future__ import annotations

from typing import Any


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _recursive_find_first_list(value: Any, candidate_keys: set[str]) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return []
    for key, child in value.items():
        if key in candidate_keys and isinstance(child, list):
            return child
    for child in value.values():
        found = _recursive_find_first_list(child, candidate_keys)
        if found:
            return found
    return []


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
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _normalize_product(item: Any) -> dict[str, Any]:
    source = _as_dict(item)
    product_id = _first_text(source, ("product_id", "productId", "id", "item_id", "itemId"))
    title = _first_text(source, ("title", "product_title", "name", "productName", "url_title"))
    shop_name = _first_text(source, ("shop_name", "shopName", "seller_name", "sellerName", "brand", "brand_name"))
    price = _first_number(source, ("price", "sale_price", "min_price", "current_price"))
    sold_count = _first_number(source, ("sold_count", "sales", "sold", "total_sales", "orders"))
    rating = _first_number(source, ("rating", "score", "review_score"))
    review_count = _first_number(source, ("review_count", "reviews", "comment_count", "comments"))
    return {
        "product_id": product_id,
        "title": title,
        "shop_name": shop_name,
        "price": price,
        "sold_count": sold_count,
        "rating": rating,
        "review_count": review_count,
        "raw_keys": sorted(source.keys())[:30],
    }


def normalize_hot_products(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = _recursive_find_first_list(payload, {"products", "product_list", "items", "list", "data"})
    return [_normalize_product(item) for item in _as_list(items)]


def normalize_search_products(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = _recursive_find_first_list(payload, {"products", "product_list", "items", "list", "data"})
    return [_normalize_product(item) for item in _as_list(items)]


def normalize_product_detail(payload: dict[str, Any]) -> dict[str, Any]:
    data = _as_dict(payload.get("data")) or payload
    if isinstance(data.get("product"), dict):
        data = data["product"]
    return _normalize_product(data)


def normalize_keywords(payload: dict[str, Any]) -> list[str]:
    items = _recursive_find_first_list(
        payload,
        {"keywords", "words", "suggestions", "trending_search_words", "trendingSearchWords", "list", "data"},
    )
    keywords: list[str] = []
    for item in _as_list(items):
        if isinstance(item, str):
            text = item.strip()
        else:
            text = _first_text(_as_dict(item), ("keyword", "word", "query", "text", "name", "search_word", "trendingSearchWord"))
        if text and text not in keywords:
            keywords.append(text)
    return keywords


def normalize_trending_posts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = _recursive_find_first_list(
        payload,
        {"posts", "videos", "items", "item_list", "aweme_list", "video_list", "trending_posts", "list", "data"},
    )
    posts: list[dict[str, Any]] = []
    for item in _as_list(items):
        source = _as_dict(item)
        posts.append(
            {
                "post_id": _first_text(source, ("post_id", "video_id", "id", "aweme_id")),
                "title": _first_text(source, ("title", "desc", "description")),
                "view_count": _first_number(source, ("view_count", "views", "play_count", "playCount")),
                "like_count": _first_number(source, ("like_count", "likes", "digg_count", "diggCount")),
                "comment_count": _first_number(source, ("comment_count", "comments", "commentCount")),
            }
        )
    return posts
