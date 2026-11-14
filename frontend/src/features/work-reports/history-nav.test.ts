import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

/**
 * Report preview <-> edit must never loop in browser history.
 *
 * History must stay `Reports -> Report`: opening Edit, saving, "← Report" and
 * Delete all REPLACE the current entry, so Back from the preview (and the
 * edit form's Cancel) lands on the Reports log - never on the edit form.
 * No React render harness exists under `node --test`; guard at source level.
 */
const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

test("preview opens Edit with replace (both Edit buttons)", () => {
  const src = read("./components/work-report-detail.tsx");
  const replaced = src.match(/<Link href=\{`\/work-reports\/\$\{report\.id\}\/edit`\} replace>/g) ?? [];
  assert.equal(replaced.length, 2);
  assert.equal(/<Link href=\{`\/work-reports\/\$\{report\.id\}\/edit`\}>/.test(src), false);
});

test("saving returns to the preview by replacing the form's entry", () => {
  const src = read("./components/work-report-form.tsx");
  assert.ok(src.includes("router.replace(`/work-reports/${result.id}`);"));
  assert.equal(src.includes("router.push(`/work-reports/${result.id}`)"), false);
  assert.ok(src.includes("router.replace(`/work-reports/${savedReportId}/edit`);"));
});

test("'← Report' on the edit page replaces too", () => {
  const src = read("./components/work-report-edit.tsx");
  assert.match(src, /href=\{`\/work-reports\/\$\{report\.id\}`\}\s*replace/);
});

test("deleting from the preview replaces it with the Reports log", () => {
  const src = read("./components/work-report-detail.tsx");
  assert.ok(src.includes('onDone={() => router.replace("/reports")}'));
  assert.equal(src.includes('router.push("/reports")'), false);
});
