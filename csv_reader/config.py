"""Loki product configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parent / "products_config.json"
LOKI_PRODUCTS_PATH = Path(__file__).resolve().parent / "loki_products.json"
LOKI_RAW_PATH = Path(__file__).resolve().parent / "loki_products_raw.json"

NOTE_FIXES = {
    "glitter-and-pet-sweatpants": "PO-stt\tItem ID\tQuantity\tArtwork Front\tSize\tType(Product Code)",
    "glitter-pet": "PO-stt\tItem ID\tQuantity\tArtwork Front\tSize\tType(Product Code)",
    "3dts": "PO-stt\tItem ID\tQuantity\tArtwork Front\tSize",
    "plant-pot-a4": "PO-stt\tItem ID\tQuantity\tArtwork Front\tSize",
    "pocket-t-shirt": "PO-stt\tItem ID\tQuantity\tArtwork Front\tType\tSize\tPrint-side",
    "printed-pet-sweatpants": "PO-stt\tItem ID\tQuantity\tArtwork Front\tType\tSize\tPrint-side",
    "printed-pet-dog-hoodie": "PO-stt\tItem ID\tQuantity\tArtwork Front\tType\tSize\tPrint-side",
}

EXTRA_META = {
    "pet": {
        "sp_product": ["Printed PET", "Printed PET 5000 Gildan Heavy Cotton T-Shirt"],
        "product_codes": ["CTSPP", "GGCTSPPL03"],
        "color": "#2563eb",
    },
    "glitter-pet": {"product_codes": ["GPCSW", "GPCSM"], "color": "#a855f7"},
    "glitter-and-pet-sweatpants": {
        "sp_product": ["Glitter and Pet Sweatshirt", "Glitter and Pet Sweatshirt V-Notch"],
        "product_codes": ["GPSVN", "GGGPSWNL042S"],
        "color": "#7c3aed",
    },
    "glitter-and-pet-sweatshirt": {
        "sp_product": ["Glitter and Pet Sweatshirt", "Glitter and Pet Sweatshirt V-Notch"],
        "product_codes": ["GPSVN", "GGGPSWNL042S"],
        "color": "#7c3aed",
    },
    "white-coined-napkins": {
        "product_codes": ["WCN", "GGWCNF250S"],
        "color": "#0ea5e9",
    },
}


@dataclass
class LokiProduct:
    id: str
    name: str
    columns: list[str]
    note: str = ""
    sp_product: list[str] = field(default_factory=list)
    product_codes: list[str] = field(default_factory=list)
    example: str = ""
    color: str = "#4f46e5"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "columns": self.columns,
            "note": self.note,
            "sp_product": self.sp_product,
            "product_codes": self.product_codes,
            "example": self.example,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: dict) -> LokiProduct:
        note = data.get("note", "")
        columns = data.get("columns") or ([c.strip() for c in note.split("\t") if c.strip()] if note else [
            "Item ID", "Quantity", "Artwork Front",
        ])
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            columns=columns,
            note=note,
            sp_product=data.get("sp_product", []),
            product_codes=data.get("product_codes", []),
            example=data.get("example", ""),
            color=data.get("color", "#4f46e5"),
        )


@dataclass
class AppConfig:
    auto_copy: bool = True
    copy_separator: str = "\t"
    include_header: bool = False
    products: list[LokiProduct] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "auto_copy": self.auto_copy,
            "copy_separator": self.copy_separator,
            "include_header": self.include_header,
            "products": [p.to_dict() for p in self.products],
        }

    @classmethod
    def from_dict(cls, data: dict) -> AppConfig:
        return cls(
            auto_copy=data.get("auto_copy", True),
            copy_separator=data.get("copy_separator", "\t"),
            include_header=data.get("include_header", False),
            products=[LokiProduct.from_dict(p) for p in data.get("products", [])],
        )


def _parse_columns(note: str) -> list[str]:
    if not note:
        return ["Item ID", "Quantity", "Artwork Front"]
    if "\t" in note:
        return [c.strip() for c in note.split("\t") if c.strip()]
    # fallback: split combined loki typos
    known = ["PO-stt", "Item ID", "Item Input", "Quantity", "Artwork Front", "Artwork Back",
             "Size", "Color", "Print-side", "Print Side", "Type(Product Code)", "Type", "Layer", "Pack"]
    cols: list[str] = []
    rest = note
    for token in known:
        if token in rest:
            cols.append(token)
            rest = rest.replace(token, " ", 1)
    return cols or [note.strip()]


def build_loki_products_from_raw() -> list[LokiProduct]:
    if not LOKI_RAW_PATH.is_file():
        raise FileNotFoundError(f"Thiếu file {LOKI_RAW_PATH}")

    raw = json.loads(LOKI_RAW_PATH.read_text(encoding="utf-8"))
    products: list[LokiProduct] = []

    for item in raw:
        key = item["key"]
        note = NOTE_FIXES.get(key, item.get("note", ""))
        extra = EXTRA_META.get(key, {})
        products.append(LokiProduct(
            id=key,
            name=item["name"],
            columns=_parse_columns(note),
            note=note,
            sp_product=list(dict.fromkeys(item.get("sp_product", []) + extra.get("sp_product", []))),
            product_codes=extra.get("product_codes", []),
            example=item.get("example", ""),
            color=extra.get("color", "#4f46e5"),
        ))

    # Extra product for sweatshirt variant
    if not any(p.id == "glitter-and-pet-sweatshirt" for p in products):
        meta = EXTRA_META["glitter-and-pet-sweatpants"]
        note = "PO-stt\tItem ID\tQuantity\tArtwork Front\tSize\tType(Product Code)"
        products.append(LokiProduct(
            id="glitter-and-pet-sweatshirt",
            name="Glitter and Pet Sweatshirt",
            columns=_parse_columns(note),
            note=note,
            sp_product=meta.get("sp_product", []),
            product_codes=meta.get("product_codes", []),
            color=meta.get("color", "#7c3aed"),
        ))

    return products


def default_config() -> AppConfig:
    return AppConfig(products=build_loki_products_from_raw())


def save_loki_products_json() -> Path:
    products = build_loki_products_from_raw()
    LOKI_PRODUCTS_PATH.write_text(
        json.dumps({"products": [p.to_dict() for p in products]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return LOKI_PRODUCTS_PATH


def load_config(path: Path | None = None) -> AppConfig:
    cfg_path = path or CONFIG_PATH
    if not cfg_path.is_file():
        save_loki_products_json()
        config = default_config()
        save_config(config, cfg_path)
        return config
    return AppConfig.from_dict(json.loads(cfg_path.read_text(encoding="utf-8")))


def save_config(config: AppConfig, path: Path | None = None) -> None:
    cfg_path = path or CONFIG_PATH
    cfg_path.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


# Backward compat aliases
ProductRule = LokiProduct


# ── Thêm / sửa sản phẩm (dùng khi update) ─────────────────────
#
# Cách 1 — sửa JSON (nhanh, không cần code):
#   Mở csv_reader/products_config.json → thêm object vào mảng "products"
#
# Cách 2 — code:
#   from csv_reader.config import add_product
#   add_product(
#       id="my-hoodie",
#       name="My Hoodie",
#       columns=["PO-stt", "Item ID", "Quantity", "Artwork Front", "Size"],
#       product_codes=["MHD01"],
#       color="#f59e0b",
#   )
#
PRODUCT_TEMPLATE = {
    "id": "new-product-id",
    "name": "Tên hiển thị",
    "columns": ["PO-stt", "Item ID", "Quantity", "Artwork Front", "Size"],
    "note": "PO-stt\tItem ID\tQuantity\tArtwork Front\tSize",
    "sp_product": [],
    "product_codes": [],
    "example": "",
    "color": "#4f46e5",
}


def find_product(product_id: str, config: AppConfig | None = None) -> LokiProduct | None:
    cfg = config or load_config()
    for p in cfg.products:
        if p.id == product_id:
            return p
    return None


def add_product(
    *,
    id: str,
    name: str,
    columns: list[str] | None = None,
    note: str = "",
    sp_product: list[str] | None = None,
    product_codes: list[str] | None = None,
    example: str = "",
    color: str = "#4f46e5",
    path: Path | None = None,
    overwrite: bool = False,
) -> LokiProduct:
    """
    Thêm 1 sản phẩm vào products_config.json và trả về LokiProduct.
    Nếu id đã tồn tại: overwrite=True thì ghi đè, else ValueError.
    """
    cfg = load_config(path)
    cols = columns or ([c.strip() for c in note.split("\t") if c.strip()] if note else list(PRODUCT_TEMPLATE["columns"]))
    if not note and cols:
        note = "\t".join(cols)
    product = LokiProduct(
        id=id,
        name=name,
        columns=cols,
        note=note,
        sp_product=list(sp_product or []),
        product_codes=list(product_codes or []),
        example=example,
        color=color,
    )
    existing = {p.id: i for i, p in enumerate(cfg.products)}
    if id in existing:
        if not overwrite:
            raise ValueError(f"Sản phẩm '{id}' đã có — dùng overwrite=True để ghi đè")
        cfg.products[existing[id]] = product
    else:
        cfg.products.append(product)
    save_config(cfg, path)
    return product


def remove_product(product_id: str, path: Path | None = None) -> bool:
    """Xóa sản phẩm theo id. True nếu đã xóa."""
    cfg = load_config(path)
    before = len(cfg.products)
    cfg.products = [p for p in cfg.products if p.id != product_id]
    if len(cfg.products) == before:
        return False
    save_config(cfg, path)
    return True


def list_product_ids(path: Path | None = None) -> list[str]:
    return [p.id for p in load_config(path).products]