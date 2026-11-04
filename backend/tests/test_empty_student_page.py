import hashlib
import json

from PIL import Image

from app.ocr import internvl
from app.ocr.schemas import StudentPageResult


def test_empty_scan_recheck_retains_original_image_and_coordinate_system(tmp_path, monkeypatch):
    image = tmp_path / "source.png"
    Image.new("RGB", (200, 300), "white").save(image)
    original = hashlib.sha256(image.read_bytes()).hexdigest()
    sizes = []

    def call(system, user, image_path, **kwargs):
        with Image.open(image_path) as im:
            sizes.append(im.size)
        if len(sizes) == 1:
            return '{"page_number":2,"answers":[]}'
        assert "Do not mistake missing question numbers for an empty page" in user
        return json.dumps({"page_number": 2, "answers": [{"answer_text": "5 + 6 = 11",
            "bbox": {"x": 10, "y": 20, "width": 40, "height": 50}}]})

    monkeypatch.setattr(internvl, "_call_once", call)
    result = internvl.chat_structured("Read only visible ink", "page 2 (200x300 pixels)", StudentPageResult, image)
    assert sizes == [(200, 300), (300, 200)]
    assert result.parsed.answers[0].bbox.model_dump() == {"x": 130, "y": 10, "width": 50, "height": 40}
    assert hashlib.sha256(image.read_bytes()).hexdigest() == original
    assert not list(tmp_path.glob("*orientation*"))
