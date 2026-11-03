"""Build app/cbse/textbook_subjects.json, the Create Exam subject list, from the "CBSE - Website/Text Books" folder.

The folder is not deployed, so the list is generated here and committed. One subject per subject folder: parts
(Part 1/Part 2 zips, Social Science's Economics/History/... subfolders) are already inside it, and "Hindi Course A"
and "Hindi Course B" join into "Hindi". Tamil has no textbook there but is added. Each subject lists the CBSE paper
profiles it can be (cbse/catalog.py), the usual one first; the uploaded question paper picks between them.

Run: .venv\\Scripts\\python scripts\\build_textbook_subjects.py
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.cbse.catalog import PROFILES  # noqa: E402

ROOT = Path(__file__).resolve().parents[2] / "CBSE - Website" / "Text Books"
OUT = Path(__file__).resolve().parents[1] / "app" / "cbse" / "textbook_subjects.json"
BUILT_IN = ["Tamil"]
USUAL = {"184", "002", "041"}  # English Language and Literature, Hindi Course A, Mathematics Standard


def join_name(folder: str) -> str:
    return re.sub(r"\s+Course\s+[A-Z]$", "", folder.strip())  # "Hindi Course B" -> "Hindi"


def profiles_for(name: str, grade: int) -> list[str]:
    n = name.casefold()
    hits = [p for p in PROFILES if p["class_level"] == grade
            and (p["name"].casefold() == n or p["name"].casefold().startswith(n + " ")
                 or n in [a.casefold() for a in p["aliases"]])]
    hits.sort(key=lambda p: p["code"] not in USUAL)
    return [p["id"] for p in hits]


def main() -> None:
    out = {}
    for grade_dir in sorted(ROOT.glob("Class *")):
        grade = int(grade_dir.name.split()[-1])
        names = {join_name(d.name) for d in grade_dir.iterdir() if d.is_dir()} | set(BUILT_IN)
        out[str(grade)] = [{"key": f"{grade}-{re.sub(r'[^a-z0-9]+', '-', n.casefold()).strip('-')}", "name": n,
                            "profiles": profiles_for(n, grade)} for n in sorted(names)]
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for grade, subjects in out.items():
        print(f"Class {grade}:", ", ".join(f"{s['name']}{'' if s['profiles'] else ' (generic)'}" for s in subjects))


if __name__ == "__main__":
    main()
