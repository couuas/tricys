# P2: 约束型缓冲组件 — 容量上限与处理速率约束

## 背景与目标

- **问题/需求描述**：tricys 现有 Modelica 子系统模型（Blanket、TES、SDS 等）不具备运行时约束能力——盘存量可无限增长，出流速率与盘存量成线性关系无上限。实际聚变装置的每个子系统都有明确的物理容量上限（如 SDS 最大盘存 500 g）和处理速率上限（如 TES 最大吞吐 20 g/h）。缺少这些约束导致仿真结果可能出现非物理的无限累积，且无法进行安全裕度分析。
- **目标**：
  1. 实现一个通用的 `ConstrainedBuffer` Modelica 组件，支持容量上限 (`capacity_max`) 和速率上限 (`rate_max`) 两种约束
  2. 超限部分通过 `overflow` / `rate_clip` 端口导出（质量守恒）
  3. 组件参数可通过 tricys JSON 配置的 `simulation_parameters` 注入和扫描
  4. 提供独立验证用例（含 Cycle 集成测试配置），确认约束行为符合预期
  5. 更新文档说明约束组件用法
- **非目标（不做什么）**：
  - 不修改现有 Blanket/TES/SDS 等组件源码 — 新组件为独立新增
  - 不修改 tricys Python 核心层（`jobs.py`, `simulation.py`）— 参数注入机制已天然支持新 `parameter Real`
  - 不在本 PR 中实现自动约束检测/告警后处理 — 那是后续功能
  - 不实现动态约束（运行中改变 capacity_max）— 本期仅支持编译期常量参数
- **已有代码/流程复用分析**：
  - `TES.mo` 的 `threshold` + `I_total` 判定逻辑：**复用**设计模式（总量判定→分流），扩展为双向约束
  - `Blanket.mo` 的 `outflow = I/T` + 分流比例：**复用**作为基础出流公式
  - `parameter_sweep.json` 的 dotted-path 注入：**复用**，新组件参数直接兼容
  - `package.order` 注册机制：**复用**

## 技术方案

- **方案概述**：
  在 `example_model/` 包中新增 `ConstrainedBuffer.mo` 组件，采用 sigmoid 软约束（可退化为硬约束），并新增一个 `Cycle_Constrained.mo` 顶层模型作为验证用例。通过专门的 JSON 配置文件驱动参数扫描验证。

- **关键设计决策**：
  1. **软约束 vs 硬约束**：默认使用 sigmoid 平滑（`softness=0.02`）避免 DASSL 求解器频繁事件切换；`softness=0` 退化为硬 `min/if`
  2. **容量约束方向**：约束 `sum(I)`（总氚当量），非逐同位素分别约束——物理上容量限制是总量级别的
  3. **速率约束方向**：约束 `sum(outflow)`（总出流），而非逐通道
  4. **守恒处理**：超容量的入流转 `overflow_out` 端口；超速率的出流差额转 `rate_clip_out` 端口。任何质量都不凭空消失
  5. **默认值 1e9**：未设约束时等价于无约束，向后兼容

- **影响范围**：
  - 新增：`tricys/example/example_data/example_model/ConstrainedBuffer.mo`
  - 新增：`tricys/example/example_data/example_model/Cycle_Constrained.mo`
  - 修改：`tricys/example/example_data/example_model/package.order`（追加 2 行）
  - 新增：`tricys/example/example_data/basic/6_constrained_buffer/constrained_buffer.json`
  - 新增：`tricys/example/example_data/basic/6_constrained_buffer/constrained_buffer_sweep.json`
  - 新增：`test/core/test_constrained_buffer.py`（pytest 测试）
  - 修改：`docs/zh/questions/advanced_features.md`（追加 FAQ 条目）
  - 修改：`docs/en/questions/advanced_features.md`（追加 FAQ 条目）

## Error & Rescue Map（关键失败路径映射）

| 代码路径/操作 | 可能的失败 | 错误类型 | 已处理？ | 处理方式 | 用户可见行为 |
|-------------|-----------|---------|---------|---------|------------|
| sigmoid 公式 `1/(1+exp(...))` | `softness*capacity_max` 为 0 → 除零 | 数值异常 | Y | 公式中加 `+1e-30` 保护 | — |
| 硬约束 `if I_total >= capacity_max` | 事件风暴导致 DASSL 不收敛 | SimulationError | Y | 文档建议用 `softness≥0.01`；测试中用 `softness=0` 验证上界 | 仿真失败日志 |
| `rate_max` 设得过小 | 盘存量持续增长突破 `capacity_max` | 物理不一致 | Y | 两个约束同时生效——超速率时入流也被限制在出流能力内 | overflow 端口非零 |
| 连接 overflow_out 到 SDS | SDS `from_*` 端口命名不匹配 | 编译错误 | Y | Cycle_Constrained.mo 中使用新端口变量，不修改 SDS 接口 | — |
| `sum(I)` 在全 0 初始化时 | 除法 `threshold/I_total` 中 `I_total=0` | 除零 | Y | 本组件不用 `threshold/I_total` 模式，改用 sigmoid | — |

