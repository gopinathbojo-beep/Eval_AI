"""IndicOCR (Bodhan AI / AI4Bharat) over HTTP for the ADEM backend.

Runs in its own venv on the GPU machine: IndicOCR ships its own CUDA wheels, which must not mix with the backend's.
POST /parse   (multipart "image") -> {"image", "width", "height",
              "blocks": [{order, label, type, bbox_xyxy, conf, text, text_conf, low_words}]}
              conf is the layout model's certainty about the box; text_conf is the recognizer's about the text in it
              (confidence.py), low_words the words it doubted
POST /release -> frees GPU memory once running pages finish; the backend calls it when its job queue switches to InternVL
GET  /health  -> {"status": "ok", "model": "bodhan-ai/indic-ocr", "loaded": bool}
The model loads on the first page after start or release. Pages from parallel backend jobs are read at the same time
on the one loaded model; the backend's INDIC_PARALLEL_JOBS sets how many.
"""
from __future__ import annotations
import gc
import logging
import os
import sys
import tempfile
import threading
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from huggingface_hub import snapshot_download

MODEL_REPO = os.environ.get("INDIC_OCR_REPO", "bodhan-ai/indic-ocr")
log = logging.getLogger("indic_ocr_service")

_repo = snapshot_download(MODEL_REPO)
sys.path.insert(0, _repo)
from indic_ocr import IndicOCR  # noqa: E402  (shipped inside the model repo)
import confidence  # noqa: E402

_parser = None
_load_lock = threading.Lock()
# Pages are read in parallel: the backend's job queue caps how many (INDIC_PARALLEL_JOBS). /release waits for them.
_state = threading.Condition()
_active = 0
_releasing = False


def _get_parser():
    global _parser
    with _load_lock:
        if _parser is None:
            # The backend stores tables as Markdown everywhere; IndicOCR defaults to HTML.
            _parser = IndicOCR.from_pretrained(_repo, table_format="markdown")
            confidence.install()
        return _parser


app = FastAPI(title="ADEM IndicOCR service")


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_REPO, "loaded": _parser is not None}


@app.post("/release")
def release():
    global _parser, _releasing
    with _state:
        _releasing = True  # no new page starts until the model is gone
        _state.wait_for(lambda: _active == 0)
        try:
            with _load_lock:
                if _parser is not None:
                    _parser = None
                    gc.collect()
                    try:
                        import torch
                        torch.cuda.empty_cache()
                    except Exception:  # CPU-only install or no torch: nothing more to free
                        pass
        finally:
            _releasing = False
            _state.notify_all()
    return {"status": "released"}


@app.post("/parse")
def parse(image: UploadFile = File(...)):
    global _active
    suffix = Path(image.filename or "page.png").suffix or ".png"
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / f"page{suffix}"
        path.write_bytes(image.file.read())
        with _state:
            _state.wait_for(lambda: not _releasing)
            _active += 1
        try:
            confidence.start()
            page = _get_parser().parse(str(path))
            measured = confidence.results()
            for block in page.get("blocks") or []:
                block.update(measured.get(block.get("order"), {}))
        except Exception as e:
            log.exception("IndicOCR failed on %s", image.filename)
            raise HTTPException(500, f"IndicOCR failed: {type(e).__name__}: {e}")
        finally:
            with _state:
                _active -= 1
                _state.notify_all()
    return {k: page[k] for k in ("image", "width", "height", "blocks") if k in page}
