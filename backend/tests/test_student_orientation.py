import hashlib
import json

from PIL import Image, ImageDraw

from app.ocr.orientation import sideways_ruled_page
from app.ocr import internvl
from app.ocr.schemas import StudentPageResult


def ruled(path, sideways=True):
    image = Image.new("RGB", (600, 800), "white")
    draw = ImageDraw.Draw(image)
    for y in range(60, 760, 25):
        draw.line((25, y, 575, y), fill="#4090b0", width=2)
    if sideways:
        image = image.rotate(-90, expand=True)
    image.save(path)


def test_ruled_orientation_requires_distributed_vertical_rules(tmp_path):
    path = tmp_path / "source.png"
    ruled(path)
    assert sideways_ruled_page(path)
    ruled(path, False)
    assert not sideways_ruled_page(path)
    Image.new("RGB", (600, 800), "white").save(path)
    assert not sideways_ruled_page(path)


def test_student_ocr_rotates_copy_and_restores_source_bbox_and_provenance(tmp_path, monkeypatch):
    path = tmp_path / "source.png"
    ruled(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    def read(system, prompt, image_path, **kwargs):
        with Image.open(image_path) as image:
            assert image.size == (600, 800)
        assert "600x800 pixels" in prompt
        return json.dumps({"answers": [{"question_number": "8", "answer_text": "(ii) visible work",
            "bbox": {"x": 20, "y": 30, "width": 100, "height": 50}}]})
    monkeypatch.setattr(internvl, "_call_once", read)
    result = internvl.chat_structured("read ink", "800x600 pixels", StudentPageResult, path)
    assert result.parsed.answers[0].bbox.model_dump() == {"x": 720, "y": 20, "width": 50, "height": 100}
    raw = json.loads(result.raw)
    assert raw["answers"][0]["bbox"]["x"] == 720
    assert raw["_source_view"]["provider_raw"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert not list(tmp_path.glob("*upright*"))
