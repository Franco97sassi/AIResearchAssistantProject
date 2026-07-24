from dataclasses import dataclass
import re


@dataclass(frozen=True)
class InvoiceExtraction:
    cliente: str
    importe: float
    moneda: str | None
    fecha: str | None
    numero_factura: str | None
    confidence: float
    missing_fields: list[str]


def _clean_value(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip(" :-#\t")


def _find_first(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return _clean_value(match.group(1))
    return None


def _parse_amount(raw_amount: str | None) -> float:
    if not raw_amount:
        return 0.0

    normalized = raw_amount.strip().replace(" ", "")
    if "," in normalized and "." in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    elif "," in normalized:
        normalized = normalized.replace(",", ".")

    normalized = re.sub(r"[^0-9.]", "", normalized)
    try:
        return float(normalized)
    except ValueError:
        return 0.0


def extract_invoice_fields(text: str) -> InvoiceExtraction:
    """Best-effort invoice field extraction from OCR/text PDF content."""
    cliente = _find_first(
        [
            r"(?:cliente|customer|bill\s+to|facturar\s+a)\s*[:\-]\s*(.+)",
            r"(?:señor(?:es)?|senor(?:es)?)\s*[:\-]\s*(.+)",
        ],
        text,
    )
    invoice_number = _find_first(
        [
            r"(?:factura|invoice|n(?:ú|u)mero|no\.?|nro\.?)\s*(?:#|n(?:ú|u)mero)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-/.]+)",
        ],
        text,
    )
    date = _find_first(
        [
            r"(?:fecha|date)\s*[:\-]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            r"(?:fecha|date)\s*[:\-]\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        ],
        text,
    )
    amount_raw = _find_first(
        [
            r"(?:total\s+a\s+pagar|importe\s+total|total|amount\s+due|importe)\s*[:\-]?\s*(?:USD|US\$|\$|EUR|€)?\s*([0-9][0-9.,]*)",
        ],
        text,
    )
    amount = _parse_amount(amount_raw)
    currency = _find_first(
        [
            r"\b(USD|EUR|ARS|MXN|COP|CLP|PEN)\b",
            r"(US\$|\$|€)",
        ],
        text,
    )

    missing_fields: list[str] = []
    if not cliente:
        missing_fields.append("cliente")
    if amount <= 0:
        missing_fields.append("importe")
    if not date:
        missing_fields.append("fecha")
    if not invoice_number:
        missing_fields.append("numero_factura")

    total_fields = 4
    confidence = round((total_fields - len(missing_fields)) / total_fields, 2)

    return InvoiceExtraction(
        cliente=cliente or "",
        importe=amount,
        moneda=currency,
        fecha=date,
        numero_factura=invoice_number,
        confidence=confidence,
        missing_fields=missing_fields,
    )
