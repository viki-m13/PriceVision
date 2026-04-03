"""Vercel serverless entry point for LeakEngine."""

import sys
import os

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set data directory to /tmp for Vercel's ephemeral filesystem
os.environ.setdefault("LEAKENGINE_DATA_DIR", "/tmp/leakengine/data")
os.environ.setdefault("LEAKENGINE_REPORTS_DIR", "/tmp/leakengine/reports")

from app import app

# Vercel expects the Flask app as `app`
