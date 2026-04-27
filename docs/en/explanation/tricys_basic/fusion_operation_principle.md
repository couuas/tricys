# FOC Architecture Design and Implementation Report

## 1. Overview and Core Ideas

In system-level dynamic macro-simulation of fusion reactor plants, the transient response of the fuel cycle system, such as exhaust TEP, isotope separation ISS, and water detritiation WDS, depends strongly on source terms from plasma burn and blanket breeding. Traditional built-in square-wave or pulse generators suffer from missing physical semantics, difficulty expressing complex operating scenarios, and a tendency to trigger dense solver time events.

The **FOC (Fusion Operation Config)** architecture is intended to fully decouple operating-scenario definition from model execution. Its core ideas are:

1. **Physical semanticization**: use thermal power (MW) as the top-level input, and let the system automatically perform the hard physical conversion to mass flow (g/h).
2. **Data-driven workflow**: use a minimal domain-specific language (DSL) to describe operating scenarios, then compile it in Python into arrays or time-table datasets that Modelica can consume.
3. **Elimination of state events**: use stateless logic or linearly interpolated tables underneath, greatly improving solver efficiency and numerical stability for long-horizon simulations over months or years.

---

## 2. FOC Syntax Specification

FOC uses a lightweight text-command syntax. The default convention is: **thermal power in MW, time in seconds (s)**. Comments begin with `#`. FOC supports arbitrary combinations of the following four core operating rules.

If the target Modelica model does not use seconds as its internal time base, or if you want to declare the time unit used by the FOC file explicitly, you can add time-header directives at the beginning of the FOC file:

```text
TIME_UNIT <second|hour|day|week|year>
TIME_CONVERSION <factor>
TIME_CONVERSION <source_unit>_to_<target_unit>
```

Where:

- when neither `TIME_UNIT` nor `TIME_CONVERSION` appears, the FOC time unit defaults to seconds and no time conversion is applied
- `TIME_UNIT <unit>` explicitly declares the time unit used by the current FOC file, but does not trigger any conversion by itself; for example, `TIME_UNIT hour` only states that the following time values are written in hours
- `TIME_CONVERSION NONE` means no time conversion is applied and the time values in the FOC file are used directly
- `TIME_CONVERSION 3600` means all time values written in the FOC file are multiplied by `3600` before entering the model
- `TIME_CONVERSION second_to_hour` means time values written in seconds in the FOC file are converted into hours for the model; likewise `hour_to_second` is also supported; named conversions currently support `second/hour/day/week/year`
- time conversion is executed only when `TIME_CONVERSION` is declared explicitly, so there is no implicit conversion in the parser
- when `TIME_UNIT` and a named `TIME_CONVERSION` are declared together, they must agree on the source unit, for example `TIME_UNIT second` together with `TIME_CONVERSION second_to_hour`
- these header directives must appear before all business commands such as `POWER`, `BURN`, `DWELL`, `PULSE`, and `BEGIN_SCHEDULE`, and each directive may only be declared once

Therefore, for the case where the model keeps its default second-based time axis and the FOC is written in hours with an explicit conversion to seconds, you can write:

```text
TIME_UNIT hour
TIME_CONVERSION hour_to_second
POWER 1500
BURN 10
```

If you only want to declare that the FOC is written in hours without performing any conversion, you can write:

```text
TIME_UNIT hour
POWER 1500
BURN 10
```

For the case where the FOC is written in seconds but the model uses hours internally, you can write:

```text
TIME_CONVERSION second_to_hour
POWER 1500
BURN 7200
```

If you only want to state explicitly that no conversion is required, you can also write:

```text
TIME_CONVERSION NONE
POWER 1500
BURN 10
```

### 2.1 Rule 1: Continuous Burn

Set a constant thermal-power baseline and maintain it for a specified duration.

