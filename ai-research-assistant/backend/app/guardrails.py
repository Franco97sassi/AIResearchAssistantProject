import re
from dataclasses import dataclass

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)")
INJECTION_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"ignore (all )?(previous|prior) instructions",
        r"ignora (todas )?(las )?instrucciones",
        r"system prompt",
        r"developer message",
        r"reveal.*(prompt|instructions)",
        r"act as (?:dan|jailbreak)",
    ]
]

@dataclass(frozen=True)
class GuardrailResult:
    allowed: bool
    pii: dict[str, int]
    prompt_injection: bool
    violations: list[str]


def _luhn(value: str) -> bool:
    digits = [int(ch) for ch in re.sub(r"\D", "", value)]
    if len(digits) < 13:
        return False
    total = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def inspect_text(text: str) -> GuardrailResult:
    emails = EMAIL_RE.findall(text)
    phones = PHONE_RE.findall(text)
    cards = [match.group(0) for match in CARD_RE.finditer(text) if _luhn(match.group(0))]
    prompt_injection = any(pattern.search(text) for pattern in INJECTION_PATTERNS)
    violations: list[str] = []
    if emails or phones or cards:
        violations.append("pii_detected")
    if prompt_injection:
        violations.append("prompt_injection_detected")
    return GuardrailResult(
        allowed=not prompt_injection,
        pii={"emails": len(emails), "phones": len(phones), "cards": len(cards)},
        prompt_injection=prompt_injection,
        violations=violations,
    )


def answer_has_required_sources(answer: str, source_count: int) -> bool:
    if source_count == 0:
        return True
    normalized = answer.lower()
    return "pagina" in normalized or "página" in normalized or "fuente" in normalized
