## 1. Background and Goal

TRICYS already has a solid co-simulation boundary: stage-one simulation produces an input CSV, an external handler produces an output CSV plus output-port mapping, and the interceptor mechanism injects that result back into the Modelica model.

The current limitation is not handler extensibility itself, but the execution model. Handlers are still assumed to run inside the local `tricys` process. For toolchains such as `win32com.client`, Aspen COM, some COMSOL integrations, or any third-party interface that depends on host-specific environments, this process-local import model couples operating system, dependency installation, and license environment directly to the main TRICYS runtime, which conflicts with Docker-based deployment.

The goal of the RPC Worker architecture is therefore not to replace the existing co-simulation workflow, but to upgrade handler execution from an in-process plugin model to a unified local-or-remote execution runtime. Third-party integrators should only implement solver-specific core logic rather than repeatedly rebuilding service-side integration glue.

## 2. Core Design Principles

This architecture follows five principles:

- Preserve the existing TRICYS co-simulation flow: stage-one simulation, handler execution, interceptor integration, stage-two simulation.
- Fully decouple solver-specific logic from service integration logic.
- Centralize cross-cutting concerns such as job lifecycle, asset transfer, logging, timeout control, cancellation, concurrency, and result packaging.
- Define one minimal extension model for Aspen, COMSOL, and future third-party tools.
- Keep backward compatibility with local handlers. RPC is an additional execution backend, not a rewrite of the configuration model.

## 3. Four-Layer RPC Architecture

The recommended architecture is split into four layers:

```text
┌────────────────────────────────────────────┐
│ Layer 1: TRICYS Remote Transport          │
│ Initiates remote execution from co-sim    │
└────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────┐
│ Layer 2: Worker Runtime                   │
│ Owns lifecycle, assets, logs, timeout     │
└────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────┐
│ Layer 3: Solver Plugin SDK                │
│ Unified extension interface for tools     │
└────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────┐
│ Layer 4: Tool Adapter / Manifest          │
│ Declares capability, schema, constraints  │
└────────────────────────────────────────────┘
```

### 3.1. Layer 1: TRICYS Remote Transport

This layer lives inside the TRICYS co-simulation flow and replaces local `import + function call` handler execution with a unified remote execution path.

Its responsibilities are:

- Read remote execution configuration from `co_simulation.handlers`.
- Package the stage-one input CSV, parameters, and asset manifest into a remote job request.
- Submit the job to an RPC Worker and track job state.
- Materialize the returned output CSV into the current job workspace.
- Translate structured remote outputs back into TRICYS `output_placeholder` semantics.

This layer should not understand Aspen COM, COMSOL APIs, Windows services, or any solver-specific detail. It only speaks TRICYS co-simulation contracts.

### 3.2. Layer 2: Worker Runtime

The Worker Runtime is the core of the generic RPC Worker. It owns all non-business integration concerns.

At minimum, it should provide:

- job intake and validation
- authentication and source control
- workspace creation and cleanup
- input and asset materialization
- log capture and streaming
- timeout handling and cancellation
- queueing and concurrency control
- error normalization and result packaging
- capability discovery and health checks

The runtime should not encode TRICYS interceptor logic, nor should it hardcode Aspen or COMSOL-specific behavior. It is a general-purpose remote solver execution runtime.

### 3.3. Layer 3: Solver Plugin SDK

The plugin SDK is the layer exposed to third-party tool integrators. Its purpose is to constrain plugin development to “core solver logic only”.

Plugin authors should only need to handle:

- reading prepared local input files from a workspace
- invoking the target third-party solver
- producing standard output files or structured results

Plugin authors should not need to reimplement:

- HTTP routing
- upload and download handling
- authentication
- log transport
- timeout or retry policy
- job state management
- TRICYS-specific execution glue

A recommended plugin execution abstraction looks like this:

```python
class ExecutionContext:
    job_id: str
    workspace_dir: str
    params: dict
    inputs: dict
    assets: dict
    output_dir: str
    logger: object


class ExecutionResult:
    status: str
    output_artifacts: dict
    structured_outputs: dict
    metrics: dict
    warnings: list[str]
```

Plugins should work with local execution semantics instead of raw network payloads.

