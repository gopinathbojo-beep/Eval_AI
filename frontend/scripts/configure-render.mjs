import { readFile, writeFile } from "node:fs/promises";

const input = process.argv[2];
if (!input) throw new Error("Usage: npm run configure:api -- https://YOUR-SERVICE.onrender.com");
const url = new URL(input);
if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash || !["", "/"].includes(url.pathname)) {
  throw new Error("Provide the HTTPS origin of your Render backend without credentials, a path or query string.");
}
const file = new URL("../vercel.json", import.meta.url);
const config = JSON.parse(await readFile(file, "utf8"));
config.rewrites.find(rule => rule.source === "/api/:path*").destination = `${url.origin}/api/:path*`;
await writeFile(file, JSON.stringify(config, null, 2) + "\n");
console.log(`Vercel API proxy configured for ${url.origin}. Commit and push frontend/vercel.json to redeploy.`);
