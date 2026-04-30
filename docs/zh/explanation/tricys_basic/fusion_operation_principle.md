# FOC 架构设计与实现报告

## 1. 概述与核心理念

在聚变堆系统级动态宏观仿真中，燃料循环系统（如排气 TEP、同位素分离 ISS、水去氚 WDS 等）的瞬态响应高度依赖于等离子体燃烧和包层增殖的源项输入。传统的“原生方波/脉冲发生器”存在物理语义缺失、复杂工况难定义、以及容易引发求解器时间事件密集等问题。

**FOC (Fusion Operation Config)** 架构旨在彻底解耦“工况定义”与“模型执行”。其核心理念包括：
1. **物理语义化**：以“热功率 (MW)”为顶层输入，由系统自动完成向“质量流 (g/h)”的硬核物理换算。
2. **数据驱动**：采用极简的领域特定语言 (DSL) 描述工况，通过 Python 编译为 Modelica 可识别的数组或时间表数据集。
3. **消除状态事件**：在底层利用无状态逻辑或线性插值表格，极大提高长周期（月/年级）复杂仿真的求解效率与数值稳定性。

---

## 2. FOC 语法设计规范

FOC 采用基于文本指令的轻量级语法，默认约定为：**热功率为 MW，时间为 秒 (s)**。注释以 `#` 开头。FOC 支持以下四种核心运行规则的任意组合。

如果目标 Modelica 模型的时间基准不是秒，或者希望显式声明 FOC 文件当前使用的时间单位，可以在 FOC 文件顶部增加时间头指令：

```text
TIME_UNIT <second|hour|day|week|year>
TIME_CONVERSION <factor>
TIME_CONVERSION <source_unit>_to_<target_unit>
```

其中：

- 当 `TIME_UNIT` 与 `TIME_CONVERSION` 都未出现时，默认认为 FOC 中时间单位为秒，且不做任何时间转换
- `TIME_UNIT <unit>` 仅用于显式声明当前 FOC 文件中的时间单位，本身不触发任何时间换算，例如 `TIME_UNIT hour` 只表示后续时间值按小时理解
- `TIME_CONVERSION NONE` 表示不做时间换算，直接使用 FOC 中写入的时间值
- `TIME_CONVERSION 3600` 表示把 FOC 中的时间统一乘以 `3600` 后再送入模型
- `TIME_CONVERSION second_to_hour` 表示把 FOC 中以秒写入的时间转换为模型所需的小时单位；同理也支持 `hour_to_second` 等命名转换；当前支持 `second/hour/day/week/year` 之间的命名转换
- 只有显式出现 `TIME_CONVERSION` 时程序才会执行时间转换，避免出现隐式转换
- 当同时声明 `TIME_UNIT` 和命名式 `TIME_CONVERSION` 时，二者的起始单位必须一致，例如 `TIME_UNIT second` 搭配 `TIME_CONVERSION second_to_hour`
- 这些头指令必须写在所有 `POWER`、`BURN`、`DWELL`、`PULSE`、`BEGIN_SCHEDULE` 等业务指令之前，且各自只能声明一次

因此，针对“模型内部默认时间单位为秒，而 FOC 希望按小时编写并显式转换到秒”的场景，可以写成：

```text
TIME_UNIT hour
TIME_CONVERSION hour_to_second
POWER 1500
BURN 10
```

而如果只是希望声明“当前 FOC 以小时书写，但暂不做任何时间转换”，则可以写成：

```text
TIME_UNIT hour
POWER 1500
BURN 10
```

针对“FOC 以秒编写，但模型内部时间单位为小时”的场景，可以写成：

```text
TIME_CONVERSION second_to_hour
POWER 1500
BURN 7200
```

如果只希望显式声明不做转换，也可以写成：

```text
TIME_CONVERSION NONE
POWER 1500
BURN 10
```

### 2.1 规则 1：单段连续运行 (Continuous Burn)
设定恒定热功率基准，维持指定时长。
* **语法**：`POWER <value>` + `BURN <time>`
* **说明**：仅当顶部显式声明 `TIME_CONVERSION` 时，`<time>` 才会乘以对应换算系数；否则直接按原值使用
* **示例**：
  ```text
  POWER 1500
  BURN 36000  # 1500 MW 连续燃烧 10 小时
  ```

### 2.2 规则 2：多段运行与驻留 (Step & Dwell)
在不同功率段之间插入零功率的驻留期（停堆排气阶段）。
* **语法**：`DWELL <time>`
* **说明**：仅当顶部显式声明 `TIME_CONVERSION` 时，`<time>` 才会乘以对应换算系数；否则直接按原值使用
* **示例**：
  ```text
  POWER 1500
  BURN 7200
  DWELL 3600  # 强制零功率，系统进行停堆排空
  POWER 2000
  BURN 7200
  ```