### 3.4. Layer 4: Tool Adapter / Manifest

Each plugin should provide a declarative manifest in addition to executable code. The manifest describes the plugin’s static capability and runtime requirements.

Typical fields include:

- plugin name and version
- supported operations
- parameter schema
- input asset schema
- output artifact schema
- required platform and third-party software version
- default timeout
- maximum concurrency
- license or environment requirements

The manifest is valuable because it allows:

- TRICYS to validate jobs before submission
- the Worker Runtime to perform preflight checks
- frontends or configuration tools to generate forms and documentation automatically

## 4. Recommended Data and Execution Model

### 4.1. Unified Job Model

The Worker should expose a job model rather than “run an arbitrary Python function remotely”.

A generic job request should include at least:

- identifiers such as `job_id` and `trace_id`
- `plugin_name` and `operation_name`
- structured `params`
- execution policy such as timeout, priority, or retry
- input files and asset references
- output and return strategy

The API should preferably expose asynchronous endpoints:

- `submit_job`
- `get_job_status`
- `get_job_logs`
- `get_job_artifacts`
- `cancel_job`

For long-running tools like Aspen or COMSOL, which often have strict concurrency or license constraints, an asynchronous job model is more robust than a purely blocking RPC call.

### 4.2. Unified Asset Model

Assets should be treated as a first-class concern. Three asset modes are recommended:

- `inline`: small files embedded directly in the request, suitable for input CSVs or lightweight JSON.
- `upload`: the caller uploads files first and then references them by `asset_id`.
- `reference`: the caller sends a logical reference, and the Worker resolves it locally. This is best for large model files, licenses, or fixed installation resources.

For Aspen and COMSOL integrations, `reference` will often be the primary mode because large files and host-specific environments should not be re-uploaded for every TRICYS job.

## 5. Integration with TRICYS Co-Simulation

RPC Workers should not change the meaning of TRICYS co-simulation. They only replace the handler execution backend.

The recommended integration flow is:

1. TRICYS performs stage-one simulation and generates an input CSV.
2. The Remote Transport submits the input CSV, parameters, and asset references to the Worker.
3. The Worker Runtime invokes the target solver plugin.
4. The Worker returns an output CSV plus structured result metadata.
5. TRICYS stores the output CSV back into the local job workspace.
6. TRICYS continues with the existing interceptor mechanism and stage-two simulation.

In other words, the RPC Worker extends the handler execution boundary. It does not replace the interceptor mechanism or the two-stage simulation model.

## 6. Why This Fits Docker + Host Hybrid Deployment

The main benefit of this design is that TRICYS can remain inside a Linux Docker environment while platform-dependent plugins run on Windows hosts or other dedicated remote nodes.

A typical deployment looks like this:

- `tricys` and `tricys-backend` run inside Linux containers.
- an Aspen Worker runs on a Windows host with Aspen, COM, and license support.
- a COMSOL Worker runs on another node that has the required COMSOL runtime.
- TRICYS calls these nodes through one consistent RPC protocol instead of importing their Python dependencies locally.

This confines OS-specific dependencies, licensing, and third-party software installation requirements to Worker nodes rather than forcing them into the main container image.

## 7. Recommended Minimum Viable Version

To keep the initial implementation tractable, the first iteration should include only:

- one generic Worker Runtime
- one minimal plugin SPI
- one plugin manifest format
- one core job API set: submit, status, logs, artifacts, cancel
- one Aspen reference plugin
- one Remote Transport adapter on the TRICYS side

That is already enough to validate the main objective: when a new third-party solver is introduced, the developer only writes plugin-specific core logic rather than rebuilding the integration framework.

## 8. Design Conclusion

TRICYS already has a clear co-simulation boundary. The abstraction that needs to evolve is not the simulation flow itself, but the handler execution backend.

By introducing this four-layer RPC architecture:

- TRICYS remains the simulation orchestrator
- the Worker Runtime becomes the generic remote execution runtime
- solver plugins contain only third-party solver logic
- manifests become the static capability and contract layer

The result is a clean separation between solver logic and integration logic, providing one consistent onboarding path for Aspen, COMSOL, and any future third-party interface.