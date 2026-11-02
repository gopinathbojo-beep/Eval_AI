"""Visual ownership must follow source question boundaries, including continuations."""
from io import BytesIO
from types import SimpleNamespace

import pymupdf
import pytest
from PIL import Image

from app.cbse import layout
from app.cbse.extraction import Fragment, Page, VisualEvidence


def source_pdf(tmp_path, monkeypatch):
    path = tmp_path / "paper.pdf"
    pdf = pymupdf.open()
    first = pdf.new_page(width=600, height=800)
    first.insert_text((40, 650), "Q26. Prove that a number is irrational.")
    first.insert_text((40, 710), "Q27. (A) In the given figure, prove the identity.")
    second = pdf.new_page(width=600, height=800)
    image = BytesIO()
    Image.new("RGB", (80, 80), "black").save(image, format="PNG")
    second.insert_image(pymupdf.Rect(220, 40, 340, 180), stream=image.getvalue(), keep_proportion=False)
    second.insert_text((40, 250), "Q27. (B) Alternative proof.")
    second.insert_text((40, 310), "Q28. A question with no diagram.")
    second.insert_text((40, 370), "Q30. (A) Find the missing frequency.")
    second.insert_text((40, 550), "Q30. (B) Find the modal weight.")
    second.insert_text((40, 730), "Q31. A question with no diagram.")
    for top, headers in [(400, ("Class", "Frequency")), (580, ("Weight", "Students"))]:
        for y in (top, top + 30, top + 60):
            second.draw_line((100, y), (400, y))
        for x in (100, 200, 300, 400):
            second.draw_line((x, top), (x, top + 60))
        second.insert_text((110, top + 20), headers[0])
        second.insert_text((110, top + 50), headers[1])
        second.insert_text((210, top + 20), "20")
        second.insert_text((210, top + 50), "8")
    pdf.save(path)
    pdf.close()
    monkeypatch.setattr(layout, "abs_path", lambda _: path)
    return SimpleNamespace(original_file="paper.pdf")


def meta(number):
    # Different image and PDF sizes catch accidental mixing of coordinate spaces.
    return {"page_number": number, "ocr_width": 1200, "ocr_height": 1600}


def visual(kind, labels, bbox):
    return VisualEvidence(kind=kind, description="Source visual", labels=labels, bbox=bbox)


def test_continued_diagram_belongs_to_printed_previous_root_not_q26(tmp_path, monkeypatch):
    doc = source_pdf(tmp_path, monkeypatch)
    first = Page(page_number=1, fragments=[Fragment(root=26, text="No diagram"), Fragment(root=27, text="In the figure")])
    second = Page(page_number=2, fragments=[
        Fragment(root=26, text="Alternative for visually impaired candidates", continues=True,
                 visuals=[visual("diagram", ["A", "B"], {"x": 430, "y": 70, "width": 250, "height": 300})]),
        Fragment(root=27, text="Alternative proof", continues=True),
        Fragment(root=28, text="No diagram"),
    ])
    layout.ground_visuals(doc, [(meta(1), first), (meta(2), second)])
    assert first.fragments[0].visuals == []
    assert second.fragments[0].root == 27
    assert len(second.fragments[0].visuals) == 1
    assert second.fragments[0].visuals[0].bbox == {"x": 440, "y": 80, "width": 240, "height": 280}
    assert second.fragments[2].visuals == []


def test_or_tables_use_source_labels_and_grid_not_ai_coordinates(tmp_path, monkeypatch):
    doc = source_pdf(tmp_path, monkeypatch)
    fragment = Fragment(root=30, text="Two alternative distribution tables", visuals=[
        visual("table", ["Class", "Frequency", "20", "8"], {"x": 200, "y": 550, "width": 600, "height": 80}),
        visual("table", ["Weight", "Students", "20", "8"], {"x": 200, "y": 810, "width": 600, "height": 80}),
    ])
    layout.ground_visuals(doc, [(meta(2), Page(page_number=2, fragments=[fragment]))])
    assert [v.bbox["y"] for v in fragment.visuals] == [800, 1160]
    assert fragment.issues == []


def test_unmatched_visual_is_flagged_instead_of_borrowed_from_another_question(tmp_path, monkeypatch):
    doc = source_pdf(tmp_path, monkeypatch)
    fragment = Fragment(root=28, text="No diagram", visuals=[
        visual("table", ["Class", "Frequency"], {"x": 200, "y": 800, "width": 600, "height": 120}),
    ])
    layout.ground_visuals(doc, [(meta(2), Page(page_number=2, fragments=[fragment]))])
    assert fragment.visuals == []
    assert "could not be confirmed" in fragment.issues[0]


