#!/usr/bin/env python3
"""Extract thermodynamic and equipment parameters from Aspen Plus .bkp file.

This script uses the Aspen Plus COM interface to extract:
  - Compound critical properties (Tc, Pc, omega, MW, Tb, Vc)
  - SRK binary interaction parameters (kij matrix)
  - Column configurations (stages, feed stage, specs, pressure)
  - Stream topology (connections, initial T/P)

Output: JSON file with all parameters needed to build a DWSIM equivalent model.

Usage (Windows only):
    python script/dwsim/extract_aspen_params.py \\
        --bkp example/example_aspenbkp/T2-Threetowers4.bkp \\
        --output example/example_dwsim/aspen_params.json

Requires: win32com (pywin32), Aspen Plus installed and licensed.
"""

import argparse
import json
import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# The 6 hydrogen isotopologue compounds in the I_ISS model
COMPOUNDS = ["H2", "HD", "D2", "HT", "DT", "T2"]

# The 3 distillation columns in the T2-Threetowers4 model
COLUMNS = ["CD1", "CD2", "CD3"]

# Key output streams
OUTPUT_STREAMS = ["S4", "S16", "S17", "FROMTEP"]


def safe_get_value(tree, path, default=None):
    """Safely get a value from the Aspen COM tree."""
    try:
        node = tree.FindNode(path)
        if node is not None:
            return node.Value
    except Exception as e:
        logger.debug(f"Could not read {path}: {e}")
    return default


def extract_compound_properties(aspen):
    """Extract critical properties for all 6 hydrogen isotopologue compounds."""
    tree = aspen.Tree
    compounds = {}

    # Property paths in Aspen COM tree (APV140 parameter set)
    # Try multiple path patterns for different Aspen versions
    prop_paths = {
        "MW": [
            r"\Data\Components\Specifications\{comp}\Input\MW",
            r"\Data\Components\Specifications\{comp}\Output\MW",
        ],
        "Tc": [
            r"\Data\Components\Specifications\{comp}\Input\TC",
            r"\Data\Components\Specifications\{comp}\Output\TC",
        ],
        "Pc": [
            r"\Data\Components\Specifications\{comp}\Input\PC",
            r"\Data\Components\Specifications\{comp}\Output\PC",
        ],
        "omega": [
            r"\Data\Components\Specifications\{comp}\Input\OMEGA",
            r"\Data\Components\Specifications\{comp}\Output\OMEGA",
        ],
        "Tb": [
            r"\Data\Components\Specifications\{comp}\Input\TB",
            r"\Data\Components\Specifications\{comp}\Output\TB",
        ],
        "Vc": [
            r"\Data\Components\Specifications\{comp}\Input\VC",
            r"\Data\Components\Specifications\{comp}\Output\VC",
        ],
    }

    for comp in COMPOUNDS:
        props = {}
        for prop_name, paths in prop_paths.items():
            value = None
            for path_template in paths:
                path = path_template.format(comp=comp)
                value = safe_get_value(tree, path)
                if value is not None:
                    break
            props[prop_name] = value
        compounds[comp] = props
        logger.info(
            f"  {comp}: MW={props.get('MW')}, Tc={props.get('Tc')}, Pc={props.get('Pc')}")

    return compounds


