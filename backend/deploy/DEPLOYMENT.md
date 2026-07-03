# CoreOps Notifications - VPS Deployment Guide

Step-by-step guide to run the Daily Report Reminder automation on a VPS with
systemd. Three independent services:

| Service           | Role                                             |
|-------------------|--------------------------------------------------|
| `coreops-backend` | FastAPI API (also applies DB migrations on start)|
| `coreops-worker`  | Celery worker - executes the reminder task       |
| `coreops-beat`    | Celery beat - schedules the reminder task        |

The API keeps serving even if worker/beat are stopped (the backend never imports
Celery). Run exactly ONE beat instance.

---

## 0. Prerequisites (once)

```bash
# App at /opt/coreops (adjust paths in the unit files if you use another location)
cd /opt/coreops/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Configure environment - copy the template and fill in real values.
cp .env.example .env
```

Edit `/opt/coreops/backend/.env` and set at least:

```ini
# SMTP (Brevo) - real secret lives ONLY in this file, never in git.
EMAIL_ENABLED=true
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USERNAME=<brevo-smtp-login>
SMTP_PASSWORD=<brevo-smtp-key>
SMTP_FROM=noreply@coreops.cdccmms.com
SMTP_FROM_NAME=CoreOps

# Schedule - PRODUCTION default (09:30 Asia/Kolkata).
REMINDER_SCHEDULE_ENABLED=true
REMINDER_EVERY_MINUTE=false
REMINDER_HOUR=9
REMINDER_MINUTE=30

# Broker / DB point at the VPS services.
CELERY_BROKER_URL=redis://localhost:6379/1
DATABASE_URL=postgresql+psycopg://...
```

Confirm `.env` is not world-readable (it holds the SMTP key):

```bash
chmod 600 /opt/coreops/backend/.env
```

---

## 1. Install the systemd unit files

```bash
sudo cp /opt/coreops/backend/deploy/systemd/coreops-*.service /etc/systemd/system/
sudo systemctl daemon-reload
```

If your app path, service user, or venv differ from the defaults
(`/opt/coreops/backend`, user `coreops`, `.venv/`), edit the three unit files
before `daemon-reload`.

---

## 2. Start the services

Start the backend first (it runs migrations), then worker, then beat:

```bash
sudo systemctl start coreops-backend
sudo systemctl start coreops-worker
sudo systemctl start coreops-beat
```

### Enable both automation services at boot

```bash
sudo systemctl enable coreops-worker
sudo systemctl enable coreops-beat
# (enable the backend too if systemd manages it)
sudo systemctl enable coreops-backend

# Or start + enable in one step:
sudo systemctl enable --now coreops-worker coreops-beat
```

---

## 3. Verify with systemctl status

```bash
systemctl status coreops-worker
systemctl status coreops-beat
```

Expect `Active: active (running)`. Healthy markers:

- worker: `Connected to redis://.../1` and `celery@<host> ready.`
- beat:   `beat: Starting...` and `Scheduler: Sending due task daily-report-reminder`

A one-line health snapshot of all three:

```bash
systemctl is-active coreops-backend coreops-worker coreops-beat
```

---

## 4. View logs with journalctl

```bash
# Follow live
journalctl -u coreops-worker -f
journalctl -u coreops-beat -f

# Recent history / since a time
journalctl -u coreops-worker -n 200 --no-pager
journalctl -u coreops-beat --since "10 min ago" --no-pager
```

End-to-end trace to look for across beat + worker (one firing):

```
beat   | Scheduler: Sending due task daily-report-reminder (coreops.reminders.send_daily_report_reminders)
worker | Task coreops.reminders.send_daily_report_reminders[...] received
worker | reminder.started job=daily_report_reminder
worker | reminder.collected pms_with_missing=<n>
worker | reminder.pm pm=<email> employees_checked=<n> missing_found=<n>     # only when there are missing reports
worker | reminder.email_sent pm=<email> sent=True missing=<n>              # only when an email is sent
worker | reminder.completed job=daily_report_reminder pms=<n> sent=<n> skipped=<n> failed=<n> missing=<n>
worker | Task ... succeeded in ...s: {...}
```

If there are no missing reports, the run ends at `reminder.completed ... pms=0`
with no email - that is the correct "nothing to send" outcome. SMTP credentials
are never written to the logs.

---

## 5. Switching schedule: development (every minute) <-> production (09:30 IST)

The schedule is driven entirely by environment variables in `.env` - nothing is
hardcoded. Beat reads them at startup, so a change requires a beat restart.

### To development (fire every minute) - for verification only

```bash
# In /opt/coreops/backend/.env
REMINDER_EVERY_MINUTE=true

sudo systemctl restart coreops-beat
journalctl -u coreops-beat -f      # confirm "Sending due task" every minute
```

### Back to production (09:30 Asia/Kolkata)

```bash
# In /opt/coreops/backend/.env
REMINDER_EVERY_MINUTE=false
REMINDER_HOUR=9
REMINDER_MINUTE=30

# Clear the persisted beat state so the new cron is picked up cleanly, then restart.
sudo rm -f /var/lib/coreops-beat/celerybeat-schedule*
sudo systemctl restart coreops-beat
```

Confirm the active schedule after restart:

```bash
cd /opt/coreops/backend
.venv/bin/python -c "from app.core.celery_app import celery_app as c; \
print(c.conf.beat_schedule['daily-report-reminder']['schedule'])"
# production -> <crontab: 30 9 * * * (m/h/dM/MY/d)>
# development -> <crontab: * * * * * (m/h/dM/MY/d)>
```

Beat uses `timezone = Asia/Kolkata`, so `30 9` means 09:30 IST regardless of the
server clock's zone.

---

## 6. Stop / restart / disable

```bash
sudo systemctl restart coreops-worker coreops-beat
sudo systemctl stop    coreops-worker coreops-beat     # API keeps running
sudo systemctl disable coreops-worker coreops-beat     # stop starting at boot
```

## 7. Kill switch

To pause reminders without touching systemd, set `REMINDER_SCHEDULE_ENABLED=false`
(beat registers no schedule) or `EMAIL_ENABLED=false` (pipeline runs but sends
nothing), then `sudo systemctl restart coreops-beat` / `coreops-worker`.
