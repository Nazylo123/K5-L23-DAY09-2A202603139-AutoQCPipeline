"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict

import yaml

from ..common import ERROR, ROOT, parse_yolo_line


DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
REMOVE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}


def _clip(text):
    cls, x, y, w, h = parse_yolo_line(text)
    left, top = max(0, x - w / 2), max(0, y - h / 2)
    right, bottom = min(1, x + w / 2), min(1, y + h / 2)
    if right <= left or bottom <= top:
        return None
    return f"{cls} {(left + right) / 2} {(top + bottom) / 2} {right - left} {bottom - top}"


def fix(ds, issues, cfg):
    root = ds.root.resolve()
    source = (ROOT / "data").resolve()
    if root.is_relative_to(source):
        raise ValueError("Chỉ sửa bản sao làm việc, không sửa dữ liệu gốc")

    def local(path):
        if not path.resolve().is_relative_to(root):
            raise ValueError(f"Đường dẫn nằm ngoài bản sao làm việc: {path}")
        return path

    fixes = []
    def record(image, action, before, after, line=None):
        fixes.append(dict(image=image, line=line, action=action, before=before, after=after))

    remove = set()
    missing = set()
    edits = defaultdict(lambda: defaultdict(set))
    rename = False
    for issue in issues:
        if issue.severity != ERROR:
            continue
        code, stem = issue.code, issue.image
        if code in REMOVE_CODES or code.startswith("DUP_IMAGE_"):
            remove.add(stem)
        elif code == "MISSING_LABEL_FILE":
            missing.add(stem)
        elif code == "BAD_CLASS_NAME":
            rename = True
        elif issue.line is not None and (code in DROP_CODES or code == "BOX_OUT_OF_IMAGE"):
            edits[stem][issue.line].add(code)

    for stem in sorted(remove):
        image = ds.image_path(stem)
        if image is not None:
            label = local(ds.label_path(stem))
            local(image).unlink()
            label.unlink(missing_ok=True)
            record(stem, "remove_image", image.name, "")
    for stem in sorted(missing - remove):
        if ds.image_path(stem) is not None and not local(ds.label_path(stem)).exists():
            record(stem, "needs_label", "(không có file)", "chuyển người gán")
    if rename:
        path = local(ds.yaml_path)
        data = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}
        old_names = data.get("names")
        names = list(cfg["classes"])
        if old_names != names:
            data["names"] = names
            path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            record("data.yaml", "rename_classes", str(old_names), str(names))

    for stem in sorted(edits.keys() - remove):
        path = local(ds.label_path(stem))
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        updated = []
        for line, original in enumerate(lines, 1):
            codes = edits[stem].get(line)
            if not codes:
                updated.append(original)
                continue
            before = original.rstrip("\r\n")
            after = None if codes & DROP_CODES else _clip(before)
            if after is None:
                record(stem, "drop_line", before, "", line)
            else:
                updated.append(after + original[len(before):])
                if after != before:
                    record(stem, "clip_box", before, after, line)
        if updated != lines:
            path.write_text("".join(updated), encoding="utf-8")
    return fixes
