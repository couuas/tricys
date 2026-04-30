# tricys/visualizer/app.py
from pathlib import Path

import dash
import dash_bootstrap_components as dbc

from tricys.visualizer.callbacks import register_callbacks
from tricys.visualizer.context import build_viewer_context, get_default_context_dir
from tricys.visualizer.data import load_h5_data
from tricys.visualizer.layout import create_layout


def create_app(
    h5_file_path: str = None,
    server_mode: bool = False,
    context_secret: str = None,
    base_pathname: str = "/",
    context_dir: str = None,
):
    """
    Creates and configures the Dash application.
    """
    normalized_base_path = base_pathname or "/"
    if not normalized_base_path.startswith("/"):
        normalized_base_path = f"/{normalized_base_path}"
    if not normalized_base_path.endswith("/"):
        normalized_base_path = f"{normalized_base_path}/"

    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP],
        suppress_callback_exceptions=True,
        requests_pathname_prefix=normalized_base_path,
        routes_pathname_prefix=normalized_base_path,
        assets_folder=str(Path(__file__).resolve().parent / "assets"),
    )

    if h5_file_path:
        (
            variable_options,
            parameter_options,
            table_columns,
            jobs_data,
            config_data,
            log_data,
        ) = load_h5_data(h5_file_path)
        initial_context = build_viewer_context(
            h5_file_path,
            display_path=h5_file_path,
            mode="file",
        )
    else:
        variable_options = []
        parameter_options = []
        table_columns = []
        jobs_data = []
        config_data = None
        log_data = None
        initial_context = None

    # Set Layout
    app.layout = create_layout(
        variable_options,
        parameter_options,
        table_columns,
        jobs_data,
        config_data,
        log_data,
        initial_context=initial_context,
    )

    # Register Callbacks
    register_callbacks(
        app,
        server_mode=server_mode,
        context_secret=context_secret,
        context_dir=context_dir or get_default_context_dir(),
    )

    @app.server.get(f"{normalized_base_path.rstrip('/')}/health")
    def hdf5_health():
        return {"status": "ok", "server_mode": server_mode}

    return app
