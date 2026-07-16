"""Smart Loki product detection from CSV content."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from csv_reader.config import AppConfig, LokiProduct
from csv_reader.reader import CsvData


@dataclass
class DetectionResult:
    product: LokiProduct | None
    score: float
    confidence: str
    reason: str

    @property
    def is_confident(self) -> bool:
        return self.product is not None and self.score >= 0.5


def _norm(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _csv_product_name(data: CsvData, row: list[str] | None = None) -> str:
    row = row or (data.rows[0] if data.rows else [])
    headers_lower = [h.strip().lower() for h in data.headers]
    for key in ("product name", "variant name", "product code"):
        if key in headers_lower:
            idx = headers_lower.index(key)
            if idx < len(row) and row[idx].strip():
                return row[idx].strip()
    return ""


def _csv_product_code(data: CsvData, row: list[str] | None = None) -> str:
    row = row or (data.rows[0] if data.rows else [])
    headers_lower = [h.strip().lower() for h in data.headers]
    for key in ("product code", "variant code"):
        if key in headers_lower:
            idx = headers_lower.index(key)
            if idx < len(row) and row[idx].strip():
                return row[idx].strip()
    return ""


def _match_name(name: str, product: LokiProduct) -> float:
    if not name:
        return 0.0
    nl = _norm(name)
    pl = _norm(product.name)
    if nl == pl:
        return 1.0
    if pl in nl or nl in pl:
        return 0.85
    for sp in product.sp_product:
        sl = _norm(sp)
        if nl == sl or sl in nl or nl in sl:
            return 0.9
    return 0.0


def detect_product(
    data: CsvData,
    config: AppConfig,
    *,
    filename: str | Path | None = None,
) -> DetectionResult:
    fname = Path(filename or data.path.name).name.lower()
    prod_name = _csv_product_name(data)
    prod_code = _csv_product_code(data)

    best: LokiProduct | None = None
    best_score = 0.0
    best_reason = ""

    for product in config.products:
        score = 0.0
        reasons: list[str] = []

        name_score = _match_name(prod_name, product)
        if name_score:
            score = max(score, name_score)
            reasons.append(f"tên: {prod_name}")

        if prod_code and prod_code.upper() in [c.upper() for c in product.product_codes]:
            score = max(score, 0.95)
            reasons.append(f"mã: {prod_code}")

        key_compact = product.id.replace("-", "")
        if key_compact and key_compact in fname.replace("-", "").replace("_", ""):
            score = max(score, 0.4)
            reasons.append("tên file")

        if product.name.lower().replace(" ", "") in fname.replace("-", "").replace("_", ""):
            score = max(score, 0.55)
            reasons.append("tên file")

        # Ưu tiên sweatshirt vs sweatpants theo tên sản phẩm
        if prod_name and "sweatshirt" in _norm(prod_name):
            if product.id == "glitter-and-pet-sweatshirt":
                score += 0.05
            elif product.id == "glitter-and-pet-sweatpants":
                score -= 0.1

        if score > best_score:
            best_score = score
            best = product
            best_reason = ", ".join(reasons)

    if best is None or best_score < 0.35:
        return DetectionResult(None, best_score, "không xác định", "Không khớp sản phẩm")

    best_score = min(best_score, 1.0)
    confidence = "cao" if best_score >= 0.8 else "trung bình" if best_score >= 0.55 else "thấp"
    return DetectionResult(best, round(best_score, 2), confidence, best_reason)