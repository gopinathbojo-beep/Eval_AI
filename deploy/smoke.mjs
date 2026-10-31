// Read-only staging checks: node deploy/smoke.mjs https://eval.example.com
import assert from "node:assert/strict";

const base = new URL(process.argv[2]);
assert.equal(base.protocol, "https:", "Use the public HTTPS URL");
async function get(path) {
  return fetch(new URL(path, base), { signal: AbortSignal.timeout(20_000), redirect: "error" });
}
const index = await get("/");
assert.equal(index.status, 200);
assert.match(index.headers.get("strict-transport-security") ?? "", /max-age=/);
assert.match(index.headers.get("content-security-policy") ?? "", /script-src 'self'/);
const html = await index.text();
for (const path of ["/login", "/dashboard", "/exams/example/content"]) {
  const response = await get(path);
  assert.equal(response.status, 200, path);
  assert.equal(await response.text(), html, `SPA fallback: ${path}`);
}
for (const match of html.matchAll(/(?:src|href)="(\/assets\/[^\"]+)"/g)) {
  const response = await get(match[1]);
  assert.equal(response.status, 200, match[1]);
  assert.match(response.headers.get("cache-control") ?? "", /immutable/);
}
assert.equal((await get("/assets/missing.js")).status, 404);
assert.equal((await get("/api/ready")).status, 200);
assert.equal((await get("/api/auth/me")).status, 401);
assert.equal((await get("/api/not-a-route")).status, 404);
console.log("HTTPS, security headers, SPA routes, assets and API smoke checks passed.");
