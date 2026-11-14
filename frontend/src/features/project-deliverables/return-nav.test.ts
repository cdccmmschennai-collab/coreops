import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { beforeEach, test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  cameFromList,
  leaveDetail,
  rememberListReturn,
} from "./return-nav.ts";

// Minimal per-tab sessionStorage stand-in.
function installStorage(): void {
  const store = new Map<string, string>();
  (globalThis as { window?: unknown }).window = {
    sessionStorage: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    },
  };
}

function spyNav() {
  const calls: string[] = [];
  return {
    calls,
    nav: {
      back: () => void calls.push("back"),
      replace: (href: string) => void calls.push(`replace ${href}`),
    },
  };
}

beforeEach(installStorage);

test("opened from the list -> Back goes BACK (no new history entry)", () => {
  rememberListReturn("d1");
  const { calls, nav } = spyNav();
  leaveDetail("d1", "/projects/deliverables?status=planned", nav);
  assert.deepEqual(calls, ["back"]);
});

test("opened from elsewhere (notification / banner / pasted link) -> replace, never push", () => {
  const { calls, nav } = spyNav();
  leaveDetail("d2", "/projects/deliverables", nav);
  assert.deepEqual(calls, ["replace /projects/deliverables"]);
});

test("the record is used once, so a revisit cannot go back into a loop", () => {
  rememberListReturn("d3");
  leaveDetail("d3", "/projects/deliverables", spyNav().nav);
  assert.equal(cameFromList("d3"), false);
  const { calls, nav } = spyNav();
  leaveDetail("d3", "/projects/deliverables", nav);
  assert.deepEqual(calls, ["replace /projects/deliverables"]);
});

test("records are per deliverable", () => {
  rememberListReturn("a");
  assert.equal(cameFromList("a"), true);
  assert.equal(cameFromList("b"), false);
});

test("blocked storage falls back to replace instead of throwing", () => {
  (globalThis as { window?: unknown }).window = {
    sessionStorage: {
      getItem: () => { throw new Error("blocked"); },
      setItem: () => { throw new Error("blocked"); },
      removeItem: () => { throw new Error("blocked"); },
    },
  };
  rememberListReturn("x");
  const { calls, nav } = spyNav();
  leaveDetail("x", "/projects/deliverables", nav);
  assert.deepEqual(calls, ["replace /projects/deliverables"]);
});

// No React render harness under node --test: guard the wiring at source level.
test("details page: Edit/Delete left of the status badge, managers only, no-loop exits", () => {
  const src = readFileSync(
    fileURLToPath(new URL("./components/deliverable-detail.tsx", import.meta.url)),
    "utf8",
  );
  const at = (s: string) => src.indexOf(s);
  assert.ok(src.includes("canManageRow(deliverable) && !editing"));
  assert.ok(at('aria-label="Edit"') < at('aria-label="Delete"'));
  assert.ok(at('aria-label="Delete"') < at("<DeliverableStatusBadge status={deliverable.status} />"));
  // Reuses the list page's form and confirm dialog - nothing new.
  assert.ok(src.includes("<DeliverableFormPanel"));
  assert.ok(src.includes("<DeleteDeliverableDialog"));
  // Back link and post-delete both leave via the loop-free helper.
  assert.ok(src.includes("leaveDetail(id, backHref, router)"));
  assert.match(src, /onDeleted=\{\(\) => \{\s*setPendingDelete\(null\);\s*goBack\(\);/);
  assert.ok(src.includes("e.preventDefault();"));

  const list = readFileSync(
    fileURLToPath(new URL("./components/all-deliverables-view.tsx", import.meta.url)),
    "utf8",
  );
  assert.match(list, /rememberListReturn\(id\);\s*router\.push\(deliverableDetailHref\(id, here\)\);/);
});