### 2.3 规则 3：脉冲式运行 (Pulsed Operation)
快速生成高频重复的托卡马克脉冲宏序列。
* **语法**：`PULSE <power> <burn_time> <dwell_time> <cycles>`
* **说明**：仅当顶部显式声明 `TIME_CONVERSION` 时，`<burn_time>` 与 `<dwell_time>` 才会乘以对应换算系数；否则直接按原值使用
* **示例**：
  ```text
  # 1500MW 功率，燃烧 400s，停机排气 100s，循环执行 10 次
  PULSE 1500 400 100 10
  ```

### 2.4 规则 4：调度计划块 (Schedule Block)
将复杂指令打包成逻辑块，进行整体循环，适用于设计混合了长短脉冲和长停机的复杂运行周期。
* **语法**：`BEGIN_SCHEDULE` ... `END_SCHEDULE` + `REPEAT <n>`
* **示例**：
  ```text
  BEGIN_SCHEDULE
    PULSE 1500 400 100 5    # 先执行5个标准短脉冲
    DWELL 3600              # 大停机 1 小时进行壁处理
    POWER 1000
    BURN 7200               # 降功率长脉冲 2 小时
  END_SCHEDULE
  REPEAT 3                  # 将上述整个计划重复 3 遍
  ```

---

## 3. 核心交互机制：时间域耦合

在仿真执行时，**FOC 工况时长**与 **Modelica 求解器全局时长 (`Stop Time`)** 是独立运作的。必须合理设置以捕获完整的物理过程：

1. **强行截断**：`Stop Time < FOC时长`。求解器提前终止，适用于调试前期脉冲响应。
2. **尾迹与排空效应 (Wash-out)**：`Stop Time > FOC时长`。（**推荐做法**）当 FOC 定义的所有工况执行完毕后，源项归零。此时求解器继续推进，模型中的储罐（如 CPS、I_ISS、TEP）将基于自身的滞留时间 $T$ 和微分方程呈现指数衰减规律排空。这是评估氚滞留和停机维护安全裕度的标准方法。

---

## 4. Python 编译中间件 (`foc_compiler.py`)

该中间件负责解析 `.foc` 文件，展开宏指令，并生成 Modelica 模型所需的底层数据结构。

```python
import re
import pandas as pd

def parse_foc_file(filepath):
    """解析 FOC 配置文件，返回 amplitudes 和 durations 数组"""
    amplitudes, durations = [], []
    current_power = 0.0
    in_schedule = False
    schedule_amps, schedule_durs = [], []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for line in lines:
        line = line.split('#')[0].strip()
        if not line: continue
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
    """输出为 Modelica 数组（对应方案 A）"""
    amps_str = ", ".join([str(a) for a in amplitudes])
    durs_str = ", ".join([str(d) for d in durations])
    print(f"parameter Real amplitudes[:] = {{{amps_str}}};")
    print(f"parameter Real durations[:] = {{{durs_str}}};")

def export_for_combitimetable(amplitudes, durations, filename="foc_table.txt"):
    """输出为 CombiTimeTable 驱动文件（对应方案 B）"""
    time_col = [0.0]
    power_col = [amplitudes[0]]
    current_time = 0.0
    
    for i in range(len(durations)):
        current_time += durations[i]
        time_col.append(current_time)
        power_col.append(amplitudes[i])
        # 形成阶梯状 (Step-after)
        if i < len(durations) - 1:
            time_col.append(current_time)
            power_col.append(amplitudes[i+1])
            
    df = pd.DataFrame({'time': time_col, 'power': power_col})
    with open(filename, 'w') as f:
        f.write(f"#1\nfloat FOC_Data({len(time_col)}, 2)\n")
        df.to_csv(f, sep='\t', index=False, header=False)
```

---

## 5. Modelica 模型集成方案

根据 TRICYS 平台的集成需求，提供以下两种实现路径，二者均在组件内部完成了 **功率(MW) 到 消耗率(g/h)** 的转换（系数 $6.3935 \times 10^{-3}$），并采用左右双向端口以优化拓扑连线。

### 方案 A：数组写入型（内化配置）
利用 Modelica 的数组尺寸自动推导特性（`[:]`）。适用于工况步数较少的场景，无需外部依赖，直接在代码级更新。

```modelica
block FOC_ArrayPulse
  "基于 FOC 数组配置的离散脉冲源"
  parameter Real conversion_factor = 6.3935 * 1e-3 "1MW 对应的氚消耗率(g/h)";
  
  // 由 Python 注入的数据
  parameter Real amplitudes[:] = {1500, 0, 1500, 0};
  parameter Real durations[:] = {400, 100, 400, 100};
  
  Modelica.Blocks.Interfaces.RealOutput y1 annotation(Placement(transformation(origin={110,0}, rotation=180)));
  Modelica.Blocks.Interfaces.RealOutput y2 annotation(Placement(transformation(origin={110,0})));

protected
  parameter Integer n_steps = size(amplitudes, 1);
  parameter Real cumulative_times[n_steps + 1] = cat(1, {0}, sumSequence(durations));
  Real current_power;
  
  function sumSequence ... end sumSequence; // 累加函数定义

equation
  current_power = 0; 
  for i in 1:n_steps loop
    if time >= cumulative_times[i] and time < cumulative_times[i+1] then
      current_power = amplitudes[i];
    end if;
  end for;
  
  y1 = current_power * conversion_factor;
  y2 = y1;
end FOC_ArrayPulse;
```

