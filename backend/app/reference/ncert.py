"""NCERT file names: jemh101 = class 10, English medium, book 'mh', part 1, chapter 1; leph1an = class 12 answers."""
import re
from dataclasses import dataclass

_CLASS = {"f": 6, "g": 7, "h": 8, "i": 9, "j": 10, "k": 11, "l": 12}
_NAME = re.compile(r"^(?P<cls>[f-l])(?P<lang>[ehu])(?P<book>[a-z]{2,3})(?P<part>\d)(?P<tail>\d\d|an|ps|a\d|lp|cc|dd)$")


@dataclass(frozen=True)
class NcertName:
    standard: int
    book: str
    part: int
    kind: str  # chapter, answers, appendix, front, cover, lesson-plan, bundle
    chapter: int | None = None


def parse(filename: str) -> NcertName | None:
    stem = re.sub(r"\.(pdf|zip|jpg)$", "", filename.rsplit("/", 1)[-1].lower())
    m = _NAME.match(stem)
    if not m:
        return None
    tail = m["tail"]
    kind, chapter = {"an": ("answers", None), "ps": ("front", None), "lp": ("lesson-plan", None),
                     "cc": ("cover", None), "dd": ("bundle", None)}.get(tail, (None, None))
    if kind is None:
        kind, chapter = ("appendix", int(tail[1])) if tail[0] == "a" else ("chapter", int(tail))
    return NcertName(_CLASS[m["cls"]], m["book"], int(m["part"]), kind, chapter)
