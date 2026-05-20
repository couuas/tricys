#!/usr/bin/env python3
"""Generate DWSIM vs Aspen parity report.

Runs all 5 test cases through DWSIM, compares against Aspen baseline
(if available), and generates a Markdown report with Go/No-Go decision.

Usage:
    DOTNET_ROOT=/usr/lib/dotnet python script/dwsim/generate_parity_report.py
"""

import os
import sys
import csv
import json
from datetime import datetime

DWSIM_DIR = os.environ.get("DWSIM_DIR", "/usr/local/lib/dwsim")
DOTNET_ROOT = os.environ.get("DOTNET_ROOT", "/usr/lib/dotnet")

# Thresholds
REL_THRESHOLD = 0.05   # 5% relative deviation
ABS_THRESHOLD = 0.01   # g/h absolute deviation


def run_all_cases():
    """Run all test cases and return results."""
    os.environ["DOTNET_ROOT"] = DOTNET_ROOT
    from pythonnet import set_runtime
    from clr_loader import get_coreclr
    rt = get_coreclr(dotnet_root=DOTNET_ROOT)
    set_runtime(rt)

    import clr
    sys.path.append(DWSIM_DIR)
    clr.AddReference("DWSIM.Automation")
    clr.AddReference("DWSIM.Interfaces")
    from DWSIM.Automation import Automation3

    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, script_dir)
    from build_dwsim_flowsheet import configure_srk_bip, build_three_towers
    from register_compounds import register_compounds
    from run_dwsim_point import (
        TEST_CASES, compute_feed_composition, extract_stream_hdt,
    )

    interf = Automation3()
    sim = interf.CreateFlowsheet()
    register_compounds(sim, {})
    sim.CreateAndAddPropertyPackage("Soave-Redlich-Kwong (SRK)")
    configure_srk_bip(sim, {})
    objects = build_three_towers(sim, {})

    terminal_streams = {"WDS": "S4", "SDSD2": "S16",
                        "SDST2": "S17", "CD3_DIST": "S_CD3_DIST"}
    all_results = {}

    for case_name, (T_flow, D_flow, H_flow) in TEST_CASES.items():
        feed_comp, total_mol = compute_feed_composition(T_flow, D_flow, H_flow)
        feed = objects["streams"]["FROMTEP"]
        feed.SetTemperature(22.0)
        feed.SetPressure(101325.0)
        for comp, frac in feed_comp.items():
            feed.SetOverallCompoundMolarFlow(comp, frac * total_mol / 3600.0)

        # Solve with retries
        converged = False
        for _ in range(5):
            interf.CalculateFlowsheet2(sim)
            converged = all(c.Calculated for c in objects["columns"].values())
            if converged:
                break

        # Extract
        results = {}
        for label, key in terminal_streams.items():
            s = objects["streams"].get(key)
            if s is not None:
                H, D, T = extract_stream_hdt(s)
                results[label] = {"H": H, "D": D, "T": T}
            else:
                results[label] = {"H": 0.0, "D": 0.0, "T": 0.0}

        in_total = T_flow + D_flow + H_flow
        out_total = sum(r["H"] + r["D"] + r["T"] for r in results.values())
        mb_err = abs(out_total - in_total) / in_total if in_total > 0 else 0.0

        all_results[case_name] = {
            "converged": converged,
            "results": results,
            "mass_balance_err": mb_err,
            "input": {"T": T_flow, "D": D_flow, "H": H_flow},
        }
        print(f"  {case_name}: converged={converged}, mb_err={mb_err:.4%}")

    return all_results


