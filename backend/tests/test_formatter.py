"""Subject formatters (app/formatter): one per subject, chosen by the exam's subject; common/ for the rest."""
import pytest

from app.cbse import formatter
from app.services import paper_format


@pytest.mark.parametrize("name,key", [
    ("Tamil", "tamil"), ("Tamil II", "tamil"), ("தமிழ்", "tamil"), ("English", "english"), ("Maths", "maths"),
    ("math", "maths"), ("Mathematics", "maths"), ("physics", "physics"), ("Chemistry", "chemistry"),
    ("Biology", "common"), (None, None),
])
def test_subject_picks_its_formatter(name, key):
    assert formatter.for_subject(name) == key


def test_current_formatter_follows_the_subject_and_falls_back_to_common():
    assert formatter.current().__name__ == "app.cbse.formatter.common"  # no exam in context
    with formatter.use("maths"):
        assert formatter.current().__name__ == "app.cbse.formatter.maths"
        assert formatter.current().parse_paper([]) is None  # nothing of its own yet: the shared parser runs
    with formatter.use("tamil"):
        assert formatter.current().uses_pdf_text() is False
    with paper_format.use(paper_format.TAMIL):  # scripts and tests that only set the paper format
        assert formatter.current().__name__ == "app.cbse.formatter.tamil"
    assert formatter.current().__name__ == "app.cbse.formatter.common"


def test_every_formatter_offers_every_hook():
    from app.cbse.formatter import common
    for key in [*formatter.SUBJECTS, formatter.COMMON]:
        module = formatter.get(key)
        assert all(callable(getattr(module, hook, None)) for hook in common.__all__), key
