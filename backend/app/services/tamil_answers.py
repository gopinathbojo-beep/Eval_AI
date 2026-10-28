"""Student answer sheets for Tamil subjects (paper_format.TAMIL), in place of the shared segmenter.

A Tamil answer sheet reads like its paper: "வினா 1." (or just "1") opens an answer, அ) ஆ) இ) parts follow inside it,
and everything up to the next question number belongs to it, across pages. IndicOCR returns blocks that do not
follow those boundaries:
  - one block holds the end of an answer and the next question's heading ("... வேண்டும்\\nவினா 4. ..."), or several
    whole answers ("இ) ...\\nவானா 8. ...\\nபகுதி-இ: ...\\nவினா 9. ...");
  - the handwritten "வினா" comes back misread: "அனா 7.", "வானா 8.", "அணா 10.";
  - parts come back as labels "(a)", "(b)", "(c)" and continuation blocks with no label at all.
So answers are rebuilt from question numbers alone: a number the paper has and that moves forward starts the next
answer; parts, unlabelled blocks and the next page continue the current one. The sheet's title lines before the
first answer and the பகுதி headings belong to no answer.
"""
from __future__ import annotations
import re
from typing import Any

from . import tamil_format
from .doc_structure import is_section_heading_line
from .numbering import normalize_question_number, parent_number, subpart_path
from .student_segmentation import SegmentedAnswer, _merge_bboxes

# "வினா 7." as written by hand and read by IndicOCR: வினா, அனா, வானா, அணா, ஆனா (and the printed கேள்வி); the
# full stop is often lost ("வினா 9 கடிதம் ...")
_HEAD = re.compile(r"(?m)^[ \t]*(?:[வஅஆ][ிா]?[னண]ா|கேள்வி)[ \t]*(?:எண்[ \t]*)?(\d{1,2})(?:[ \t]*[.:)]|(?=[ \t]+[஀-௿]))[ \t]*")
_MAX_SKIP = 2  # a question number may jump this far past the last one (a skipped question)
_TAMIL_WORD = re.compile(r"[஀-௿]{3,}")
_COMMON_WORDS = {"மதிப்பெண்கள்", "மதிப்பெண்", "கீழ்க்கண்ட", "விடையளிக்கவும்", "வினாக்களுக்கு", "எழுதுக", "விடை", "விடைகள்"}
# IndicOCR sometimes "reads" a smudge as another Indian script (Bengali, Devanagari ...): such lines are noise
_OTHER_INDIC = re.compile(r"[ऀ-୿ఀ-෿]")


def _pieces(label: str | None, text: str) -> list[tuple[str | None, str, bool]]:
    """The block cut at every question heading inside it: (label, text, opened by a வினா heading)."""
    cuts = [m for m in _HEAD.finditer(text) if m.start() > 0 or not label]
    if not cuts:
        return [(label, text, False)]
    out = [(label, text[:cuts[0].start()], False)] if text[:cuts[0].start()].strip() else []
    for i, m in enumerate(cuts):
        out.append((m.group(1), text[m.end():cuts[i + 1].start() if i + 1 < len(cuts) else len(text)], True))
    return out


def _same_title(heading: str, question_text: str | None) -> bool:
    """The heading copies the question's title ("படித்துப் புரிந்து விடையளித்தல்"): a shared distinctive word."""
    words = set(_TAMIL_WORD.findall(heading.partition("\n")[0])) - _COMMON_WORDS
    return bool(words & set(_TAMIL_WORD.findall(question_text or "")))


def _part_marker(token: str) -> str:
    """"அ)" for part a, "ii)" as it is."""
    if len(token) == 1 and token in "abcdefgh":
        token = tamil_format.SUB_LETTERS["abcdefgh".index(token)]
    return f"{token})"


def _drop_section_lines(text: str) -> str:
    """Without பகுதி headings (a heading wrapped onto a second line ending in its marks, too) and without lines of
    another Indian script that hold no Tamil (OCR noise)."""
    out: list[str] = []
    after_heading = False
    for line in text.splitlines():
        s = line.strip()
        if is_section_heading_line(s):
            after_heading = True
            continue
        if after_heading and re.search(r"\(\s*\d+\s*மதிப்பெண்", s) and len(s.split()) <= 6:
            after_heading = False
            continue
        after_heading = False
        if _OTHER_INDIC.search(s) and not tamil_format.has_tamil(s):
            continue
        out.append(line)
    return "\n".join(out)


