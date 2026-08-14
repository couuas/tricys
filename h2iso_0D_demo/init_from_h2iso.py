"""Generate Modelica initialization scripts from h2iso flowsheet solution.

This script solves a multi-column hydrogen isotope separation flowsheet
using h2iso and outputs an override.txt file that sets initial
values for the corresponding tricys Modelica models.

Usage:
    python init_from_h2iso.py --config <flowsheet.json> [--output <dir>] [--prefix <prefix>]

Requirements:
    pip install "h2iso[solver]>=0.2.0"
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib import import_module
from pathlib import Path


def _load_h2iso_dependencies():
    """Import h2iso solver dependencies after CLI parsing.

    Keeping these imports lazy allows ``--help`` and argument validation to
    work even when the optional distillation dependency is not installed.
    """
    try:
        schema_module = import_module("h2iso.flowsheet.schema")
        solver_module = import_module("h2iso.flowsheet.solver")
    except ImportError as exc:
        missing_name = getattr(exc, "name", "") or ""
        if missing_name.startswith("h2iso"):
            reason = "h2iso is not installed"
        elif missing_name == "casadi":
            reason = "h2iso solver extra is not installed (missing casadi)"
        else:
            reason = f"h2iso dependency import failed: {exc}"
        print(
            f"Error: {reason}. Install with:\n"
            "  pip install \"h2iso[solver]>=0.2.0\"\n"
            "Or from source:\n"
            "  pip install -e /path/to/h2iso[solver]",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    return schema_module.load_flowsheet, solver_module.SequentialModularSolver


def _set_parameter_line(model_name: str, parameter: str, value: str, prefix: str = "") -> str:
    """Return an OpenModelica override.txt parameter line."""
    param_prefix = f"{prefix}.{model_name}" if prefix else model_name
    return f"{param_prefix}.{parameter}={value}"


ATOMIC_MOLAR_MASS_G_MOL = (3.016049, 2.014102, 1.007825, 4.002603, 1.0)


def h2iso_to_tricys_mass_flows(
    molecular_flow_mol_h: float, comp_6: list[float]
) -> list[float]:
    """Convert an h2iso molecular stream into tricys atomic mass flows.

    h2iso uses [H2, HD, HT, D2, DT, T2] mole fractions and a molecular
    molar flow. tricys uses [T, D, H, He, Imp] component mass flows in g/h.
    The result is deliberately *not* normalized: it is a mass-conserving
    reference product vector for calibrating the 0-D column surrogate.
    """
    h2, hd, ht, d2, dt, t2 = comp_6
    molecular_rates = [molecular_flow_mol_h * x for x in comp_6]
    h2_r, hd_r, ht_r, d2_r, dt_r, t2_r = molecular_rates

    atomic_mol_h = [
        ht_r + dt_r + 2.0 * t2_r,
        hd_r + 2.0 * d2_r + dt_r,
        2.0 * h2_r + hd_r + ht_r,
        0.0,
        0.0,
    ]
    return [n * mw for n, mw in zip(atomic_mol_h, ATOMIC_MOLAR_MASS_G_MOL)]


def generate_column_mos(
    col_name: str,
    n_stages: int,
    top_composition: list[float],
    bottom_composition: list[float],
    top_temperature: float,
    bottom_temperature: float,
    distillate_flow: float,
    bottoms_flow: float,
    reflux_ratio: float,
    prefix: str = "",
) -> str:
    """Generate override.txt block for a single column.
    """
    top_mass_5 = h2iso_to_tricys_mass_flows(distillate_flow, top_composition)
    bot_mass_5 = h2iso_to_tricys_mass_flows(bottoms_flow, bottom_composition)

    lines = [
        _set_parameter_line(col_name, "N_stages", str(n_stages), prefix),
        _set_parameter_line(col_name, "R", f"{reflux_ratio:.4f}", prefix),
        _set_parameter_line(col_name, "T_top", f"{top_temperature:.4f}", prefix),
    ]

    for i in range(5):
        lines.append(
            _set_parameter_line(col_name, f"m_top_ref[{i + 1}]", f"{top_mass_5[i]:.8f}", prefix)
        )

    lines.extend([
        _set_parameter_line(col_name, "T_bottom", f"{bottom_temperature:.4f}", prefix),
    ])

    for i in range(5):
        lines.append(
            _set_parameter_line(col_name, f"m_bottom_ref[{i + 1}]", f"{bot_mass_5[i]:.8f}", prefix)
        )

    return "\n".join(lines)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate Modelica init scripts from h2iso flowsheet solution"
        ),
    )
    parser.add_argument(
        "--config", type=str, required=True,
        help="Path to flowsheet JSON config file",
    )
    parser.add_argument(
        "--output", type=str, default=".",
        help="Output directory for override.txt (default: current)",
    )
    parser.add_argument(
        "--prefix", type=str, default="",
        help="Prefix for model variables (e.g. o_iss)",
    )
    parser.add_argument(
        "--max-iter", type=int, default=50,
        help="Max tear stream iterations (default: 50)",
    )
    parser.add_argument(
        "--tol", type=float, default=1e-4,
        help="Convergence tolerance (default: 1e-4)",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Abort if flowsheet does not converge",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        raise SystemExit(1)

    load_flowsheet, sequential_modular_solver = _load_h2iso_dependencies()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load and solve flowsheet
    print(f"Loading flowsheet: {config_path}")
    config = load_flowsheet(config_path)
    print(f"  {len(config.columns)} columns, {len(config.feeds)} feeds, "
          f"{len(config.tear_streams)} tear streams")

    print("Solving flowsheet...")
    solver = sequential_modular_solver(
        config,
        method="wegstein",
        continuation_substeps=3,
    )
    result = solver.solve(max_iter=args.max_iter, tol=args.tol)

    if not result.converged:
        msg = (
            "flowsheet did not converge "
            f"(residual={result.tear_residual:.2e})"
        )
        if args.strict:
            print(f"Error: {msg}", file=sys.stderr)
            raise SystemExit(1)
        print(f"Warning: {msg}", file=sys.stderr)

    status = "CONVERGED" if result.converged else "NOT CONVERGED"
    print(f"  Status: {status}, iterations: {result.iterations}")

    # Generate override.txt blocks for each column
    override_blocks = []
    for col_cfg in config.columns:
        col_name = col_cfg.name
        dist_key = f"{col_name}_distillate"
        bot_key = f"{col_name}_bottoms"

        dist_stream = result.streams.get(dist_key)
        bot_stream = result.streams.get(bot_key)

        if dist_stream is None or bot_stream is None:
            print(
                f"  Warning: {col_name} has missing output streams, skipping"
            )
            continue

        block = generate_column_mos(
            col_name=col_name,
            n_stages=col_cfg.n_stages,
            top_composition=dist_stream.composition.tolist(),
            bottom_composition=bot_stream.composition.tolist(),
            top_temperature=float(dist_stream.temperature),
            bottom_temperature=float(bot_stream.temperature),
            distillate_flow=float(dist_stream.flow),
            bottoms_flow=float(bot_stream.flow),
            reflux_ratio=col_cfg.reflux_ratio,
            prefix=args.prefix,
        )
        override_blocks.append(block)

    # Write to override.txt
    if override_blocks:
        master_path = output_dir / "override.txt"
        master_path.write_text("\n".join(override_blocks) + "\n", encoding="utf-8")
        print(f"  Generated: {master_path}")

    # Export summary
    summary = {
        "source_config": str(config_path),
        "converged": result.converged,
        "iterations": result.iterations,
        "columns_initialized": [col.name for col in config.columns],
    }
    summary_path = output_dir / "init_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nDone. override.txt generated in {output_dir}/")


if __name__ == "__main__":
    main()
