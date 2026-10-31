"""Single-process web entry point for Render and Docker Compose."""
import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")),
                workers=1, proxy_headers=True, forwarded_allow_ips="*", timeout_graceful_shutdown=60)
