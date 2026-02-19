#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const targetPath = path.join(__dirname, "..", "app", "(app)", "billing", "revenue-command", "page.tsx");
if (!fs.existsSync(targetPath)) {
  console.error(`Revenue command page not found at ${targetPath}`);
  process.exit(1);
}

const source = fs.readFileSync(targetPath, "utf8");

const violations = [];

if (source.includes(".reduce(")) {
  violations.push("Detected `.reduce(` which may compute KPIs client-side.");
}

if (source.includes("Math.")) {
  violations.push("Detected `Math.` usage in revenue command UI.");
}

const sortViolations = source
  .split("\n")
  .filter((line) => line.includes(".sort(") && !line.includes("localeCompare"));

if (sortViolations.length) {
  violations.push("Detected `.sort(` on worklist data without explicit string sort guard.");
}

if (violations.length) {
  console.error("Revenue command page must stay deterministic and avoid client KPI math.");
  for (const violation of violations) {
    console.error(`- ${violation}`);
  }
  process.exit(1);
}

console.log("Revenue command tripwire passed: no client-side KPI math detected.");
