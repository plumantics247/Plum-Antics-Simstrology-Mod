"use strict";

const path = require("node:path");

const {
  collectDuplicateLogicalKeys,
  isXmlSourceFile,
  listFilesRecursive,
  normalizeRelativePath,
  resolveProjectRoot,
} = require("../lib/shared");

function checkDuplicateKeys(projectRoot) {
  const srcRoot = path.join(projectRoot, "src");
  const xmlFiles = listFilesRecursive(srcRoot).filter(isXmlSourceFile);
  const duplicates = collectDuplicateLogicalKeys(xmlFiles).map(([logicalKey, files]) => ({
    logicalKey,
    files: files.map((filePath) => normalizeRelativePath(projectRoot, filePath)),
  }));

  return {
    checkedCount: xmlFiles.length,
    duplicates,
  };
}

function main(argv = process.argv) {
  const projectRoot = resolveProjectRoot(argv);
  const result = checkDuplicateKeys(projectRoot);
  if (result.duplicates.length > 0) {
    console.error("Duplicate logical keys found:");
    for (const duplicate of result.duplicates) {
      console.error(` - ${duplicate.logicalKey}`);
      for (const filePath of duplicate.files) {
        console.error(`   ${filePath}`);
      }
    }
    process.exitCode = 1;
    return;
  }

  console.log(`OK: no duplicate logical keys across ${result.checkedCount} XML files`);
}

if (require.main === module) {
  main();
}

module.exports = {
  checkDuplicateKeys,
};
