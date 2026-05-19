# Blanket 默认带约束 — 通过参数注入开启容量/速率限制

## 背景与目标

- **问题/需求描述**：tricys 主模型 `Cycle.mo` 中的 `Blanket` 组件没有容量/速率约束，盘存可无限增长。希望主模型默认具备约束能力，且用户通过 JSON 配置文件可自主配置上下限。
- **根因分析**：`Blanket.mo` 的状态方程 `der(I[i]) = ... + from_TES[i] - (1+nonradio_loss)*I[i]/T - decay*I[i]` 不含任何上限截断。
- **目标**：
  1. 在 `Blanket.mo` 内嵌 sigmoid 软约束（容量 + 速率），默认参数 `capacity_max=1e9, rate_max=1e9` 等价于现有无约束行为
  2. 新增守恒导出端口 `overflow_out[5]`、`rate_clip_out[5]`（默认连接到外部时可悬空，不影响仿真）
  3. 用户通过 `simulation_parameters: {"blanket.capacity_max": 500, "blanket.rate_max": 50}` 即可开启约束
  4. 全部现有测试（131 项）无回归，原有 `blanket.I[1]`、`blanket.outflow` 等变量名保持兼容
- **非目标（不做什么）**：
  - 不修改 `ConstrainedBuffer.mo`（保持 PR #81 不变）— 该组件继续作为通用独立缓冲存在
  - 不替换 Cycle.mo 中的 `Blanket blanket` 实例为 `ConstrainedBuffer` — 见 Clarify Gate 中说明，会丢失 TBR 增殖
  - 不修改 TES/SDS/WDS 等其他子系统 — 本 PR 仅聚焦 Blanket；其它子系统可在后续 PR 用同样模式扩展
  - 不修改 tricys Python 源代码 — JSON 参数注入机制已具备所需能力
- **已有代码/流程复用分析**：
  - `ConstrainedBuffer.mo` 的 sigmoid 约束公式：**复用**（在 Blanket.mo 内复制相同的 sigmoid 表达式，理由：避免引入跨组件继承依赖；公式只有 2 行）
  - tricys 参数注入机制：**复用**（已通过 `simulation_parameters` 支持 dotted path）
  - PR #81 的 `test_constrained_buffer.py` 测试模式：**复用**（新增 `test_blanket_constraints.py` 时复制 fixture 与断言结构）
  - `Blanket.mo` 原有端口与方程结构：**复用**（仅追加新参数和新等式，不改原有等式）

## Clarify Gate

| # | 类型 | 项 | 处理 |
|---|------|-----|------|
| 1 | 多义术语 | "替换为 ConstrainedBuffer" — 字面替换在物理上丢失 TBR，不可行 | 采用等价语义实现：**在 Blanket 内扩展约束参数**，效果上"主模型默认带约束"，用户通过 JSON 配置上下限。已在响应中向用户说明并选择路线 A |
| 2 | 边界条件 | `capacity_max=1e9` 时是否真的与原 Blanket 行为 0 偏差？ | PR #81 已验证 ConstrainedBuffer 在 cap=1e9 时与 Cycle.mo 基线 0.00% 偏差；同 sigmoid 公式在 Blanket 中行为一致 |
| 3 | 隐含依赖 | 新增 `overflow_out` / `rate_clip_out` 端口在 Cycle.mo 中不连接会否触发 OpenModelica 错误？ | RealOutput 端口允许悬空（无连接时输出仍计算但不被消费）— Task 1.2 需 checkModel 确认 |

[Clarify Gate: PASS — 已澄清替换语义；其余项已有证据或在 Task 中验证]

## Scope Mode

**HOLD** — 这是对现有组件的能力扩展（非新功能、非 bug 修复），需要严格保持范围：不扩展到其它子系统、不改动 Python 层、不破坏端口契约。

## 技术方案

- **方案概述**：在 `Blanket.mo` 中追加 4 个参数（`capacity_max`, `rate_max`, `softness`, `to_TES_capacity_max` 暂不引入）和 2 个输出端口（`overflow_out`, `rate_clip_out`）。原有状态方程改写为：
  ```modelica
  inflow_total[i] = (if i==1 then pulseInput*TBR else 0) + from_TES[i];
  outflow_nominal[i] = I[i] / T;
  rate_scale = sigmoid(sum(outflow_nominal), rate_max, softness);
  admit_scale = sigmoid_admit(sum(I), capacity_max, softness);
  outflow[i] = rate_scale * outflow_nominal[i];
  der(I[i]) = admit_scale*inflow_total[i] - (1+nonradio_loss[i])*outflow[i] - decay_loss[i]*I[i];
  overflow_out[i] = (1-admit_scale)*inflow_total[i];
  rate_clip_out[i] = (1-rate_scale)*outflow_nominal[i];
  to_TES[i] = to_TES_Fraction * outflow[i];   // 不变
  to_CL[i] = to_CL_Fraction * outflow[i];     // 不变
  ```
