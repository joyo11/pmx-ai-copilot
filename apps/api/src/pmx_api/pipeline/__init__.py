"""Ingestion + retrieval pipeline (M1: PDF only).

Kept isolated from the router layer so we can swap it for a Celery/RQ worker
in M2 without touching HTTP handlers. Everything here is async-safe or clearly
sync-and-blocking (PDF extraction).
"""
