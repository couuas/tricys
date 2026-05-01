#!/usr/bin/env python3
"""Register hydrogen isotopologue compounds in DWSIM.

Registers H2, HD, D2, HT, DT, T2 with critical properties from literature
(NIST, Souers 1986). Can optionally override with Aspen-extracted parameters.

Usage:
    DOTNET_ROOT=/usr/lib/dotnet python script/dwsim/register_compounds.py [--params aspen_params.json]

References:
    - NIST Chemistry WebBook (H2, D2)
    - Souers, "Hydrogen Properties for Fusion Energy" (1986)
    - Hoge & Arnold, J. Res. NBS 47, 63 (1951)
    - Mohammed, PhD thesis, Lancaster University (2016)
"""

import json
import os
import sys

DWSIM_DIR = os.environ.get("DWSIM_DIR", "/usr/local/lib/dwsim")
DOTNET_ROOT = os.environ.get("DOTNET_ROOT", "/usr/lib/dotnet")

# Literature values for hydrogen isotopologues
# Sources: NIST WebBook (H2, D2), Souers 1986, geometric mean interpolation (hetero)
# Tc in K, Pc in Pa, omega dimensionless, MW in g/mol, Tb in K (at 1 atm)
COMPOUND_DATA = {
    "Hydrogen": {  # H2 — NIST standard
        "formula": "H2",
        "MW": 2.016,
        "Tc": 33.145,    # K
        "Pc": 1296400,   # Pa (12.964 bar)
        "omega": -0.219,
        "Tb": 20.271,    # K (normal boiling point)
        "Vc": 64.2e-6,   # m³/mol
        "CAS": "1333-74-0",
    },
    "HD": {  # Hydrogen-Deuteride — geometric mean / Souers
        "formula": "HD",
        "MW": 3.022,
        "Tc": 35.91,
        "Pc": 1476000,   # Pa (~14.76 bar)
        "omega": -0.181,
        "Tb": 22.13,
        "Vc": 62.8e-6,
        "CAS": "13983-20-5",
    },
    "Deuterium": {  # D2 — NIST standard
        "formula": "D2",
        "MW": 4.028,
        "Tc": 38.34,     # K
        "Pc": 1665300,   # Pa (16.653 bar)
        "omega": -0.136,
        "Tb": 23.67,     # K
        "Vc": 60.3e-6,
        "CAS": "7782-39-0",
    },
    "HT": {  # Hydrogen-Tritide — interpolated
        "formula": "HT",
        "MW": 4.024,
        "Tc": 36.62,
        "Pc": 1542000,   # Pa (~15.42 bar)
        "omega": -0.164,
        "Tb": 22.92,
        "Vc": 62.0e-6,
        "CAS": "10028-17-8",
    },
    "DT": {  # Deuterium-Tritide — interpolated
        "formula": "DT",
        "MW": 5.030,
        "Tc": 39.42,
        "Pc": 1755000,   # Pa (~17.55 bar)
        "omega": -0.118,
        "Tb": 24.38,
        "Vc": 59.0e-6,
        "CAS": "14885-60-0",
    },
    "Tritium": {  # T2 — Souers 1986
        "formula": "T2",
        "MW": 6.032,
        "Tc": 40.44,     # K
        "Pc": 1850000,   # Pa (~18.50 bar)
        "omega": -0.100,
        "Tb": 25.04,     # K
        "Vc": 57.1e-6,
        "CAS": "10028-17-8",  # Note: T2 CAS often grouped with HT
    },
}

# Mapping from Aspen compound names to DWSIM names
ASPEN_TO_DWSIM = {
    "H2": "Hydrogen",
    "HD": "HD",
    "D2": "Deuterium",
    "HT": "HT",
    "DT": "DT",
    "T2": "Tritium",
}


def setup_runtime():
    """Configure pythonnet for CoreCLR."""
    from pythonnet import set_runtime
    from clr_loader import get_coreclr
    rt = get_coreclr(dotnet_root=DOTNET_ROOT)
    set_runtime(rt)


def load_aspen_overrides(params_path):
    """Load overrides from aspen_params.json if available."""
    if not params_path or not os.path.exists(params_path):
        return {}
    with open(params_path, "r") as f:
        data = json.load(f)
    return data.get("compounds", {})


def register_compounds(sim, aspen_overrides=None):
    """Register all 6 hydrogen isotopologue compounds in the DWSIM flowsheet.

    For H2 and D2, uses DWSIM's built-in database if available and overrides
    critical properties. For heteronuclear species (HD, HT, DT) and T2, creates
    custom compounds.

    Args:
        sim: DWSIM flowsheet object
        aspen_overrides: dict from aspen_params.json compounds section

    Returns:
        dict mapping compound names to their ConstantProperties objects
    """
    import clr
    sys.path.append(DWSIM_DIR)
    clr.AddReference("DWSIM.Thermodynamics")

    registered = {}

    for dwsim_name, props in COMPOUND_DATA.items():
        # Try built-in first for H2 and D2
        try:
            sim.AddCompound(dwsim_name)
            print(f"  {dwsim_name}: loaded from DWSIM built-in database")
        except Exception:
            # Create custom compound for species not in built-in DB
            try:
                _register_custom_compound(sim, dwsim_name, props)
                print(f"  {dwsim_name}: registered as custom compound")
            except Exception as e:
                print(f"  {dwsim_name}: FAILED to register — {e}")
                continue

        # Override critical properties if Aspen data available
        aspen_name = None
        for a_name, d_name in ASPEN_TO_DWSIM.items():
            if d_name == dwsim_name:
                aspen_name = a_name
                break

        if aspen_overrides and aspen_name and aspen_name in aspen_overrides:
            _apply_overrides(sim, dwsim_name, aspen_overrides[aspen_name])

        registered[dwsim_name] = props

    return registered