- **关键设计决策**：
  1. 默认 `capacity_max = 1e9, rate_max = 1e9` → admit_scale ≈ 1, rate_scale ≈ 1 → 与原 Blanket 行为数值等价
  2. 不修改 `to_TES` / `to_CL` 端口与方程 → 上下游组件无需改动
  3. 新增 `overflow_out` / `rate_clip_out` 端口在 Cycle.mo 中**保持悬空**，仅供需要时连接到 TES 路径
  4. sigmoid 表达式逐字复制 ConstrainedBuffer.mo 的实现以保证一致性
- **影响范围**：
  - `tricys/example/example_data/example_model/Blanket.mo`（核心修改，~30 行追加）
  - `tricys/example/example_data/basic/7_blanket_constraints/`（新增示例配置目录）
  - `test/core/test_blanket_constraints.py`（新增测试）
  - `docs/zh/questions/advanced_features.md` + `docs/en/questions/advanced_features.md`（FAQ 追加）

## Error & Rescue Map

| 代码路径/操作 | 可能的失败 | 错误类型 | 已处理？ | 处理方式 | 用户可见行为 |
|---------------|------------|----------|---------|----------|--------------|
| sigmoid 分母 `softness * capacity_max` | 用户设 softness=0 且 capacity_max=0 | DivisionByZero | Y | `+1e-30` 保护 + softness≤0 走硬约束分支 | 硬约束触发 if-else，无数值溢出 |
| 默认参数 `capacity_max=1e9` 与现有 JSON 中已有的 `blanket.T` 等参数冲突 | 用户老 JSON 不会触发新参数 | 兼容性回归 | Y | 默认值 = 无约束 = 数值等价 | 老 JSON 仍按原行为运行 |
| 新增 `overflow_out` / `rate_clip_out` 端口在 Cycle.mo 悬空 | OpenModelica 拒绝悬空 RealOutput | 编译错误 | N | Task 1.2 checkModel 验证；若失败则需在 Cycle.mo 添加 terminator 或保持端口连接到 Terminator block | 编译失败 → 阻断 |
| sigmoid 计算 `exp((I_total - cap)/(softness*cap))` 当 I_total 远大于 cap 且 softness 极小 | exp 上溢 → Inf | NumericalOverflow | Y | sigmoid 形式 `1/(1+exp(x))` 当 x → +∞ 时自然趋向 0，不上溢；当 x → -∞ 时 exp 趋向 0 也无问题 | 数值稳定 |
| 测试 `test_blanket_constraints.py` 与 PR #81 的 fixture 名冲突 | pytest fixture 重复 | TestCollision | Y | 文件级 fixture（function scope），不会跨文件冲突 | 测试独立运行 |

**Critical Gap 检查**：Task 1.2 的 checkModel 必须验证悬空 RealOutput 端口可编译，否则需要补充 Task 1.2b 在 Cycle.mo 添加 Modelica.Blocks.Routing.TerminateSimulation 或调整方案。

## 执行计划

### Phase 1: Blanket 组件扩展

#### ✅ Task 1.1: 创建 feature/blanket-default-constraints 分支
- **目标**：从 main 创建独立分支，与 PR #81 (feature/constrained-buffer) 完全独立
- **依赖**：无
- **修改内容**：
  - `git fetch upstream && git checkout main && git pull upstream main`
  - `git checkout -b feature/blanket-default-constraints`
- **修改边界**：仅创建分支，不修改任何文件
- **测试要求**：
  - `git branch --show-current` 预期输出 `feature/blanket-default-constraints`
  - `git log --oneline -1` 预期 HEAD == upstream/main
- **验收标准**：
  - ✅ 新分支基于 main 创建
  - ✅ 与 feature/constrained-buffer 无 merge-base 之外的共同提交
- **潜在风险**：本地 main 可能落后于 upstream/main，需要先 pull

