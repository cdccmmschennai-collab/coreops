/**
 * RBAC role verification pass — CoreOps v2
 * Clean URL-only route detection. Seed data present for leave approval.
 */
const { chromium } = require('C:\\Users\\softuser1\\AppData\\Local\\npm-cache\\_npx\\e41f203b7505f1fb\\node_modules\\playwright');
const fs = require('fs');
const path = require('path');

const BASE = 'http://localhost:3100';
const OUT  = path.join(__dirname, 'rbac_evidence');
fs.mkdirSync(OUT, { recursive: true });

const ACCOUNTS = [
  { role: 'admin',    email: 'admin@coreops.local',    password: 'Admin@123' },
  { role: 'manager',  email: 'manager@coreops.local',  password: 'Manager@123' },
  { role: 'employee', email: 'employee@coreops.local', password: 'Employee@123' },
];

let step = 0;
async function shot(page, role, label) {
  const name = `${String(++step).padStart(3,'0')}_${role}_${label}.png`;
  await page.screenshot({ path: path.join(OUT, name), fullPage: false });
  return name;
}

async function login(page, role, email, password) {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1200);

  const emailInput = page.locator('input[type="email"]').first();
  await emailInput.waitFor({ state: 'visible', timeout: 6000 });
  await emailInput.click({ clickCount: 3 });
  await emailInput.type(email, { delay: 40 });

  const passInput = page.locator('input[type="password"]').first();
  await passInput.click({ clickCount: 3 });
  await passInput.type(password, { delay: 40 });

  await page.locator('button[type="submit"]').click();

  try {
    await page.waitForFunction(() => !window.location.pathname.startsWith('/login'), { timeout: 10000 });
  } catch {
    await shot(page, role, 'LOGIN_FAIL');
    return false;
  }
  await page.waitForTimeout(1500);
  return true;
}

async function visitRoute(page, role, route) {
  await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle', timeout: 12000 }).catch(() => {});
  await page.waitForTimeout(1000);
  const finalUrl = page.url().replace(BASE, '');
  const redirectedToLogin   = finalUrl.startsWith('/login');
  const redirectedElsewhere = !finalUrl.startsWith(route) && !redirectedToLogin;
  // RequireCapability renders "Not allowed" inline without redirecting
  const bodyText = await page.textContent('body').catch(() => '');
  const hasNotAllowed = /not allowed|don.t have permission/i.test(bodyText);
  const blocked = redirectedToLogin || redirectedElsewhere || hasNotAllowed;
  const img = await shot(page, role, `route_${route.replace(/\//g,'_')}`);
  return { route, finalUrl, blocked, redirectedToLogin, redirectedElsewhere, hasNotAllowed, img };
}

async function clickTab(page, label) {
  const tab = page.getByRole('tab', { name: label });
  if (await tab.isVisible({ timeout: 3000 }).catch(() => false)) {
    await tab.click();
    await page.waitForTimeout(2000); // extra time for React Query fetch
    return true;
  }
  const btn = page.locator(`button:has-text("${label}")`).first();
  if (await btn.isVisible({ timeout: 1000 }).catch(() => false)) {
    await btn.click();
    await page.waitForTimeout(2000);
    return true;
  }
  return false;
}