def extract_bip_parameters(aspen):
    """Extract SRK binary interaction parameters (kij matrix).

    Returns dict of {("CompA", "CompB"): {"kij": value, "lij": value}}.
    Also checks LLE-ASPEN parameter set paths.
    """
    tree = aspen.Tree
    bips = {}

    # Try multiple path patterns for BIP parameters
    # The model uses both SRK-ASPEN and LLE-ASPEN property methods
    bip_path_templates = [
        # SRK BIP paths
        r"\Data\Properties\Parameters\Binary Interaction\SRKKIJ-1\Input\{p}\{i}\{j}",
        r"\Data\Properties\Parameters\Binary Interaction\ESRKIJ-1\Input\{p}\{i}\{j}",
        r"\Data\Properties\Parameters\Binary Interaction\SRKKIJ\Input\{p}\{i}\{j}",
        # NRTL/UNIQUAC BIP paths (if LLE-ASPEN uses these)
        r"\Data\Properties\Parameters\Binary Interaction\NRTL-1\Input\{p}\{i}\{j}",
    ]

    pair_count = 0
    for i_idx, comp_i in enumerate(COMPOUNDS):
        for j_idx, comp_j in enumerate(COMPOUNDS):
            if j_idx <= i_idx:
                continue
            pair_key = f"{comp_i}/{comp_j}"
            pair_data = {}

            for param_name in ["KAIJ", "KBIJ", "KCIJ", "KDIJ"]:
                for template in bip_path_templates:
                    path = template.format(p=param_name, i=comp_i, j=comp_j)
                    val = safe_get_value(tree, path)
                    if val is not None:
                        pair_data[param_name] = val
                        break
                    # Try reversed order
                    path = template.format(p=param_name, i=comp_j, j=comp_i)
                    val = safe_get_value(tree, path)
                    if val is not None:
                        pair_data[param_name] = val
                        break

            bips[pair_key] = pair_data
            if pair_data:
                pair_count += 1
                logger.info(f"  {pair_key}: {pair_data}")

    logger.info(f"Found BIP data for {pair_count}/15 pairs")
    return bips


def extract_column_config(aspen):
    """Extract distillation column configurations."""
    tree = aspen.Tree
    columns = {}

    for col_name in COLUMNS:
        col = {}
        base_path = rf"\Data\Blocks\{col_name}"

        # Number of stages
        col["stage_count"] = safe_get_value(
            tree, f"{base_path}\\Input\\NSTAGE")

        # Feed stage (may be multiple feeds)
        col["feed_stage"] = safe_get_value(
            tree, f"{base_path}\\Input\\FEED_STAGE\\FROMTEP")
        if col["feed_stage"] is None:
            # Try to find any feed stage
            for stream in ["FROMTEP", "S1", "S2", "S3", "S4", "S5"]:
                val = safe_get_value(
                    tree, f"{base_path}\\Input\\FEED_STAGE\\{stream}")
                if val is not None:
                    col["feed_stage"] = val
                    col["feed_stream"] = stream
                    break

        # Condenser type: TOTAL, PARTIAL-V, PARTIAL-V-L, NONE
        col["condenser_type"] = safe_get_value(
            tree, f"{base_path}\\Input\\CONDENSER")

        # Reboiler type: KETTLE, THERMOSIPHON, NONE
        col["reboiler_type"] = safe_get_value(
            tree, f"{base_path}\\Input\\REBOILER")

        # Column pressure (top stage)
        col["pressure"] = safe_get_value(tree, f"{base_path}\\Input\\PRES1")

        # Pressure drop
        col["pressure_drop"] = safe_get_value(
            tree, f"{base_path}\\Input\\DP_STAGE")

        # Reflux ratio or distillate rate spec
        col["reflux_ratio"] = safe_get_value(tree, f"{base_path}\\Input\\RR")
        col["distillate_rate"] = safe_get_value(
            tree, f"{base_path}\\Input\\D:F")
        col["bottoms_rate"] = safe_get_value(tree, f"{base_path}\\Input\\B:F")

        # Condenser/reboiler duty specs
        col["condenser_duty"] = safe_get_value(tree, f"{base_path}\\Input\\Q1")
        col["reboiler_duty"] = safe_get_value(tree, f"{base_path}\\Input\\QN")

        # Property method used
        col["property_method"] = safe_get_value(
            tree, f"{base_path}\\Input\\PROPERTIES")

        columns[col_name] = col
        logger.info(f"  {col_name}: stages={col.get('stage_count')}, feed={col.get('feed_stage')}, "
                    f"cond={col.get('condenser_type')}, reb={col.get('reboiler_type')}")

    return columns