def segment(page_results: list[tuple[dict, Any]], canonical_questions: list[Any] | None = None) -> list[SegmentedAnswer]:
    exam_norms = {getattr(q, "normalized_number", None) for q in canonical_questions or []}
    tops = {int(p) for n in exam_norms if (p := parent_number(n or "")).isdigit()}
    texts_by_num = {int(p): getattr(q, "question_text", "") for q in canonical_questions or []
                    if (p := parent_number(getattr(q, "normalized_number", None) or "")).isdigit()}
    answers: list[dict] = []  # {num, part, label, texts, page, bbox, confs}

    def start(num: int, part: str | None, label: str, page: int, bbox: dict | None) -> None:
        answers.append({"num": num, "part": part, "label": label, "texts": [], "page": page, "bbox": bbox, "confs": []})

    for page_info, page_res in page_results:
        page = page_info["page_number"]
        for item in getattr(page_res, "answers", []):
            bbox = item.bbox.model_dump() if getattr(item, "bbox", None) else None
            conf = getattr(item, "ocr_confidence", None)
            block_label = (item.question_number or "").strip() or None
            text = tamil_format.strip_page_furniture((item.answer_text or "").strip())
            for label, piece, from_heading in _pieces(block_label, text):
                piece = _drop_section_lines(piece).strip()
                if not piece and not label:
                    continue
                if not label and tamil_format.is_total_line(piece):
                    continue
                norm = normalize_question_number(label) if label else None
                top = int(parent_number(norm)) if norm and parent_number(norm).isdigit() else None
                last = answers[-1]["num"] if answers else 0
                parts = subpart_path(norm)
                # "வினா 1. படித்துப் புரிந்து ..." after Q6: a handwritten 7 read as 1. A வினா heading going backwards
                # is the next question when it carries that question's title.
                if (from_heading and top is not None and answers and top <= last
                        and (not tops or last + 1 in tops) and _same_title(piece, texts_by_num.get(last + 1))):
                    top, label, norm = last + 1, str(last + 1), str(last + 1)

                # The next question: a number the paper has, moving forward (the first answer may be any of them:
                # the student skipped the opening questions)
                if top is not None and (not tops or top in tops) and last < top and (not answers or top <= last + _MAX_SKIP + 1):
                    part = parts[0] if parts and f"{top}({parts[0]})" in exam_norms else None
                    start(top, part, label, page, bbox)
                    if parts and not part:
                        piece = f"{_part_marker(parts[0])} {piece}"
                elif not answers:
                    continue  # the sheet's title lines, the student's name: no answer yet
                else:
                    cur = answers[-1]
                    if norm and norm.startswith("(") and parts:
                        tok = parts[-1]
                        if f"{cur['num']}({tok})" in exam_norms:  # the paper scores this part on its own
                            start(cur["num"], tok, f"{cur['num']}({tok})", page, bbox)
                        elif not re.match(rf"^\s*\(?{re.escape(_part_marker(tok)[:-1])}[)\.]", piece):
                            piece = f"{_part_marker(tok)} {piece}"
                    elif label:
                        piece = f"{label} {piece}"  # a number that is no question here: keep it in the text
                cur = answers[-1]
                if piece:
                    cur["texts"].append(piece)
                if conf is not None:
                    cur["confs"].append(conf)
                if bbox and cur["page"] == page:
                    cur["bbox"] = _merge_bboxes(cur["bbox"], bbox)

    out = []
    for i, a in enumerate(answers, 1):
        norm = f"{a['num']}({a['part']})" if a["part"] else str(a["num"])
        text = "\n".join(a["texts"]).strip()
        out.append(SegmentedAnswer(
            raw_question_number=a["label"], normalized_number=norm, answer_text=text, raw_ocr_text=text,
            page_number=a["page"], bbox=a["bbox"],
            ocr_confidence=round(sum(a["confs"]) / len(a["confs"]), 2) if a["confs"] else None, position=i,
        ))
    return out


# "கீழ்க்கண்ட தலைப்புகளில் ஏதேனும் ஒன்றைப் பற்றி ... கட்டுரை எழுதுக. அ) ... ஆ) ... இ) ...": write on any ONE topic
_ONE_OF = re.compile(r"(?:ஏதேனும்|எவையேனும்)\s*ஒன்ற")
_OPTION_LINE = re.compile(rf"(?m)^[ \t]*\(?[ \t]*([{tamil_format.SUB_LETTERS}])[ \t]*\)[ \t]*")


