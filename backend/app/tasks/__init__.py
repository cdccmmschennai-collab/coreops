"""Celery task layer.

Tasks here are intentionally tiny: they only trigger application services. No
SQL, no SMTP, and no HTML generation live in this package.
"""