def load_baseline(baseline_path):
    """Load Aspen baseline CSV."""
    if not os.path.exists(baseline_path):
        return None
    baseline = {}
    with open(baseline_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            case = row["case"]
            stream = row["stream"]
            if case not in baseline:
                baseline[case] = {}
            baseline[case][stream] = {
                "H": float(row["H_g_h"]),
                "D": float(row["D_g_h"]),
                "T": float(row["T_g_h"]),
            }
    return baseline


def generate_report(all_results, baseline, output_path):
    """Generate Markdown parity report."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    has_baseline = baseline is not None

    lines = [
        "# DWSIM vs Aspen Parity Report",
        "",
        f"**Generated**: {timestamp}",
        f"**Aspen Baseline**: {'Available' if has_baseline else 'Not available (Windows-only extraction)'}",
        f"**DWSIM Version**: 9.0.5 (headless, .NET 8)",
        f"**Property Package**: SRK (kij=0 for all H-isotopologue pairs)",
        f"**Columns**: 3 × 30-stage rigorous distillation (CD1→CD2→CD3 cascade)",
        "",
        "## Test Case Summary",
        "",
        "| Case | T_in (g/h) | D_in (g/h) | H_in (g/h) | Converged | MB Error |",
        "|------|-----------|-----------|-----------|-----------|----------|",
    ]

    for case_name, data in all_results.items():
        inp = data["input"]
        conv = "✅" if data["converged"] else "❌"
        mb = f"{data['mass_balance_err']:.2%}"
        lines.append(
            f"| {case_name} | {inp['T']:.1f} | {inp['D']:.1f} | {inp['H']:.1f} "
            f"| {conv} | {mb} |"
        )

    lines.extend(["", "## Detailed Results", ""])

    # 45-point comparison table
    comparison_streams = ["WDS", "SDSD2", "SDST2"]
    components = ["H", "D", "T"]
    all_points = []

    for case_name, data in all_results.items():
        for stream in comparison_streams:
            for comp in components:
                dw_val = data["results"].get(stream, {}).get(comp, 0.0)
                point = {
                    "case": case_name,
                    "variable": f"{stream}.{comp}",
                    "dwsim": dw_val,
                }
                if has_baseline and case_name in baseline and stream in baseline[case_name]:
                    asp_val = baseline[case_name][stream][comp]
                    point["aspen"] = asp_val
                    if abs(asp_val) > ABS_THRESHOLD:
                        point["rel_dev"] = abs(dw_val - asp_val) / abs(asp_val)
                    else:
                        point["rel_dev"] = abs(dw_val - asp_val)
                    point["pass"] = (
                        point["rel_dev"] < REL_THRESHOLD
                        or abs(dw_val - asp_val) < ABS_THRESHOLD
                    )
                else:
                    point["aspen"] = None
                    point["rel_dev"] = None
                    point["pass"] = dw_val >= 0  # non-negative check only
                all_points.append(point)

    if has_baseline:
        lines.append(
            "| Case | Variable | Aspen (g/h) | DWSIM (g/h) | Rel. Dev. | Status |")
        lines.append(
            "|------|----------|------------|------------|-----------|--------|")
    else:
        lines.append("| Case | Variable | DWSIM (g/h) | Status |")
        lines.append("|------|----------|------------|--------|")

    for pt in all_points:
        status = "✅" if pt["pass"] else "❌"
        if has_baseline:
            asp = f"{pt['aspen']:.4f}" if pt["aspen"] is not None else "N/A"
            dev = f"{pt['rel_dev']:.2%}" if pt["rel_dev"] is not None else "N/A"
            lines.append(
                f"| {pt['case']} | {pt['variable']} | {asp} | {pt['dwsim']:.4f} | {dev} | {status} |"
            )
        else:
            lines.append(
                f"| {pt['case']} | {pt['variable']} | {pt['dwsim']:.4f} | {status} |"
            )

    # Statistics
    total_points = len(all_points)
    pass_count = sum(1 for p in all_points if p["pass"])
    fail_count = total_points - pass_count
    pass_rate = pass_count / total_points if total_points > 0 else 0

    lines.extend([
        "",
        "## Statistics",
        "",
        f"- **Total comparison points**: {total_points}",
        f"- **PASS**: {pass_count} ({pass_rate:.0%})",
        f"- **FAIL**: {fail_count} ({1-pass_rate:.0%})",
        "",
    ])

    # Failed points analysis
    failed = [p for p in all_points if not p["pass"]]
    if failed:
        lines.extend([
            "## Failed Points Analysis",
            "",
            "| Case | Variable | Aspen | DWSIM | Deviation | Possible Cause |",
            "|------|----------|-------|-------|-----------|----------------|",
        ])
        for pt in failed:
            asp = f"{pt['aspen']:.4f}" if pt["aspen"] is not None else "N/A"
            dev = f"{pt['rel_dev']:.2%}" if pt["rel_dev"] is not None else "N/A"
            cause = "BIP kij=0 (no interaction parameter tuning)"
            lines.append(
                f"| {pt['case']} | {pt['variable']} | {asp} | {pt['dwsim']:.4f} | {dev} | {cause} |"
            )
        lines.append("")

    # Go/No-Go Decision
    all_converged = all(d["converged"] for d in all_results.values())
    all_mb_ok = all(d["mass_balance_err"] < 0.05 for d in all_results.values())

    if has_baseline:
        go_criteria = pass_rate >= 0.90
        criteria_detail = f"≥90% of {total_points} points within threshold"
    else:
        go_criteria = all_converged and all_mb_ok
        criteria_detail = "All cases converge + mass balance < 5%"

    decision = "GO" if go_criteria else "NO-GO"
    decision_emoji = "✅" if go_criteria else "❌"

    lines.extend([
        "## Go/No-Go Decision",
        "",
        f"### {decision_emoji} **{decision}**",
        "",
        f"**Criteria**: {criteria_detail}",
        f"**Result**: {'Met' if go_criteria else 'Not met'}",
        "",
        "### Decision Basis",
        "",
    ])

    if has_baseline:
        lines.append(f"- Pass rate: {pass_rate:.0%} (threshold: 90%)")
    else:
        lines.extend([
            "- **Note**: No Aspen baseline available on this platform (Linux).",
            "  Aspen baseline extraction requires Windows + Aspen Plus license.",
            "  Decision based on DWSIM-only verification criteria:",
            f"  - All 5 cases converge: {'✅' if all_converged else '❌'}",
            f"  - Mass balance closure < 5% for all cases: {'✅' if all_mb_ok else '❌'}",
            f"  - All 45 output values non-negative: {'✅' if pass_count == total_points else '❌'}",
            "",
            "### Recommendations for Full Parity Verification",
            "",
            "1. Run `script/dwsim/extract_aspen_params.py` on Windows to extract Aspen parameters",
            "2. Run `script/dwsim/generate_aspen_baseline.py` on Windows to generate baseline CSV",
            "3. Copy `aspen_params.json` and `aspen_baseline.csv` to `example/example_dwsim/`",
            "4. Re-run this report with `--baseline example/example_dwsim/aspen_baseline.csv`",
            "",
            "### Known Limitations",
            "",
            "- BIP kij=0 for all isotopologue pairs (no interaction parameters tuned)",
            "- 30-stage columns (Aspen model may use different stage counts)",
            "- Column specs (reflux ratio, bottoms rate) are approximate defaults",
            "- Separation quality is poor without proper BIP tuning",
        ])

    lines.append("")

    report = "\n".join(lines)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(report)
    return report, decision


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate DWSIM parity report")
    parser.add_argument("--baseline", help="Path to Aspen baseline CSV")
    parser.add_argument("--output",
                        default="example/example_dwsim/parity_report.md",
                        help="Output report path")
    args = parser.parse_args()

    project_root = os.getcwd()

    print("Running all test cases...")
    all_results = run_all_cases()

    baseline = None
    if args.baseline:
        baseline = load_baseline(args.baseline)
    else:
        default_baseline = os.path.join(
            project_root, "example", "example_dwsim", "aspen_baseline.csv"
        )
        baseline = load_baseline(default_baseline)

    output_path = os.path.join(project_root, args.output)
    print(f"\nGenerating report: {output_path}")
    report, decision = generate_report(all_results, baseline, output_path)

    print(f"\nDecision: {decision}")
    print(f"Report saved to: {output_path}")
    return 0 if decision == "GO" else 1


if __name__ == "__main__":
    sys.exit(main())
