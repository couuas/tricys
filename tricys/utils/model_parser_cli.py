import json
import logging
import os
import sys

from tricys.core.modelica import (
    get_all_parameters_details,
    get_om_session,
    load_modelica_package,
)


def parse_model_cli(package_path: str, model_name: str) -> None:
    """
    CLI handler for parsing a Modelica model and outputting its parameters as JSON.

    Args:
        package_path: Path to the package.mo file.
        model_name: Fully qualified model name (e.g. package.Model).
    """
    # Configure logging to go to stderr so stdout is kept clean for JSON output
    # We remove existing handlers to avoid duplicate logs if main.py already set them up
    root_logger = logging.getLogger()
    if root_logger.handlers:
        for handler in root_logger.handlers:
            root_logger.removeHandler(handler)

    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr, format="%(levelname)s: %(message)s"
    )

    if not os.path.exists(package_path):
        print(
            json.dumps({"error": f"Package file not found: {package_path}"}),
            file=sys.stdout,
        )
        sys.exit(1)

    try:
        omc = get_om_session()
        if not load_modelica_package(omc, package_path):
            print(
                json.dumps({"error": "Failed to load package via OMC"}), file=sys.stdout
            )
            sys.exit(1)

        params = get_all_parameters_details(omc, model_name)

        # Output the result as JSON to stdout
        print(json.dumps(params, indent=2), file=sys.stdout)

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stdout)
        sys.exit(1)
