"""Format checks for account and school details (registration, profile, sign-in). Each returns the cleaned value or
raises ValueError with a message the registration chat can show as it is."""
import re

_EMAIL = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
_PIN = re.compile(r"^[1-9][0-9]{5}$")


def person_name(value: str, what: str = "Name") -> str:
    """Letters in any script (Tamil, Hindi...), spaces, dots, apostrophes and hyphens; at least two letters."""
    v = re.sub(r"\s+", " ", value or "").strip()
    if sum(c.isalpha() for c in v) < 2:
        raise ValueError(f"{what} must have at least two letters.")
    if any(not (c.isalpha() or c in " .'-" or unicodedata_mark(c)) for c in v):
        raise ValueError(f"{what} can contain only letters, spaces, dots, apostrophes and hyphens.")
    return v


def unicodedata_mark(c: str) -> bool:
    """Combining vowel signs (Tamil/Devanagari matras) are part of a letter, not punctuation."""
    import unicodedata
    return unicodedata.category(c).startswith("M")


def place_name(value: str, what: str) -> str:
    v = re.sub(r"\s+", " ", value or "").strip()
    if sum(c.isalpha() for c in v) < 2:
        raise ValueError(f"{what} must have at least two letters.")
    return v


def phone(value: str) -> str:
    """Indian phone: 10 digits once spaces, dashes, brackets and a +91 / 0 prefix are removed (landlines included)."""
    digits = re.sub(r"[\s\-()]", "", value or "")
    digits = re.sub(r"^(\+91|0091|91(?=\d{10}$)|0(?=\d{10}$))", "", digits)
    if not re.fullmatch(r"\d{10}", digits):
        raise ValueError("Enter a valid 10-digit phone number.")
    return digits


def email(value: str) -> str:
    v = (value or "").strip().lower()
    if len(v) > 254 or not _EMAIL.fullmatch(v):
        raise ValueError("Enter a valid email address, like name@school.edu.")
    return v


def pin_code(value: str) -> str:
    v = re.sub(r"\s", "", value or "")
    if not _PIN.fullmatch(v):
        raise ValueError("Enter a valid 6-digit PIN code.")
    return v