#### ✅ Task 1.2: 扩展 Blanket.mo 添加约束参数与端口
- **目标**：在 Blanket.mo 中追加 sigmoid 约束逻辑，默认行为不变
- **依赖**：T1.1
- **修改内容**：
  - `tricys/example/example_data/example_model/Blanket.mo`：
    - 追加参数 `capacity_max=1e9, rate_max=1e9, softness=0.02`
    - 追加输出端口 `overflow_out[5], rate_clip_out[5]`
    - 追加中间变量 `I_total, outflow_nominal[5], inflow_total[5], rate_scale, admit_scale, outflow[5]`
    - 改写 equation 段：原 `der(I[i])` 等式替换为带 admit_scale/rate_scale 的版本
    - 原 `to_TES[i]`, `to_CL[i]` 表达式更新为基于 `outflow[i]` 而非 `I[i]/T`（数学上当 rate_scale=1 时等价）
- **修改边界**：
  - 不得修改 `Cycle.mo`、`ConstrainedBuffer.mo`、`Cycle_Constrained.mo`、`package.order`
  - 不得修改任何其它 .mo 文件
- **测试要求**：
  - 运行 `omc -- check example_model.Blanket`（或在 OMShell 中 checkModel）预期输出 `Check of example_model.Blanket completed successfully`
  - 运行 `omc -- check example_model.Cycle` 验证 Cycle.mo 编译不受影响（悬空 overflow_out / rate_clip_out 端口是否被接受）
- **验收标准**：
  - ✅ Blanket.mo checkModel 0 errors 0 warnings
  - ✅ Cycle.mo checkModel 0 errors 0 warnings（关键：验证悬空端口可接受）
  - ✅ 新追加的参数与端口在 `omc -- dumpJSON example_model.Blanket` 中可见
- **潜在风险**：
  - 悬空 RealOutput 端口可能触发警告 → 若仅是 warning 不阻断；若是 error，需 Task 1.2b 在 Cycle.mo 添加哑连接

#### Task 1.2b (条件性): 处理悬空端口编译问题
- **目标**：仅当 Task 1.2 验证悬空端口失败时执行
- **依赖**：T1.2 验证发现错误
- **修改内容**：在 Cycle.mo 中为 `blanket.overflow_out` 和 `blanket.rate_clip_out` 添加到 `Modelica.Blocks.Routing.RealPassThrough` 的连接或注释为可选端口
- **跳过条件**：Task 1.2 检查通过则跳过该任务

### Phase 2: 验证与示例

#### Task 2.1: 创建示例 JSON 配置
- **目标**：用户拿来即用的约束配置示例
- **依赖**：T1.2
- **修改内容**：
  - 新建目录 `tricys/example/example_data/basic/7_blanket_constraints/`
  - 文件 1：`blanket_constraints.json`
    ```json
    {
      "paths": {"package_path": "../../example_model/package.mo"},
      "simulation": {
        "model_name": "example_model.Cycle",
        "variableFilter": "time|blanket.I[1]|blanket.I_total|blanket.overflow_out[1]|blanket.rate_clip_out[1]|sds.I[1]",
        "stop_time": 5000.0,
        "step_size": 1.0
      },
      "simulation_parameters": {
        "blanket.capacity_max": 500,
        "blanket.rate_max": 50
      }
    }
    ```
  - 文件 2：`blanket_constraints_sweep.json` — 4×4 网格扫描 `capacity_max ∈ [200, 500, 1000, 1e9]` × `rate_max ∈ [20, 50, 100, 1e9]`
- **修改边界**：不得修改 `1_basic_configuration/` ~ `6_constrained_buffer/` 中的任何已有文件
- **测试要求**：
  - 在 tricys repo 根目录运行 `tricys basic -c tricys/example/example_data/basic/7_blanket_constraints/blanket_constraints.json` 预期：1/1 jobs success
  - 运行 sweep 配置预期 16/16 jobs success
- **验收标准**：
  - ✅ 单点配置 1/1 仿真完成
  - ✅ 扫描配置 16/16 仿真完成
  - ✅ 默认（无 simulation_parameters）等价于原 Cycle 行为
- **潜在风险**：variableFilter 中的 `blanket.I_total` 在原 Blanket.mo 中不存在 → 必须在 Task 1.2 中确实添加该变量

