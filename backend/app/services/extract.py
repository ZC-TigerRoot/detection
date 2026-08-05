from __future__ import annotations

import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SS_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _read_text_auto(path: Path) -> str:
    """按常见中文编码尝试解码，避免 GBK 文本被当 UTF-8 丢掉。"""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "cp936"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_file(path: Path) -> str:
    ext = path.suffix.lower()
    try:
        if ext == ".docx":
            return _extract_docx(path)
        if ext in {".xlsx", ".xlsm"}:
            return _extract_xlsx(path)
        if ext == ".pdf":
            return _extract_pdf(path)
        if ext == ".doc":
            return _extract_doc(path)
        if ext in {".txt", ".md", ".csv"}:
            return _read_text_auto(path)
        if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
            return f"[图片附件，未做 OCR: {path.name}]"
        return f"[暂不支持的文件类型: {path.name}]"
    except Exception as exc:  # noqa: BLE001
        return f"[解析失败 {path.name}: {exc}]"


def _extract_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    blocks: list[str] = []

    body = root.find(f"{W_NS}body")
    if body is None:
        return ""

    for child in list(body):
        tag = child.tag
        if tag == f"{W_NS}p":
            text = _para_text(child)
            if text:
                blocks.append(text)
        elif tag == f"{W_NS}tbl":
            blocks.append(_table_markdown(child))

    return "\n".join(blocks).strip()


def _para_text(p: ET.Element) -> str:
    parts = [t.text for t in p.iter(f"{W_NS}t") if t.text]
    return "".join(parts).strip()


def _table_markdown(tbl: ET.Element) -> str:
    rows: list[list[str]] = []
    for tr in tbl.findall(f"{W_NS}tr"):
        cells: list[str] = []
        for tc in tr.findall(f"{W_NS}tc"):
            texts = [t.text for t in tc.iter(f"{W_NS}t") if t.text]
            cells.append(re.sub(r"\s+", " ", "".join(texts)).strip())
        if any(cells):
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(norm[0]) + " |"]
    lines.append("| " + " | ".join(["---"] * width) + " |")
    for r in norm[1:]:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def _extract_xlsx(path: Path) -> str:
    try:
        from openpyxl import load_workbook
    except ImportError:
        return _extract_xlsx_raw(path)

    wb = load_workbook(path, data_only=True, read_only=True)
    parts: list[str] = []
    for sheet in wb.worksheets:
        parts.append(f"## 工作表: {sheet.title}")
        rows_out: list[str] = []
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            vals = ["" if c is None else str(c).replace("\n", " ").strip() for c in row]
            if not any(vals):
                continue
            rows_out.append(" | ".join(vals))
            if i > 500:
                rows_out.append("... (已截断)")
                break
        parts.append("\n".join(rows_out))
    wb.close()
    return "\n\n".join(parts).strip()


def _extract_xlsx_raw(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall(f"{SS_NS}si"):
                texts = [t.text or "" for t in si.iter(f"{SS_NS}t")]
                shared.append("".join(texts))
        sheets = sorted(n for n in zf.namelist() if n.startswith("xl/worksheets/sheet"))
        parts: list[str] = []
        for sh in sheets:
            root = ET.fromstring(zf.read(sh))
            lines: list[str] = []
            for row in root.findall(f".//{SS_NS}row"):
                vals: list[str] = []
                for c in row.findall(f"{SS_NS}c"):
                    t = c.get("t")
                    v = c.find(f"{SS_NS}v")
                    if v is None or v.text is None:
                        vals.append("")
                        continue
                    val = v.text
                    if t == "s" and val.isdigit():
                        idx = int(val)
                        val = shared[idx] if idx < len(shared) else val
                    vals.append(val.replace("\n", " "))
                if any(vals):
                    lines.append(" | ".join(vals))
            parts.append("\n".join(lines))
        return "\n\n".join(parts).strip()


def _extract_pdf(path: Path) -> str:
    try:
        import fitz  # pymupdf
    except ImportError:
        return f"[未安装 pymupdf，无法解析 PDF: {path.name}]"

    doc = fitz.open(path)
    texts: list[str] = []
    max_pages = min(doc.page_count, 40)
    for i in range(max_pages):
        page = doc.load_page(i)
        texts.append(page.get_text("text"))
    doc.close()
    text = "\n".join(texts).strip()
    if text:
        return text
    return _ocr_pdf(path, max_pages)


_ocr_engine: object | None = None


def _get_ocr_engine():
    """懒加载 RapidOCR 引擎（首次初始化较慢，之后复用）。"""
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _ocr_engine = RapidOCR()
    return _ocr_engine


def _ocr_pdf(path: Path, max_pages: int) -> str:
    """无文字层的扫描件 PDF：渲染成图片后用 RapidOCR 识别中文。"""
    try:
        engine = _get_ocr_engine()
    except ImportError:
        return f"[PDF 无文字层，且未安装 rapidocr-onnxruntime: {path.name}]"

    import fitz  # pymupdf

    doc = fitz.open(path)
    parts: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="detection_ocr_") as tmp:
            for i in range(max_pages):
                page = doc.load_page(i)
                pix = page.get_pixmap(dpi=200)
                png = Path(tmp) / f"page_{i}.png"
                pix.save(png)
                result, _ = engine(str(png))
                if result:
                    lines = [item[1] for item in result]
                    parts.append("\n".join(lines))
    finally:
        doc.close()
    return "\n".join(parts).strip()


def _extract_doc(path: Path) -> str:
    # macOS
    try:
        result = subprocess.run(
            ["textutil", "-convert", "txt", "-stdout", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # LibreOffice
    try:
        out_dir = path.parent
        result = subprocess.run(
            [
                "soffice",
                "--headless",
                "--convert-to",
                "txt:Text",
                "--outdir",
                str(out_dir),
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        txt_path = out_dir / f"{path.stem}.txt"
        if txt_path.exists():
            return _read_text_auto(txt_path).strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return f"[无法解析 .doc，请另存为 .docx 后重新上传: {path.name}]"


def combine_project_texts(file_texts: list[tuple[str, str]], max_chars: int) -> str:
    chunks: list[str] = []
    for name, text in file_texts:
        chunks.append(f"===== 文件: {name} =====\n{text}")
    combined = "\n\n".join(chunks)
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n\n...[内容过长已截断]"
    return combined
