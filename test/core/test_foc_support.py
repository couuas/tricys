import re
from pathlib import Path

import pytest

from tricys.core.foc import build_foc_preview, prepare_foc_simulation_package


def _extract_generated_foc_block(prepared_text, block_name):
    match = re.search(
        rf"block {block_name}\b.*?end {block_name};",
        prepared_text,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group(0)


def test_build_foc_preview_parses_content_into_rows():
    preview = build_foc_preview("PULSE 1000 10 5 2\n")

    assert preview["amplitudes"] == [1000.0, 0.0, 1000.0, 0.0]
    assert preview["durations"] == [10.0, 5.0, 10.0, 5.0]
    assert preview["schedule_duration"] == 30.0
    assert preview["step_count"] == 4
    assert preview["rows"] == [
        (0.0, 1000.0),
        (10.0, 1000.0),
        (10.0, 0.0),
        (15.0, 0.0),
        (15.0, 1000.0),
        (25.0, 1000.0),
        (25.0, 0.0),
        (30.0, 0.0),
    ]


def test_build_foc_preview_applies_time_conversion_rule():
    preview = build_foc_preview("TIME_CONVERSION 3600\nPULSE 1000 0.5 0.25 1\n")

    assert preview["amplitudes"] == [1000.0, 0.0]
    assert preview["durations"] == [1800.0, 900.0]
    assert preview["schedule_duration"] == 2700.0
    assert preview["rows"] == [
        (0.0, 1000.0),
        (1800.0, 1000.0),
        (1800.0, 0.0),
        (2700.0, 0.0),
    ]


def test_build_foc_preview_declares_time_unit_without_implicit_conversion():
    preview = build_foc_preview("TIME_UNIT hour\nPULSE 1000 0.5 0.25 1\n")

    assert preview["amplitudes"] == [1000.0, 0.0]
    assert preview["durations"] == [0.5, 0.25]
    assert preview["schedule_duration"] == 0.75
    assert preview["rows"] == [
        (0.0, 1000.0),
        (0.5, 1000.0),
        (0.5, 0.0),
        (0.75, 0.0),
    ]


def test_build_foc_preview_supports_named_time_conversion_alias():
    preview = build_foc_preview(
        "TIME_CONVERSION second_to_hour\nPULSE 1000 7200 3600 1\n"
    )

    assert preview["amplitudes"] == [1000.0, 0.0]
    assert preview["durations"] == [2.0, 1.0]
    assert preview["schedule_duration"] == 3.0
    assert preview["rows"] == [
        (0.0, 1000.0),
        (2.0, 1000.0),
        (2.0, 0.0),
        (3.0, 0.0),
    ]


def test_prepare_foc_simulation_package_patches_single_file_model(tmp_path):
    model_path = tmp_path / "Example.mo"
    model_path.write_text(
        """
package Example
model Cycle
  Modelica.Blocks.Sources.Pulse pulseSource(amplitude = 1, period = 10, width = 90) annotation(
    Placement(transformation(origin = {-90, 10}, extent = {{-10, -10}, {10, 10}})));
equation
  connect(pulseSource.y, plasma.pulseInput);
end Cycle;
end Example;
""".strip(),
        encoding="utf-8",
    )
    foc_path = tmp_path / "scenario.foc"
    foc_path.write_text("PULSE 1000 10 5 2\n", encoding="utf-8")

    result = prepare_foc_simulation_package(
        model_path,
        "Example.Cycle",
        foc_path,
        tmp_path / "prepared",
        foc_component="pulseSource",
    )

    prepared_model = Path(result["package_path"])
    prepared_text = prepared_model.read_text(encoding="utf-8")
    table_path = Path(result["table_path"])

    assert prepared_model.exists()
    assert table_path.exists()
    assert "block FOC_TablePulse" in prepared_text
    assert "FOC_TablePulse pulseSource(fileName=" in prepared_text
    assert table_path.as_posix() in prepared_text
    generated_block = _extract_generated_foc_block(prepared_text, "FOC_TablePulse")
    assert "RealOutput y;" in generated_block
    assert result["schedule_duration"] == 30.0
    assert result["step_count"] == 4


def test_prepare_foc_simulation_package_patches_single_file_model_array_strategy(
    tmp_path,
):
    model_path = tmp_path / "Example.mo"
    model_path.write_text(
        """
package Example
model Cycle
  Modelica.Blocks.Sources.Pulse pulseSource(amplitude = 1, period = 10, width = 90) annotation(
    Placement(transformation(origin = {-90, 10}, extent = {{-10, -10}, {10, 10}})));
equation
  connect(pulseSource.y, plasma.pulseInput);
end Cycle;
end Example;
""".strip(),
        encoding="utf-8",
    )
    foc_path = tmp_path / "scenario.foc"
    foc_path.write_text("PULSE 1000 10 5 2\n", encoding="utf-8")

    result = prepare_foc_simulation_package(
        model_path,
        "Example.Cycle",
        foc_path,
        tmp_path / "prepared",
        strategy="array",
        foc_component="pulseSource",
    )

    prepared_model = Path(result["package_path"])
    prepared_text = prepared_model.read_text(encoding="utf-8")

    assert prepared_model.exists()
    assert result["table_path"] is None
    assert "block FOC_ArrayPulse" in prepared_text
    assert (
        "FOC_ArrayPulse pulseSource(amplitudes={1000.0, 0.0, 1000.0, 0.0}, durations={10.0, 5.0, 10.0, 5.0})"
        in prepared_text
    )
    assert result["schedule_duration"] == 30.0
    assert result["step_count"] == 4


def test_prepare_foc_simulation_package_patches_named_custom_component(tmp_path):
    model_path = tmp_path / "Example.mo"
    model_path.write_text(
        """
package Example
model Plasma
    Modelica.Blocks.Interfaces.RealInput pulse annotation(
        Placement(transformation(origin = {-90, 10}, extent = {{-10, -10}, {10, 10}})));
end Plasma;

block Pulse
    Modelica.Blocks.Interfaces.RealOutput y1;
    Modelica.Blocks.Interfaces.RealOutput y2;
end Pulse;

model Cycle
    Pulse pulse annotation(
        Placement(transformation(origin = {-90, 10}, extent = {{-10, -10}, {10, 10}})));
equation
    connect(pulse.y1, plasma.pulseInput);
end Cycle;
end Example;
""".strip(),
        encoding="utf-8",
    )
    foc_path = tmp_path / "scenario.foc"
    foc_path.write_text("PULSE 1000 10 5 2\n", encoding="utf-8")

    result = prepare_foc_simulation_package(
        model_path,
        "Example.Cycle",
        foc_path,
        tmp_path / "prepared",
        foc_component="pulse",
    )

    prepared_text = Path(result["package_path"]).read_text(encoding="utf-8")

    assert 'FOC_TablePulse pulse(fileName="' in prepared_text
    assert "connect(pulse.y1, plasma.pulseInput);" in prepared_text
    assert "Modelica.Blocks.Interfaces.RealInput pulse annotation(" in prepared_text
    generated_block = _extract_generated_foc_block(prepared_text, "FOC_TablePulse")
    assert "RealOutput y1;" in generated_block
    assert "RealOutput y2;" not in generated_block
    assert "RealOutput y;" not in generated_block
    assert result["foc_component"] == "pulse"


def test_prepare_foc_simulation_package_generates_multiple_outputs_from_downstream_usage(
    tmp_path,
):
    model_path = tmp_path / "Example.mo"
    model_path.write_text(
        """
package Example
block Pulse
    Modelica.Blocks.Interfaces.RealOutput y1;
    Modelica.Blocks.Interfaces.RealOutput y2;
end Pulse;

model Cycle
    Pulse pulse annotation(
        Placement(transformation(origin = {-90, 10}, extent = {{-10, -10}, {10, 10}})));
equation
    connect(pulse.y1, plasma.pulseInput);
    connect(pulse.y2, blanket.pulseInput);
end Cycle;
end Example;
""".strip(),
        encoding="utf-8",
    )
    foc_path = tmp_path / "scenario.foc"
    foc_path.write_text("PULSE 1000 10 5 2\n", encoding="utf-8")

    result = prepare_foc_simulation_package(
        model_path,
        "Example.Cycle",
        foc_path,
        tmp_path / "prepared",
        foc_component="pulse",
    )

    prepared_text = Path(result["package_path"]).read_text(encoding="utf-8")
    generated_block = _extract_generated_foc_block(prepared_text, "FOC_TablePulse")

    assert "RealOutput y1;" in generated_block
    assert "RealOutput y2;" in generated_block
    assert "RealOutput y;" not in generated_block


def test_prepare_foc_simulation_package_accepts_component_path_selector(tmp_path):
    model_path = tmp_path / "Example.mo"
    model_path.write_text(
        """
package Example
model OtherModel
    Pulse pulse annotation(
        Placement(transformation(origin = {-50, 10}, extent = {{-10, -10}, {10, 10}})));
end OtherModel;

block Pulse
    Modelica.Blocks.Interfaces.RealOutput y1;
    Modelica.Blocks.Interfaces.RealOutput y2;
end Pulse;

model Cycle
    Pulse pulse annotation(
        Placement(transformation(origin = {-90, 10}, extent = {{-10, -10}, {10, 10}})));
equation
    connect(pulse.y1, plasma.pulseInput);
end Cycle;
end Example;
""".strip(),
        encoding="utf-8",
    )
    foc_path = tmp_path / "scenario.foc"
    foc_path.write_text("PULSE 1000 10 5 2\n", encoding="utf-8")

    result = prepare_foc_simulation_package(
        model_path,
        "Example.Cycle",
        foc_path,
        tmp_path / "prepared",
        foc_component="Example.Cycle.pulse",
    )

    prepared_text = Path(result["package_path"]).read_text(encoding="utf-8")

    assert prepared_text.count("FOC_TablePulse pulse(fileName=") == 1
    assert "model OtherModel" in prepared_text
    assert prepared_text.count("Pulse pulse annotation(") == 1
    assert result["foc_component"] == "Example.Cycle.pulse"


def test_prepare_foc_simulation_package_accepts_component_type_selector(tmp_path):
    model_path = tmp_path / "Example.mo"
    model_path.write_text(
        """
package Example
block Pulse
    Modelica.Blocks.Interfaces.RealOutput y1;
    Modelica.Blocks.Interfaces.RealOutput y2;
end Pulse;

block SupportSignal
    Modelica.Blocks.Interfaces.RealOutput y annotation(
        Placement(transformation(origin = {50, 10}, extent = {{-10, -10}, {10, 10}})));
end SupportSignal;

model Cycle
    Pulse pulse annotation(
        Placement(transformation(origin = {-90, 10}, extent = {{-10, -10}, {10, 10}})));
    SupportSignal helper annotation(
        Placement(transformation(origin = {20, 10}, extent = {{-10, -10}, {10, 10}})));
equation
    connect(pulse.y1, plasma.pulseInput);
end Cycle;
end Example;
""".strip(),
        encoding="utf-8",
    )
    foc_path = tmp_path / "scenario.foc"
    foc_path.write_text("PULSE 1000 10 5 2\n", encoding="utf-8")

    result = prepare_foc_simulation_package(
        model_path,
        "Example.Cycle",
        foc_path,
        tmp_path / "prepared",
        foc_component="type:Pulse",
    )

    prepared_text = Path(result["package_path"]).read_text(encoding="utf-8")

    assert prepared_text.count("FOC_TablePulse pulse(fileName=") == 1
    assert "SupportSignal helper annotation(" in prepared_text
    assert result["foc_component"] == "type:Pulse"


@pytest.mark.parametrize(
    ("strategy", "block_name", "expected_instance"),
    [
        (
            "table",
            "FOC_TablePulse",
            'FOC_TablePulse pulseSource(fileName="',
        ),
        (
            "array",
            "FOC_ArrayPulse",
            "FOC_ArrayPulse pulseSource(amplitudes={1000.0, 0.0, 1000.0, 0.0}, durations={10.0, 5.0, 10.0, 5.0})",
        ),
    ],
)
def test_prepare_foc_simulation_package_patches_multi_file_package(
    tmp_path, strategy, block_name, expected_instance
):
    package_dir = tmp_path / "Example"
    package_dir.mkdir()
    (package_dir / "package.mo").write_text(
        """
within;
package Example
end Example;
""".strip(),
        encoding="utf-8",
    )
    (package_dir / "package.order").write_text("Cycle\n", encoding="utf-8")
    (package_dir / "Cycle.mo").write_text(
        """
within Example;
model Cycle
  Modelica.Blocks.Sources.Pulse pulseSource(amplitude = 1, period = 10, width = 90) annotation(
    Placement(transformation(origin = {-90, 10}, extent = {{-10, -10}, {10, 10}})));
equation
  connect(pulseSource.y, plasma.pulseInput);
end Cycle;
""".strip(),
        encoding="utf-8",
    )
    foc_path = tmp_path / "scenario.foc"
    foc_path.write_text("PULSE 1000 10 5 2\n", encoding="utf-8")

    result = prepare_foc_simulation_package(
        package_dir / "package.mo",
        "Example.Cycle",
        foc_path,
        tmp_path / "prepared",
        strategy=strategy,
        foc_component="pulseSource",
    )

    prepared_package = Path(result["package_path"])
    prepared_dir = prepared_package.parent
    prepared_cycle = prepared_dir / "Cycle.mo"
    helper_file = prepared_dir / f"{block_name}.mo"
    package_order = (
        (prepared_dir / "package.order").read_text(encoding="utf-8").splitlines()
    )
    cycle_text = prepared_cycle.read_text(encoding="utf-8")
    helper_text = helper_file.read_text(encoding="utf-8")

    assert prepared_package.name == "package.mo"
    assert prepared_cycle.exists()
    assert helper_file.exists()
    assert f"within Example;\nblock {block_name}" in helper_text
    assert block_name in package_order
    assert package_order.index(block_name) < package_order.index("Cycle")
    assert expected_instance in cycle_text
    assert f"block {block_name}" not in cycle_text


def test_prepare_foc_simulation_package_requires_foc_component(tmp_path):
    model_path = tmp_path / "Example.mo"
    model_path.write_text(
        """
package Example
model Cycle
    Modelica.Blocks.Sources.Pulse pulseSource(amplitude = 1, period = 10, width = 90) annotation(
        Placement(transformation(origin = {-90, 10}, extent = {{-10, -10}, {10, 10}})));
equation
    connect(pulseSource.y, plasma.pulseInput);
end Cycle;
end Example;
""".strip(),
        encoding="utf-8",
    )
    foc_path = tmp_path / "scenario.foc"
    foc_path.write_text("PULSE 1000 10 5 2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="foc_component is required"):
        prepare_foc_simulation_package(
            model_path,
            "Example.Cycle",
            foc_path,
            tmp_path / "prepared",
        )