#### Task 2.2: 创建 pytest 自动化验证
- **目标**：5 项测试确保约束功能正确 + 无回归
- **依赖**：T1.2, T2.1
- **修改内容**：
  - 新建 `test/core/test_blanket_constraints.py`：
    - `test_default_matches_baseline`: 不设 capacity_max → 与原 Cycle.mo 基线 0.00% 偏差（取 `blanket.I[1] @ t=5000`）
    - `test_capacity_constraint_effective`: 设 cap=100 → `blanket.I_total` 最大值 ≤ 102
    - `test_rate_constraint_effective`: 设 rate=2 → `rate_clip_out[1]` 最大值 > 0
    - `test_mass_conservation`: 入流积分 ≈ 盘存增量 + 出流积分 + overflow 积分 + rate_clip 积分（误差 < 1%）
    - `test_hard_constraint`: softness=0.001 → `blanket.I_total` 最大值 ≤ cap×1.02
- **修改边界**：
  - 不得修改 `test/core/test_constrained_buffer.py`（PR #81 已有）
  - 不得修改 `conftest.py`
- **测试要求**：
  - `pytest test/core/test_blanket_constraints.py -v` 预期 5/5 PASSED
  - `pytest test/ -x` 预期 131+5 = 136 passed（确认无回归）
- **验收标准**：
  - ✅ 5 项新测试全部通过
  - ✅ 全量回归 0 失败
  - ✅ 单测试运行时间 < 60s（标记 pytest.mark.slow）
- **潜在风险**：质量守恒测试中数值误差可能来自 sigmoid 软过渡区，需调整容差到 1-2%

#### Task 2.3: 更新 FAQ 文档
- **目标**：用户文档说明如何启用约束
- **依赖**：T2.1, T2.2
- **修改内容**：
  - `docs/zh/questions/advanced_features.md`：追加一节 "如何为 Blanket 设置盘存与处理速率上限"
  - `docs/en/questions/advanced_features.md`：英文对应版本
  - 内容覆盖：(1) 默认行为说明 (2) JSON 参数注入示例 (3) overflow_out / rate_clip_out 端口含义 (4) 与 ConstrainedBuffer 的关系（指向 PR #81 示例 6）
- **修改边界**：不得修改其它 FAQ 章节
- **测试要求**：mkdocs build 预期 0 errors
- **验收标准**：
  - ✅ 中英双语 FAQ 追加
  - ✅ 包含可复制的 JSON 片段
- **潜在风险**：无

### Phase 3: 提交与 PR

#### Task 3.1: 分阶段 commit 并推送
- **目标**：清晰的 commit 历史
- **依赖**：T2.3
- **修改内容**：
  - Commit 1: `feat(model): extend Blanket with capacity/rate sigmoid constraints` — 仅 Blanket.mo
  - Commit 2: `chore(example): add 7_blanket_constraints sample configs` — JSON 配置
  - Commit 3: `test: pytest verification for Blanket constraints` — 测试文件 + pyproject 标记（如需）
  - Commit 4: `docs: FAQ for Blanket capacity/rate constraints` — 文档
  - `git push -u origin feature/blanket-default-constraints`
- **修改边界**：仅本分支
- **测试要求**：
  - `git log --oneline upstream/main..HEAD` 显示 4 个 commit
  - `git diff upstream/main --stat` 仅涉及上述目录
- **验收标准**：
  - ✅ 4 个原子 commit
  - ✅ 不含任何与 PR #81 冲突的文件修改（验证：`git diff feature/constrained-buffer..feature/blanket-default-constraints --name-only` 不出现 Blanket.mo 之外的冲突项 — 实际上 PR #81 不改 Blanket.mo，所以无冲突）

#### Task 3.2: 创建 PR
- **目标**：提交到 asipp-neutronics/tricys main
- **依赖**：T3.1 + PR #81 状态判断
- **修改内容**：使用 github-pull-request 工具创建 PR
- **PR 顺序策略**：
  - **首选**：等 PR #81 合入 main 后再提交本 PR（避免 reviewer 混淆）
  - **次选**：在 #81 未合入时提交本 PR，base = main（因本 PR 不依赖 #81 任何文件），在 PR 描述中明确说明"独立于 #81，可任意顺序合入"
- **PR 标题**：`feat(model): Blanket 默认支持容量与速率约束（JSON 可配置）`
- **PR 正文要点**：
  - 与 #81 的关系（独立但互补：#81 提供通用组件，本 PR 让 Blanket 默认可约束）
  - 默认行为 0 偏差证明（test_default_matches_baseline）
  - 用户配置示例（JSON 片段）
- **验收标准**：
  - ✅ PR 创建成功
  - ✅ CI 通过（如有）

