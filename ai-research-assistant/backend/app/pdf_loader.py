from dataclasses import dataclass
from pathlib import Path

import fitz

from app.config import OCR_LANGUAGE


@dataclass(frozen=True)
class PDFPage:
    page_number: int
    text: str
    extraction_method: str = "text"


@dataclass(frozen=True)
class PDFTextExtractionResult:
    pages: list[PDFPage]
    ocr_attempted: bool = False
    ocr_available: bool = True

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages if page.text)

    @property
    def character_count(self) -> int:
        return len(self.text)

    @property
    def extraction_method(self) -> str:
        if any(page.extraction_method == "ocr" for page in self.pages):
            return "ocr"
        return "text"


def _extract_page_text_with_ocr(page: fitz.Page) -> tuple[str, bool]:
    """Return OCR text for a page when the local PyMuPDF OCR runtime is available."""
    try:
        textpage = page.get_textpage_ocr(language=OCR_LANGUAGE, full=True)
        return page.get_text("text", textpage=textpage).strip(), True
    except RuntimeError:
        return "", False


def extract_text_from_pdf(
    pdf_path: Path,
    *,
    use_ocr_fallback: bool = False,
) -> PDFTextExtractionResult:
    """Extract text from every page of a PDF using PyMuPDF, with optional OCR fallback."""
    pages: list[PDFPage] = []
    ocr_attempted = False
    ocr_available = True

    with fitz.open(pdf_path) as document:
        for page_index, page in enumerate(document, start=1):
            text = page.get_text("text").strip()
            extraction_method = "text"

            if not text and use_ocr_fallback:
                ocr_attempted = True
                text, ocr_available = _extract_page_text_with_ocr(page)
                extraction_method = "ocr" if text else "text"

            pages.append(
                PDFPage(
                    page_number=page_index,
                    text=text,
                    extraction_method=extraction_method,
                )
            )

    return PDFTextExtractionResult(
        pages=pages,
        ocr_attempted=ocr_attempted,
        ocr_available=ocr_available,
    )
