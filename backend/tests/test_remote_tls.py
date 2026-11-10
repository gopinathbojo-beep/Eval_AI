import ssl

import httpx
from app.config import get_settings
import pytest

from app.ocr import remote
from app.ocr.internvl import AIUnavailable, check_model


def assert_verified_context(context):
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname


def test_ai_certificate_context_keeps_certificate_and_hostname_verification():
    assert_verified_context(remote.tls_context())


def test_status_and_completions_both_use_the_verified_context(monkeypatch):
    calls = []
    monkeypatch.setattr(remote, "connection", lambda: ("https://provider.invalid/api", "test-key", "vision-model"))

    def get(url, **kwargs):
        assert_verified_context(kwargs["verify"])
        calls.append(url)
        body = {"data": [{"id": m, "architecture": {"input_modalities": ["text", "image"]}}
                         for m in ("vision-model", get_settings().ai_indic_model)]}
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    def post(url, **kwargs):
        assert_verified_context(kwargs["verify"])
        calls.append(url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(remote.httpx, "get", get)
    monkeypatch.setattr(remote.httpx, "post", post)
    assert remote.status()["available"]
    assert remote.call("Read", "Source", None, True)[0] == "{}"
    assert len(calls) == 3


@pytest.mark.parametrize("error, expected", [
    (httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"), "HTTPS certificate"),
    (httpx.ConnectError("Connection refused"), "network, proxy and firewall"),
    (RuntimeError("Model not found"), "API key and model access"),
])
def test_diagnostics_distinguish_certificate_network_and_configuration_errors(monkeypatch, error, expected):
    def unavailable():
        raise error

    monkeypatch.setattr(remote, "status", unavailable)
    with pytest.raises(AIUnavailable) as failure:
        check_model()
    assert expected in failure.value.detail
