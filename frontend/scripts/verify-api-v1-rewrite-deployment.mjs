import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { execSync } from "node:child_process";

const repoRoot = resolve(new URL("../..", import.meta.url).pathname);
const frontendRoot = resolve(new URL("..", import.meta.url).pathname);
const frontendUrl = (process.env.FRONTEND_URL ?? "https://360-encompass.com").replace(/\/$/, "");
const deployBranch = process.env.FRONTEND_DEPLOY_BRANCH ?? "main";
const apiBaseUrl = process.env.API_BASE_URL?.replace(/\/$/, "") ?? null;
const expectedCommitSha =
  process.env.EXPECTED_COMMIT_SHA ??
  execSync("git rev-parse HEAD", { cwd: repoRoot, encoding: "utf8" }).trim();
const skipBuildArtifactCheck = process.env.SKIP_BUILD_ARTIFACT_CHECK === "1";
const accessLogPath = process.env.ACCESS_LOG_PATH ?? null;

function readRuntimeCheck(pathname) {
  return fetch(`${frontendUrl}${pathname}`, {
    method: "GET",
    redirect: "manual",
    headers: {
      "cache-control": "no-cache",
      pragma: "no-cache",
    },
  }).then(async (response) => {
    const body = await response.text();
    const proxyHeaders = {};
    for (const [key, value] of response.headers.entries()) {
      if (
        key === "location" ||
        key.startsWith("x-forwarded-") ||
        key.startsWith("x-render-") ||
        key === "via" ||
        key.startsWith("cf-") ||
        key.startsWith("x-amz-")
      ) {
        proxyHeaders[key] = value;
      }
    }
    return {
      path: pathname,
      status: response.status,
      location: response.headers.get("location"),
      proxyHeaders,
      body,
    };
  });
}