def extract_stream_topology(aspen):
    """Extract stream conditions and connectivity."""
    tree = aspen.Tree
    streams = {}

    # All streams to check
    stream_names = ["FROMTEP", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9",
                    "S10", "S11", "S12", "S13", "S14", "S15", "S16", "S17"]

    for stream_name in stream_names:
        s = {}
        base = rf"\Data\Streams\{stream_name}"

        # Check if stream exists
        temp = safe_get_value(tree, f"{base}\\Input\\TEMP\\MIXED")
        if temp is None:
            temp = safe_get_value(tree, f"{base}\\Output\\TEMP_OUT\\MIXED")

        if temp is None and safe_get_value(tree, f"{base}\\Output\\MOLEFLOW\\MIXED\\H2") is None:
            continue

        s["temperature"] = temp
        s["pressure"] = safe_get_value(tree, f"{base}\\Input\\PRES\\MIXED")
        if s["pressure"] is None:
            s["pressure"] = safe_get_value(
                tree, f"{base}\\Output\\PRES_OUT\\MIXED")

        s["total_flow"] = safe_get_value(
            tree, f"{base}\\Input\\TOTFLOW\\MIXED")
        if s["total_flow"] is None:
            s["total_flow"] = safe_get_value(
                tree, f"{base}\\Output\\TOT_FLOW\\MIXED")

        # Source and destination blocks
        s["from_block"] = safe_get_value(tree, f"{base}\\Input\\SOURCE\\BLOCK")
        s["to_block"] = safe_get_value(tree, f"{base}\\Input\\DEST\\BLOCK")

        streams[stream_name] = s

    logger.info(f"Found {len(streams)} streams")
    return streams


def extract_property_methods(aspen):
    """Extract global and block-level property method settings."""
    tree = aspen.Tree
    methods = {}

    methods["global"] = safe_get_value(
        tree, r"\Data\Properties\Analysis\SYS-PROP\Input\GLOBAL_PROPERTY_METHOD")
    methods["global_alt"] = safe_get_value(
        tree, r"\Data\Setup\SimulationOptions\Input\SIM_PROPMETHOD")

    # Per-block property methods
    for col_name in COLUMNS:
        val = safe_get_value(
            tree, rf"\Data\Blocks\{col_name}\Input\PROPERTIES")
        if val:
            methods[col_name] = val

    return methods


def main():
    parser = argparse.ArgumentParser(
        description="Extract Aspen Plus parameters for DWSIM migration")
    parser.add_argument("--bkp", required=True, help="Path to Aspen .bkp file")
    parser.add_argument("--output", required=True,
                        help="Output JSON file path")
    args = parser.parse_args()

    bkp_path = os.path.abspath(args.bkp)
    output_path = os.path.abspath(args.output)

    if not os.path.exists(bkp_path):
        logger.error(f"BKP file not found: {bkp_path}")
        sys.exit(1)

    # Initialize COM
    try:
        import pythoncom
        import win32com.client as win32
    except ImportError:
        logger.error(
            "This script requires pywin32 (pip install pywin32). Must run on Windows.")
        sys.exit(1)

    pythoncom.CoInitialize()

    aspen = None
    try:
        logger.info(f"Loading Aspen backup: {bkp_path}")
        aspen = win32.DispatchEx("Apwn.Document.40.0")
        aspen.InitFromArchive2(bkp_path)
        aspen.Visible = 0
        aspen.SuppressDialogs = 1
        logger.info("Aspen initialized.")

        # Extract all parameters
        result = {
            "_meta": {
                "source_bkp": os.path.basename(bkp_path),
                "extraction_script": "extract_aspen_params.py",
                "aspen_version": safe_get_value(aspen, r"\Data\Setup\SimulationOptions\Input\ASPEN_VERSION"),
            },
            "property_methods": extract_property_methods(aspen),
            "compounds": extract_compound_properties(aspen),
            "bips": extract_bip_parameters(aspen),
            "columns": extract_column_config(aspen),
            "streams": extract_stream_topology(aspen),
        }

        # Write output
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        logger.info(f"Parameters written to {output_path}")

        # Summary
        n_compounds = len(result["compounds"])
        n_bips = sum(1 for v in result["bips"].values() if v)
        n_columns = len(result["columns"])
        n_streams = len(result["streams"])
        print(f"\nExtraction summary:")
        print(f"  Compounds: {n_compounds} (expected 6)")
        print(f"  BIP pairs with data: {n_bips} (expected ≤15)")
        print(f"  Columns: {n_columns} (expected 3)")
        print(f"  Streams: {n_streams}")

    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if aspen:
            try:
                app = getattr(aspen, "Application", None)
                aspen.Close()
                if app:
                    app.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()

    return 0


if __name__ == "__main__":
    sys.exit(main())