## 执行计划

### Phase 1: 分支创建与 Modelica 组件开发

#### ✅ Task 1.1: 创建特性分支
- **目标**：从 `main` 创建 `feature/constrained-buffer` 分支
- **依赖**：无
- **修改内容**：
  - `git checkout main && git pull && git checkout -b feature/constrained-buffer`
- **修改边界**：仅 git 操作，不修改任何文件
- **测试要求**：
  - 运行 `git branch --show-current` → 输出 `feature/constrained-buffer`
- **验收标准**：
  - ✅ 当前分支为 `feature/constrained-buffer`
  - ✅ 分支基于最新 `main` 创建
- **潜在风险**：当前工作区有未提交修改 → 先 stash

#### ✅ Task 1.2: 创建 ConstrainedBuffer.mo 组件
- **目标**：实现带容量/速率约束的通用缓冲组件
- **依赖**：T1.1
- **修改内容**：
  - 新建 `tricys/example/example_data/example_model/ConstrainedBuffer.mo`
  - 组件结构：
    - 参数：`T`, `capacity_max`, `rate_max`, `softness`, `decay_loss[5]`, `nonradio_loss[5]`, `to_Down_Fraction`
    - 端口：`from_Upstream[5]`(RealInput), `from_Recycle[5]`(RealInput), `to_Downstream[5]`(RealOutput), `overflow_out[5]`(RealOutput), `rate_clip_out[5]`(RealOutput)
    - 状态变量：`I[5]`, `I_total`, `outflow_nominal[5]`, `outflow[5]`, `rate_scale`, `admit_scale`
    - 方程逻辑：sigmoid 软约束，容量→限入流，速率→限出流
- **修改边界**：不修改任何现有 .mo 文件
- **测试要求**：
  - 用 OMPython 加载包并执行 `checkModel("example_model.ConstrainedBuffer")` → 返回无错误
- **验收标准**：
  - ✅ `checkModel` 通过，无编译错误
  - ✅ 参数默认值 capacity_max=1e9, rate_max=1e9 时行为退化为标准 `I/T` 出流
  - ✅ 5-同位素向量约定与现有组件一致（`RealInput[5]`/`RealOutput[5]`）
- **潜在风险**：sigmoid 公式中除零保护不够 → 确保 `+1e-30` 在所有分母

#### ✅ Task 1.3: 注册组件到 package
- **目标**：将新组件注册到 Modelica 包中
- **依赖**：T1.2
- **修改内容**：
  - 编辑 `tricys/example/example_data/example_model/package.order`：追加 `ConstrainedBuffer` 和 `Cycle_Constrained`
- **修改边界**：仅修改 `package.order`，不修改 `package.mo`
- **测试要求**：
  - OMPython `loadFile("package.mo")` 后 `getClassNames()` 包含 `ConstrainedBuffer`
- **验收标准**：
  - ✅ `package.order` 包含 `ConstrainedBuffer` 行
  - ✅ `package.order` 包含 `Cycle_Constrained` 行
  - ✅ 加载包无报错
- **潜在风险**：行尾需确保无多余空格/BOM

### Phase 2: 集成验证模型与测试配置

#### ✅ Task 2.1: 创建 Cycle_Constrained.mo 顶层模型
- **目标**：用 ConstrainedBuffer 替换原 Blanket 作为包层子系统，构建可运行的集成模型
- **依赖**：T1.3
- **修改内容**：
  - 新建 `tricys/example/example_data/example_model/Cycle_Constrained.mo`
  - 基于现有 `Cycle.mo` 复制，将 `Blanket blanket` 替换为 `ConstrainedBuffer blanket_c`
  - 调整 connect 语句：`blanket.to_CL` → `blanket_c.to_Downstream`, `blanket.to_TES` → 保留（通过 `to_Down_Fraction` 分流）
  - `overflow_out` 连接到新增的 `Modelica.Blocks.Sources.Constant zero_recycle[5](each k=0)` 占位（或直接接地）
  - `from_Recycle` 连接到 `tes.to_BZ`（替代原 `blanket.from_TES`）
- **修改边界**：不修改 `Cycle.mo`；新文件独立存在
- **测试要求**：
  - `checkModel("example_model.Cycle_Constrained")` 通过
  - 使用 `basic_configuration.json` 的等效配置（model_name 改为 Cycle_Constrained）仿真 2000h 成功完成
