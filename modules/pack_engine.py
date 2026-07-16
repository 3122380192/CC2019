"""Engine đóng gói file — ZIP / copy theo loại file và cấu hình."""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

CONFIG_NAME = "pack_config.json"

ACTION_TYPES = {
    "pack_all_zip": "Nén các file đã xử lý",
    "copy_all_folder": "Sao chép các file đã xử lý",
    "pack_left_match": "Nén theo nhóm ký tự trùng khớp",
    "pack_folder_name": "Nén theo danh sách tên từ thư mục Nguồn",
    "pack_same_name": "ZIP theo trùng tên (stem)",
    "pack_list_zip": "ZIP theo list / từ khóa tên",
}

# alias cũ → action mới (cấu hình đã lưu)
ACTION_ALIASES = {
    "pack_prefix_zip": "pack_left_match",
    "ZIP tất cả (1 file ZIP)": "pack_all_zip",
    "ZIP theo trùng tên (stem)": "pack_same_name",
    "ZIP theo N ký tự từ trái →": "pack_left_match",
    "ZIP theo list / từ khóa tên": "pack_list_zip",
    "Copy vào folder (không nén)": "copy_all_folder",
}

DEFAULT_EXTENSIONS = ["png", "jpg", "jpeg", "tif", "tiff", "dxf", "pdf"]
PS_EXTENSIONS = ["jpg", "png", "tif"]  # loại file PS xử lý (UI)

DEFAULT_PROFILE = {
    "input_folder": "",
    "output_folder": "",  # base tùy chọn; trống = Desktop
    "action_type": "pack_left_match",
    "pack_extensions": ["jpg", "png"],
    "ps_extensions": ["png"],  # file PS batch
    "pack_custom_extensions": "",
    "selected_files": [],
    "pack_file_mode": "all",  # all | selected
    "match_prefix_length": 17,
    "match_keyword": "",
    "name_list": "",
    "zip_name": "",
    "delete_after_packaging": True,
    "delete_source_folder_after_packaging": True,
    "auto_backup_before_delete": True,  # backup Desktop\_ACC_Backup trước khi xóa
    "backup_folder": "",  # trống = Desktop\_ACC_Backup
    "auto_pack_after_action": False,
    "use_daily_folder": True,
    "product_subfolder": "Print",
    "product_name": "",
    "open_after_pack": True,
    "note": "",
    "ps_script": "",
    "ps_action_set": "",
    "ps_action_name": "",
    "detect_keywords": "",
    "detect_column": "B",
}


def new_profile_dict(**overrides) -> dict:
    p = dict(DEFAULT_PROFILE)
    p["pack_extensions"] = list(DEFAULT_PROFILE["pack_extensions"])
    p["selected_files"] = []
    p.update(overrides)
    return p


def list_profiles(base_dir: str) -> list[str]:
    data = load_config(base_dir)
    names = list((data.get("profiles") or {}).keys())
    if not names:
        names = ["Mặc định"]
    return sorted(names, key=lambda s: (s != "Mặc định", s.lower()))


def create_profile(base_dir: str, name: str, *, from_profile: dict | None = None) -> tuple[bool, str]:
    """Tạo cấu hình mới. Trả (ok, message)."""
    name = (name or "").strip()
    if not name:
        return False, "Tên cấu hình trống"
    if len(name) > 48:
        return False, "Tên tối đa 48 ký tự"
    data = load_config(base_dir)
    profiles = data.setdefault("profiles", {})
    if name in profiles:
        return False, f"«{name}» đã tồn tại"
    profiles[name] = new_profile_dict(**(from_profile or {})) if from_profile else new_profile_dict()
    # don't copy selected_files by default when blank new
    if from_profile is None:
        profiles[name]["selected_files"] = []
    data["active_profile"] = name
    save_config(base_dir, data)
    return True, f"Đã tạo «{name}»"


