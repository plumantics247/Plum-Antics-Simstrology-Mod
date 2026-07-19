"use strict";

const fs = require("node:fs");
const path = require("node:path");

const {
  loadProjectConfig,
  normalizeRelativePath,
  resolveProjectRoot,
} = require("../lib/shared");

function auditOutArtifacts(projectRoot) {
  const outRoot = path.join(projectRoot, "out");
  const { ts4scriptBaseName } = loadProjectConfig(projectRoot);
  const expectedNames = [
    `${ts4scriptBaseName}.ts4script`,
    `${ts4scriptBaseName}.source.ts4script`,
  ];
  const issues = [];
  const summaries = [];

  if (!fs.existsSync(outRoot)) {
    issues.push("missing out/ directory");
    return { expectedNames, issues, summaries };
  }

  const actualNames = fs
    .readdirSync(outRoot)
    .filter((name) => name.toLowerCase().endsWith(".ts4script"));

  for (const expectedName of expectedNames) {
    const fullPath = path.join(outRoot, expectedName);
    if (!fs.existsSync(fullPath)) {
      issues.push(`missing expected output: ${expectedName}`);
      continue;
    }

    const stat = fs.statSync(fullPath);
    if (stat.size <= 0) {
      issues.push(`zero-byte output: ${expectedName}`);
      continue;
    }

    summaries.push({
      name: normalizeRelativePath(projectRoot, fullPath),
      size: stat.size,
      modified: stat.mtime.toISOString(),
    });
  }

  const expectedNameSet = new Set(expectedNames);
  const unexpectedNames = actualNames
    .filter((name) => !expectedNameSet.has(name))
    .sort((left, right) => left.localeCompare(right));
  for (const unexpectedName of unexpectedNames) {
    issues.push(`unexpected ts4script output: ${unexpectedName}`);
  }

  return {
    expectedNames,
    issues,
    summaries,
  };
}

function main(argv = process.argv) {
  const projectRoot = resolveProjectRoot(argv);
  const result = auditOutArtifacts(projectRoot);
  if (result.issues.length > 0) {
    console.error("OUT artifact audit failed:");
    for (const issue of result.issues) {
      console.error(` - ${issue}`);
    }
    process.exitCode = 1;
    return;
  }

  console.log("OK: found expected ts4script outputs");
  for (const summary of result.summaries) {
    console.log(` - ${summary.name} (${summary.size} bytes, ${summary.modified})`);
  }
}

if (require.main === module) {
  main();
}

module.exports = {
  auditOutArtifacts,
};