def one_of_attempts(question_text: str | None, answer_text: str | None) -> list[tuple[str, str]]:
    """A question asking for any one of its topics, answered on several: [(topic heading, that attempt's text)], in
    the order written, so each is graded and the best counts. [] when the question is not of that kind or the
    student wrote on one topic only."""
    if not _ONE_OF.search(question_text or "") or not answer_text:
        return []
    options = [m.group(1) for m in _OPTION_LINE.finditer(question_text)]
    if len(options) < 2:
        return []
    starts, seen = [], set()
    for m in _OPTION_LINE.finditer(answer_text):
        letter = m.group(1)
        # each topic once, in the paper's order: a later "அ)" inside an essay is the essay's own list
        if letter in options and letter not in seen and (not starts or options.index(letter) > options.index(starts[-1][0])):
            starts.append((letter, m))
            seen.add(letter)
    if len(starts) < 2:
        return []
    out = []
    for i, (letter, m) in enumerate(starts):
        body = answer_text[m.end():starts[i + 1][1].start() if i + 1 < len(starts) else len(answer_text)].strip()
        out.append((f"{letter}) {body.partition(chr(10))[0].strip()}", f"{letter}) {body}"))
    return out


# --- Checking the grader's deductions against the student's own text ------------------------------------------------
# The grading model sometimes deducts for a marking point the answer plainly contains (it wrote "ஒழுக்கத்தையும் ...
# வாழ்க்கையில் முன்னேற", the model says "ஒழுக்கம் அல்லது வாழ்க்கை முன்னேற்றம்" is missing). A deduction stands only when
# a point it names is really absent; a word is present when, without a final ம், it starts a word of the answer
# (ஒழுக்கம் ~ ஒழுக்கத்தையும், முன்னேற்றம் ~ முன்னேற), never by a changed ending (சென்றாள் is not சென்றான்).

_SCHEME_WORDS: set[str] | None = None  # the marking-scheme words, stemmed on first use
_SCHEME_TEXT = ("மதிப்பெண் மதிப்பெண்கள் குறிப்பிடுதல் பெறுதல் அல்லது மற்றும் மூலம் சரியான விடை விடைகள் எழுதுதல் "
                "கூறுதல் விளக்குதல் ஒவ்வொரு ஒவ்வொன்றும் மதிப்பீட்டுத் திட்டம் சொல் சொல்")
RESTORED_NOTE = "Marks restored: every point the AI called missing is in the student's answer."
KEY_COPY_NOTE = "Full marks: the answer contains every word of the model answer."


def _scheme_words() -> set[str]:
    global _SCHEME_WORDS
    if _SCHEME_WORDS is None:
        _SCHEME_WORDS = tamil_format.indic_tokens(_SCHEME_TEXT)
    return _SCHEME_WORDS


def _present(word: str, answer_words: set[str]) -> bool:
    if word in answer_words:
        return True
    root = word[:-1] if word.endswith("ம") else word
    return len(root) >= 3 and any(w.startswith(root) for w in answer_words)


def _point_present(point: str, answer_words: set[str]) -> bool:
    """A named point is in the answer: all its words for a one- or two-word point ("சென்றான்"), else two thirds (the
    grader rewords and misspells the points it names: "வாழ்கை" for "வாழ்க்கை")."""
    words = _content(point)
    found = sum(_present(w, answer_words) for w in words)
    return found == len(words) if len(words) <= 2 else found * 3 >= len(words) * 2


def _content(text: str) -> set[str]:
    return tamil_format.indic_tokens(re.sub(r"\d+(?:\.\d+)?|½", " ", text or "")) - _scheme_words()


def check_deductions(result: Any, answer_text: str, key_text: str | None, max_marks: float) -> Any:
    """The grader's result, with marks restored where its deduction is contradicted by the student's text."""
    if result.marks_awarded >= max_marks or not tamil_format.has_tamil(answer_text):
        return result
    answer = _content(answer_text)
    key = _content(key_text or "")
    named = [p for p in (result.missing_points or []) if _content(str(p))]
    if key and key <= answer:
        note = KEY_COPY_NOTE
    elif named and all(_point_present(str(p), answer) for p in named):
        note = RESTORED_NOTE
    else:
        return result
    result.marks_awarded, result.decision, result.missing_points = max_marks, "CORRECT", []
    result.feedback = f"{(result.feedback or '').strip()} ({note})".strip()
    return result
