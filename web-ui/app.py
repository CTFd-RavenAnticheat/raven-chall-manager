"""
Chall-Manager Web UI
Communicates with chall-manager REST API only (no direct Kubernetes access)
"""

from flask import Flask, render_template
from flask_cors import CORS
import os

# Import route blueprints
from routes import (
    challenges_bp,
    instances_bp,
    secrets_bp,
    scenarios_bp,
    health_bp,
)

app = Flask(__name__)
CORS(app)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# Register blueprints
app.register_blueprint(challenges_bp)
app.register_blueprint(instances_bp)
app.register_blueprint(secrets_bp)
app.register_blueprint(scenarios_bp)
app.register_blueprint(health_bp)


@app.route("/")
def index():
    """Main dashboard page."""
    return render_template("dashboard.html")


@app.route("/scenario-builder")
def scenario_builder():
    """Scenario builder page."""
    return render_template("index.html")


@app.route("/secrets")
def secrets_management():
    """Secret management page."""
    return render_template("secrets.html")


if __name__ == "__main__":
    CHALL_MANAGER_URL = os.environ.get("CHALL_MANAGER_URL", "http://localhost:8080")
    print("🚩 Chall-Manager Web UI")
    print("======================")
    print(f"Chall-Manager URL: {CHALL_MANAGER_URL}")
    print("")
    print("Starting server on http://localhost:5000")
    print("")

    app.run(debug=True, host="0.0.0.0", port=5000)
