#!/usr/bin/env python3
"""DWSIM headless smoke test on Linux.

Creates a simple flowsheet with Water + Ethanol, a material stream, a mixer,
and verifies that DWSIM can solve it headlessly via Python.NET + CoreCLR.

Usage:
    DOTNET_ROOT=/usr/lib/dotnet python script/dwsim/smoke_test_dwsim.py

Exit code 0 = PASSED, non-zero = FAILED.
"""

import os
import sys

DWSIM_DIR = os.environ.get("DWSIM_DIR", "/usr/local/lib/dwsim")
DOTNET_ROOT = os.environ.get("DOTNET_ROOT", "/usr/lib/dotnet")


def setup_runtime():
    """Configure pythonnet to use CoreCLR instead of Mono."""
    from pythonnet import set_runtime
    from clr_loader import get_coreclr

    rt = get_coreclr(dotnet_root=DOTNET_ROOT)
    set_runtime(rt)


def main():
    # Step 1: Set up .NET CoreCLR runtime
    print(f"DWSIM_DIR  = {DWSIM_DIR}")
    print(f"DOTNET_ROOT = {DOTNET_ROOT}")
    setup_runtime()

    import clr

    sys.path.append(DWSIM_DIR)

    # Step 2: Load DWSIM assemblies
    clr.AddReference("DWSIM.Automation")
    clr.AddReference("DWSIM.Interfaces")
    clr.AddReference("DWSIM.Thermodynamics")

    from DWSIM.Automation import Automation3
    from DWSIM.Interfaces.Enums.GraphicObjects import ObjectType

    interf = Automation3()
    print("Automation3 instance created.")

    # Step 3: Create flowsheet and add compounds
    sim = interf.CreateFlowsheet()
    sim.AddCompound("Water")
    sim.AddCompound("Ethanol")
    print(f"Compounds added: {list(sim.SelectedCompounds.Keys)}")

    # Step 4: Add property package
    sim.CreateAndAddPropertyPackage("NRTL")
    print("Property package: NRTL")

    # Step 5: Create material streams and a mixer
    from DWSIM.Thermodynamics.Streams import MaterialStream

    m1 = sim.AddObject(ObjectType.MaterialStream, 50, 50, "feed")
    m1 = m1.GetAsObject()

    # Set feed conditions: 300 K, 101325 Pa, 100 mol/s
    m1.SetTemperature(300.0)  # K
    m1.SetPressure(101325.0)  # Pa
    m1.SetMolarFlow(100.0)  # mol/s
    m1.SetOverallCompoundMolarFlow("Water", 70.0)
    m1.SetOverallCompoundMolarFlow("Ethanol", 30.0)

    print(f"Feed stream set: T=300 K, P=101325 Pa, F=100 mol/s")

    # Step 6: Solve the flowsheet
    print("Solving flowsheet...")
    interf.CalculateFlowsheet2(sim)
    print("Flowsheet solved.")

    # Step 7: Read back results
    T_result = m1.GetTemperature()
    P_result = m1.GetPressure()
    F_result = m1.GetMolarFlow()

    print(
        f"Results: T={T_result:.2f} K, P={P_result:.2f} Pa, F={F_result:.4f} mol/s")

    # Step 8: Validate
    ok = True
    if abs(T_result - 300.0) > 0.1:
        print(f"FAIL: Temperature mismatch: {T_result} vs expected 300.0")
        ok = False
    if abs(P_result - 101325.0) > 1.0:
        print(f"FAIL: Pressure mismatch: {P_result} vs expected 101325.0")
        ok = False
    if F_result < 1e-6:
        print(f"FAIL: Molar flow is zero or negative: {F_result}")
        ok = False

    if ok:
        print("\nDWSIM smoke test PASSED")
        return 0
    else:
        print("\nDWSIM smoke test FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
