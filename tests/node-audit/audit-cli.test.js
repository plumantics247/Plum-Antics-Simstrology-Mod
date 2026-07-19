const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { mkdtempSync, mkdirSync, writeFileSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const path = require('node:path');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const CLI_ROOT = path.join(REPO_ROOT, 'tools', 'node-audit', 'cli');
const TS4SCRIPT_BASE_NAME = 'PlumAntics_Simstrology';
const CLI_TIMEOUT_MS = 10_000;

function createProjectRoot(t, populate) {
  const projectRoot = mkdtempSync(path.join(tmpdir(), 'node-audit-fixture-'));
  t.after(() => {
    rmSync(projectRoot, { recursive: true, force: true });
  });

  writeJson(projectRoot, 'package.json', {
    name: 'node-audit-fixture',
    version: '1.0.0',
    config: {
      ts4scriptBaseName: TS4SCRIPT_BASE_NAME,
    },
  });

  populate(projectRoot);
  return projectRoot;
}

function writeJson(projectRoot, relativePath, value) {
  writeFile(projectRoot, relativePath, JSON.stringify(value, null, 2));
}

function writeFile(projectRoot, relativePath, contents) {
  const filePath = path.join(projectRoot, relativePath);
  mkdirSync(path.dirname(filePath), { recursive: true });
  writeFileSync(filePath, contents);
  return filePath;
}

function runCli(relativeCliPath, projectRoot) {
  const cliPath = path.join(CLI_ROOT, relativeCliPath);
  const result = spawnSync(process.execPath, [cliPath, projectRoot], {
    cwd: REPO_ROOT,
    encoding: 'utf8',
    timeout: CLI_TIMEOUT_MS,
  });

  return {
    ...result,
    cliPath,
    relativeCliPath,
  };
}

function formatResult(result) {
  return [
    `cli: ${result.relativeCliPath}`,
    `path: ${result.cliPath}`,
    `status: ${result.status}`,
    `signal: ${result.signal ?? 'none'}`,
    `error: ${result.error ? `${result.error.name}: ${result.error.message}` : 'none'}`,
    'stdout:',
    result.stdout,
    'stderr:',
    result.stderr,
  ].join('\n');
}

function isMissingCli(result) {
  const output = `${result.stdout}\n${result.stderr}`;
  return result.status !== 0
    && /MODULE_NOT_FOUND/.test(output)
    && output.includes(result.cliPath);
}

function assertCliCompleted(result, context) {
  assert.equal(
    result.error,
    undefined,
    `${context}\nCLI process errored unexpectedly.\n${formatResult(result)}`,
  );
  assert.equal(
    result.signal,
    null,
    `${context}\nCLI process exited via signal unexpectedly.\n${formatResult(result)}`,
  );
}

function assertCliSucceeded(result, context) {
  assertCliCompleted(result, context);

  assert.equal(
    result.status,
    0,
    `${context}\n${isMissingCli(result) ? 'CLI not implemented yet.\n' : ''}${formatResult(result)}`,
  );
}

function assertCliFailed(result, context, expectedText) {
  assertCliCompleted(result, context);

  assert.notEqual(
    result.status,
    0,
    `${context}\n${formatResult(result)}`,
  );

  if (isMissingCli(result)) {
    assert.fail(
      `${context}\nCLI not implemented yet.\n${formatResult(result)}`,
    );
  }

  if (expectedText) {
    const output = `${result.stdout}\n${result.stderr}`;
    assert.match(
      output,
      expectedText,
      `${context}\n${formatResult(result)}`,
    );
  }
}

test('valid src XML passes', (t) => {
  const projectRoot = createProjectRoot(t, (root) => {
    writeFile(
      root,
      path.join('src', 'core', 'Trait', 'ValidTrait.xml'),
      [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<I n="ValidTrait" s="1234567890"></I>',
        '',
      ].join('\n'),
    );
  });

  const result = runCli('audit-src-xml.js', projectRoot);

  assertCliSucceeded(result, 'Expected valid XML fixture to pass src audit.');
});

test('malformed XML fails', (t) => {
  const projectRoot = createProjectRoot(t, (root) => {
    writeFile(
      root,
      path.join('src', 'core', 'Trait', 'BrokenTrait.xml'),
      '<I n="BrokenTrait"><U></I>\n',
    );
  });

  const result = runCli('audit-src-xml.js', projectRoot);

  assertCliFailed(
    result,
    'Expected malformed XML fixture to fail src audit.',
    /BrokenTrait\.xml|malformed|parse/i,
  );
});

test('duplicate basenames across folders fail duplicate-key audit', (t) => {
  const projectRoot = createProjectRoot(t, (root) => {
    writeFile(
      root,
      path.join('src', 'Alpha', 'SharedKey.xml'),
      '<I n="SharedKey" s="1"></I>\n',
    );
    writeFile(
      root,
      path.join('src', 'Beta', 'SharedKey.xml'),
      '<I n="SharedKey" s="2"></I>\n',
    );
  });

  const result = runCli('check-duplicate-keys.js', projectRoot);

  assertCliFailed(
    result,
    'Expected duplicate basenames to fail key audit.',
    /SharedKey\.xml/i,
  );
});

test('unique basenames pass duplicate-key audit', (t) => {
  const projectRoot = createProjectRoot(t, (root) => {
    writeFile(
      root,
      path.join('src', 'Alpha', 'FirstKey.xml'),
      '<I n="FirstKey" s="1"></I>\n',
    );
    writeFile(
      root,
      path.join('src', 'Beta', 'SecondKey.xml'),
      '<I n="SecondKey" s="2"></I>\n',
    );
  });

  const result = runCli('check-duplicate-keys.js', projectRoot);

  assertCliSucceeded(result, 'Expected unique basenames to pass key audit.');
});

test('missing expected ts4script output fails out audit', (t) => {
  const projectRoot = createProjectRoot(t, (root) => {
    mkdirSync(path.join(root, 'out'), { recursive: true });
  });

  const result = runCli('audit-out-artifacts.js', projectRoot);

  assertCliFailed(
    result,
    'Expected missing runtime artifacts to fail out audit.',
    /PlumAntics_Simstrology(?:\.source)?\.ts4script|missing/i,
  );
});

test('zero-byte ts4script output fails out audit', (t) => {
  const projectRoot = createProjectRoot(t, (root) => {
    writeFile(root, path.join('out', `${TS4SCRIPT_BASE_NAME}.ts4script`), '');
    writeFile(
      root,
      path.join('out', `${TS4SCRIPT_BASE_NAME}.source.ts4script`),
      'non-empty source archive placeholder',
    );
  });

  const result = runCli('audit-out-artifacts.js', projectRoot);

  assertCliFailed(
    result,
    'Expected zero-byte runtime artifact to fail out audit.',
    /PlumAntics_Simstrology\.ts4script|zero-byte|empty/i,
  );
});

test('expected non-empty ts4script filenames pass out audit', (t) => {
  const projectRoot = createProjectRoot(t, (root) => {
    writeFile(
      root,
      path.join('out', `${TS4SCRIPT_BASE_NAME}.ts4script`),
      'compiled runtime archive placeholder',
    );
    writeFile(
      root,
      path.join('out', `${TS4SCRIPT_BASE_NAME}.source.ts4script`),
      'source runtime archive placeholder',
    );
  });

  const result = runCli('audit-out-artifacts.js', projectRoot);

  assertCliSucceeded(
    result,
    'Expected non-empty ts4script filenames to pass the first out audit.',
  );
});