def duplicate_profile(base_dir: str, source: str, new_name: str) -> tuple[bool, str]:
    data = load_config(base_dir)
    profiles = data.get("profiles") or {}
    if source not in profiles:
        return False, f"Không thấy «{source}»"
    new_name = (new_name or "").strip()
    if not new_name:
        return False, "Tên mới trống"
    if new_name in profiles:
        return False, f"«{new_name}» đã tồn tại"
    src = profiles[source]
    profiles[new_name] = new_profile_dict(**{k: (list(v) if isinstance(v, list) else v) for k, v in src.items()})
    data["profiles"] = profiles
    data["active_profile"] = new_name
    save_config(base_dir, data)
    return True, f"Nhân bản «{source}» → «{new_name}»"


def rename_profile(base_dir: str, old: str, new: str) -> tuple[bool, str]:
    data = load_config(base_dir)
    profiles = data.get("profiles") or {}
    old, new = (old or "").strip(), (new or "").strip()
    if old not in profiles:
        return False, f"Không thấy «{old}»"
    if not new:
        return False, "Tên mới trống"
    if new == old:
        return True, "Giữ nguyên tên"
    if new in profiles:
        return False, f"«{new}» đã tồn tại"
    profiles[new] = profiles.pop(old)
    data["profiles"] = profiles
    if data.get("active_profile") == old:
        data["active_profile"] = new
    save_config(base_dir, data)
    return True, f"Đổi tên «{old}» → «{new}»"


def delete_profile(base_dir: str, name: str) -> tuple[bool, str]:
    data = load_config(base_dir)
    profiles = data.get("profiles") or {}
    name = (name or "").strip()
    if name not in profiles:
        return False, f"Không thấy «{name}»"
    if len(profiles) <= 1:
        return False, "Phải giữ ít nhất 1 cấu hình"
    del profiles[name]
    data["profiles"] = profiles
    if data.get("active_profile") == name:
        data["active_profile"] = next(iter(profiles))
    save_config(base_dir, data)
    return True, f"Đã xóa «{name}»"


def set_active_profile(base_dir: str, name: str) -> tuple[bool, str, dict]:
    data = load_config(base_dir)
    profiles = data.get("profiles") or {}
    if name not in profiles:
        return False, f"Không thấy «{name}»", new_profile_dict()
    data["active_profile"] = name
    save_config(base_dir, data)
    return True, name, dict(profiles[name])


def save_profile(base_dir: str, name: str, profile: dict) -> tuple[bool, str]:
    name = (name or "").strip() or "Mặc định"
    data = load_config(base_dir)
    profiles = data.setdefault("profiles", {})
    # merge with defaults so keys đầy đủ
    full = new_profile_dict()
    full.update(profile or {})
    profiles[name] = full
    data["active_profile"] = name
    save_config(base_dir, data)
    return True, f"Đã lưu «{name}»"


def _desktop_base() -> str:
    for p in (
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop"),
    ):
        if os.path.isdir(p):
            return p
    return os.path.expanduser("~")


def config_path(base_dir: str) -> str:
    return os.path.join(base_dir, CONFIG_NAME)


def load_config(base_dir: str) -> dict:
    path = config_path(base_dir)
    if not os.path.isfile(path):
        return {
            "active_profile": "Mặc định",
            "profiles": {"Mặc định": new_profile_dict()},
        }
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        profiles = data.get("profiles") or {}
        # sửa tên bị lỗi encoding
        fixed: dict = {}
        for k, v in profiles.items():
            name = k
            if not isinstance(name, str) or "M?c" in name or "\ufffd" in name:
                name = "Mặc định"
            if not isinstance(v, dict):
                v = new_profile_dict()
            else:
                merged = new_profile_dict()
                merged.update(v)
                v = merged
            # merge nếu trùng tên sau fix
            if name in fixed and name != k:
                continue
            fixed[name] = v
        if not fixed:
            fixed = {"Mặc định": new_profile_dict()}
        data["profiles"] = fixed
        active = data.get("active_profile") or next(iter(fixed))
        if active not in fixed:
            # active cũng lỗi encoding
            if isinstance(active, str) and ("M?c" in active or "\ufffd" in active):
                active = "Mặc định" if "Mặc định" in fixed else next(iter(fixed))
            else:
                active = next(iter(fixed))
        data["active_profile"] = active
        return data
    except (OSError, json.JSONDecodeError):
        return {
            "active_profile": "Mặc định",
            "profiles": {"Mặc định": new_profile_dict()},
        }


