# Trust the Eval AI local certificate authority for the current Windows user, so https://localhost:5173 and
# https://<lan-ip>:5173 show as secure in Edge and Chrome. Windows asks you to confirm once.
# The CA is made by scripts/make-cert.sh and only exists on this PC (certs/ is not committed).
$ca = Join-Path $PSScriptRoot "..\certs\eval-ai-local-ca.crt"
if (-not (Test-Path $ca)) { throw "Run 'bash scripts/make-cert.sh' first." }
Import-Certificate -FilePath $ca -CertStoreLocation Cert:\CurrentUser\Root -ErrorAction Stop | Out-Null
Write-Output "Trusted: Eval AI Local CA. Restart the browser."
