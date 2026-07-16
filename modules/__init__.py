"""
modules/ — các phần UI & service của ACC2019.

Cấu trúc gợi ý khi update:
  modules/registry.py     TabRegistry, màu tab
  modules/tabs/           Mỗi tab 1 file (thêm tab ở đây)
  modules/image_viewer.py Lightbox xem ảnh
  modules/*_panel.py      Panel chức năng
  csv_reader/             CSV Loki + products_config.json
"""

from modules.registry import TabRegistry, TabSpec, get_registry

__all__ = ["TabRegistry", "TabSpec", "get_registry"]