async function verifyRole(browser, account) {
  const { role, email, password } = account;
  console.log(`\n${'='.repeat(64)}`);
  console.log(`🔐 ${role.toUpperCase()}  (${email})`);
  console.log('='.repeat(64));

  const ctx  = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();
  const R = { role, loginOk: false, routes: [], checks: [], sidebar: [] };

  // ── LOGIN ──
  await shot(page, role, '01_login_page');
  R.loginOk = await login(page, role, email, password);
  if (!R.loginOk) { console.log('  ❌ Login FAILED'); await ctx.close(); return R; }

  await shot(page, role, '02_landing');
  R.landingUrl = page.url().replace(BASE, '');
  console.log(`  ✅ Login OK → ${R.landingUrl}`);

  // ── SIDEBAR ──
  await page.goto(`${BASE}/dashboard`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  R.sidebar = (await page.getByRole('navigation').locator('a').allTextContents())
    .map(t => t.trim()).filter(Boolean);
  await shot(page, role, '03_sidebar');
  console.log(`  📋 Nav: [${R.sidebar.join(' | ')}]`);

  // ── ROUTE CHECKS ──
  const routes = ['/dashboard','/employees','/employees/new','/projects',
                  '/attendance','/reports','/analytics','/settings'];
  for (const route of routes) {
    const r = await visitRoute(page, role, route);
    R.routes.push(r);
    const icon = r.blocked ? '🚫' : '✅';
    console.log(`  ${icon} ${route.padEnd(20)} → ${r.finalUrl.padEnd(30)} blocked=${r.blocked}`);
  }

  // ── ATTENDANCE PAGE ──
  await page.goto(`${BASE}/attendance`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  await shot(page, role, '04_attendance');

  // Request Leave button
  const hasReqLeave = await page.locator('button:has-text("Request Leave")').first()
    .isVisible({ timeout: 1500 }).catch(() => false);
  R.checks.push({ name: 'Request Leave button visible', value: hasReqLeave });
  console.log(`  ${hasReqLeave ? '⚠️ ' : '✅'} Request Leave button: ${hasReqLeave}`);

  // Show all tabs visible on attendance page
  const allTabs = await page.getByRole('tab').allTextContents();
  console.log(`  📌 Attendance tabs: [${allTabs.join(' | ')}]`);

  // ── LEAVE TAB ──
  const leaveClicked = await clickTab(page, 'Leave');
  if (leaveClicked) {
    await shot(page, role, '05_leave_tab');
    const approveVisible = await page.locator('button:has-text("Approve")').first()
      .isVisible({ timeout: 1500 }).catch(() => false);
    const rejectVisible  = await page.locator('button:has-text("Reject")').first()
      .isVisible({ timeout: 1500 }).catch(() => false);
    const bodyText = await page.textContent('body');
    const hasMyHistory = /My leave history/i.test(bodyText ?? '');
    R.checks.push(
      { name: 'Leave tab: Approve button', value: approveVisible },
      { name: 'Leave tab: Reject button',  value: rejectVisible },
      { name: 'Leave tab: My leave history', value: hasMyHistory },
    );
    console.log(`  📋 Leave tab — Approve:${approveVisible}  Reject:${rejectVisible}  MyHistory:${hasMyHistory}`);
  } else {
    console.log('  ⚠️  Leave tab not found');
  }

  // ── HOLIDAYS TAB ──
  await page.goto(`${BASE}/attendance`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  const holidayClicked = await clickTab(page, 'Holidays');
  if (holidayClicked) {
    await shot(page, role, '06_holidays_tab');
    const bodyText = await page.textContent('body');
    const hasAddForm  = /New Holiday|Add Holiday/i.test(bodyText ?? '');
    const hasDeleteBtn = await page.locator('[aria-label*="Remove"]').first()
      .isVisible({ timeout: 1500 }).catch(() => false);
    R.checks.push(
      { name: 'Holidays tab: Add Holiday form', value: hasAddForm },
    );
    console.log(`  📋 Holidays tab — AddHoliday:${hasAddForm}  DeleteBtn:${hasDeleteBtn}`);
  } else {
    console.log('  ⚠️  Holidays tab not found');
    R.checks.push({ name: 'Holidays tab: Add Holiday form', value: false });
  }

  // ── ROLE-SPECIFIC DEEP CHECKS ──
  if (role === 'employee') {
    await page.goto(`${BASE}/attendance`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    const rlBtn = page.locator('button:has-text("Request Leave")').first();
    if (await rlBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await rlBtn.click();
      await page.waitForTimeout(800);
      await shot(page, role, '07_leave_modal');
      // Modal has a "Request Leave" heading
      const modalHeading = await page.locator('text="Request Leave"').nth(1)
        .isVisible({ timeout: 2000 }).catch(() => false);
      const hasForm = await page.locator('form, select[name], input[name]').first()
        .isVisible({ timeout: 1500 }).catch(() => false);
      R.checks.push({ name: 'Leave modal opens', value: modalHeading || hasForm });
      console.log(`  ${(modalHeading || hasForm) ? '✅' : '❌'} Leave modal: ${modalHeading || hasForm}`);
      await page.keyboard.press('Escape');
    } else {
      R.checks.push({ name: 'Leave modal opens', value: false });
      console.log('  ❌ Request Leave button not found for employee');
    }
  }

  if (role === 'admin') {
    await page.goto(`${BASE}/employees/new`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(800);
    const hasForm = await page.locator('form').first().isVisible({ timeout: 2000 }).catch(() => false);
    const notRedirected = !page.url().includes('/login');
    await shot(page, role, '07_employees_new');
    R.checks.push({ name: 'Admin /employees/new accessible', value: hasForm && notRedirected });
    console.log(`  ${(hasForm && notRedirected) ? '✅' : '❌'} /employees/new form=${hasForm} notRedirected=${notRedirected}`);

    await page.goto(`${BASE}/settings`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(800);
    await shot(page, role, '08_settings');
    const settingsOk = !page.url().includes('/login') && page.url().includes('/settings');
    R.checks.push({ name: 'Admin /settings accessible', value: settingsOk });
    console.log(`  ${settingsOk ? '✅' : '❌'} /settings url=${page.url().replace(BASE,'')}`);
  }

  if (role === 'manager') {
    await page.goto(`${BASE}/employees/new`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    const empNewBody = await page.textContent('body').catch(() => '');
    const empNewBlocked = page.url().includes('/login')
      || !page.url().includes('/employees/new')
      || /not allowed|don.t have permission/i.test(empNewBody);
    await shot(page, role, '07_employees_new');
    R.checks.push({ name: 'Manager blocked from /employees/new', value: empNewBlocked });
    console.log(`  ${empNewBlocked ? '✅' : '❌'} /employees/new blocked=${empNewBlocked}  url=${page.url().replace(BASE,'')}`);

    await page.goto(`${BASE}/settings`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    const settingsBody = await page.textContent('body').catch(() => '');
    const settingsBlocked = page.url().includes('/login')
      || !page.url().includes('/settings')
      || /not allowed|don.t have permission/i.test(settingsBody);
    await shot(page, role, '08_settings');
    R.checks.push({ name: 'Manager blocked from /settings', value: settingsBlocked });
    console.log(`  ${settingsBlocked ? '✅' : '❌'} /settings blocked=${settingsBlocked}  url=${page.url().replace(BASE,'')}`);
  }

  // ── LOGOUT ──
  await page.evaluate(() => { try { localStorage.removeItem('wms.token'); } catch {} });
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await shot(page, role, '09_logout');
  console.log('  ✅ Logged out');

  await ctx.close();
  return R;
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const allResults = [];
  for (const account of ACCOUNTS) allResults.push(await verifyRole(browser, account));
  await browser.close();

  // ── EXPECTED matrix ──
  const EXP = {
    admin: {
      routes: { '/dashboard':'accessible','/employees':'accessible','/employees/new':'accessible',
                '/projects':'accessible','/attendance':'accessible','/reports':'accessible',
                '/analytics':'accessible','/settings':'accessible' },
      checks: {
        'Request Leave button visible': false,
        'Leave tab: Approve button': false,
        'Leave tab: My leave history': false,
        'Holidays tab: Add Holiday form': true,
        'Admin /employees/new accessible': true,
        'Admin /settings accessible': true,
      }
    },
    manager: {
      routes: { '/dashboard':'accessible','/employees':'accessible','/employees/new':'blocked',
                '/projects':'accessible','/attendance':'accessible','/reports':'accessible',
                '/analytics':'accessible','/settings':'blocked' },
      checks: {
        'Request Leave button visible': false,
        'Leave tab: Approve button': true,
        'Leave tab: My leave history': false,
        'Holidays tab: Add Holiday form': true,
        'Manager blocked from /employees/new': true,
        'Manager blocked from /settings': true,
      }
    },
    employee: {
      routes: { '/dashboard':'accessible','/employees':'blocked','/employees/new':'blocked',
                '/projects':'blocked','/attendance':'accessible','/reports':'accessible',
                '/analytics':'blocked','/settings':'blocked' },
      checks: {
        'Request Leave button visible': true,
        'Leave modal opens': true,
        'Leave tab: Approve button': false,
        'Leave tab: My leave history': false,
        'Holidays tab: Add Holiday form': false,
      }
    },
  };

  console.log(`\n${'='.repeat(64)}`);
  console.log('  RBAC VERIFICATION REPORT');
  console.log('='.repeat(64));

  let total = 0, pass = 0, fail = 0;
  const mismatches = [];

  for (const R of allResults) {
    const exp = EXP[R.role];
    console.log(`\n── ${R.role.toUpperCase()} ──`);
    if (!R.loginOk) {
      console.log('  ❌ Login FAILED'); fail++; total++; mismatches.push(`${R.role} LOGIN`); continue;
    }

    for (const r of R.routes) {
      const expVal = exp.routes[r.route];
      if (!expVal) continue;
      total++;
      const actualOk = !r.blocked;
      const expectedOk = expVal === 'accessible';
      if (actualOk === expectedOk) {
        pass++;
        console.log(`  ✅ ${r.route.padEnd(22)} ${expVal}`);
      } else {
        fail++;
        const actual = r.blocked ? 'blocked' : 'accessible';
        console.log(`  ❌ ${r.route.padEnd(22)} actual=${actual}  expected=${expVal}  url=${r.finalUrl}`);
        mismatches.push(`${R.role} ${r.route}`);
      }
    }

    for (const c of R.checks) {
      const expVal = exp.checks[c.name];
      if (expVal === undefined) { console.log(`  ℹ️  ${c.name}: ${c.value}`); continue; }
      total++;
      if (c.value === expVal) {
        pass++;
        console.log(`  ✅ ${c.name}: ${c.value}`);
      } else {
        fail++;
        console.log(`  ❌ ${c.name}: ${c.value}  (expected ${expVal})`);
        mismatches.push(`${R.role} — ${c.name}`);
      }
    }
  }

  console.log(`\n${'='.repeat(64)}`);
  console.log(`  Checks: ${total}   Pass: ${pass}   Fail: ${fail}`);
  if (mismatches.length) {
    console.log('\n  MISMATCHES:');
    mismatches.forEach(m => console.log(`    ❌ ${m}`));
  }
  console.log(`\n  Verdict: ${fail === 0 ? '✅  PASS — all RBAC checks hold' : '❌  FAIL'}`);
  console.log(`  Evidence → ${OUT}`);
  console.log('='.repeat(64));

  fs.writeFileSync(path.join(OUT, 'report.json'),
    JSON.stringify({ allResults, mismatches, pass, fail, total }, null, 2));
})();
