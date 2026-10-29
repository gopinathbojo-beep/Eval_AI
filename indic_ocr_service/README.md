# IndicOCR service

ADEM uses [Bodhan AI's IndicOCR](https://huggingface.co/bodhan-ai/indic-ocr) to read Indian-language subjects (Tamil, Hindi, ...).
Every other subject stays on InternVL. This folder is a small HTTP wrapper that the backend calls.

It runs on this PC next to the backend, in its **own** virtual environment (`indic_ocr_service\.venv`, Python 3.11),
because IndicOCR brings its own PyTorch/CUDA build.

## Setup (once)

Before running setup, on Hugging Face:
1. Open https://huggingface.co/bodhan-ai/indic-ocr, log in, and accept the Indic Open Model License.
2. Create a **Read** token at https://huggingface.co/settings/tokens.

Then double-click **`setup.bat`** in the project folder. Its step 5 creates the venv, asks for the token if this PC
is not logged in to Hugging Face, and runs `install.py`, which:
- downloads the model (about 1.9 GB, into the Hugging Face cache);
- picks the PyTorch build for your GPU and installs `torch` + `torchvision` together (several GB);
- installs IndicOCR's requirements and checks that the model imports.

`install.py` follows the model's own `install.sh`, with one addition: CUDA 13 builds no longer support GPUs older
than compute capability 7.5 (e.g. the Quadro M2000), so those get the CUDA 12.6 build. To force a build:
`set IDP_CUDA=cpu` (or `cu124`, `cu126`, `cu128`, `cu130`) before running it.

Manual equivalent:
```
cd indic_ocr_service
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\hf.exe auth login
.venv\Scripts\python.exe install.py
```

## Run

On the GPU server, double-click `start.bat`: it stops any other program on port 8090 (such as a standalone
"IndicOCR Inference Server"), installs the service on first run, and starts it for the network on port 8090.
By hand:
```
cd indic_ocr_service
.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8090
```

Check: http://127.0.0.1:8090/health. The model loads on the first Tamil page, not at start.

## Backend settings (`backend/.env`)

`setup.bat` adds these if they are missing:
```
INDIC_OCR_ENABLED=true
INDIC_OCR_URL=http://127.0.0.1:8090
```
Optional: `INDIC_SUBJECTS` (default: tamil, தமிழ், hindi, हिन्दी, telugu, kannada, malayalam, marathi, bengali, gujarati,
odia, punjabi, assamese, urdu, sanskrit).

An exam goes to IndicOCR when its subject name contains one of `INDIC_SUBJECTS` (case-insensitive).
For those exams IndicOCR reads the question paper, answer key, answer sheets and the student details box.

### Grading model (optional)

IndicOCR only reads. By default, Indian-language subjects are graded by InternVL, as before, and the AI labeler is
off. Optionally, set `INDIC_TEXT_MODEL` in `backend/.env` to the name of an Ollama model that understands Tamil
(pull it on the Ollama machine first). That model then grades and generates answer keys for those subjects.

It is also the **AI labeler** for those subjects: it classifies questions whose type no keyword rule could
decide, and splits answer-key entries without marking points into points whose marks add up to the question's marks.
Its output is checked (known types only, marks must add up, points must come from the official answer) and
discarded if it fails; the rule result then stays.

## One GPU, one engine at a time

The backend queues every model job (reading papers, keys and sheets, identifying students, grading). Up to
`INTERNVL_PARALLEL_JOBS` / `INDIC_PARALLEL_JOBS` jobs (default 1) run at once on the engine that is loaded, and
waiting jobs for that engine go ahead of jobs for the other one: an English, Tamil, English, Tamil upload runs both
English papers, switches once, then both Tamil papers. A job is passed over at most 4 times; then the running jobs
finish and the queue switches to it. Bulk sheet uploads queue one job per sheet, so a batch runs in parallel.

Before switching, the backend frees the GPU: InternVL is unloaded from Ollama before Tamil jobs, and IndicOCR (via
`POST /release`) and the Tamil text model are unloaded before English jobs. So the GPU only ever holds one engine;
the first page after a switch is slower while the model loads.

For parallel InternVL jobs, also set `OLLAMA_NUM_PARALLEL` (at least `INTERNVL_PARALLEL_JOBS`) on the Ollama machine
and restart Ollama; otherwise Ollama runs the requests one by one. IndicOCR reads parallel pages on its one loaded
model; that is not documented upstream, so compare a few Tamil sheets with `INDIC_PARALLEL_JOBS=1` before relying on it.

## Notes

- IndicOCR reads handwriting in English plus 12 Indian languages: Hindi, Bengali, Telugu, Marathi, Tamil, Gujarati, Kannada, Malayalam, Odia, Punjabi, Assamese and Urdu.
  Other scheduled languages (e.g. Sanskrit) are printed-text only. Bodhan says handwriting quality is still a work in progress.
- License: free for school and commercial use, with attribution. Offering it to *other organisations* as a hosted service needs written approval from Bodhan AI unless you are a nonprofit, government or academic body. Read the full license before deploying ADEM for other schools.
