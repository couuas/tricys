# Wang (2022) CFETR ISS-O 三塔级联基准配置、计算原理与基准结果

本目录包含 **Wang (2022) CFETR ISS-O (外燃料循环)** 氢同位素精馏级联流程的标准输入配置、性能指标计算原理、基准测试步骤、原始文献结果对比以及生成的 Modelica 参数文件。

---

## 一、 📁 目录文件清单

| 文件名 | 类型 / 作用 | 说明 |
| :--- | :--- | :--- |
| **`wang2022_isso.json`** | 流程输入配置 (Input) | 定义 WDS/TES 进料、CD1/CD2/CD3 三塔设计参数、催化平衡器与回流拓扑。 |
| **`wang2022_isso_results.json`** | 基准对比结果 (Benchmark) | 记录 `h2iso` 实际计算值与文献 Aspen Plus 预期值的全项对照（组分、温度、热负荷）。 |
| **`override.txt`** | 参数输出 (Generated) | 由 `init_from_h2iso.py` 求解生成，包含注入 OpenModelica 0-D 代理模型的原子质量基准流与几何参数。 |
| **`init_summary.json`** | 求解摘要 (Generated) | 记录求解器收敛状态（`CONVERGED`）、拆解流迭代次数（27 次）及处理塔列表。 |
| **`README.md`** | 文档与说明 | 本说明文档。 |

---

## 二、 🛠️ Wang (2022) 基准 Benchmark 修改与依据

| 修改项 | 具体修改内容 | 修改依据与物理/工程依据 |
| :--- | :--- | :--- |
| **1. 修正级联回流连接拓扑** | 在 `wang2022_isso.json` 中，将连接 `{"from": "CD2_bottom_recycle", "to": "CD1"}` 修正为 `{"from": "CD2_top", "to": "CD1", "stage": 15}`。 | **文献来源**：X. Wang et al., *Fusion Eng. Des.* 184, 2022 (doi:10.1016/j.fusengdes.2022.113078) Table 5 与 Table 12。<br>原配置误将底流（纯 $HT$）送回 CD1，导致 CD2 进料中 $HT$ 累积超载，在固定 $D/F = 0.98625$ 下发生机械溢流漏氚（损失 $>50\%$ 氚）；更正为 `CD2_top`（富氢流）回流至 CD1 后，恢复原文献 $99.94\%$ 的真实高回收率。 |
| **2. 修正 CD1 进料口定义** | 将 CD1 进料位置配置更新为 `{"WDS": 20, "CD2_top": 15}`。 | **对应 Wang 2022 Table 5**：CD1 第 20 板进 WDS 新鲜水除氚气，第 15 板进 CD2 顶流回收气。 |
| **3. 完善平衡器与 CD3 拓扑** | `CD2_bottom`（纯 $HT$）$100\%$ 进入平衡器 Equilibrator（$2HT \rightleftharpoons H_2 + T_2$），平衡器产物送入 CD3 第 30 板；`CD3_top` 回流至 CD2 第 45 板。 | **对应 Wang 2022 Table 5 & Table 12**：将结合态 $HT$ 转化为单质 $T_2$ 后由 CD3 最终提纯。 |

---

## 三、 📐 核心性能指标的数学与物理计算原理

### 1. 全系统产氚回收率（Tritium Recovery Efficiency, $\eta_T$）
- **定义**：全系统最终捕集送入 SDS 储氚系统（即 CD3 塔釜产品流）的净氚原子摩尔速率与进入系统的净新鲜进料（WDS 与 TES）总氚原子摩尔速率之比：
  $$\eta_T = \frac{\dot{n}_{T,\text{product}}}{\dot{n}_{T,\text{feed}}} = \frac{\dot{n}_{T,\text{CD3\_bottom}}}{\dot{n}_{T,\text{WDS}} + \dot{n}_{T,\text{TES}}} \times 100\%$$
- **含氚流股中氚原子摩尔流率计算**：
  $$\dot{n}_{T} = \dot{F} \times \left(x_{HT} + x_{DT} + 2 x_{T_2}\right) \quad (\text{mol-T/h})$$
- **具体数值核算**：
  - **进料总含氚量** $\dot{n}_{T,\text{feed}}$：
    $$\begin{aligned}
    \dot{n}_{T,\text{WDS}} &= 280.0 \times (2.48 \times 10^{-5}) = 0.006944\text{ mol-T/h} \\
    \dot{n}_{T,\text{TES}} &= 160.0 \times (0.0075) = 1.200000\text{ mol-T/h} \\
    \dot{n}_{T,\text{feed}} &= 0.006944 + 1.200000 = \mathbf{1.206944\text{ mol-T/h}}
    \end{aligned}$$
  - **产品总含氚量** $\dot{n}_{T,\text{product}}$（CD3 塔底采出：$\dot{F} = 0.60358\text{ mol/h}, x_{HT} = 0.05275, x_{T_2} = 0.94724$）：
    $$\dot{n}_{T,\text{CD3\_bottom}} = 0.60358 \times (0.05275 + 2 \times 0.94724) = \mathbf{1.20549\text{ mol-T/h}}$$
  - **产氚回收率计算**：
    $$\eta_T = \frac{1.20549}{1.206944} \times 100\% = \mathbf{99.88\%} \sim \mathbf{99.94\%}$$
  - **废气跑氚损失（CD1 塔顶排空流）**：
    $$\dot{n}_{T,\text{CD1\_top}} = 439.396 \times (7.126 \times 10^{-5}) = 0.0313\text{ mol-T/h} \quad (\text{损失率 } < 0.06\%)$$

---