## Execution Wave（并行执行波次）

| Wave | 可并行 Task | 依赖已完成 |
|------|-------------|------------|
| W1 | T1.1 | — |
| W2 | T1.2 | W1 |
| W3 | T2.1 | W2 |
| W4 | T2.2, T2.3 | W3 |
| W5 | T3.1 | W4 |
| W6 | T3.2 | W5 + (PR #81 决策) |

## 回归检查清单
- [ ] `pytest test/ -x` 全量通过（131 原有 + 5 新增 = 136）
- [ ] 原有 6 个示例配置（1_basic_configuration ~ 6_constrained_buffer）仍能跑：`tricys basic -c <各 json>` 全部 success
- [ ] `omc -- check example_model.Cycle` 0 errors（验证悬空端口可接受）
- [ ] `omc -- check example_model.Cycle_Constrained` 0 errors（PR #81 模型不受影响）
- [ ] mkdocs build 0 errors
- [ ] 与 PR #81 分支 diff：`git diff origin/feature/constrained-buffer..HEAD -- tricys/example/example_data/example_model/` 仅 Blanket.mo 出现

## 分支与 PR 关系图

```
upstream/main
    │
    ├── feature/constrained-buffer (PR #81)
    │     ├── 新增 ConstrainedBuffer.mo
    │     ├── 新增 Cycle_Constrained.mo
    │     └── 新增 6_constrained_buffer/*.json
    │
    └── feature/blanket-default-constraints (本 PR)
          ├── 修改 Blanket.mo（追加参数+端口）
          ├── 新增 7_blanket_constraints/*.json
          └── 新增 test_blanket_constraints.py
```

**关键性质**：两个分支修改的文件**完全不重叠**（除 package.order 在 #81 已添加 ConstrainedBuffer/Cycle_Constrained，本 PR 不改 package.order）。无论哪个先合入，另一个都能直接 rebase 通过。

## 已知局限

- 本 PR 只为 Blanket 启用约束。TES/SDS/WDS 的同等扩展留待后续 PR
- sigmoid 公式在 Blanket.mo 中复制了 ConstrainedBuffer.mo 的实现 — 后续如有第三个组件需要约束，可考虑提取为 Modelica function 共享
- `overflow_out` / `rate_clip_out` 在 Cycle.mo 中悬空 — 若用户需要将这些质量流路由到 TES，需要自行添加 connect 语句（FAQ 中说明）

## 审查日志

| 轮次 | 聚焦 | 发现问题数 | 已修正 | 剩余 |
|------|------|-----------|--------|------|
| R1 | 结构完整性 | 0 | 0 | 0 |
| R1.5 | 外部引用事实核查 | 2 | 2 | 0 |
| R2 | 可执行性 | 1 | 1 | 0 |
| R3 | 风险与边缘 | 1 | 1 | 0 |
| **终止** | **T4 — 零缺陷快速通过** | | | **0** |

### R1.5 修正记录
- **Issue R1.5-1**: 最初草案 Task 1.2 写"修改 `to_TES[i]` 表达式"但未确认现有 to_TES_Fraction 参数名 → 已 read Blanket.mo:31 确认参数为 `to_TES_Fraction = 1 - to_CL_Fraction`，方案中明确保留该参数 ✅
- **Issue R1.5-2**: 草案引用"OpenModelica checkModel 命令" → 已确认 `omc -- check <ModelName>` 与 OMShell `checkModel(<ModelName>)` 两种方式均可；测试要求使用 omc CLI 形式 ✅

### R2 修正记录
- **Issue R2-1**: 草案 Task 2.1 中 variableFilter 引用 `blanket.I_total` 但原 Blanket.mo 无此变量 → 在 Task 1.2 修改内容中明确添加 `Real I_total = sum(I)` 中间变量；并在风险中提示 ✅

### R3 修正记录
- **Issue R3-1**: 悬空 RealOutput 端口编译行为未确认 → 已添加 Task 1.2b 作为条件性 fallback，Error & Rescue Map 中标注为待 Task 1.2 验证 ✅

## Pre-Delivery Audit (Level: L1-Lite)

| § | Check | Status | Note |
|---|-------|--------|------|
| 1 | 计划文本格式规范 | ✅ PASS | Markdown 结构完整，Task 字段齐全 |

[De-AI-Fier Gate: SKIPPED — 内部计划文件，按 L1-Tone 标准自检通过，未调用 MCP]
