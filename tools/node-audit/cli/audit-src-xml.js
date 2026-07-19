"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { XMLValidator } = require("fast-xml-parser");
const { XmlDocumentNode } = require("@s4tk/xml-dom");

const {
  collectDuplicateLogicalKeys,
  isXmlSourceFile,
  listFilesRecursive,
  normalizeRelativePath,
  resolveProjectRoot,
} = require("../lib/shared");

function auditSrcXml(projectRoot) {
  const srcRoot = path.join(projectRoot, "src");
  const xmlFiles = listFilesRecursive(srcRoot).filter(isXmlSourceFile);
  const issues = [];
  const warnings = [];

  for (const filePath of xmlFiles) {
    try {
      const xml = fs.readFileSync(filePath, "utf8");
      const validation = XMLValidator.validate(xml);
      if (validation !== true) {
        const message = validation?.err?.msg || validation?.err?.code || "XML validation failed";
        throw new Error(String(message));
      }
      XmlDocumentNode.from(xml);
    } catch (error) {
      const relativePath = normalizeRelativePath(projectRoot, filePath);
      const message = error instanceof Error ? error.message : String(error);
      issues.push(`${relativePath}: ${message}`);
    }
  }

  for (const [logicalKey, files] of collectDuplicateLogicalKeys(xmlFiles)) {
    const relativePaths = files.map((filePath) => normalizeRelativePath(projectRoot, filePath));
    warnings.push(`duplicate basename warning for "${logicalKey}": ${relativePaths.join(", ")}`);
  }

  return {
    checkedCount: xmlFiles.length,
    issues,
    warnings,
  };
}

function main(argv = process.argv) {
  const projectRoot = resolveProjectRoot(argv);
  const result = auditSrcXml(projectRoot);
  if (result.issues.length > 0) {
    console.error("SRC XML audit failed:");
    for (const issue of result.issues) {
      console.error(` - ${issue}`);
    }
    process.exitCode = 1;
    return;
  }

  console.log(`OK: checked ${result.checkedCount} XML files in src/`);
  for (const warning of result.warnings) {
    console.warn(`WARN: ${warning}`);
  }
}

if (require.main === module) {
  main();
}

module.exports = {
  auditSrcXml,
};