function findHardcodedApiUrls() {
  const findings = [];
  const root = join(frontendRoot, "src");
  const stack = [root];

  while (stack.length) {
    const current = stack.pop();
    for (const entry of readdirSync(current)) {
      const absolutePath = join(current, entry);
      const info = statSync(absolutePath);
      if (info.isDirectory()) {
        stack.push(absolutePath);
        continue;
      }
      if (!/\.(ts|tsx|js|jsx)$/.test(entry)) {
        continue;
      }
      const content = readFileSync(absolutePath, "utf8");
      const lines = content.split("\n");
      lines.forEach((line, idx) => {
        if (/https?:\/\/[^\s"']+\/api(\/|"|'|`)/.test(line)) {
          findings.push(`${absolutePath}:${idx + 1}`);
        }
      });
    }
  }

  return findings;
}

function checkBuiltArtifact() {
  if (skipBuildArtifactCheck) {
    return [];
  }
  const manifestPath = join(frontendRoot, ".next", "routes-manifest.json");
  assert.ok(existsSync(manifestPath), "Missing .next/routes-manifest.json; run `npm run build` in frontend first");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  const rewrites = manifest?.rewrites?.afterFiles ?? [];
  const rewriteSources = rewrites.map((entry) => entry.source);

  assert.ok(rewriteSources.includes("/api/v1/:path*"), "Missing /api/v1/:path* rewrite");
  assert.ok(rewriteSources.includes("/api"), "Missing /api rewrite");
  assert.ok(rewriteSources.includes("/api/:path((?!v1/).*)"), "Missing guarded /api/:path rewrite");

  return rewrites;
}

async function fetchJson(url) {
  const response = await fetch(url, {
    method: "GET",
    headers: {
      "cache-control": "no-cache",
      pragma: "no-cache",
    },
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} from ${url}`);
  }
  return response.json();
}

async function fetchDeployedCommitSha() {
  const versionEndpoints = [`${frontendUrl}/api/v1/version`];
  if (apiBaseUrl) {
    versionEndpoints.push(`${apiBaseUrl}/version`);
  }

  let lastError = null;
  for (const endpoint of versionEndpoints) {
    try {
      const body = await fetchJson(endpoint);
      const commitSha = typeof body?.commit_sha === "string" ? body.commit_sha.trim() : "";
      if (commitSha) {
        return { commitSha, source: endpoint };
      }
      throw new Error(`Missing commit_sha in ${endpoint}`);
    } catch (error) {
      lastError = error;
    }
  }

  throw new Error(`Unable to resolve deployed commit SHA: ${lastError?.message ?? "unknown error"}`);
}

async function fetchOpenApiSpec() {
  const candidates = [`${frontendUrl}/api/v1/openapi.json`, `${frontendUrl}/openapi.json`];
  let lastError = null;
  for (const candidate of candidates) {
    try {
      const spec = await fetchJson(candidate);
      return { spec, source: candidate };
    } catch (error) {
      lastError = error;
    }
  }
  throw new Error(`Unable to fetch OpenAPI spec: ${lastError?.message ?? "unknown error"}`);
}

function assertEraUploadOpenApi(openApiSpec) {
  const operation = openApiSpec?.paths?.["/api/v1/revenue/era-pdfs/upload"]?.post;
  assert.ok(operation, "Missing POST /api/v1/revenue/era-pdfs/upload in OpenAPI");
  const multipart = operation?.requestBody?.content?.["multipart/form-data"]?.schema;
  assert.ok(multipart, "Missing multipart/form-data request body schema for ERA upload");
  const files = multipart?.properties?.files;
  assert.equal(files?.type, "array", "ERA upload files field must be an array");
  assert.equal(files?.items?.format, "binary", "ERA upload files array items must be binary format");
}

function checkLogs() {
  if (!accessLogPath || !existsSync(accessLogPath)) {
    return null;
  }
  const logText = readFileSync(accessLogPath, "utf8");
  const doubleVersionHits = (logText.match(/\/api\/v1\/v1\//g) ?? []).length;
  const api404Hits = (logText.match(/"(GET|POST|PUT|PATCH|DELETE) \/api[^\"]*" 404/g) ?? []).length;
  return { doubleVersionHits, api404Hits };
}

async function main() {
  const rewrites = checkBuiltArtifact();
  const { commitSha: deployedCommitSha, source: deployedCommitShaSource } = await fetchDeployedCommitSha();
  const { spec: openApiSpec, source: openApiSource } = await fetchOpenApiSpec();
  assertEraUploadOpenApi(openApiSpec);

  const [apiHealth, apiV1Health, apiRoot, apiV1V1Health] = await Promise.all([
    readRuntimeCheck("/api/health"),
    readRuntimeCheck("/api/v1/health"),
    readRuntimeCheck("/api"),
    readRuntimeCheck("/api/v1/v1/health"),
  ]);

  assert.equal(apiHealth.status, apiV1Health.status, "/api/health status does not match /api/v1/health");
  assert.equal(apiHealth.body, apiV1Health.body, "/api/health body does not match /api/v1/health");
  assert.ok(!String(apiV1Health.location ?? "").includes("/api/v1/v1/"), "/api/v1/* appears to be rewritten twice");
  assert.ok(apiV1V1Health.status >= 400, "/api/v1/v1/* unexpectedly resolved successfully");
  assert.equal(
    deployedCommitSha,
    expectedCommitSha,
    `Deployed commit SHA (${deployedCommitSha}) does not match expected (${expectedCommitSha})`,
  );

  const logSummary = checkLogs();
  const hardcodedApiUrls = findHardcodedApiUrls();

  const result = {
    frontendDomain: frontendUrl,
    frontendBranch: deployBranch,
    expectedCommitSha,
    deployedCommitSha,
    deployedCommitShaSource,
    openApiSource,
    rewriteArtifact: rewrites,
    runtimeChecks: [apiHealth, apiV1Health, apiRoot, apiV1V1Health],
    accessLogSummary: logSummary,
    hardcodedApiBypassCallsites: hardcodedApiUrls,
    verdict:
      hardcodedApiUrls.length === 0 && (!logSummary || logSummary.doubleVersionHits === 0)
        ? "PASS"
        : "FAIL",
  };

  console.log(JSON.stringify(result, null, 2));

  if (hardcodedApiUrls.length > 0) {
    throw new Error(`Found hardcoded absolute /api callsites:\n${hardcodedApiUrls.join("\n")}`);
  }
  if (logSummary && logSummary.doubleVersionHits > 0) {
    throw new Error(`Found ${logSummary.doubleVersionHits} /api/v1/v1/ entries in access logs`);
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