- **验收标准**：
  - ✅ 仿真完成无 crash
  - ✅ 当 `capacity_max=1e9, rate_max=1e9` 时，`blanket_c.I[1]` 曲线与原 `Cycle.mo` 的 `blanket.I[1]` 偏差 < 1%
  - ✅ overflow_out 在无约束时全程为 0
- **潜在风险**：connect 拓扑改变后求解初始条件可能不同 → 对比初始瞬态后 t>100h 的稳态值

#### ✅ Task 2.2: 创建验证用 JSON 配置
- **目标**：编写 tricys 配置文件验证约束行为
- **依赖**：T2.1
- **修改内容**：
  - 新建 `tricys/example/example_data/basic/6_constrained_buffer/constrained_buffer.json`：
    ```json
    {
      "paths": { "package_path": "../../example_model/package.mo" },
      "simulation": {
        "model_name": "example_model.Cycle_Constrained",
        "variableFilter": "time|blanket_c.I\\[1\\]|blanket_c.I_total|blanket_c.overflow_out\\[1\\]|blanket_c.rate_clip_out\\[1\\]|blanket_c.outflow\\[1\\]",
        "stop_time": 5000.0,
        "step_size": 1.0
      },
      "simulation_parameters": {
        "blanket_c.capacity_max": 500,
        "blanket_c.rate_max": 50
      }
    }
    ```
  - 新建 `constrained_buffer_sweep.json`：对 capacity_max 和 rate_max 做参数扫描
    ```json
    {
      "paths": { "package_path": "../../example_model/package.mo" },
      "simulation": {
        "model_name": "example_model.Cycle_Constrained",
        "variableFilter": "time|blanket_c.I\\[1\\]|blanket_c.I_total|blanket_c.overflow_out\\[1\\]|blanket_c.rate_clip_out\\[1\\]",
        "stop_time": 5000.0,
        "step_size": 1.0
      },
      "simulation_parameters": {
        "blanket_c.capacity_max": [200, 500, 1000, 2000],
        "blanket_c.rate_max": [20, 50, 100, 1e9]
      }
    }
    ```
- **修改边界**：仅在 `6_constrained_buffer/` 目录下新建文件
- **测试要求**：
  - `tricys basic -c constrained_buffer.json` 运行成功
  - 结果中 `blanket_c.I_total` 不超过 `capacity_max` + softness 裕度 (< 525 g when cap=500)
  - `blanket_c.overflow_out[1]` 在 `I_total` 接近 500g 时 > 0
- **验收标准**：
  - ✅ 单点仿真完成无报错
  - ✅ 参数扫描（4×4=16 job）全部完成
  - ✅ 容量约束生效：peak `I_total` ≤ `capacity_max * (1 + 2*softness)`
  - ✅ 速率约束生效：peak `sum(outflow)` ≤ `rate_max * (1 + 2*softness)`
- **潜在风险**：`variableFilter` 正则转义需双反斜杠（JSON 中 `\\[`）

#### ✅ Task 2.3: 编写 pytest 自动化验证
- **目标**：确保 CI 中约束行为可回归验证
- **依赖**：T2.2
- **修改内容**：
  - 新建 `test/core/test_constrained_buffer.py`
  - 测试用例：
    1. `test_no_constraint_matches_baseline`：cap=1e9, rate=1e9 → 结果与 Cycle.mo 基线偏差 < 1%
    2. `test_capacity_constraint_effective`：cap=500 → peak I_total ≤ 525
    3. `test_rate_constraint_effective`：rate=50 → peak outflow ≤ 52.5
    4. `test_mass_conservation`：∫(inflow) ≈ ∫(outflow + overflow + rate_clip) + ΔI + ∫(decay)，误差 < 0.1%
    5. `test_softness_zero_hard_constraint`：softness=0 → peak I_total ≤ cap（可标记 slow）
  - 标记 `@pytest.mark.slow`（依赖 OpenModelica 环境）
- **修改边界**：不修改 `test/` 下现有文件
- **测试要求**：
  - `pytest test/core/test_constrained_buffer.py -v` 全部通过（需 OM 环境）
- **验收标准**：
  - ✅ 5 个测试用例全部 PASS
  - ✅ 质量守恒验证误差 < 0.1%
- **潜在风险**：CI 环境可能无 OpenModelica → 用 `@pytest.mark.slow` 允许 skip

### Phase 3: 文档更新

