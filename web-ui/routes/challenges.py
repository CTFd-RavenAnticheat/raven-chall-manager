"""
Challenge management routes.
"""

from flask import Blueprint, jsonify, request
import requests
import json
import os

challenges_bp = Blueprint("challenges", __name__, url_prefix="/api/chall-manager")

CHALL_MANAGER_URL = os.environ.get("CHALL_MANAGER_URL", "http://localhost:8080")


@challenges_bp.route("/challenges", methods=["GET"])
def list_challenges():
    """List all challenges from chall-manager."""
    try:
        response = requests.get(f"{CHALL_MANAGER_URL}/api/v1/challenge", timeout=30)

        if response.status_code == 200:
            challenges = []
            for line in response.iter_lines():
                if line:
                    challenges.append(json.loads(line))
            return jsonify({"challenges": challenges})
        else:
            return jsonify(
                {"error": f"Failed to list challenges: {response.status_code}"}
            ), response.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@challenges_bp.route("/challenges", methods=["POST"])
def create_challenge():
    """Create a challenge in chall-manager."""
    try:
        data = request.get_json()

        payload = {
            "id": data["id"],
            "scenario": data["scenario"],
        }

        if "timeout" in data and data["timeout"]:
            payload["timeout"] = data["timeout"]
        if "until" in data and data["until"]:
            payload["until"] = data["until"]
        if "additional" in data and data["additional"]:
            payload["additional"] = data["additional"]
        if "min" in data:
            payload["min"] = int(data["min"])
        if "max" in data:
            payload["max"] = int(data["max"])
        if "image_pull_secrets" in data and data["image_pull_secrets"]:
            payload["image_pull_secrets"] = data["image_pull_secrets"]

        response = requests.post(
            f"{CHALL_MANAGER_URL}/api/v1/challenge", json=payload, timeout=60
        )

        if response.status_code in [200, 201]:
            return jsonify({"success": True, "challenge": response.json()})
        else:
            return jsonify(
                {"error": f"Failed to create challenge: {response.text}"}
            ), response.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@challenges_bp.route("/challenges/<challenge_id>", methods=["GET"])
def get_challenge(challenge_id):
    """Get a specific challenge."""
    try:
        response = requests.get(
            f"{CHALL_MANAGER_URL}/api/v1/challenge/{challenge_id}", timeout=30
        )

        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify(
                {"error": f"Challenge not found: {response.status_code}"}
            ), response.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@challenges_bp.route("/challenges/<challenge_id>", methods=["DELETE"])
def delete_challenge(challenge_id):
    """Delete a challenge."""
    try:
        response = requests.delete(
            f"{CHALL_MANAGER_URL}/api/v1/challenge/{challenge_id}", timeout=60
        )

        if response.status_code in [200, 204]:
            return jsonify(
                {"success": True, "message": f"Challenge {challenge_id} deleted"}
            )
        else:
            return jsonify(
                {"error": f"Failed to delete challenge: {response.text}"}
            ), response.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500
