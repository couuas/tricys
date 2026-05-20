??? question "Q: What is co-simulation and how to use it?"
    Co-simulation allows TRICYS to interact with external software (like Aspen Plus):

    **Workflow**:
    1. Run preliminary simulation
    2. Call external processor (Handler)
    3. External software calculates new data
    4. Inject data back into the Modelica model
    5. Run the final full simulation

    **Configuration Example**:
    ```json
    {
        "co_simulation": [
            {
                "mode": "interceptor",
                "submodel_name": "example_model.I_ISS",
                "instance_name": "i_iss",
                "handler_module": "tricys.handlers.i_iss_handler",
                "handler_function": "run_aspen_simulation",
                "params": {
                    "bkp_path": "path/to/aspen/file.bkp"
                }
            }
        ]
    }
    ```
    *   `mode`: `interceptor` (default) or `replacement`.
    *   `handler_module`: The module where the handler is located.
    *   `handler_script_path`: Alternatively, provide the direct path to the handler script.

    For details, see: [Co-simulation Module](../guides/tricys_basic/co_simulation_module.md)

??? question "Q: How to create a custom post-processing module?"
    Post-processing modules are Python functions that receive simulation results and perform analysis:

    **1. Create the handler function**:
    ```python
    # my_postprocess.py
    def analyze_results(df, output_filename="my_report.txt"):
        """
        Custom post-processing function
        
        Args:
            df: Pandas DataFrame containing simulation results
            output_filename: Output file name
        """
        # Perform analysis
        max_inventory = df['sds.I[1]'].max()
        
        # Save results
        with open(output_filename, 'w') as f:
            f.write(f"Maximum tritium inventory: {max_inventory} g\n")
    ```
    **Note**: Please place your custom module (e.g., `my_postprocess.py`) in the root directory of the `tricys` project, or ensure it is in a path that Python can import.

    **2. Reference it in the configuration file**:
    ```json
    {
        "post_processing": [
            {
                "module": "my_postprocess",
                "function": "analyze_results",
                "params": {
                    "output_filename": "custom_report.txt"
                }
            }
        ]
    }
    ```

??? question "Q: How to perform sensitivity analysis?"
    TRICYS offers several sensitivity analysis methods:

    **1. Single-parameter sensitivity analysis**:
    ```bash
    tricys analysis -c single_param_analysis.json
    ```

    Studies the impact of a single parameter on KPIs.

    **2. Multi-parameter sensitivity analysis**:
    ```bash
    tricys analysis -c multi_param_analysis.json
    ```

    Studies the coupling effects between parameters.

    **3. SOBOL global sensitivity analysis**:
    ```bash
    tricys analysis -c sobol_analysis.json
    ```

    Quantifies the contribution of parameters and their interactions.

    **4. Latin Hypercube uncertainty quantification**:
    ```bash
    tricys analysis -c latin_analysis.json
    ```

    Assesses the impact of input uncertainty on the output.

    For details, see: [Sensitivity Analysis Tutorial](../guides/tricys_analysis/single_parameter_sensitivity_analysis.md)

??? question "Q: How to define custom performance metrics?"
    Performance metrics (KPIs) are defined in `sensitivity_analysis.metrics_definition`:

    **Using built-in metrics**:
    ```json
    {
        "metrics_definition": {
            "Max_Inventory": {
                "source_column": "sds.I[1]",
                "method": "max_value"
            }
        }
    }
    ```

    **Built-in metric methods**:
    * `get_final_value`
    * `max_value`, `min_value`, `mean_value`
    * `time_of_max`, `time_of_min`
    * `time_of_turning_point`
    * `calculate_startup_inventory`
    * `calculate_doubling_time`
    * `calculate_required_tbr` (bisection search)

    For a detailed physical explanation of the built-in metrics, see [Core Performance Metrics](../explanation/tricys_analysis/performance_metrics.md).

    **Creating custom metrics**:
    ```python
    # my_metrics.py
    def calculate_peak_to_peak(series):
        """Calculate peak-to-peak value"""
        return series.max() - series.min()
    ```

    Register your function in `tricys/analysis/metric.py` or reference it directly in the configuration.

---

??? question "How do I set maximum inventory capacity and processing rate for a subsystem?"
    Use the `ConstrainedBuffer` component to replace a standard subsystem model (e.g., Blanket) to gain capacity and rate constraint capabilities.

    **Key Parameters**:

    | Parameter | Description | Default | Unit |
    |-----------|-------------|---------|------|
    | `capacity_max` | Maximum inventory (total tritium equivalent) | 1e9 (unconstrained) | g |
    | `rate_max` | Maximum outflow rate | 1e9 (unconstrained) | g/h |
    | `softness` | Sigmoid soft constraint coefficient | 0.02 | — |
    | `to_Down_Fraction` | Fraction routed to downstream | 1.0 | — |

    **JSON Configuration Example** (cap at 500g, rate at 50 g/h):
    ```json
    {
        "simulation_parameters": {
            "blanket_c.capacity_max": 500,
            "blanket_c.rate_max": 50
        }
    }
    ```

    **Parameter Sweep Example**:
    ```json
    {
        "simulation_parameters": {
            "blanket_c.capacity_max": [200, 500, 1000, 2000],
            "blanket_c.rate_max": [20, 50, 100, 1000000000]
        }
    }
    ```

    **Constraint Behavior**:

    - Over-capacity: Inflow is soft-limited by a sigmoid function; excess is routed to the `overflow_out` port
    - Over-rate: Outflow is capped at `rate_max`; excess is routed to the `rate_clip_out` port
    - Mass conservation: All constrained mass is exported through the corresponding ports — nothing disappears

    **Full example configuration** available at `tricys/example/example_data/basic/6_constrained_buffer/`.


---