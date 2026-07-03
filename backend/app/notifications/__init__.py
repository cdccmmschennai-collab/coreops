"""Notification infrastructure.

Reusable, transport-only building blocks for outbound notifications. This layer
knows *how* to deliver a message (SMTP today), never *why* a message is sent —
business rules live in the reminder services under ``app.reminders``.
"""
