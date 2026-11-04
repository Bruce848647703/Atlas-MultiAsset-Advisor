import yaml

from invest_agent import config


def test_factor_dir_defaults_to_bundled_sample():
    cfg = config.load_config(force=True)
    assert cfg["factors"]["data_dir"].endswith("examples/factor_library_sample")


def test_factor_dir_can_be_overridden_by_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ATLAS_FACTOR_DIR", str(tmp_path / "factors"))
    cfg = config.load_config(force=True)
    assert cfg["factors"]["data_dir"] == str(tmp_path / "factors")
    # Don't leak the override into the cached config used by other tests.
    monkeypatch.delenv("ATLAS_FACTOR_DIR")
    config.load_config(force=True)


def test_ci_workflow_is_valid_yaml():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    workflow = root / ".github" / "workflows" / "ci.yml"
    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    assert "test" in data["jobs"]
    assert "compliance" in data["jobs"]