"""Read-only local AI connection diagnostics; never prints API keys or provider response bodies."""
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from app.ocr.remote import connection, tls_context


def main():
    base, key, selected = connection()
    print("Endpoint:", base)
    print("Model:", selected)
    print("API key configured:", bool(key))
    print("Proxy/certificate environment names:", [name for name in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR"
    ) if os.environ.get(name)])
    for label, verify in (("HTTPX default certificates", True), ("Application trusted certificates", tls_context())):
        print(label, flush=True)
        try:
            with httpx.Client(verify=verify, timeout=15) as client:
                auth = client.get(base + "/v1/key", headers={"Authorization": "Bearer " + key})
                print("Authentication HTTP:", auth.status_code, flush=True)
                models = client.get(base + "/v1/models", headers={"Authorization": "Bearer " + key})
                print("Model catalog HTTP:", models.status_code, flush=True)
                if models.is_success:
                    model = next((m for m in models.json().get("data", []) if m.get("id") == selected), None)
                    print("Configured model found:", bool(model))
                    if model:
                        print("Input modalities:", (model.get("architecture") or {}).get("input_modalities"))
        except Exception as error:
            # The exception contains transport details only, not response bodies.
            print(type(error).__name__, str(error), flush=True)
            if error.__cause__:
                print("Transport cause:", repr(error.__cause__), flush=True)


if __name__ == "__main__":
    main()
