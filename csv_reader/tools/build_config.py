"""Build products_config.json from Loki raw products."""

from csv_reader.config import default_config, save_config, save_loki_products_json

if __name__ == "__main__":
    save_loki_products_json()
    cfg = default_config()
    save_config(cfg)
    print(f"OK: {len(cfg.products)} products")