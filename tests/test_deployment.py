import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_entrypoint_fails_closed_without_token():
    env = {k: v for k, v in os.environ.items()
           if k not in ("ATLAS_ACCESS_TOKEN", "ATLAS_ALLOW_INSECURE")}
    proc = subprocess.run(
        ["sh", str(ROOT / "deploy" / "docker-entrypoint.sh")],
        capture_output=True, text=True, env=env, timeout=15,
    )
    assert proc.returncode == 1
    assert "ATLAS_ACCESS_TOKEN is required" in proc.stderr


def test_docker_assets_exist_and_are_non_root():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "USER atlas" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    # compose must not publish the dashboard on all host interfaces by default
    port = re.search(r"ports:\s*\n\s*-\s*\"([^\"]+)\"", compose)
    assert port and port.group(1) == "127.0.0.1:8501:8501"
    assert "ATLAS_ACCESS_TOKEN" in compose