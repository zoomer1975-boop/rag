"""file_guard 단위 테스트"""

import io
import zipfile

import pytest

from app.services.security import file_guard
from app.services.security.types import SecurityError

_PDF_MAGIC = b"%PDF-1.4 test content"
_ZIP_MAGIC = b"PK\x03\x04"


def _make_docx(extra_files: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", b"<xml/>")
        if extra_files:
            for name, data in extra_files.items():
                zf.writestr(name, data)
    return buf.getvalue()


# --- PDF ---

def test_valid_pdf_passes():
    file_guard.validate(_PDF_MAGIC, ".pdf")


def test_pdf_magic_mismatch_blocked():
    with pytest.raises(SecurityError) as exc_info:
        file_guard.validate(b"not a pdf", ".pdf")
    assert exc_info.value.threat.category == "magic_mismatch"


def test_pdf_javascript_blocked():
    content = _PDF_MAGIC + b" /JS (alert(1))"
    with pytest.raises(SecurityError) as exc_info:
        file_guard.validate(content, ".pdf")
    assert exc_info.value.threat.category == "pdf_active_content"


def test_pdf_launch_blocked():
    content = _PDF_MAGIC + b" /Launch << /F (cmd.exe) >>"
    with pytest.raises(SecurityError) as exc_info:
        file_guard.validate(content, ".pdf")
    assert exc_info.value.threat.category == "pdf_active_content"


# --- DOCX ---

def test_valid_docx_passes():
    docx = _make_docx()
    file_guard.validate(docx, ".docx")


def test_docx_magic_mismatch_blocked():
    with pytest.raises(SecurityError) as exc_info:
        file_guard.validate(b"not a zip", ".docx")
    assert exc_info.value.threat.category == "magic_mismatch"


def test_docx_with_macro_blocked():
    docx = _make_docx({"word/vbaProject.bin": b"\x00" * 100})
    with pytest.raises(SecurityError) as exc_info:
        file_guard.validate(docx, ".docx")
    assert exc_info.value.threat.category == "docx_macro"


def test_zip_bomb_ratio_blocked():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big.txt", b"A" * (10 * 1024 * 1024))
    content = buf.getvalue()
    compressed_size = len(content)
    # 압축률 50x 이상이면 차단 — 10MB/tiny_compressed 는 통과 가능성 있으므로
    # 실제 ZIP bomb 모킹 대신 임계값 경계를 직접 검증
    import zipfile as zf_mod
    with zf_mod.ZipFile(io.BytesIO(content)) as z:
        total_uncompressed = sum(i.file_size for i in z.infolist())
        total_compressed = sum(i.compress_size for i in z.infolist())
    ratio = total_uncompressed / total_compressed if total_compressed > 0 else 0
    # ratio가 50 이하면 파일 가드 통과는 정상
    if ratio <= 50:
        file_guard.validate(content, ".docx")
    else:
        with pytest.raises(SecurityError):
            file_guard.validate(content, ".docx")


# --- TXT / MD ---

def test_txt_passes():
    file_guard.validate(b"hello world", ".txt")


def test_md_passes():
    file_guard.validate(b"# Heading\ncontent", ".md")


# --- 지원하지 않는 형식 ---

def test_unsupported_extension_blocked():
    with pytest.raises(SecurityError) as exc_info:
        file_guard.validate(b"data", ".exe")
    assert exc_info.value.threat.category == "unsupported_type"
