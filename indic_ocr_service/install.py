"""Install IndicOCR into this folder's venv. Windows-friendly replacement for the model repo's install.sh.

    .venv\\Scripts\\python.exe install.py              # download model, pick CUDA build, install, verify
    set IDP_CUDA=cpu && .venv\\Scripts\\python.exe install.py   # force a build: cpu, cu121, cu124, cu126, cu128, cu130

Needs a Hugging Face login with the model licence accepted (https://huggingface.co/bodhan-ai/indic-ocr).
Same steps as install.sh (torch + torchvision together from one index, then the repo's requirements), plus one
check it lacks: CUDA 13 builds no longer support GPUs older than compute capability 7.5 (e.g. Maxwell/Pascal
cards such as the Quadro M2000), so those get the CUDA 12.6 build, which still does.
"""
from __future__ import annotations
import os
import re
import subprocess
import sys

MODEL_REPO = os.environ.get("INDIC_OCR_REPO", "bodhan-ai/indic-ocr")


def _nvidia_smi(*args: str) -> str:
    try:
        return subprocess.run(["nvidia-smi", *args], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def detect_cuda() -> str:
    m = re.search(r"CUDA Version:\s*(\d+)\.", _nvidia_smi())
    if not m:
        return "cpu"
    driver = int(m.group(1))
    caps = re.findall(r"(\d+)\.(\d+)", _nvidia_smi("--query-gpu=compute_cap", "--format=csv,noheader"))
    old_gpu = bool(caps) and (int(caps[0][0]), int(caps[0][1])) < (7, 5)
    if old_gpu:
        return "cu126"
    return "cu130" if driver >= 13 else "cu124"


def pip(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", *args], check=True)


def main() -> int:
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import GatedRepoError

    print(f"==> downloading {MODEL_REPO}")
    try:
        repo = snapshot_download(MODEL_REPO)
    except GatedRepoError:
        print("    Access denied. Accept the licence at https://huggingface.co/bodhan-ai/indic-ocr and log in with:\n"
              "    .venv\\Scripts\\hf.exe auth login", file=sys.stderr)
        return 1
    print(f"    {repo}")

    cuda = os.environ.get("IDP_CUDA") or detect_cuda()
    print(f"==> torch + torchvision ({cuda}), together")
    pip("torch", "torchvision", "--index-url", f"https://download.pytorch.org/whl/{cuda}")

    print("==> IndicOCR requirements")
    pip("-r", os.path.join(repo, "requirements.txt"))

    print("==> checking")
    check = ("import sys, torch, torchvision, transformers;"
             "print('    torch', torch.__version__, '| torchvision', torchvision.__version__,"
             " '| transformers', transformers.__version__);"
             "print('    cuda ', ('yes, ' + torch.cuda.get_device_name(0)) if torch.cuda.is_available() else 'NO, running on CPU');"
             f"sys.path.insert(0, {repo!r}); from indic_ocr import IndicOCR; print('    import ok')")
    subprocess.run([sys.executable, "-c", check], check=True)
    print("==> done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
