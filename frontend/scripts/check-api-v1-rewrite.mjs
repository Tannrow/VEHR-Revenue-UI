import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const nextConfigPath = new URL("../next.config.ts", import.meta.url);
const nextConfig = readFileSync(nextConfigPath, "utf8");

assert.match(nextConfig, /source:\s*"\/api\/v1\/:path\*"/);
assert.match(nextConfig, /destination:\s*`\$\{normalized\}\/api\/v1\/:path\*`/);
assert.match(nextConfig, /source:\s*"\/api"/);
assert.match(nextConfig, /destination:\s*`\$\{normalized\}\/api\/v1`/);
assert.match(nextConfig, /source:\s*"\/api\/:path\(\(\?!v1\/\)\.\*\)"/);
assert.match(nextConfig, /destination:\s*`\$\{normalized\}\/api\/v1\/:path`/);

const normalized = "https://example.test";

function applyRewrite(path) {
  if (path === "/api") {
    return `${normalized}/api/v1`;
  }
  if (path === "/api/v1" || path.startsWith("/api/v1/")) {
    return `${normalized}${path}`;
  }
  const match = /^\/api\/(?!v1\/)(.*)$/.exec(path);
  if (match) {
    return `${normalized}/api/v1/${match[1]}`;
  }
  return null;
}

assert.equal(applyRewrite("/api/tasks"), `${normalized}/api/v1/tasks`);
assert.equal(applyRewrite("/api/v1"), `${normalized}/api/v1`);
assert.equal(applyRewrite("/api/v1/tasks"), `${normalized}/api/v1/tasks`);

console.log("API rewrite checks passed");
