// web-test core/fsutil v1.0 - deletion and copying robust to non-ASCII paths on Windows.
// Source: https://github.com/Nikolay-Shirokov/cc-1c-skills

// ─── fsutil:begin ───────────────────────────────────────────────────────────
// Below this marker the file is byte-for-byte identical to the second copy. Divergence is caught by
// tests/skills/check-nonascii-fs.mjs. Make edits in both copies at once.

import { cpSync, copyFileSync, existsSync, lstatSync, mkdirSync, readdirSync,
         rmSync, rmdirSync, unlinkSync } from 'node:fs';
import { join, resolve } from 'node:path';

// On Windows fs.rmSync and fs.cpSync break when non-ASCII characters are in the path argument
// ITSELF (nodejs/node#61067, upstream still open). Captured on a stand of eight builds:
//
//   build                          rmSync   cpSync → dest       cpSync ← source
//   22.15.1                        ok       ok                  ok
//   22.18.0 … 22.23.2 (LTS Jod)    ok       silently nothing    crash 0xC0000409
//   24.12.0, 24.13.0               silently silently nothing    crash
//   24.14.0                        ok       silently nothing    crash
//   24.15.0, 24.19.0, 25.9.0, 26.7.0   ok   ok                  ok
//
// This is NOT a workaround for one old release: the 22 LTS branch is still broken - the fix landed in
// the Node 24.15 fs layer and was not backported to 22.x, while the project README recommends "Node.js 18+".
// The dependency is not monotonic across versions (24.14 fixes rmSync but not cpSync), so a version-number
// guard is impossible in principle: only the path itself decides. The guard can be removed only when
// the whole supported line becomes healthy, not just the current developer machine.
//
// mkdirSync, readdirSync, lstatSync, existsSync, copyFileSync (including overwrite),
// unlinkSync, rmdirSync with non-ASCII are healthy on ALL broken builds - the manual walk relies on them.
// Asynchronous fs.promises.rm/cp are not affected.

const NON_ASCII = /[^\x00-\x7F]/;
const RETRY_CODES = new Set(['EBUSY', 'EPERM', 'ENOTEMPTY', 'EMFILE']);

// We check the RESOLVED path, not the argument string: a relative ASCII argument with a
// non-ASCII cwd crashes the platform just as silently, and the argument string does not show it.
export function pathIsUnsafe(p) {
  // Test seam only for check-nonascii-fs.mjs: without it the manual walk never runs
  // on macOS/Linux and stays uncovered. In a normal run the variable is not set.
  if (process.env.CC1C_FSUTIL_FORCE_WALK === "1") return true;
  return process.platform === 'win32' && NON_ASCII.test(resolve(p));
}

function sleepSync(ms) {
  if (ms > 0) Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function withRetrySync(fn, maxRetries, retryDelay) {
  for (let attempt = 0; ; attempt++) {
    try { return fn(); }
    catch (e) {
      if (attempt >= maxRetries || !RETRY_CODES.has(e.code)) throw e;
      sleepSync(retryDelay);
    }
  }
}

// Symlink or junction to a directory: unlinkSync gives EPERM on it, rmdirSync removes it.
// We do not go inside - rmSync also removes the link itself, not its target.
function removeLeafSync(p) {
  try { unlinkSync(p); }
  catch (e) {
    if (e.code !== 'EPERM' && e.code !== 'EISDIR') throw e;
    rmdirSync(p);
  }
}

function removeTreeWalkSync(dir, maxRetries, retryDelay) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const child = join(dir, entry.name);
    if (entry.isDirectory()) removeTreeWalkSync(child, maxRetries, retryDelay);
    else withRetrySync(() => removeLeafSync(child), maxRetries, retryDelay);
  }
  withRetrySync(() => rmdirSync(dir), maxRetries, retryDelay);
}

// rm -rf semantics: file, directory or missing path. opts.maxRetries / opts.retryDelay
// work on both paths - on the fast one rmSync accepts them, on the manual walk we retry ourselves.
export function removePathSync(target, opts = {}) {
  const { maxRetries = 0, retryDelay = 100 } = opts;

  if (!pathIsUnsafe(target)) {
    rmSync(target, { recursive: true, force: true, maxRetries, retryDelay });
    // A silent failure right here is the disease: confirm the result with a single existsSync.
    if (!existsSync(target)) return;
  } else if (!existsSync(target)) {
    return;
  }

  if (lstatSync(target).isDirectory()) removeTreeWalkSync(target, maxRetries, retryDelay);
  else withRetrySync(() => removeLeafSync(target), maxRetries, retryDelay);

  if (existsSync(target)) throw new Error(`Не удалось удалить путь: ${target}`);
}

function copyTreeWalkSync(src, dest) {
  mkdirSync(dest, { recursive: true });
  for (const entry of readdirSync(src, { withFileTypes: true })) {
    const from = join(src, entry.name);
    const to = join(dest, entry.name);
    // Overwrite unconditionally - like cpSync with the default force: true.
    if (entry.isDirectory()) copyTreeWalkSync(from, to);
    else copyFileSync(from, to);
  }
}

// Recursive copy of a DIRECTORY with overwrite. For a single file copyFileSync is enough:
// it is not affected and works with non-ASCII on all builds.
export function copyTreeSync(src, dest) {
  if (!pathIsUnsafe(src) && !pathIsUnsafe(dest)) {
    // We do not swallow errors: a real ENOENT/EACCES must reach the caller.
    cpSync(src, dest, { recursive: true });
    return;
  }
  copyTreeWalkSync(src, dest);
}