#### ✅ Task 3.1: 更新中英文 FAQ 文档
- **目标**：为用户提供约束组件使用说明
- **依赖**：T2.2
- **修改内容**：
  - 编辑 `docs/zh/questions/advanced_features.md`：在末尾追加 FAQ 条目
    ```markdown
    ??? question "问：如何为子系统设置最大盘存量和最大处理速率？"
        使用 `ConstrainedBuffer` 组件替换标准子系统...
    ```
  - 编辑 `docs/en/questions/advanced_features.md`：追加对应英文 FAQ
- **修改边界**：仅追加内容，不修改现有 FAQ 条目
- **测试要求**：
  - `mkdocs build` 无报错（如配置了 mkdocs）
- **验收标准**：
  - ✅ 中文 FAQ 包含约束组件使用示例（含 JSON 配置片段）
  - ✅ 英文 FAQ 包含对应内容
  - ✅ 文档中参数名与 .mo 文件一致
- **潜在风险**：mkdocs 的 admonition 语法缩进必须严格 4 空格

## Execution Wave（并行执行波次）

| Wave | 可并行 Task | 依赖已完成 |
|------|------------|------------|
| W1 | T1.1 | — |
| W2 | T1.2 | W1 |
| W3 | T1.3 | W2 |
| W4 | T2.1, T2.2 (JSON 文件可预写) | W3 |
| W5 | T2.3, T3.1 | W4 |

> Task Executor 按 Wave 顺序实施：同一 Wave 内的 Task 可并行或任意顺序执行，跨 Wave 必须等待前序 Wave 全部完成。

## 回归检查清单
- [ ] `checkModel("example_model.ConstrainedBuffer")` 通过
- [ ] `checkModel("example_model.Cycle_Constrained")` 通过
- [ ] 原有 `Cycle.mo` 未被修改（`git diff main -- tricys/example/example_data/example_model/Cycle.mo` 为空）
- [ ] `tricys basic -c constrained_buffer.json` 完成无错误
- [ ] 16-job 参数扫描全部完成
- [ ] `pytest test/core/test_constrained_buffer.py -v` 全部 PASS（需 OM 环境）
- [ ] peak `I_total` ≤ `capacity_max * 1.05` 对所有约束场景成立
- [ ] peak `outflow_total` ≤ `rate_max * 1.05` 对所有约束场景成立
- [ ] 质量守恒误差 < 0.1%
- [ ] `docs/zh/questions/advanced_features.md` 包含约束组件 FAQ
- [ ] `docs/en/questions/advanced_features.md` 包含约束组件 FAQ

## 审查日志

| 轮次 | 聚焦 | 发现问题数 | 已修正 | 剩余 |
|------|------|-----------|--------|------|
| R1 | 结构完整性 | 3 | 3 | 0 |
| R1.5 | 外部引用事实核查 | 2 | 2 | 0 |
| R2 | 可执行性 | 2 | 2 | 0 |
| R3 | 风险与边缘 | 1 | 1 | 0 |
| **终止** | **T1 — 收敛终止** | | | **0** |

### Completion Summary

| 维度 | 结果 |
|------|------|
| 背景与目标 | 完整 |
| 技术方案 | 完整 |
| Error & Rescue Map | 5 条路径，0 CRITICAL GAP |
| 执行计划 | 3 Phase、7 Task |
| 回归检查清单 | 11 项（含项目特定检查） |
| 已知局限 | 无 |

### [R1 Issues]
- **Issue R1-1**: 缺少 Error & Rescue Map → 已补充 5 条失败路径
- **Issue R1-2**: 非目标缺少理由说明 → 已补充"不修改 Python 核心层"的理由（机制天然支持）
- **Issue R1-3**: 缺少已有代码复用分析 → 已补充 TES.mo 的 threshold 逻辑复用说明

### [R1.5 Issues]
- **Issue R1.5-1**: `package.order` 格式 — 已用 `read_file` 确认为每行一个模型名，无文件扩展名 [verified: package.order:L1-17]
- **Issue R1.5-2**: JSON `variableFilter` 中正则转义 — 已确认 `parameter_sweep.json` 中使用 `|` 分隔且方括号需转义 [verified: parameter_sweep.json:L9]

### [R2 Issues]
- **Issue R2-1**: Task 2.1 修改文件数可能超过 3（Cycle_Constrained.mo 本身 + connect 逻辑） → 确认为单文件新建，符合粒度要求
- **Issue R2-2**: Task 2.2 的 `variableFilter` 中 `\\[` 需在 JSON 中双转义 → 已在配置示例中标注

### [R3 Issues]
- **Issue R3-1**: 当 `rate_max` 极小而入流极大时，容量约束和速率约束可能竞争导致振荡 → 已在 Error Map 中说明"两个约束同时生效"的处理逻辑，sigmoid 保证平滑过渡