def _register_custom_compound(sim, name, props):
    """Register a compound not in DWSIM's built-in database."""
    import clr
    clr.AddReference("DWSIM.Thermodynamics")
    from DWSIM.Thermodynamics.BaseClasses import ConstantProperties

    comp = ConstantProperties()
    comp.Name = name
    comp.Formula = props["formula"]
    comp.Molar_Weight = props["MW"]
    comp.Critical_Temperature = props["Tc"]
    comp.Critical_Pressure = props["Pc"]
    comp.Acentric_Factor = props["omega"]
    comp.Normal_Boiling_Point = props["Tb"]
    comp.Critical_Volume = props["Vc"]
    comp.CAS_Number = props.get("CAS", "")
    comp.OriginalDB = "User"
    comp.CurrentDB = "User"

    # Generate a unique ID
    import random
    comp.ID = random.randint(700000, 799999)

    # Add to flowsheet
    if not sim.AvailableCompounds.ContainsKey(name):
        sim.AvailableCompounds.Add(name, comp)
    sim.SelectedCompounds.Add(name, comp)


def _apply_overrides(sim, dwsim_name, aspen_props):
    """Apply Aspen-extracted property overrides to an already-registered compound."""
    if dwsim_name not in sim.SelectedCompounds:
        return

    comp = sim.SelectedCompounds[dwsim_name]
    overrides = {}

    if aspen_props.get("Tc") is not None:
        comp.Critical_Temperature = float(aspen_props["Tc"])
        overrides["Tc"] = aspen_props["Tc"]
    if aspen_props.get("Pc") is not None:
        comp.Critical_Pressure = float(aspen_props["Pc"])
        overrides["Pc"] = aspen_props["Pc"]
    if aspen_props.get("omega") is not None:
        comp.Acentric_Factor = float(aspen_props["omega"])
        overrides["omega"] = aspen_props["omega"]

    if overrides:
        print(f"    → overrides applied: {overrides}")


def verify_compounds(sim, interf):
    """Verify registered compounds with flash calculation."""
    print("\nVerification: flash calculations at T=30K, P=200000 Pa")
    from DWSIM.Interfaces.Enums.GraphicObjects import ObjectType

    m = sim.AddObject(ObjectType.MaterialStream, 50, 50, "verify_stream")
    m = m.GetAsObject()

    m.SetTemperature(30.0)   # K — above H2 Tc, below D2/T2 Tc
    m.SetPressure(200000.0)  # 2 atm
    m.SetMolarFlow(1.0)      # 1 mol/s

    # Set equal molar fractions
    n_compounds = len(COMPOUND_DATA)
    for name in COMPOUND_DATA:
        try:
            m.SetOverallCompoundMolarFlow(name, 1.0 / n_compounds)
        except Exception as e:
            print(f"  Warning: could not set flow for {name}: {e}")

    try:
        interf.CalculateFlowsheet2(sim)
        T = m.GetTemperature()
        P = m.GetPressure()
        print(f"  Flash OK: T={T:.2f} K, P={P:.0f} Pa")
        return True
    except Exception as e:
        print(f"  Flash FAILED: {e}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Register H-isotopologue compounds in DWSIM")
    parser.add_argument("--params", help="Path to aspen_params.json for overrides")
    parser.add_argument("--verify", action="store_true", default=True,
                        help="Run flash verification after registration")
    args = parser.parse_args()

    print(f"DWSIM_DIR  = {DWSIM_DIR}")
    print(f"DOTNET_ROOT = {DOTNET_ROOT}")

    setup_runtime()
    import clr
    sys.path.append(DWSIM_DIR)
    clr.AddReference("DWSIM.Automation")
    clr.AddReference("DWSIM.Interfaces")

    from DWSIM.Automation import Automation3
    interf = Automation3()
    sim = interf.CreateFlowsheet()

    # Load optional Aspen overrides
    overrides = load_aspen_overrides(args.params)
    if overrides:
        print(f"Loaded Aspen overrides for {len(overrides)} compounds")

    # Register compounds
    print("\nRegistering compounds:")
    registered = register_compounds(sim, overrides)
    print(f"\nRegistered {len(registered)}/6 compounds")

    # Add property package (SRK for hydrogen systems)
    sim.CreateAndAddPropertyPackage("Soave-Redlich-Kwong (SRK)")
    print("Property package: SRK")

    # Verify
    if args.verify:
        ok = verify_compounds(sim, interf)
        if ok:
            print("\nCompound registration PASSED")
            return 0
        else:
            print("\nCompound registration FAILED (flash error)")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
