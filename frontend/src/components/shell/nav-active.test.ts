import assert from "node:assert/strict";
import { test } from "node:test";

import { isNavItemActive, type NavMatch } from "./nav-active.ts";

const HOME: NavMatch = { href: "/dashboard" };
const EMPLOYEES: NavMatch = { href: "/employees" };
const PROJECTS: NavMatch = { href: "/projects" };
const REPORTS: NavMatch = { href: "/reports", alsoMatch: ["/work-reports"] };
const NOTIFICATIONS: NavMatch = { href: "/notifications" };

test("an exact route match activates its item", () => {
  assert.equal(isNavItemActive("/dashboard", HOME), true);
  assert.equal(isNavItemActive("/projects", PROJECTS), true);
});

test("nested employee pages keep Employees active", () => {
  assert.equal(isNavItemActive("/employees/emp-1", EMPLOYEES), true);
  assert.equal(isNavItemActive("/employees/emp-1/edit", EMPLOYEES), true);
  assert.equal(isNavItemActive("/employees/new", EMPLOYEES), true);
});

test("nested project pages keep Projects active", () => {
  assert.equal(isNavItemActive("/projects/proj-1", PROJECTS), true);
  assert.equal(isNavItemActive("/projects/proj-1/edit", PROJECTS), true);
  assert.equal(isNavItemActive("/projects/list", PROJECTS), true);
});

test("deliverables stay under Projects rather than activating nothing", () => {
  assert.equal(isNavItemActive("/projects/deliverables", PROJECTS), true);
  assert.equal(isNavItemActive("/projects/deliverables/del-1", PROJECTS), true);
});

test("/work-reports activates Reports through alsoMatch", () => {
  assert.equal(isNavItemActive("/work-reports", REPORTS), true);
  assert.equal(isNavItemActive("/work-reports/new", REPORTS), true);
  assert.equal(isNavItemActive("/work-reports/rep-1", REPORTS), true);
  assert.equal(isNavItemActive("/work-reports/rep-1/edit", REPORTS), true);
});

test("Reports still owns its own route", () => {
  assert.equal(isNavItemActive("/reports", REPORTS), true);
});

test("a sibling route never activates an unrelated item", () => {
  assert.equal(isNavItemActive("/notifications", HOME), false);
  assert.equal(isNavItemActive("/work-reports", PROJECTS), false);
  assert.equal(isNavItemActive("/employees", PROJECTS), false);
  assert.equal(isNavItemActive("/dashboard", NOTIFICATIONS), false);
});

test("a shared prefix does not leak activation across routes", () => {
  assert.equal(isNavItemActive("/projects-archive", PROJECTS), false);
  assert.equal(isNavItemActive("/reports-export", REPORTS), false);
  assert.equal(isNavItemActive("/work-reports-export", REPORTS), false);
});

test("a route with no nav entry activates nothing", () => {
  for (const item of [HOME, EMPLOYEES, PROJECTS, REPORTS, NOTIFICATIONS]) {
    assert.equal(isNavItemActive("/activity-requests", item), false);
    assert.equal(isNavItemActive("/profile", item), false);
    assert.equal(isNavItemActive("/account/change-password", item), false);
  }
});

test("an item without alsoMatch is unaffected by the alsoMatch branch", () => {
  assert.equal(isNavItemActive("/work-reports", HOME), false);
});
