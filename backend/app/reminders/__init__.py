"""Reminder services.

Each reminder is a small service that turns business rules into structured data.
Reminders never talk to SMTP or render transport-specific payloads directly — the
dispatcher wires a reminder's data through a template and the EmailService.
"""