* **Syntax**: `POWER <value>` + `BURN <time>`
* **Note**: `<time>` is multiplied only when a top-level `TIME_CONVERSION` is declared; otherwise the raw value is used directly
* **Example**:
    ```text
    POWER 1500
    BURN 36000  # 1500 MW continuous burn for 10 hours
    ```

### 2.2 Rule 2: Step and Dwell

Insert a zero-power dwell period between different power segments to represent shutdown and exhaust phases.

* **Syntax**: `DWELL <time>`
* **Note**: `<time>` is multiplied only when a top-level `TIME_CONVERSION` is declared; otherwise the raw value is used directly
* **Example**:
    ```text
    POWER 1500
    BURN 7200
    DWELL 3600  # force zero power so the system performs shutdown exhaust
    POWER 2000
    BURN 7200
    ```

### 2.3 Rule 3: Pulsed Operation

Quickly generate a high-frequency repeated macro-sequence of tokamak pulses.

* **Syntax**: `PULSE <power> <burn_time> <dwell_time> <cycles>`
* **Note**: `<burn_time>` and `<dwell_time>` are multiplied only when a top-level `TIME_CONVERSION` is declared; otherwise the raw values are used directly
* **Example**:
    ```text
    # 1500 MW power, 400 s burn, 100 s shutdown exhaust, repeated 10 times
    PULSE 1500 400 100 10
    ```

### 2.4 Rule 4: Schedule Block

Wrap complex commands into a logical block and repeat the entire block as a unit. This is suitable for designing complex operating cycles that mix short pulses, long pulses, and long shutdowns.

* **Syntax**: `BEGIN_SCHEDULE` ... `END_SCHEDULE` + `REPEAT <n>`
* **Example**:
    ```text
    BEGIN_SCHEDULE
        PULSE 1500 400 100 5    # first run 5 standard short pulses
        DWELL 3600              # major shutdown for 1 hour of wall conditioning
        POWER 1000
        BURN 7200               # reduced-power long pulse for 2 hours
    END_SCHEDULE
    REPEAT 3                  # repeat the entire plan 3 times
    ```

---

## 3. Core Interaction Mechanism: Coupling in the Time Domain

During simulation, the **FOC schedule duration** and the **Modelica solver global duration (`Stop Time`)** operate independently. They must be set properly to capture the full physical process:

1. **Forced truncation**: `Stop Time < FOC duration`. The solver terminates early. This is suitable for debugging early pulse responses.
2. **Wash-out and drain-down effect**: `Stop Time > FOC duration`. (**Recommended**) After all operating scenarios defined by the FOC have finished, the source term drops to zero. The solver then continues advancing, and tanks inside the model, such as CPS, I_ISS, and TEP, empty according to exponential decay governed by their own residence time $T$ and differential equations. This is the standard way to assess tritium retention and shutdown maintenance safety margin.

---

## 4. Python Compilation Middleware (`foc_compiler.py`)

This middleware is responsible for parsing `.foc` files, expanding macro commands, and generating the low-level data structures required by the Modelica model.

