"""Question paper and answer key generation grounded in the reference library (RAG).

blueprint.py  which questions the paper has: CBSE board pattern (cbse/catalog.py) or a custom mark mix
retrieve.py   which textbook passages and sample-paper examples each section is written from
generate.py   the AI call per section, validation, grounding check, and the background job
render.py     the question paper and marking scheme as PDFs
"""
