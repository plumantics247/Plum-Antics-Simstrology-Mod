"use strict";

const fs = require("node:fs");
const path = require("node:path");

function listFilesRecursive(rootPath) {
  if (!rootPath || !fs.existsSync(rootPath)) {
    return [];
  }

  const out = [];
  const stack = [rootPath];
  while (stack.length > 0) {
    const currentPath = stack.pop();
    const entries = fs.readdirSync(currentPath, { withFileTypes: true });
    for (const entry of entries) {
      const entryPath = path.join(currentPath, entry.name);
      if (entry.isDirectory()) {
        stack.push(entryPath);
        continue;
      }
      if (entry.isFile()) {
        out.push(entryPath);
      }
    }
  }
  return out.sort((left, right) => left.localeCompare(right));
}

function isXmlSourceFile(filePath) {
  return path.extname(String(filePath || "")).toLowerCase() === ".xml";
}

function normalizeRelativePath(projectRoot, filePath) {
  return path.relative(projectRoot, filePath).split(path.sep).join("/");
}

function toLogicalKey(filePath) {
  return path.basename(String(filePath || "")).toLowerCase();
}

function collectDuplicateLogicalKeys(filePaths) {
  const grouped = new Map();
  for (const filePath of filePaths) {
    const logicalKey = toLogicalKey(filePath);
    const current = grouped.get(logicalKey) || [];
    current.push(filePath);
    grouped.set(logicalKey, current);
  }

  return Array.from(grouped.entries())
    .filter(([, group]) => group.length > 1)
    .sort((left, right) => left[0].localeCompare(right[0]));
}

function loadProjectConfig(projectRoot) {
  const packageJsonPath = path.join(projectRoot, "package.json");
  const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
  return {
    ts4scriptBaseName: packageJson.config?.ts4scriptBaseName || "PlumAntics_Simstrology",
  };
}

function resolveProjectRoot(argv) {
  const candidate = argv[2];
  return path.resolve(candidate || process.cwd());
}

module.exports = {
  collectDuplicateLogicalKeys,
  isXmlSourceFile,
  listFilesRecursive,
  loadProjectConfig,
  normalizeRelativePath,
  resolveProjectRoot,
  toLogicalKey,
};
