"""파일 업로드 보안 검사 — 매직바이트, ZIP bomb, PDF/DOCX 활성 콘텐츠"""

from __future__ import annotations

import io
import logging
import zipfile

from .patterns import PDF_DANGEROUS_KEYWORDS
from .types import SecurityError, Severity, Threat

logger = logging.getLogger(__name__)

# 매직바이트 시그니처
_PDF_MAGIC = b"%PDF"
_ZIP_MAGIC = b"PK\x03\x04"  # DOCX는 ZIP 포맷

# ZIP bomb 임계값
_MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 200MB
_MAX_COMPRESSION_RATIO = 50  # 압축 비율 50배 초과 시 차단


def validate(content: bytes, extension: str) -> None:
    """파일 바이트와 확장자를 검사한다. 위반 시 SecurityError 발생."""
    ext = extension.lower().lstrip(".")

    if ext == "pdf":
        _check_pdf_magic(content)
        _check_pdf_active_content(content)
    elif ext == "docx":
        _check_zip_magic(content, extension)
        _check_zip_bomb(content, extension)
        _check_docx_macros(content)
    elif ext in ("txt", "md"):
        # 텍스트 파일은 매직바이트 검사 생략 (UTF-8 BOM 허용)
        pass
    else:
        raise SecurityError(
            Threat(
                category="unsupported_type",
                severity=Severity.MEDIUM,
                detail=f"지원하지 않는 파일 확장자: {extension}",
            )
        )


def _check_pdf_magic(content: bytes) -> None:
    if not content.startswith(_PDF_MAGIC):
        raise SecurityError(
            Threat(
                category="magic_mismatch",
                severity=Severity.HIGH,
                detail="파일이 PDF 시그니처(%PDF)로 시작하지 않습니다. 폴리글롯 파일 의심.",
                location="file header",
            )
        )


def _check_zip_magic(content: bytes, extension: str) -> None:
    if not content.startswith(_ZIP_MAGIC):
        raise SecurityError(
            Threat(
                category="magic_mismatch",
                severity=Severity.HIGH,
                detail=f"{extension} 파일이 ZIP 시그니처(PK)로 시작하지 않습니다. 폴리글롯 파일 의심.",
                location="file header",
            )
        )


def _check_zip_bomb(content: bytes, extension: str) -> None:
    """ZIP 압축 해제 없이 메타데이터만 검사한다."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            total_uncompressed = sum(info.file_size for info in zf.infolist())
            total_compressed = sum(info.compress_size for info in zf.infolist())

            if total_uncompressed > _MAX_UNCOMPRESSED_BYTES:
                raise SecurityError(
                    Threat(
                        category="zip_bomb",
                        severity=Severity.CRITICAL,
                        detail=(
                            f"압축 해제 크기({total_uncompressed // 1024 // 1024}MB)가 "
                            f"허용 한도({_MAX_UNCOMPRESSED_BYTES // 1024 // 1024}MB)를 초과합니다."
                        ),
                    )
                )

            if total_compressed > 0:
                ratio = total_uncompressed / total_compressed
                if ratio > _MAX_COMPRESSION_RATIO:
                    raise SecurityError(
                        Threat(
                            category="zip_bomb",
                            severity=Severity.CRITICAL,
                            detail=(
                                f"압축 비율({ratio:.0f}x)이 허용 한도({_MAX_COMPRESSION_RATIO}x)를 초과합니다. "
                                "ZIP bomb 의심."
                            ),
                        )
                    )
    except SecurityError:
        raise
    except zipfile.BadZipFile:
        raise SecurityError(
            Threat(
                category="corrupt_archive",
                severity=Severity.HIGH,
                detail=f"손상된 ZIP/DOCX 파일입니다.",
            )
        )
    except Exception as exc:
        logger.warning("ZIP 검사 중 예외 발생: %s", exc)


def _check_pdf_active_content(content: bytes) -> None:
    """PDF 바이트에서 위험한 키워드를 탐지한다 (파싱 없이 바이트 스캔)."""
    found = [kw.decode() for kw in PDF_DANGEROUS_KEYWORDS if kw in content]
    if found:
        logger.warning("PDF 활성 콘텐츠 탐지: %s", found)
        raise SecurityError(
            Threat(
                category="pdf_active_content",
                severity=Severity.HIGH,
                detail=f"PDF에 위험한 요소가 포함되어 있습니다: {', '.join(found)}",
                location="pdf body",
            )
        )


def _check_docx_macros(content: bytes) -> None:
    """DOCX ZIP 내 vbaProject.bin(매크로) 존재 여부를 검사한다."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names = zf.namelist()
            macro_files = [n for n in names if "vbaProject" in n or n.endswith(".bin")]
            if macro_files:
                raise SecurityError(
                    Threat(
                        category="docx_macro",
                        severity=Severity.HIGH,
                        detail=f"DOCX에 매크로 파일이 포함되어 있습니다: {', '.join(macro_files)}",
                        location="docx archive",
                    )
                )
    except SecurityError:
        raise
    except Exception as exc:
        logger.warning("DOCX 매크로 검사 중 예외 발생: %s", exc)
