const fs = require("fs");
const path = require("path");
const Module = require("module");


function parseArgs(argv) {
  let mode = "build";
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--mode") {
      mode = argv[index + 1] || "";
      index += 1;
    } else if (arg === "--help" || arg === "-h") {
      printUsage();
      process.exit(0);
    }
  }
  if (mode !== "build" && mode !== "release") {
    throw new Error(`Unsupported mode "${mode}". Expected "build" or "release".`);
  }
  return { mode };
}

function printUsage() {
  console.log("Usage: node .\\tools\\build_s4tk_packages.js --mode <build|release>");
}

function createUri(fsPath) {
  const resolved = path.resolve(fsPath);
  return {
    fsPath: resolved,
    path: resolved.replace(/\\/g, "/"),
    toString() {
      return this.fsPath;
    },
  };
}

function createFakeVscode() {
  class Range {
    constructor(startLine, startCharacter, endLine, endCharacter) {
      this.start = { line: startLine, character: startCharacter };
      this.end = { line: endLine, character: endCharacter };
    }
  }

  return {
    Range,
    Uri: {
      file(fsPath) {
        return createUri(fsPath);
      },
      joinPath(baseUri, ...segments) {
        return createUri(path.join(baseUri.fsPath, ...segments));
      },
    },
    workspace: {
      textDocuments: [],
      getConfiguration(section) {
        return {
          get(setting) {
            if (section === "s4tk") {
              const defaults = {
                defaultStringTableLocale: "English",
                showConfigLoadedMessage: false,
                showConfigUnloadedMessage: false,
              };
              return defaults[setting];
            }
            if (section === "editor" && setting === "tabSpaces") {
              return 2;
            }
            return undefined;
          },
        };
      },
    },
  };
}

function findS4tkExtensionRoot() {
  const extensionsRoot = path.join(process.env.USERPROFILE || "", ".vscode", "extensions");
  if (!extensionsRoot || !fs.existsSync(extensionsRoot)) {
    throw new Error("VS Code extensions folder was not found.");
  }

  const matches = fs
    .readdirSync(extensionsRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name.startsWith("sims4toolkit.s4tk-vscode-"))
    .map((entry) => path.join(extensionsRoot, entry.name))
    .sort((left, right) => right.localeCompare(left));

  if (!matches.length) {
    throw new Error("S4TK VS Code extension was not found under ~/.vscode/extensions.");
  }

  return matches[0];
}

function resolveGlobPattern(baseFsPath, pattern) {
  return `${baseFsPath}/${pattern}`.replace(/\\/g, "/");
}

function createWorkspace(rootPath, config) {
  const rootUri = createUri(rootPath);
  return {
    rootUri,
    active: true,
    config,
    resolvePath(relativePath, isGlob = false) {
      if (isGlob) {
        return resolveGlobPattern(rootUri.fsPath, relativePath);
      }
      return path.isAbsolute(relativePath)
        ? path.normalize(relativePath)
        : path.resolve(rootUri.fsPath, relativePath);
    },
  };
}

async function main() {
  const { mode } = parseArgs(process.argv.slice(2));
  const rootPath = path.resolve(__dirname, "..");
  const extensionRoot = findS4tkExtensionRoot();
  const fakeVscode = createFakeVscode();
  const originalLoad = Module._load;

  Module._load = function patchedLoad(request, parent, isMain) {
    if (request === "vscode") {
      return fakeVscode;
    }
    return originalLoad.call(this, request, parent, isMain);
  };

  try {
    const assets = require(path.join(extensionRoot, "out", "assets.js")).default;
    assets.setExtensionContext({
      extension: {
        extensionUri: createUri(extensionRoot),
      },
    });

    const { S4TKConfig } = require(path.join(extensionRoot, "out", "core", "models", "s4tk-config.js"));
    const { buildProject } = require(path.join(extensionRoot, "out", "core", "building", "builder.js"));

    const configPath = path.join(rootPath, "s4tk.config.json");
    const config = S4TKConfig.parse(fs.readFileSync(configPath, "utf8"));
    const workspace = createWorkspace(rootPath, config);
    const summary = await buildProject(workspace, mode);

    const summaryPath = path.join(rootPath, "BuildSummary.json");
    fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");

    if (!summary.buildInfo.success) {
      throw new Error(summary.buildInfo.fatalErrorMessage || `S4TK ${mode} failed.`);
    }

    console.log(`S4TK ${mode} completed successfully.`);
    console.log(`BuildSummary.json written to ${summaryPath}`);
  } finally {
    Module._load = originalLoad;
  }
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