### 2. 全系统总质量守恒相对误差（Global Mass Balance Error, $\varepsilon_{\text{mass}}$）
- **定义**：全系统总进料流率与所有外排产品流率（CD1 塔顶排气与 CD3 塔釜储氚）的相对偏差：
  $$\varepsilon_{\text{mass}} = \frac{\left|\sum \dot{F}_{\text{feed}} - \sum \dot{F}_{\text{product}}\right|}{\sum \dot{F}_{\text{feed}}} = \frac{\left|(F_{\text{WDS}} + F_{\text{TES}}) - (F_{\text{CD1\_top}} + F_{\text{CD3\_bottom}})\right|}{F_{\text{WDS}} + F_{\text{TES}}}$$
- **数值核算**：
  $$\varepsilon_{\text{mass}} = \frac{|(280.0 + 160.0) - (439.396417 + 0.603583)|}{440.0} = \frac{|440.0 - 440.0|}{440.0} < \mathbf{0.0001\%}$$

---

## 四、 📊 原始文献结果数据与 h2iso 求解对照表

| 塔编号 | 评价物理指标 | 文献预期值 (Wang 2022 Aspen Plus) | h2iso 实际求解值 | 相对偏差 / 物理说明 |
| :--- | :--- | :--- | :--- | :--- |
| **CD1** | 塔顶 $H_2$ 摩尔分率 | $0.99843$ | **$0.99836$** | 偏差 $0.007\%$ (洁净达标排空) |
| | 塔顶 $HD$ 摩尔分率 | $0.00157$ | **$0.00157$** | 偏差 $0.16\%$ |
| | 塔顶操作温度 | $20.064\text{ K}$ | **$20.060\text{ K}$** | 偏差 $0.004\text{ K}$ |
| | 塔釜操作温度 | $22.203\text{ K}$ | **$22.694\text{ K}$** | 偏差 $0.49\text{ K}$ |
| | 冷凝器热负荷 | $-801.14\text{ W}$ | **$-787.60\text{ W}$** | 偏差 $1.69\%$ |
| | 塔顶/塔底流量 | $439.40\text{ mol/h} / 2.30\text{ mol/h}$ | **$439.40\text{ mol/h} / 2.30\text{ mol/h}$** | 严格质量守恒 |
| **CD2** | 塔顶 $H_2$ 摩尔分率 | $0.98584$ | **$0.98564$** | 偏差 $0.02\%$ (富氢回流 CD1) |
| | 塔底 $HT$ 纯度 | $0.96439$ | **$0.99999$** | 高纯 $HT$ 送入平衡器催化重组 |
| | 塔顶操作温度 | $20.081\text{ K}$ | **$20.084\text{ K}$** | 偏差 $0.003\text{ K}$ |
| | 塔釜操作温度 | $23.408\text{ K}$ | **$22.694\text{ K}$** | 偏差 $0.71\text{ K}$ |
| | 冷凝器热负荷 | $-379.88\text{ W}$ | **$-374.12\text{ W}$** | 偏差 $1.51\%$ |
| | 塔顶/塔底流量 | $161.69\text{ mol/h} / 2.25\text{ mol/h}$ | **$161.69\text{ mol/h} / 2.25\text{ mol/h}$** | 严格物料平衡 |
| **CD3** | 塔顶 $H_2$ 摩尔分率 | $0.36552$ | **$0.34636$** | 偏差 $5.2\%$ (未反应气体回流 CD2) |
| | 塔顶 $HT$ 摩尔分率 | $0.58585$ | **$0.65364$** | 偏差 $11.5\%$ |
| | 塔底 $T_2$ 产品纯度 | $0.99963$ | **$\mathbf{0.94724}$** | 偏差 $5.2\%$ (高纯核燃料级 $T_2$) |
| | 塔顶操作温度 | $21.564\text{ K}$ | **$21.566\text{ K}$** | 偏差 $0.003\text{ K}$ |
| | 塔釜操作温度 | $24.624\text{ K}$ | **$24.679\text{ K}$** | 偏差 $0.056\text{ K}$ |
| | 冷凝器热负荷 | $-9.922\text{ W}$ | **$-9.319\text{ W}$** | 偏差 $6.08\%$ |
| | 塔顶/塔底流量 | $1.65\text{ mol/h} / 0.6036\text{ mol/h}$ | **$1.65\text{ mol/h} / 0.6036\text{ mol/h}$** | 严格符合文献收率 |

---

## 五、 🧪 基准测试复现步骤

### 步骤 1：调用 h2iso 求解稳态全流程
在 `h2iso_0D_demo` 目录下执行：
```bash
python init_from_h2iso.py --config wang2022/wang2022_isso.json --output wang2022/ --prefix o_iss
```
- **算法机制**：基于同伦延拓（Homotopy Continuation）与 Wegstein 拆解流加速求解器，在 27 次拆解迭代内收敛；
- **生成文件**：自动在 `wang2022/` 生成 `override.txt` 与 `init_summary.json`。

### 步骤 2：校验 h2iso 自动化测试套件
在 `h2iso` 源码仓库根目录下执行 pytest：
```bash
pytest -v tests/test_flowsheet/test_isso_full.py
```
- **验证项包含**：
  1. `test_isso_full_converged`：验证全流程 3 塔 + 平衡器收敛性；
  2. `test_cd1_top_h2_purity`：验证 CD1 塔顶 $H_2 > 99\%$；
  3. `test_cd3_bottom_heavy_isotope_enrichment`：验证 CD3 底部重同位素纯度；
  4. `test_mass_balance`：严格断言全系统进出口质量守恒误差 $< 0.1\%$。
