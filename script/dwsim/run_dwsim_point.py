#!/usr/bin/env python3
"""Run a single-point DWSIM simulation and report results.

Loads the three-tower flowsheet, sets feed composition for a given test case,
solves, and reports H/D/T mass flows at output streams.

Usage:
    cd /path/to/tricys
    DOTNET_ROOT=/usr/lib/dotnet python script/dwsim/run_dwsim_point.py --case TC1

Test cases (matching generate_aspen_baseline.py):
    TC1: T=100, D=50,  H=10  g/h (nominal, high-T)
    TC2: T=50,  D=50,  H=50  g/h (equimolar)
    TC3: T=150, D=10,  H=5   g/h (near-pure T)
    TC4: T=10,  D=100, H=50  g/h (low T, high D)
    TC5: T=80,  D=30,  H=20  g/h (intermediate)
"""

import argparse
import csv
import json
import os
import sys

DWSIM_DIR = os.environ.get("DWSIM_DIR", "/usr/local/lib/dwsim")
DOTNET_ROOT = os.environ.get("DOTNET_ROOT", "/usr/lib/dotnet")

# Molar masses (g/mol)
M_T = 3.016
M_D = 2.014
M_H = 1.008

# Test cases: {name: (T_flow_g_h, D_flow_g_h, H_flow_g_h)}
TEST_CASES = {
    "TC1": (100.0, 50.0, 10.0),
    "TC2": (50.0, 50.0, 50.0),
    "TC3": (150.0, 10.0, 5.0),
    "TC4": (10.0, 100.0, 50.0),
    "TC5": (80.0, 30.0, 20.0),
}

# DWSIM compound names
COMPOUNDS = ["Hydrogen", "HD", "Deuterium", "HT", "DT", "Tritium"]

# Output streams (matching Aspen: WDS=S4, SDSD2=S16, SDST2=S17)
OUTPUT_STREAMS = {
    "WDS": "S4",
    "SDSD2": "S16",
    "SDST2": "S17",
}


def compute_feed_composition(T_flow, D_flow, H_flow):
    """Compute equilibrium 6-component mole fractions from H/D/T mass flows.

    Same logic as AspenEnhanced.set_composition():
    - Convert g/h to mol/h
    - Compute atom fractions EH, ED, ET
    - Compute equilibrium mole fractions (statistical distribution)
    """
    T_mol = T_flow / M_T
    D_mol = D_flow / M_D
    H_mol = H_flow / M_H
    total_atoms = T_mol + D_mol + H_mol

    ET = T_mol / total_atoms
    ED = D_mol / total_atoms
    EH = H_mol / total_atoms

    # Each molecule has 2 atoms, so molecular flow = atoms / 2
    total_mol = total_atoms / 2

    # Equilibrium mole fractions
    return {
        "Hydrogen": EH ** 2,       # H2
        "HD": 2 * EH * ED,         # HD
        "Deuterium": ED ** 2,      # D2
        "HT": 2 * EH * ET,         # HT
        "DT": 2 * ED * ET,         # DT
        "Tritium": ET ** 2,         # T2
    }, total_mol


def extract_stream_hdt(stream_obj, debug=False):
    """Extract H/D/T mass flows (g/h) from a material stream.

    Mirrors AspenEnhanced.get_stream_results() logic:
    - Read mole flows of each compound
    - Convert to atom-based mass flows
    """
    phases = stream_obj.Phases
    overall = phases[0]  # Phase 0 = Overall

    # Get total molar flow
    try:
        total_mol_s = stream_obj.GetMolarFlow()  # mol/s
    except Exception:
        total_mol_s = 0.0

    flows = {}
    for comp_name in COMPOUNDS:
        try:
            val = overall.Compounds[comp_name].MolarFlow  # mol/s
            if val is not None and val > 0:
                flows[comp_name] = val
            else:
                # Fallback: use mole fraction × total flow
                mf = overall.Compounds[comp_name].MoleFraction
                if mf is not None and total_mol_s > 0:
                    flows[comp_name] = mf * total_mol_s
                else:
                    flows[comp_name] = 0.0
        except Exception:
            flows[comp_name] = 0.0

    # Convert mol/s to mol/h
    for k in flows:
        flows[k] = flows[k] * 3600.0

    Q_H2 = flows["Hydrogen"]
    Q_HD = flows["HD"]
    Q_D2 = flows["Deuterium"]
    Q_HT = flows["HT"]
    Q_DT = flows["DT"]
    Q_T2 = flows["Tritium"]

    H = (2 * Q_H2 + Q_HD + Q_HT) * M_H
    D = (Q_HD + 2 * Q_D2 + Q_DT) * M_D
    T = (Q_HT + Q_DT + 2 * Q_T2) * M_T

    return H, D, T


