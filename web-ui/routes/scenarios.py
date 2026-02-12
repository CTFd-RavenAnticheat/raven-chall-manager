"""
Scenario builder routes.
"""

from flask import Blueprint, jsonify, request, send_file
import requests
import subprocess
import tempfile
import os

from routes.utils import (
    build_monopod_scenario,
    build_multipod_scenario,
    build_kompose_scenario,
    create_scenario_zip,
)

scenarios_bp = Blueprint("scenarios", __name__, url_prefix="/api")

CHALL_MANAGER_URL = os.environ.get("CHALL_MANAGER_URL", "http://localhost:8080")


@scenarios_bp.route("/create-scenario", methods=["POST"])
def create_scenario():
    """Create scenario and return downloadable ZIP."""
    try:
        data = request.get_json()
        scenario_type = data.get("scenario_type")

        if scenario_type == "monopod":
            scenario = build_monopod_scenario(data)
        elif scenario_type == "multipod":
            scenario = build_multipod_scenario(data)
        elif scenario_type == "kompose":
            scenario = build_kompose_scenario(data)
        else:
            return jsonify({"error": "Invalid scenario type"}), 400

        scenario_name = data.get("identity", "scenario")
        memory_file = create_scenario_zip(scenario, scenario_name)

        return send_file(
            memory_file,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"{scenario_name}-scenario.zip",
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@scenarios_bp.route("/build-and-push-scenario", methods=["POST"])
def build_and_push_scenario():
    """
    Build scenario, create OCI artifact, and push to registry using chall-manager API.
    Uses the globally configured OCI credentials (OCI_USERNAME, OCI_PASSWORD).
    Returns the scenario reference that can be used with chall-manager.
    """
    try:
        data = request.get_json()
        scenario_type = data.get("scenario_type")
        registry_url = data.get("registry_url", "").strip()
        # Get scenario info
        tag = data.get("tag", "latest").strip()
        if not registry_url:
            return jsonify({"error": "Registry URL is required"}), 400
        # Build scenario
        if scenario_type == "monopod":
            scenario = build_monopod_scenario(data)
        elif scenario_type == "multipod":
            scenario = build_multipod_scenario(data)
        elif scenario_type == "kompose":
            scenario = build_kompose_scenario(data)
        else:
            return jsonify({"error": "Invalid scenario type"}), 400

        scenario_name = data.get("identity", "scenario")
        scenario_ref = f"{registry_url}/{scenario_name}:{tag}"
        
        # Create ZIP file
        import io
        import base64

        memory_file = create_scenario_zip(scenario, scenario_name)
        zip_bytes = memory_file.getvalue()

        # Call chall-manager API to push scenario
        # Chall-manager uses its globally configured OCI credentials
        payload = {
            "scenario_zip": base64.b64encode(zip_bytes).decode("utf-8"),
            "reference": scenario_ref,
        }

        response = requests.post(
            f"{CHALL_MANAGER_URL}/api/v1/scenarios/push",
            json=payload,
            timeout=120,  # Pushing can take a while
        )

        if response.status_code in [200, 201]:
            result = response.json()
            return jsonify(
                {
                    "success": True,
                    "scenario_ref": result.get("reference", scenario_ref),
                    "message": result.get(
                        "message", f"Successfully pushed to {scenario_ref}"
                    ),
                    "digest": result.get("digest"),
                }
            )
        else:
            error_msg = response.text
            try:
                error_data = response.json()
                if "message" in error_data:
                    error_msg = error_data["message"]
            except:
                pass
            return jsonify(
                {"error": f"Failed to push scenario: {error_msg}"}
            ), response.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@scenarios_bp.route("/create-challenge-from-scenario", methods=["POST"])
def create_challenge_from_scenario():
    """
    Create a challenge directly from a scenario reference.
    Assumes the scenario has already been pushed to the registry.
    """
    try:
        data = request.get_json()

        identity = data.get("identity")
        scenario_ref = data.get("scenario_ref")
        image_pull_secrets = data.get("image_pull_secrets", "")

        if not identity or not scenario_ref:
            return jsonify({"error": "Identity and scenario_ref are required"}), 400

        # Build payload for chall-manager
        payload = {
            "id": identity,
            "scenario": scenario_ref,
        }

        if image_pull_secrets:
            payload["image_pull_secrets"] = image_pull_secrets

        # Call chall-manager to create challenge
        response = requests.post(
            f"{CHALL_MANAGER_URL}/api/v1/challenge", json=payload, timeout=60
        )

        if response.status_code in [200, 201]:
            return jsonify(
                {
                    "success": True,
                    "challenge": response.json(),
                    "cli_command": f"chall-manager-cli challenge create --id {identity} --scenario {scenario_ref}",
                }
            )
        else:
            return jsonify(
                {"error": f"Failed to create challenge: {response.text}"}
            ), response.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500
