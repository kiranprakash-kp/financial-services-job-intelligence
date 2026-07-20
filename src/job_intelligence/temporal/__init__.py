"""Temporal orchestration: workflows, activities, worker, schedule, and client.

Workflows contain only deterministic orchestration logic. All network calls,
database operations, Playwright operations, and other side effects live in
Activities (activities.py), never in workflow code.
"""

TASK_QUEUE = "job-intelligence"
