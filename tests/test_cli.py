import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(*args, stdin=subprocess.DEVNULL):
    return subprocess.run(
        [sys.executable, "-m", "invest_agent.cli", *args],
        cwd=ROOT, capture_output=True, text=True, stdin=stdin, check=False,
    )


def test_cli_help_does_not_start_the_questionnaire():
    result = _run("--help")
    assert result.returncode == 0
    assert "usage:" in result.stdout
    assert "适当性问卷" not in result.stdout


def test_cli_non_interactive_plan_runs_offline():
    result = _run(
        "--offline", "--answers", "2,2,2,2,2,2,2,2,2",
        "--capital", "200000", "--no-report",
    )
    assert result.returncode == 0
    assert "=== 结果 ===" in result.stdout
    assert "适当性:" in result.stdout


def test_cli_requires_inputs_when_stdin_is_not_a_tty():
    result = _run("--offline")
    assert result.returncode == 2
    assert "no answers" in result.stderr
