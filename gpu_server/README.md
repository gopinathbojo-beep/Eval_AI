# GPU server

Runs both models on one GPU machine, the remote server, so other PCs run only the backend and apps:
- Ollama (InternVL, and the optional Tamil text model) on port 11434
- IndicOCR (`indic_ocr_service`) on port 8090

## On the GPU machine (once)

1. Install [Ollama](https://ollama.com/download) and [Python 3.11](https://www.python.org/downloads/release/python-3119/).
2. Copy the `gpu_server` and `indic_ocr_service` folders (or the whole project) to it.
3. Double-click `gpu_server\setup.bat` and accept the administrator prompt. It:
   - sets `OLLAMA_HOST=0.0.0.0:11434` and `OLLAMA_NUM_PARALLEL=2`, so Ollama accepts requests from the network, two at a time;
   - opens ports 11434 and 8090, and ping, in Windows Firewall, for the local network only (neither service has a login);
   - restarts Ollama and downloads `blaifa/InternVL3_5:4B` if it is missing;
   - installs IndicOCR (asks for a Hugging Face token the first time; see `indic_ocr_service\README.md`).

## Every day

- `gpu_server\start.bat` starts Ollama (for the network) and IndicOCR on `0.0.0.0:8090`, and prints this machine's address.
- `gpu_server\stop.bat` stops both.

Keep the machine awake while ADEM is used (Settings > System > Power: Sleep = Never).

## On the PC running the backend

Point `backend\.env` at the GPU machine:
```
INTERNVL_API_URL=http://192.168.1.10:11434
INDIC_OCR_URL=http://192.168.1.10:8090
```
`start.bat` then skips the local IndicOCR and checks that both models answer; `setup.bat` skips installing IndicOCR.
Give the GPU machine a fixed IP (a DHCP reservation in the router) so this address does not change.
