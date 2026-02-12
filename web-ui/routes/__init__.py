"""
Routes package for web UI.
"""

from routes.challenges import challenges_bp
from routes.instances import instances_bp
from routes.secrets import secrets_bp
from routes.scenarios import scenarios_bp
from routes.health import health_bp

__all__ = [
    "challenges_bp",
    "instances_bp",
    "secrets_bp",
    "scenarios_bp",
    "health_bp",
]
