# CoreOps Notifications — Deployment & Testing

Email notification infrastructure for CoreOps. Phase 1 ships exactly one
notification: the **Daily Missing Report Reminder** to Project Managers.

## Architecture (layered, single responsibility)

```
Celery Beat  (app/core/celery_app.py: beat_schedule)
     │  enqueues at 09:30 Asia/Kolkata
     ▼
Celery Task  (app/tasks/periodic_tasks.py)         # thin trigger only
     ▼
Dispatcher   (app/reminders/daily_report/dispatcher.py)  # orchestration + logging
     ├─ Reminder Service (service.py)   # who owes which reports -> data only
     ├─ Template         (template.py)  # data -> subject/html/text
     └─ Email Service    (app/notifications/email_service.py)  # SMTP transport only
```

Layers never leak: the reminder service knows nothing about SMTP/HTML, the email
service knows nothing about reports, and the Celery task contains no SQL, SMTP,
or templating.

## Processes (run independently)

| Service           | Command                                                             |
|-------------------|--------------------------------------------------------------------|
| `coreops-api`     | `uvicorn app.main:app` (also applies migrations on start)          |
| `coreops-worker`  | `celery -A app.core.celery_app.celery_app worker`                  |
| `coreops-beat`    | `celery -A app.core.celery_app.celery_app beat`                    |

The backend keeps serving even if the worker/beat are stopped — Celery is never
imported by the API.

## systemd install (Linux server)

```bash
sudo cp deploy/systemd/coreops-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now coreops-api coreops-worker coreops-beat
sudo systemctl status coreops-worker coreops-beat
journalctl -u coreops-worker -f      # watch worker logs
```

Adjust `User`, `WorkingDirectory`, venv path, and `EnvironmentFile` in the unit
files to match the server layout (defaults assume `/opt/coreops/backend`). Run a
**single** beat instance across the fleet.

## Configuration (environment only — no hardcoded secrets)

See `backend/.env.example`. Key variables:

- SMTP: `EMAIL_ENABLED`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`,
  `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_FROM_NAME`, `SMTP_USE_TLS`, `SMTP_USE_SSL`.
- Schedule: `REMINDER_SCHEDULE_ENABLED`, `REMINDER_EVERY_MINUTE` (testing),
  `REMINDER_HOUR`, `REMINDER_MINUTE`.
- Debug: `ENABLE_DEBUG_ENDPOINTS` (mounts `/debug/*`, PM-role gated).

`EMAIL_ENABLED=false` makes every send a logged no-op — safe default until SMTP
is verified.

## Testing (phased)

**Phase 1 — processes start**
```bash
celery -A app.core.celery_app.celery_app worker --loglevel=info
celery -A app.core.celery_app.celery_app beat   --loglevel=info
```

Set `ENABLE_DEBUG_ENDPOINTS=true` and authenticate as a project_manager for the
rest. Endpoints are under the API prefix, e.g. `POST /api/v1/debug/send-test-email`.

**Phase 2 — SMTP works**
```
POST /api/v1/debug/send-test-email   { "to": "you@gmail.com" }
```
Verify Gmail + company inbox receive it. (Requires `EMAIL_ENABLED=true`.)

**Phase 3 — grouping is correct**
```
GET /api/v1/debug/missing-reports     # JSON only, no email sent
```

**Phase 4 — reminders send correctly**
```
POST /api/v1/debug/send-reminders     # one email per affected PM
```
Verify correct PM, employees, dates, and exactly one email per PM.

**Phase 5 — beat schedule**
Set `REMINDER_EVERY_MINUTE=true`, restart beat, confirm it fires each minute.
Then set it back to `false` (09:30 Asia/Kolkata) for production and restart beat.

## Logging

Each run logs: `reminder.started`, per-PM `reminder.pm` (employees checked +
missing found), `reminder.email_sent` / `reminder.email_failed`, and
`reminder.completed` (totals). A single PM's email failure is logged and the run
continues with the remaining PMs.
