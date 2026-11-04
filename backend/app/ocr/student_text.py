"""Explicit cancellation markers are source annotations, never positive grading evidence."""
import re


def cancelled_block(block):
    return isinstance(block, dict) and (
        any(block.get(flag) is True for flag in ("crossed_out", "is_crossed_out", "cancelled", "is_cancelled"))
        or str(block.get("type") or "").lower() in {"crossed_out", "struck_out", "cancelled"}
    )


def active_student_text(text):
    text = re.sub(r"~~[\s\S]*?~~", "", text or "")
    text = re.sub(r"<(?:del|s|strike)\b[^>]*>[\s\S]*?</(?:del|s|strike)>", "", text, flags=re.I)
    return re.sub(r"\[(?:crossed[- ]out|struck[- ]out|cancelled)\s*:[^\]]*\]", "", text, flags=re.I)