```python
import re
import pandas as pd

def parse_foc_file(filepath):
        """Parse an FOC config file and return amplitudes and durations arrays."""
        amplitudes, durations = [], []
        current_power = 0.0
        in_schedule = False
        schedule_amps, schedule_durs = [], []

        with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

        for line in lines:
                line = line.split('#')[0].strip()
                if not line:
                        continue
                parts = line.split()
                cmd = parts[0].upper()

                def append_step(amp, dur):
                        if in_schedule:
                                schedule_amps.append(amp)
                                schedule_durs.append(dur)
                        else:
                                amplitudes.append(amp)
                                durations.append(dur)

                if cmd == 'POWER':
                        current_power = float(parts[1])
                elif cmd == 'BURN':
                        append_step(current_power, float(parts[1]))
                elif cmd == 'DWELL':
                        append_step(0.0, float(parts[1]))
                elif cmd == 'PULSE':
                        p_power, p_burn, p_dwell, p_cycles = map(float, parts[1:5])
                        for _ in range(int(p_cycles)):
                                append_step(p_power, p_burn)
                                append_step(0.0, p_dwell)
                elif cmd == 'BEGIN_SCHEDULE':
                        in_schedule = True
                        schedule_amps.clear()
                        schedule_durs.clear()
                elif cmd == 'END_SCHEDULE':
                        in_schedule = False
                elif cmd == 'REPEAT':
                        repeats = int(parts[1])
                        for _ in range(repeats):
                                amplitudes.extend(schedule_amps)
                                durations.extend(schedule_durs)

        return amplitudes, durations

def export_for_modelica(amplitudes, durations):
        """Export as Modelica arrays (Scheme A)."""
        amps_str = ", ".join([str(a) for a in amplitudes])
        durs_str = ", ".join([str(d) for d in durations])
        print(f"parameter Real amplitudes[:] = {{{amps_str}}};")
        print(f"parameter Real durations[:] = {{{durs_str}}};")

def export_for_combitimetable(amplitudes, durations, filename="foc_table.txt"):
        """Export as a CombiTimeTable driving file (Scheme B)."""
        time_col = [0.0]
        power_col = [amplitudes[0]]
        current_time = 0.0

        for i in range(len(durations)):
                current_time += durations[i]
                time_col.append(current_time)
                power_col.append(amplitudes[i])
                # build a step-after staircase
                if i < len(durations) - 1:
                        time_col.append(current_time)
                        power_col.append(amplitudes[i + 1])

        df = pd.DataFrame({'time': time_col, 'power': power_col})
        with open(filename, 'w') as f:
                f.write(f"#1\nfloat FOC_Data({len(time_col)}, 2)\n")
                df.to_csv(f, sep='\t', index=False, header=False)
```

---

## 5. Modelica Integration Schemes

To match TRICYS platform integration needs, two implementation paths are provided. Both complete the conversion from **power (MW) to consumption rate (g/h)** inside the component using the factor $6.3935 \times 10^{-3}$, and both use left-right bidirectional ports to optimize topology wiring.

### Scheme A: Array-Injected Mode (Embedded Configuration)

Use Modelica's automatic array-size inference capability (`[:]`). This is suitable when the number of schedule steps is small. It has no external file dependency and can be updated directly at the code level.

```modelica
block FOC_ArrayPulse
    "Discrete pulse source based on FOC array configuration"
    parameter Real conversion_factor = 6.3935 * 1e-3 "Tritium consumption rate (g/h) corresponding to 1 MW";

    // Data injected by Python
    parameter Real amplitudes[:] = {1500, 0, 1500, 0};
    parameter Real durations[:] = {400, 100, 400, 100};

    Modelica.Blocks.Interfaces.RealOutput y1 annotation(Placement(transformation(origin={110,0}, rotation=180)));
    Modelica.Blocks.Interfaces.RealOutput y2 annotation(Placement(transformation(origin={110,0})));

protected
    parameter Integer n_steps = size(amplitudes, 1);
    parameter Real cumulative_times[n_steps + 1] = cat(1, {0}, sumSequence(durations));
    Real current_power;

    function sumSequence ... end sumSequence; // cumulative-sum helper

equation
    current_power = 0;
    for i in 1:n_steps loop
        if time >= cumulative_times[i] and time < cumulative_times[i + 1] then
            current_power = amplitudes[i];
        end if;
    end for;

    y1 = current_power * conversion_factor;
    y2 = y1;
end FOC_ArrayPulse;
```

### Scheme B: External Data Table Driven Mode (Recommended)

Use the `CombiTimeTable` component. This scheme offers excellent numerical stability when handling pulse sequences with thousands of cycles. The solver can step directly against the linear interpolation matrix, making this the preferred practice for long-term simulation of large loops.

