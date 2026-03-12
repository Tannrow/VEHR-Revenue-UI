import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import openapiTS, { COMMENT_HEADER, astToString } from "openapi-typescript";

const DEFAULT_SCHEMA_URL = "https://api-staging.360-encompass.com/openapi.json";
const REPOSITORY_ROOT = process.cwd();
const OUTPUT_FILE_PATH = resolve(REPOSITORY_ROOT, "src/lib/api/schema.d.ts");

function resolveSchemaSource(source: string): string | URL {
  if (/^[a-z]+:\/\//i.test(source)) {
    return new URL(source);
  }

  return pathToFileURL(resolve(REPOSITORY_ROOT, source));
}

async function main() {
  const source = process.env.API_SCHEMA_SOURCE?.trim() || DEFAULT_SCHEMA_URL;
  const schema = resolveSchemaSource(source);
  const ast = await openapiTS(schema);
  const output = `${COMMENT_HEADER}${astToString(ast)}`.replace(/\s*$/, "\n");

  await mkdir(dirname(OUTPUT_FILE_PATH), { recursive: true });
  await writeFile(OUTPUT_FILE_PATH, output, "utf8");

  console.log(`Generated API types from ${source} -> ${OUTPUT_FILE_PATH}`);
}

main().catch((error) => {
  console.error("Failed to generate API types.", error);
  process.exitCode = 1;
});
