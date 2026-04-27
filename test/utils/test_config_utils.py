import os
import shutil
from pathlib import Path

import pytest

from tricys.utils.config_utils import (
    analysis_validate_analysis_cases_config,
    basic_validate_config,
    convert_relative_paths_to_absolute,
)

TEST_DIR = "temp_config_utils_test"


@pytest.fixture(autouse=True)
def setup_and_teardown_test_dir():
    """Set up and tear down the test directory."""
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR)
    yield
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)


def test_convert_relative_paths_to_absolute():
    """Test convert_relative_paths_to_absolute."""
    base_dir = os.path.abspath(TEST_DIR)
    config = {
        "paths": {"package_path": "model.mo"},
        "a_list": [{"log_dir": "logs/"}],
    }

    abs_config = convert_relative_paths_to_absolute(config, base_dir)

    assert os.path.normpath(abs_config["paths"]["package_path"]) == os.path.normpath(
        os.path.join(base_dir, "model.mo")
    )
    assert os.path.normpath(abs_config["a_list"][0]["log_dir"]) == os.path.normpath(
        os.path.join(base_dir, "logs/")
    )


def test_basic_validate_config_success():
    """Test basic_validate_config with a valid config."""
    package_path = Path(TEST_DIR) / "model.mo"
    package_path.touch()

    config = {
        "paths": {"package_path": str(package_path)},
        "simulation": {
            "model_name": "MyModel",
            "stop_time": 10,
            "step_size": 0.1,
            "variableFilter": "time|sub.var",
        },
    }

    try:
        basic_validate_config(config)
    except SystemExit as e:
        pytest.fail(f"Validation failed unexpectedly: {e}")


def test_basic_validate_config_missing_key():
    """Test basic_validate_config with a missing key."""
    config = {"paths": {}}
    with pytest.raises(SystemExit):
        basic_validate_config(config)


def test_basic_validate_config_rejects_missing_foc_file():
    package_path = Path(TEST_DIR) / "model.mo"
    package_path.touch()

    config = {
        "paths": {"package_path": str(package_path)},
        "simulation": {
            "model_name": "MyModel",
            "stop_time": 10,
            "step_size": 0.1,
            "variableFilter": "time|sub.var",
        },
        "foc": {
            "foc_path": str(Path(TEST_DIR) / "missing.foc"),
            "foc_component": "pulseSource",
        },
    }

    with pytest.raises(SystemExit):
        basic_validate_config(config)


def test_basic_validate_config_rejects_invalid_foc_component():
    package_path = Path(TEST_DIR) / "model.mo"
    foc_path = Path(TEST_DIR) / "scenario.foc"
    package_path.touch()
    foc_path.write_text("PULSE 1000 10 5 1\n", encoding="utf-8")

    config = {
        "paths": {"package_path": str(package_path)},
        "simulation": {
            "model_name": "MyModel",
            "stop_time": 10,
            "step_size": 0.1,
            "variableFilter": "time|sub.var",
        },
        "foc": {
            "foc_path": str(foc_path),
            "foc_component": "   ",
        },
    }

    with pytest.raises(SystemExit):
        basic_validate_config(config)


def test_basic_validate_config_requires_foc_component_when_foc_is_enabled():
    package_path = Path(TEST_DIR) / "model.mo"
    foc_path = Path(TEST_DIR) / "scenario.foc"
    package_path.touch()
    foc_path.write_text("PULSE 1000 10 5 1\n", encoding="utf-8")

    config = {
        "paths": {"package_path": str(package_path)},
        "simulation": {
            "model_name": "MyModel",
            "stop_time": 10,
            "step_size": 0.1,
            "variableFilter": "time|sub.var",
        },
        "foc": {
            "foc_path": str(foc_path),
        },
    }

    with pytest.raises(SystemExit):
        basic_validate_config(config)


def test_basic_validate_config_rejects_unreplaceable_foc_component():
    package_path = Path(TEST_DIR) / "model.mo"
    foc_path = Path(TEST_DIR) / "scenario.foc"
    package_path.write_text(
        """
package Example
model Cycle
  SupportSignal helper annotation(
    Placement(transformation(origin = {-90, 10}, extent = {{-10, -10}, {10, 10}})));
end Cycle;

block SupportSignal
  Modelica.Blocks.Interfaces.RealOutput y;
end SupportSignal;
end Example;
""".strip(),
        encoding="utf-8",
    )
    foc_path.write_text("PULSE 1000 10 5 1\n", encoding="utf-8")

    config = {
        "paths": {"package_path": str(package_path)},
        "simulation": {
            "model_name": "Example.Cycle",
            "stop_time": 10,
            "step_size": 0.1,
            "variableFilter": "time|sub.var",
        },
        "foc": {
            "foc_path": str(foc_path),
            "foc_component": "helper",
        },
    }

    with pytest.raises(SystemExit):
        basic_validate_config(config)


def test_analysis_validate_analysis_cases_config_success():
    """Test analysis_validate_analysis_cases_config with a valid config."""
    config = {
        "sensitivity_analysis": {
            "analysis_cases": [
                {
                    "name": "case1",
                    "independent_variable": "p1",
                    "independent_variable_sampling": [1, 2, 3],
                }
            ]
        }
    }
    assert analysis_validate_analysis_cases_config(config)


def test_analysis_validate_analysis_cases_config_fail():
    """Test analysis_validate_analysis_cases_config with an invalid config."""
    config = {"sensitivity_analysis": {}}
    assert not analysis_validate_analysis_cases_config(config)

    config = {"sensitivity_analysis": {"analysis_cases": [{}]}}
    assert not analysis_validate_analysis_cases_config(config)
