"""Re-import product list from E:\\Loki\\tool.html."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def extract_products(tool_html: Path) -> list[dict]:
    text = tool_html.read_text(encoding="utf-8")
    start = text.index("const products = [") + len("const products = ")
    end = text.index("];", start)
    block = text[start:end]

    products = []
    for chunk in re.split(r"\},\s*\{", block):
        chunk = chunk.strip().strip("{}")
        name_m = re.search(r'name:\s*"([^"]*)"', chunk)
        key_m = re.search(r'key:\s*"([^"]*)"', chunk)
        note_m = re.search(r'note:\s*"((?:[^"\\]|\\.)*)"', chunk)
        example_m = re.search(r'example:\s*"((?:[^"\\]|\\.)*)"', chunk)
        sp_m = re.search(r"sp_product:\s*\[([^\]]*)\]", chunk)
        if not name_m or not key_m:
            continue
        sp_product = re.findall(r'"([^"]*)"', sp_m.group(1)) if sp_m else []
        note = note_m.group(1).replace("\\t", "\t").replace('\\"', '"') if note_m else ""
        example = example_m.group(1).replace("\\t", "\t") if example_m else ""
        products.append({
            "name": name_m.group(1),
            "key": key_m.group(1),
            "note": note,
            "example": example,
            "sp_product": sp_product,
        })
    return products


if __name__ == "__main__":
    src = Path(r"E:\Loki\tool.html")
    raw_out = Path(__file__).resolve().parents[1] / "loki_products_raw.json"
    products = extract_products(src)
    raw_out.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Extracted {len(products)} products -> {raw_out}")
    subprocess.run([sys.executable, "-m", "csv_reader.tools.build_config"], check=True)