def save_config(base_dir: str, data: dict) -> None:
    with open(config_path(base_dir), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_active_profile(base_dir: str) -> tuple[str, dict]:
    data = load_config(base_dir)
    name = data.get("active_profile", "Mặc định")
    profile = data.get("profiles", {}).get(name) or dict(DEFAULT_PROFILE)
    return name, profile


def get_pack_extensions(profile: dict) -> list[str]:
    exts = [e.strip().lower().lstrip(".") for e in profile.get("pack_extensions", []) if e.strip()]
    custom = profile.get("pack_custom_extensions", "")
    if custom:
        for part in custom.replace(";", ",").split(","):
            p = part.strip().lower().lstrip(".")
            if p:
                exts.append(p)
    return list(dict.fromkeys(exts)) or list(DEFAULT_EXTENSIONS)


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def resolve_output_parent(profile: dict) -> str:
    """Thư mục nhận ZIP.

    Mặc định (use_daily_folder=True):
        {Desktop hoặc output_folder}\\YYYY-MM-DD\\Print
        vd. C:\\Users\\Tx\\Desktop\\2026-07-10\\Print

    Tắt daily: dùng output_folder (hoặc Desktop\\Print).
    """
    use_daily = profile.get("use_daily_folder", True)
    if use_daily is None:
        use_daily = True
    use_daily = bool(use_daily)

    base = (profile.get("output_folder") or "").strip()
    if not base:
        base = _desktop_base()
    sub = (profile.get("product_subfolder") or "Print").strip() or "Print"
    # làm sạch tên folder con
    for ch in '<>:"/\\|?*':
        sub = sub.replace(ch, "_")
    sub = sub.strip(" .") or "Print"

    if use_daily:
        parent = os.path.join(base, today_str(), sub)
    else:
        parent = os.path.join(base, sub) if not base.lower().endswith(sub.lower()) else base

    os.makedirs(parent, exist_ok=True)
    return parent


def preview_output_path(profile: dict) -> str:
    """Đường dẫn sẽ dùng (không bắt buộc đã tồn tại)."""
    use_daily = bool(profile.get("use_daily_folder", True))
    base = (profile.get("output_folder") or "").strip() or _desktop_base()
    sub = (profile.get("product_subfolder") or "Print").strip() or "Print"
    for ch in '<>:"/\\|?*':
        sub = sub.replace(ch, "_")
    if use_daily:
        return os.path.join(base, today_str(), sub)
    return os.path.join(base, sub)


def _ext_ok(path: str, exts: list[str]) -> bool:
    ext = os.path.splitext(path)[1].replace(".", "").lower()
    return ext in exts


def normalize_action(action: str) -> str:
    action = (action or "pack_all_zip").strip()
    return ACTION_ALIASES.get(action, action)


def sanitize_zip_name(name: str, fallback: str = "") -> str:
    """Tên ZIP an toàn (không đuôi .zip)."""
    raw = (name or "").strip()
    if raw.lower().endswith(".zip"):
        raw = raw[:-4]
    # bỏ ký tự cấm Windows
    bad = '<>:"/\\|?*'
    for ch in bad:
        raw = raw.replace(ch, "_")
    raw = raw.strip(" .")
    if not raw:
        raw = (fallback or datetime.now().strftime("%H%M%S")).strip() or "pack"
    return raw[:120]


def parse_name_list(text: str) -> list[str]:
    """Tách list tên: mỗi dòng hoặc phân tách , ; |"""
    if not text:
        return []
    names: list[str] = []
    for line in str(text).replace(";", "\n").replace("|", "\n").splitlines():
        for part in line.split(","):
            n = part.strip()
            if n:
                names.append(n)
    # unique keep order
    out, seen = [], set()
    for n in names:
        k = n.lower()
        if k not in seen:
            seen.add(k)
            out.append(n)
    return out


def file_stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def collect_files(
    profile: dict,
    *,
    keyword: str = "",
    selected_override: list[str] | None = None,
) -> list[str]:
    selected = selected_override if selected_override is not None else profile.get("selected_files", [])
    if selected:
        return [p for p in selected if os.path.isfile(p)]

    input_folder = (profile.get("input_folder") or "").strip()
    if not input_folder or not os.path.isdir(input_folder):
        return []

    exts = get_pack_extensions(profile)
    action = normalize_action(profile.get("action_type", "pack_all_zip"))
    kw = (keyword or profile.get("match_keyword") or "").strip().lower()
    name_list = parse_name_list(profile.get("name_list") or "")
    matched: list[str] = []

    for name in os.listdir(input_folder):
        path = os.path.join(input_folder, name)
        if not os.path.isfile(path) or not _ext_ok(path, exts):
            continue
        stem = file_stem(path).lower()
        base = name.lower()
        if action == "pack_list_zip":
            # có list tên → chỉ lấy file khớp 1 trong list
            if name_list:
                ok = False
                for n in name_list:
                    nl = n.lower()
                    if stem == nl or stem.startswith(nl) or nl in stem or nl in base:
                        ok = True
                        break
                if not ok:
                    continue
            elif kw and kw not in base:
                continue
        matched.append(path)
    return matched


@dataclass
class PackResult:
    ok: bool
    message: str = ""
    archives: list[str] = field(default_factory=list)
    copied_dirs: list[str] = field(default_factory=list)
    deleted_files: int = 0
    cleaned_folder: bool = False


def cleanup_folder(folder: str, *, extensions: list[str] | None = None) -> int:
    """Xóa file trong folder (theo đuôi nếu có), giữ folder trống."""
    if not folder or not os.path.isdir(folder):
        return 0
    deleted = 0
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        if extensions and not _ext_ok(path, extensions):
            continue
        try:
            os.remove(path)
            deleted += 1
        except OSError:
            pass
    return deleted


def _unique_zip_path(folder: str, base_name: str) -> str:
    """Tránh ghi đè: name.zip, name_2.zip…"""
    safe = sanitize_zip_name(base_name)
    path = os.path.join(folder, f"{safe}.zip")
    if not os.path.exists(path):
        return path
    i = 2
    while True:
        path = os.path.join(folder, f"{safe}_{i}.zip")
        if not os.path.exists(path):
            return path
        i += 1


def _write_zip_group(
    target_parent: str,
    zip_base: str,
    paths: list[str],
    *,
    delete_after: bool,
    log: Callable[[str], None] | None = None,
) -> tuple[str, int]:
    zip_path = _unique_zip_path(target_parent, zip_base)
    deleted = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in paths:
            zf.write(p, os.path.basename(p))
    if log:
        log(f"ZIP: {os.path.basename(zip_path)} ({len(paths)} file)")
    if delete_after:
        for p in paths:
            try:
                os.remove(p)
                deleted += 1
            except OSError:
                pass
    return zip_path, deleted


def _group_by_same_stem(files: list[str]) -> dict[str, list[str]]:
    """Gom file trùng tên stem (không phân biệt hoa thường). Key = stem gốc (file đầu)."""
    groups: dict[str, list[str]] = {}
    key_map: dict[str, str] = {}  # lower -> display key
    for fpath in files:
        stem = file_stem(fpath)
        k = stem.lower()
        if k not in key_map:
            key_map[k] = stem
        groups.setdefault(key_map[k], []).append(fpath)
    return groups


def _group_by_left_chars(files: list[str], n: int) -> dict[str, list[str]]:
    """Gom theo N ký tự đầu (trái → phải) của stem."""
    n = max(1, int(n or 1))
    groups: dict[str, list[str]] = {}
    for fpath in files:
        stem = file_stem(fpath)
        if len(stem) < n:
            prefix = stem  # file ngắn: mỗi stem riêng
        else:
            prefix = stem[:n]
        # gộp không phân biệt hoa thường
        found = None
        for key in groups:
            if key.lower() == prefix.lower():
                found = key
                break
        if found is None:
            groups[prefix] = [fpath]
        else:
            groups[found].append(fpath)
    return groups


def _group_by_name_list(files: list[str], names: list[str]) -> dict[str, list[str]]:
    """Mỗi tên trong list → 1 ZIP gồm file stem trùng / bắt đầu bằng / chứa tên đó."""
    groups: dict[str, list[str]] = {n: [] for n in names}
    used: set[str] = set()
    for fpath in files:
        stem = file_stem(fpath)
        base = os.path.basename(fpath)
        stem_l, base_l = stem.lower(), base.lower()
        for n in names:
            nl = n.lower()
            if stem_l == nl or stem_l.startswith(nl) or nl in stem_l or nl in base_l:
                groups[n].append(fpath)
                used.add(fpath)
                break  # 1 file 1 nhóm (tên list đầu khớp)
    # bỏ nhóm rỗng
    return {k: v for k, v in groups.items() if v}


def run_packaging(
    profile: dict,
    *,
    keyword: str = "",
    selected_files: list[str] | None = None,
    log: Callable[[str], None] | None = None,
) -> PackResult:
    def _log(msg: str) -> None:
        if log:
            log(msg)

    input_folder = (profile.get("input_folder") or "").strip()
    if selected_files:
        selected_files = [p for p in selected_files if os.path.isfile(p)]
    if (not input_folder or not os.path.isdir(input_folder)) and not selected_files:
        return PackResult(False, "Thư mục nguồn không hợp lệ")
    if not input_folder and selected_files:
        input_folder = os.path.dirname(selected_files[0]) or "."

    action = normalize_action(profile.get("action_type", "pack_all_zip"))
    delete_after = bool(profile.get("delete_after_packaging", True))
    delete_source = bool(profile.get("delete_source_folder_after_packaging", False))
    auto_backup = bool(profile.get("auto_backup_before_delete", True))
    target_parent = resolve_output_parent(profile)
    exts = get_pack_extensions(profile)
    zip_name_ui = (profile.get("zip_name") or "").strip()
    name_list = parse_name_list(profile.get("name_list") or "")
    kw = (keyword or profile.get("match_keyword") or "").strip()

    try:
        files = collect_files(profile, keyword=keyword, selected_override=selected_files)
        if not files:
            return PackResult(False, "Không có file để đóng gói")

        # ── Auto backup trước khi xóa (an toàn) ──
        if auto_backup and (delete_after or delete_source):
            try:
                from modules.tools_order import backup_files, backup_folder_tree

                broot = (profile.get("backup_folder") or "").strip() or None
                label = (
                    (profile.get("zip_name") or profile.get("product_name") or "")
                    or os.path.basename(os.path.normpath(input_folder))
                    or "pack"
                )
                if delete_source and input_folder and os.path.isdir(input_folder):
                    backup_folder_tree(
                        input_folder, label=label, backup_root=broot, log=_log,
                    )
                else:
                    backup_files(
                        files, label=label, backup_root=broot, log=_log,
                    )
            except Exception as exc:
                _log(f"Backup cảnh báo: {exc}")

        # ── Multi-ZIP: trùng stem ──
        if action == "pack_same_name":
            groups = _group_by_same_stem(files)
            archives: list[str] = []
            deleted = 0
            for stem, paths in groups.items():
                zpath, d = _write_zip_group(
                    target_parent, stem, paths, delete_after=delete_after, log=_log,
                )
                archives.append(zpath)
                deleted += d
            if delete_source and input_folder and os.path.isdir(input_folder):
                shutil.rmtree(input_folder, ignore_errors=True)
                os.makedirs(input_folder, exist_ok=True)
            return PackResult(
                True,
                f"Trùng tên → {len(archives)} ZIP · {deleted} file xóa",
                archives=archives,
                deleted_files=deleted,
                cleaned_folder=delete_source,
            )

        # ── Multi-ZIP: N ký tự từ trái ──
        if action == "pack_left_match":
            n = int(profile.get("match_prefix_length") or 0)
            if n <= 0:
                return PackResult(False, "Đặt số ký tự từ trái (Prefix ≥ 1)")
            groups = _group_by_left_chars(files, n)
            archives = []
            deleted = 0
            for prefix, paths in groups.items():
                zpath, d = _write_zip_group(
                    target_parent, prefix, paths, delete_after=delete_after, log=_log,
                )
                archives.append(zpath)
                deleted += d
            if delete_source and input_folder and os.path.isdir(input_folder):
                shutil.rmtree(input_folder, ignore_errors=True)
                os.makedirs(input_folder, exist_ok=True)
            return PackResult(
                True,
                f"Khớp {n} ký tự trái → {len(archives)} ZIP · xóa {deleted}",
                archives=archives,
                deleted_files=deleted,
                cleaned_folder=delete_source,
            )

        # ── Multi-ZIP: theo list tên ──
        if action == "pack_list_zip" and name_list:
            groups = _group_by_name_list(files, name_list)
            if not groups:
                return PackResult(False, "List tên không khớp file nào")
            archives = []
            deleted = 0
            for n, paths in groups.items():
                zpath, d = _write_zip_group(
                    target_parent, n, paths, delete_after=delete_after, log=_log,
                )
                archives.append(zpath)
                deleted += d
            if delete_source and input_folder and os.path.isdir(input_folder):
                shutil.rmtree(input_folder, ignore_errors=True)
                os.makedirs(input_folder, exist_ok=True)
            return PackResult(
                True,
                f"List {len(archives)} tên → {len(archives)} ZIP · xóa {deleted}",
                archives=archives,
                deleted_files=deleted,
                cleaned_folder=delete_source,
            )

        # ── Single pack name ──
        # pack_folder_name: tên ZIP = tên folder nguồn (hoặc zip_name nếu có)
        if action == "pack_folder_name":
            folder_base = os.path.basename(os.path.normpath(input_folder)) if input_folder else ""
            pack_name = sanitize_zip_name(
                zip_name_ui or folder_base or kw or datetime.now().strftime("%H%M%S"),
            )
        else:
            pack_name = sanitize_zip_name(
                zip_name_ui or kw or datetime.now().strftime("%H%M%S"),
            )
        deleted = 0

        if action == "copy_all_folder":
            target_dir = os.path.join(target_parent, pack_name)
            os.makedirs(target_dir, exist_ok=True)
            for fpath in files:
                dest = os.path.join(target_dir, os.path.basename(fpath))
                shutil.copy2(fpath, dest)
                if delete_after:
                    try:
                        os.remove(fpath)
                        deleted += 1
                    except OSError:
                        pass
            _log(f"Copy → {target_dir} ({len(files)} file)")
            if delete_source and input_folder and os.path.isdir(input_folder):
                cleanup_folder(input_folder, extensions=exts)
                remaining = [
                    x for x in os.listdir(input_folder)
                    if os.path.isfile(os.path.join(input_folder, x))
                ]
                if not remaining:
                    shutil.rmtree(input_folder, ignore_errors=True)
                    os.makedirs(input_folder, exist_ok=True)
            return PackResult(
                True,
                f"Copy {len(files)} file → {os.path.basename(target_dir)}",
                copied_dirs=[target_dir],
                deleted_files=deleted,
                cleaned_folder=delete_source,
            )

        # pack_all_zip hoặc pack_list_zip (1 keyword, không list)
        zpath, deleted = _write_zip_group(
            target_parent, pack_name, files, delete_after=delete_after, log=_log,
        )
        if delete_source and input_folder and os.path.isdir(input_folder):
            shutil.rmtree(input_folder, ignore_errors=True)
            os.makedirs(input_folder, exist_ok=True)

        return PackResult(
            True,
            f"ZIP «{os.path.basename(zpath)}» · {len(files)} file · xóa {deleted}",
            archives=[zpath],
            deleted_files=deleted,
            cleaned_folder=delete_source,
        )
    except Exception as exc:
        return PackResult(False, str(exc))