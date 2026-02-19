"""Shared state for API."""
import os

PROJECTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)

# In-memory project store (keyed by project ID)
projects: dict = {}