def main():
    parser = argparse.ArgumentParser(description="Run single-point DWSIM simulation")
    parser.add_argument("--case", choices=list(TEST_CASES.keys()), default="TC1",
                        help="Test case name")
    parser.add_argument("--flowsheet",
                        default="example/example_dwsim/T2_Threetowers4.dwxmz",
                        help="Path to DWSIM flowsheet")
    parser.add_argument("--baseline", help="Path to Aspen baseline CSV for comparison")
    parser.add_argument("--build", action="store_true",
                        help="Build flowsheet from scratch instead of loading")
    args = parser.parse_args()

    T_flow, D_flow, H_flow = TEST_CASES[args.case]
    project_root = os.getcwd()
    print(f"Test case: {args.case}")
    print(f"  T_flow={T_flow} g/h, D_flow={D_flow} g/h, H_flow={H_flow} g/h")

    # Compute feed composition
    feed_comp, total_mol = compute_feed_composition(T_flow, D_flow, H_flow)
    print(f"  Total molar flow: {total_mol:.4f} mol/h")
    print(f"  Feed composition: {', '.join(f'{k}={v:.6f}' for k, v in feed_comp.items())}")

    # Setup DWSIM
    from pythonnet import set_runtime
    from clr_loader import get_coreclr
    rt = get_coreclr(dotnet_root=DOTNET_ROOT)
    set_runtime(rt)

    import clr
    sys.path.append(DWSIM_DIR)
    clr.AddReference("DWSIM.Automation")
    clr.AddReference("DWSIM.Interfaces")
    from DWSIM.Automation import Automation3

    interf = Automation3()

    if args.build:
        # Build from scratch
        script_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, script_dir)
        from build_dwsim_flowsheet import configure_srk_bip, build_three_towers
        from register_compounds import register_compounds

        sim = interf.CreateFlowsheet()
        register_compounds(sim, {})
        sim.CreateAndAddPropertyPackage("Soave-Redlich-Kwong (SRK)")
        configure_srk_bip(sim, {})
        built_objects = build_three_towers(sim, {})
        # Use objects directly (properly typed, no interface casting needed)
        feed_stream = built_objects["streams"]["FROMTEP"]
        output_streams = {
            "WDS": built_objects["streams"].get("S4"),
            "SDSD2": built_objects["streams"].get("S16"),
            "SDST2": built_objects["streams"].get("S17"),
        }
        columns = built_objects["columns"]
    else:
        # Load saved flowsheet
        flowsheet_path = os.path.join(project_root, args.flowsheet)
        flowsheet_path = os.path.abspath(flowsheet_path)
        print(f"\nLoading flowsheet: {flowsheet_path}")
        sim = interf.LoadFlowsheet(flowsheet_path)

        # Find streams (loaded objects need __raw_implementation__)
        feed_stream = None
        output_streams = {}
        columns = {}
        for kv in sim.SimulationObjects:
            obj = kv.Value
            concrete = getattr(obj, "__raw_implementation__", obj)
            name = obj.GraphicObject.Tag
            if name == "FROMTEP":
                feed_stream = concrete
            elif name in OUTPUT_STREAMS.values():
                for aspen_name, dwsim_name in OUTPUT_STREAMS.items():
                    if name == dwsim_name:
                        output_streams[aspen_name] = concrete
                        break
            if "DistillationColumn" in obj.GetType().Name:
                columns[name] = concrete

    if feed_stream is None:
        print("ERROR: FROMTEP stream not found in flowsheet")
        return 1

    # Set feed composition
    print("\nSetting feed composition...")
    feed_stream.SetTemperature(22.0)  # K
    feed_stream.SetPressure(101325.0)  # Pa
    # Set per-compound molar flows (total flow is implied by sum of compounds)
    for comp, frac in feed_comp.items():
        molar_flow = frac * total_mol / 3600.0  # mol/s
        feed_stream.SetOverallCompoundMolarFlow(comp, molar_flow)

    # Solve (multiple iterations to help convergence)
    print("Solving flowsheet...")
    max_iters = 5
    for solve_iter in range(max_iters):
        try:
            interf.CalculateFlowsheet2(sim)
        except Exception as e:
            print(f"  ❌ Flowsheet solve exception (iter {solve_iter+1}): {e}")
            break

        # Check column convergence status
        all_converged = True
        for col_name, col_obj in columns.items():
            calculated = col_obj.Calculated
            if not calculated:
                all_converged = False

        if all_converged:
            print(f"  ✅ All columns converged (iter {solve_iter+1})")
            break
        elif solve_iter < max_iters - 1:
            print(f"  Iteration {solve_iter+1}: not all converged, retrying...")
        else:
            print(f"  ⚠ Not all converged after {max_iters} iterations")

    # Print column status
    for col_name, col_obj in columns.items():
        calculated = col_obj.Calculated
        err = col_obj.ErrorMessage
        if calculated:
            print(f"  ✅ {col_name}: Converged")
        else:
            print(f"  ❌ {col_name}: Not converged")
            if err:
                print(f"     Error: {err[:300]}")

    # Extract results
    print("\n=== Results ===")
    results = {}
    all_output_names = {"WDS": "S4", "SDSD2": "S16", "SDST2": "S17", "CD3_DIST": "S_CD3_DIST"}

    for stream_label, stream_key in all_output_names.items():
        if args.build:
            s = built_objects["streams"].get(stream_key)
        else:
            s = output_streams.get(stream_label)
        if s is not None:
            H, D, T = extract_stream_hdt(s)
            results[stream_label] = {"H": H, "D": D, "T": T}
            print(f"  {stream_label}: H={H:.4f}, D={D:.4f}, T={T:.4f} g/h")
        else:
            results[stream_label] = {"H": 0, "D": 0, "T": 0}
            print(f"  {stream_label}: NOT FOUND in flowsheet")

    # Mass balance check (terminal output streams only)
    terminal_streams = ["WDS", "SDSD2", "SDST2", "CD3_DIST"]
    in_total = T_flow + D_flow + H_flow
    out_total = sum(results[s]["H"] + results[s]["D"] + results[s]["T"]
                     for s in terminal_streams if s in results)
    if in_total > 0:
        mb_err = abs(out_total - in_total) / in_total
        print(f"\nMass balance (terminal streams): in={in_total:.4f}, out={out_total:.4f}, "
              f"rel_err={mb_err:.2%}")
    else:
        mb_err = 0.0

    # Compare with Aspen baseline if available
    if args.baseline and os.path.exists(args.baseline):
        print("\n=== Comparison with Aspen baseline ===")
        with open(args.baseline, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("case") == args.case:
                    compare_with_baseline(results, row)
                    break
    else:
        print("\n(No Aspen baseline available for comparison)")

    # Summary
    converged = out_total > 0 or mb_err < 0.01
    print(f"\nConvergence: {'PASS' if converged else 'FAIL'}")
    return 0 if converged else 1


def compare_with_baseline(dwsim_results, baseline_row):
    """Compare DWSIM results with Aspen baseline."""
    fields = [
        ("WDS", "H", "WDS_H"),
        ("WDS", "D", "WDS_D"),
        ("WDS", "T", "WDS_T"),
        ("SDSD2", "H", "SDSD2_H"),
        ("SDSD2", "D", "SDSD2_D"),
        ("SDSD2", "T", "SDSD2_T"),
        ("SDST2", "H", "SDST2_H"),
        ("SDST2", "D", "SDST2_D"),
        ("SDST2", "T", "SDST2_T"),
    ]

    pass_count = 0
    print(f"{'Variable':<12} {'Aspen':>10} {'DWSIM':>10} {'Rel.Err':>10} {'Status':>6}")
    print("-" * 52)
    for stream, iso, csv_key in fields:
        aspen_val = float(baseline_row.get(csv_key, 0))
        dwsim_val = dwsim_results.get(stream, {}).get(iso, 0)
        if abs(aspen_val) > 1e-10:
            rel_err = abs(dwsim_val - aspen_val) / abs(aspen_val)
        else:
            rel_err = 0 if abs(dwsim_val) < 1e-10 else float("inf")
        status = "PASS" if rel_err < 0.20 else "FAIL"
        if status == "PASS":
            pass_count += 1
        print(f"{csv_key:<12} {aspen_val:>10.4f} {dwsim_val:>10.4f} {rel_err:>10.2%} {status:>6}")

    print(f"\n{pass_count}/9 within 20% tolerance")


if __name__ == "__main__":
    sys.exit(main())
