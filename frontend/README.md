# Frontend — Workforce Management System (Next.js)

V0 foundations: App Router skeleton, root layout, a landing page that pings the
backend health endpoint, API client + config. No screens/auth yet (added per phase).

## Run (host)
```bash
cp .env.local.example .env.local
npm install
npm run dev    # http://localhost:3100
```

## Routes (added in later phases)
`(auth)/login`, `(app)/dashboard|employees|attendance|projects|reports` — see
`../docs/V1_ARCHITECTURE_PACKAGE.md` §5.
