"""
Health check routes.
"""

from flask import Blueprint, jsonify
from datetime import datetime
import requests
import os

health_bp = Blueprint("health", __name__)

CHALL_MANAGER_URL = os.environ.get("CHALL_MANAGER_URL", "http://localhost:8080")


@health_bp.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {},
    }

    # Check chall-manager
    try:
        response = requests.get(f"{CHALL_MANAGER_URL}/healthcheck", timeout=5)
        if response.status_code == 200:
            status["services"]["chall_manager"] = "connected"
        else:
            status["services"]["chall_manager"] = f"error: {response.status_code}"
    except:
        status["services"]["chall_manager"] = "disconnected"

    return jsonify(status)