def test_no_visual_is_invented_for_questions_without_one(tmp_path, monkeypatch):
    doc = source_pdf(tmp_path, monkeypatch)
    fragments = [Fragment(root=28, text="Plain question"), Fragment(root=31, text="Plain question")]
    layout.ground_visuals(doc, [(meta(2), Page(page_number=2, fragments=fragments))])
    assert all(not f.visuals and not f.issues for f in fragments)


def test_vector_diagrams_keep_their_source_bounds(tmp_path, monkeypatch):
    path = tmp_path / "vector.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page(width=600, height=800)
    page.insert_text((40, 100), "Q1. Refer to the circle.")
    page.draw_circle((250, 200), 40)
    page.insert_text((40, 300), "Q2. No diagram.")
    pdf.save(path)
    pdf.close()
    monkeypatch.setattr(layout, "abs_path", lambda _: path)
    fragment = Fragment(root=1, text="Refer to circle", visuals=[
        visual("diagram", [], {"x": 410, "y": 310, "width": 180, "height": 180}),
    ])
    layout.ground_visuals(SimpleNamespace(original_file="vector.pdf"), [
        (meta(1), Page(page_number=1, fragments=[fragment])),
    ])
    assert fragment.issues == []
    assert fragment.visuals[0].bbox == {"x": 420, "y": 320, "width": 160, "height": 160}


@pytest.mark.parametrize("root", [7, 41])
def test_tiled_illustrations_and_wrong_ai_boxes_use_printed_ownership(tmp_path, monkeypatch, root):
    path = tmp_path / "tiles.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page(width=600, height=800)
    page.insert_text((40, 60), f"Q{root}(A) First case study.")
    page.insert_text((40, 400), f"Q{root + 1}. Second case study.")
    image = BytesIO()
    Image.new("RGB", (80, 80), "black").save(image, format="PNG")
    for rect in [(100, 110, 180, 190), (180, 110, 260, 190), (200, 460, 300, 540)]:
        page.insert_image(pymupdf.Rect(rect), stream=image.getvalue(), keep_proportion=False)
    pdf.save(path)
    pdf.close()
    monkeypatch.setattr(layout, "abs_path", lambda _: path)
    fragments = [Fragment(root=n, text="Case study", visuals=[
        visual("diagram", [], {"x": 0, "y": 0, "width": 10, "height": 10}),
    ]) for n in (root, root + 1)]
    layout.ground_visuals(SimpleNamespace(original_file="tiles.pdf"), [(meta(1), Page(page_number=1, fragments=fragments))])
    assert all(len(f.visuals) == 1 and not f.issues for f in fragments)
    assert fragments[0].visuals[0].bbox == {"x": 200, "y": 220, "width": 320, "height": 160}
    assert fragments[1].visuals[0].bbox == {"x": 400, "y": 920, "width": 200, "height": 160}


def test_scheme_branch_labels_with_trailing_period_define_image_ownership(tmp_path, monkeypatch):
    path = tmp_path / "scheme.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page(width=600, height=800)
    page.insert_text((40, 100), "18. First solution.")
    page.insert_text((40, 400), "19(A). Alternative solution with a figure.")
    image = BytesIO()
    Image.new("RGB", (80, 80), "black").save(image, format="PNG")
    page.insert_image(pymupdf.Rect(250, 410, 350, 500), stream=image.getvalue(), keep_proportion=False)
    pdf.save(path)
    pdf.close()
    monkeypatch.setattr(layout, "abs_path", lambda _: path)
    fragments = [Fragment(root=18, text="No figure"), Fragment(root=19, text="Refer to figure")]
    layout.ground_visuals(SimpleNamespace(original_file="scheme.pdf"), [(meta(1), Page(page_number=1, fragments=fragments))])
    assert not fragments[0].visuals
    assert len(fragments[1].visuals) == 1


def test_native_images_recover_ai_omissions_without_inventing_diagrams(tmp_path, monkeypatch):
    doc = source_pdf(tmp_path, monkeypatch)
    fragments = [Fragment(root=27, text="Source figure", continues=True), Fragment(root=28, text="No image")]
    layout.ground_visuals(doc, [(meta(2), Page(page_number=2, fragments=fragments))])
    assert len(fragments[0].visuals) == 1
    assert fragments[0].visuals[0].kind == "image"
    assert fragments[1].visuals == []
