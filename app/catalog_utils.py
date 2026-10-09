"""Pure catalog transformations for TV3 UI. No database or Streamlit dependencies."""
from __future__ import annotations

from collections import Counter
from math import ceil
import unicodedata


def fold(text: object) -> str:
    """Case/diacritic-insensitive comparison while keeping original UI text intact."""
    value = unicodedata.normalize("NFD", str(text or "").casefold())
    return "".join(ch for ch in value if unicodedata.category(ch) != "Mn").replace("đ", "d").strip()


def category_label(doc: dict) -> str:
    return str(doc.get("category") or "Chưa phân loại")


def categories(docs: list[dict]) -> dict[str, int]:
    return dict(sorted(Counter(category_label(d) for d in docs).items(), key=lambda kv: (-kv[1], fold(kv[0]))))


def filter_catalog(
    docs: list[dict], query: str = "", category: str = "Tất cả", *,
    sort_by: str = "Mới nhất", search_in: str = "Tiêu đề",
) -> list[dict]:
    needle = fold(query)
    filtered: list[dict] = []
    for doc in docs:
        if category != "Tất cả" and category_label(doc) != category:
            continue
        fields = [doc.get("title", "")]
        if search_in == "Tiêu đề & nội dung đã xử lý":
            fields.append(doc.get("clean_text", ""))
        if needle and not any(needle in fold(part) for part in fields):
            continue
        filtered.append(doc)
    if sort_by == "Tiêu đề A-Z":
        return sorted(filtered, key=lambda d: (fold(d.get("title")), d.get("document_id", 0)))
    if sort_by == "Nhiều từ nhất":
        return sorted(filtered, key=lambda d: (-int(d.get("word_count") or 0), d.get("document_id", 0)))
    return sorted(filtered, key=lambda d: d.get("document_id", 0), reverse=True)


def page_slice(docs: list[dict], page: int, per_page: int) -> tuple[list[dict], int, int]:
    if per_page <= 0:
        raise ValueError("per_page must be positive")
    total_pages = max(1, ceil(len(docs) / per_page))
    safe_page = max(1, min(page, total_pages))
    start = (safe_page - 1) * per_page
    return docs[start : start + per_page], safe_page, total_pages