```modelica
block FOC_TablePulse
    "Pulse source driven by an external FOC table"
    parameter Real conversion_factor = 6.3935 * 1e-3 "Tritium consumption rate (g/h) corresponding to 1 MW";
    parameter String fileName = "foc_table.txt" "Path to the table file generated by Python";

    Modelica.Blocks.Interfaces.RealOutput y1 annotation(Placement(transformation(origin={-110,0}, rotation=180)));
    Modelica.Blocks.Interfaces.RealOutput y2 annotation(Placement(transformation(origin={110,0})));

protected
    Modelica.Blocks.Sources.CombiTimeTable table(
        tableOnFile = true,
        tableName = "FOC_Data",
        fileName = fileName,
        extrapolation = Modelica.Blocks.Types.Extrapolation.HoldLastPoint, // automatically return to zero after schedule timeout (HoldLastPoint preserves drain-down)
        smoothness = Modelica.Blocks.Types.Smoothness.LinearSegments       // together with Python stair-step data, forms an ideal square wave
    );

equation
    y1 = table.y[1] * conversion_factor;
    y2 = y1;
end FOC_TablePulse;
```

---

## 6. Standard Automated Integration Workflow for Fusion Fuel-Cycle Simulation

### 6.1 Workflow Overview

This workflow uses the Python middleware as the core orchestrator to automate the full pipeline, from high-level operating-scenario description through FOC scripts, to Modelica topology modification, and finally to simulation execution in a high-performance computing (HPC) environment.

---

### 6.2 Standard Workflow in Detail

#### 6.2.1 Step 1: Define the Operating Scenario (FOC Scripting)

* **Action**: researchers write `.foc` text files and use semantic commands such as `POWER`, `BURN`, `PULSE`, and `SCHEDULE` to define experimental operating scenarios.
* **Design objective**: fully decouple operating scenarios from model logic while ensuring experiment traceability and version control.

#### 6.2.2 Step 2: Data Compilation and Component Generation

* **Action**: the Python parser reads the `.foc` file and performs the following tasks:
        1. **Physical conversion**: convert thermal power (MW) into tritium/deuterium consumption mass flow (g/h) accepted by the system.
        2. **Data export**: generate the Modelica array snippet for Scheme A, or an external HDF5/CSV configuration file for Scheme B.
        3. **Instantiation**: generate a complete `FOC_Pulse.mo` component definition file, ready to be injected into the system.

#### 6.2.3 Step 3: Parse the Original Cycle Model and Locate the Component

* **Action**: use regular expressions or a Modelica abstract syntax tree (AST) parser to read the top-level `Cycle.mo` model file.
* **Location logic**: search the model declaration section for an instance whose type is `Modelica.Blocks.Sources.Pulse` or a custom `Pulse` class, such as `pulseSource`.
* **Context acquisition**: record the component coordinates in the `Diagram` annotation (`Placement`) and the associated `connect` statements.

#### 6.2.4 Step 4: Automated Replacement Logic

* **Action**: perform text-based or structured replacement on `Cycle.mo` in memory.
* **Lossless replacement principles**:
        1. **Type substitution**: replace `Pulse pulseSource(...)` with `FOC_Pulse pulseSource(...)`.
        2. **Attribute migration**: fill the newly generated arrays or file path into the instance parameters.
        3. **Connection preservation**: keep the original `connect(pulseSource.y, ...)` statements unchanged. Since the new component preserves a fully compatible port definition, the wiring topology remains seamless.

#### 6.2.5 Step 5: Run the Simulation and Collect Results

* **Action**: trigger the simulation through `OMPython`, the OpenModelica Python interface.
* **Key configuration points**:
        1. **Dynamic duration setting**: automatically compute and set simulation `stopTime` based on the total duration of the FOC script, with an additional 5 to 10 hours of drain-down time recommended.
        2. **Solver configuration**: specify the `DASSL` or `CVODE` solver and its tolerances.
        3. **Result export**: after simulation completes, automatically extract curve data from key nodes, such as SDS inventory and WDS purification rate, and generate visualization reports.