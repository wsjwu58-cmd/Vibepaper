from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from PIL import Image, ImageChops
from pypdf import PdfReader
from pypdf.generic import ContentStream


pdf_path = Path(sys.argv[1])
png_path = Path(sys.argv[2])
reader = PdfReader(str(pdf_path))
assert len(reader.pages) == 1, f"Expected 1 page, found {len(reader.pages)}"

page = reader.pages[0]
width = float(page.mediabox.width)
height = float(page.mediabox.height)
assert abs(width - 595.2756) < 1 and abs(height - 841.8898) < 1, (width, height)

text = page.extract_text() or ""
expected_text = ["武世杰", "TriliumNext", "VibePaper", "99.9%", "专业技能"]
missing = [value for value in expected_text if value not in text]
assert not missing, f"Missing extracted text: {missing}"

uris = [
    str(annotation.get_object().get("/A", {}).get("/URI", ""))
    for annotation in page.get("/Annots", [])
]
required_uris = [
    "mailto:wsjwu58@gmail.com",
    "https://www.wsjaly.cn",
    "https://github.com/TriliumNext/Trilium",
    "https://github.com/TriliumNext/Trilium/pull/10856",
    "https://github.com/wsjwu58-cmd/Vibepaper",
]
assert sorted(uris) == sorted(required_uris), (uris, required_uris)

embedded_fonts: list[str] = []
unicode_fonts: list[str] = []
for font_ref in page["/Resources"]["/Font"].values():
    font = font_ref.get_object()
    name = str(font.get("/BaseFont", ""))
    descriptor = font.get("/FontDescriptor")
    is_embedded = bool(
        descriptor
        and any(
            key in descriptor.get_object()
            for key in ("/FontFile", "/FontFile2", "/FontFile3")
        )
    )
    if is_embedded:
        embedded_fonts.append(name)
    if "/ToUnicode" in font:
        unicode_fonts.append(name)

assert any("Regular" in name for name in embedded_fonts), embedded_fonts
assert any("Bold" in name for name in embedded_fonts), embedded_fonts
assert set(embedded_fonts) == set(unicode_fonts), (embedded_fonts, unicode_fonts)

# ReportLab initializes Helvetica internally. It is acceptable only when it never
# paints visible text; all visible text must use the embedded Noto resources.
current_font = None
helvetica_visible: list[bytes] = []
for operands, operator in ContentStream(page.get_contents(), reader).operations:
    if operator == b"Tf":
        current_font = str(operands[0])
        continue
    if current_font != "/F1":
        continue
    if operator == b"TJ":
        raw = b"".join(value for value in operands[0] if isinstance(value, bytes))
    elif operator in (b"Tj", b"'", b'"'):
        raw = b"".join(value for value in operands if isinstance(value, bytes))
    else:
        continue
    if raw.strip():
        helvetica_visible.append(raw)
assert not helvetica_visible, helvetica_visible

render = Image.open(png_path).convert("RGB")
white = Image.new("RGB", render.size, "white")
content_bbox = ImageChops.difference(render, white).getbbox()
assert content_bbox is not None
assert content_bbox[0] > 20 and content_bbox[1] > 20
assert content_bbox[2] < render.width - 20 and content_bbox[3] < render.height - 20

sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest().upper()
print("VERIFY_OK")
print(f"file={pdf_path}")
print(f"bytes={pdf_path.stat().st_size}")
print("pages=1")
print("page_size=A4")
print(f"text_chars={len(text)}")
print(f"embedded_fonts={embedded_fonts}")
print("visible_default_font_text=0")
print(f"links={len(uris)}")
print(f"render_size={render.size}")
print(f"content_bbox={content_bbox}")
print(f"sha256={sha256}")