### 方案 B：外部数据表驱动型（推荐方案）
利用 `CombiTimeTable` 组件。该方案在处理上千个周期的脉冲序列时，数值稳定性极高，求解器可直接根据线性插值矩阵进行跨步，是大型环路长期仿真的最佳实践。

```modelica
block FOC_TablePulse
  "基于外部 FOC 表格驱动的脉冲源"
  parameter Real conversion_factor = 6.3935 * 1e-3 "1MW 对应的氚消耗率(g/h)";
  parameter String fileName = "foc_table.txt" "Python生成的表格文件路径";
  
  Modelica.Blocks.Interfaces.RealOutput y1 annotation(Placement(transformation(origin={-110,0}, rotation=180)));
  Modelica.Blocks.Interfaces.RealOutput y2 annotation(Placement(transformation(origin={110,0})));

protected
  Modelica.Blocks.Sources.CombiTimeTable table(
    tableOnFile = true,
    tableName = "FOC_Data",
    fileName = fileName,
    extrapolation = Modelica.Blocks.Types.Extrapolation.HoldLastPoint, // 仿真超时后自动归零(HoldLastPoint保持排空)
    smoothness = Modelica.Blocks.Types.Smoothness.LinearSegments       // 配合Python的阶梯数据形成完美方波
  );

equation
  y1 = table.y[1] * conversion_factor;
  y2 = y1;
end FOC_TablePulse;
```

---

## 6. 聚变堆燃料循环仿真自动化集成标准工作流

### 6.1 流程概述
本工作流通过 Python 中间件作为核心调度器，实现从高层工况描述（FOC 脚本）到 Modelica 模型拓扑修改，再到高性能计算（HPC）环境下的仿真执行全过程自动化。

---

### 6.2 标准工作流详述

#### 6.2.1 步骤 1：定义工况 (FOC Scripting)
* **操作内容**：研究人员编写 `.foc` 格式的文本文件，利用 `POWER`, `BURN`, `PULSE`, `SCHEDULE` 等语义化指令定义实验工况。
* **设计目标**：实现工况与模型逻辑的完全解耦，确保实验方案的可追溯性和版本控制。

#### 6.2.2 步骤 2：数据编译与组件生成 (Data Compilation)
* **操作内容**：Python 解析器读取 `.foc` 文件，执行以下任务：
    1.  **物理转换**：将热功率（MW）转换为系统可接受的氚/氘消耗质量流（g/h）。
    2.  **数据输出**：生成方案 A 的 Modelica 数组代码段，或方案 B 的外部 HDF5/CSV 配置文件。
    3.  **实例化**：生成一个完整的 `FOC_Pulse.mo` 组件定义文件，准备注入系统。

#### 6.2.3 步骤 3：解析原 Cycle 模型与组件定位 (Model Parsing)
* **操作内容**：利用正则表达式或 Modelica 抽象语法树（AST）解析工具读取 `Cycle.mo` 顶层模型文件。
* **定位逻辑**：搜索模型声明段，寻找类型为 `Modelica.Blocks.Sources.Pulse` 或自定义 `Pulse` 类的实例名（如 `pulseSource`）。
* **获取上下文**：记录该组件在 `Diagram` 注解中的坐标（`Placement`）以及与之关联的 `connect` 连线语句。

#### 6.2.4 步骤 4：自动化替换逻辑 (Automated Replacement)
* **操作内容**：在内存中对 `Cycle.mo` 进行文本或结构化替换。
* **无损替换原则**：
    1.  **类型变更**：将 `Pulse pulseSource(...)` 替换为 `FOC_Pulse pulseSource(...)`。
    2.  **属性迁移**：将新生成的数组或文件路径填入实例参数。
    3.  **连接保持**：确保原有的 `connect(pulseSource.y, ...)` 语句保持不变。由于新组件采用了完全兼容的端口定义，连线拓扑将实现无缝衔接。

#### 6.2.5 步骤 5：执行仿真与数据回收 (Simulation Execution)
* **操作内容**：通过 `OMPython` (OpenModelica Python 接口) 触发仿真任务。
* **关键配置**：
    1.  **动态时长设定**：自动根据 FOC 脚本的总时长，计算并设置仿真 `stopTime`（建议增加 5-10 小时的排空期）。
    2.  **求解器配置**：指定 `DASSL` 或 `CVODE` 求解器及容差。
    3.  **结果导出**：仿真完成后，自动提取关键节点（如 SDS 库存、WDS 净化率）的曲线数据，生成可视化报告。

