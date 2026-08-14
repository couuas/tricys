"""Unified comparison plotting script for Original vs Coupled (Wang 2022 3-Column Cascade) models.

Generates a single, publication-quality comprehensive comparison chart:
- Panel 1: Inflow Rates (WDS to O-ISS & TES to O-ISS)
- Panel 2: O-ISS Tritium Output to SDS (o_iss.to_SDS[1])
- Panel 3: SDS Tritium Inventory Dynamics (sds.I[1])
"""

import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path

# Paths
base_dir = Path(__file__).parent
coupled_file = base_dir / "example_model_coupled_res.csv"
original_file = base_dir / "example_model_original_res.csv"

if not coupled_file.exists():
    raise FileNotFoundError(f"Simulation result not found: {coupled_file}. Run 'omc simulate_demo.mos' first.")

if not original_file.exists():
    raise FileNotFoundError(f"Original simulation result not found: {original_file}. Run 'omc simulate_original.mos' first.")

# Load data
df_coupled = pd.read_csv(coupled_file)
df_orig = pd.read_csv(original_file)

# Set plotting style
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial']
plt.rcParams['axes.unicode_minus'] = False

# Create figure with 3 stacked subplots
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 11), dpi=300, sharex=True)

# ------------------------------------------------------------------------------
# Panel 1: O-ISS Inflow Streams Comparison (TES & WDS to O-ISS)
# ------------------------------------------------------------------------------
ax1.plot(
    df_orig["time"],
    df_orig["tes.to_O_ISS[1]"],
    label="Original Model: TES to O-ISS",
    color="#e377c2",
    linestyle=":",
    linewidth=2.0,
)
ax1.plot(
    df_coupled["time"],
    df_coupled["tes.to_O_ISS[1]"],
    label="Coupled Model: TES to O-ISS (Breeding Stream)",
    color="#1f77b4",
    linewidth=2.2,
)
ax1.plot(
    df_coupled["time"],
    df_coupled["wds.to_O_ISS[1]"],
    label="Both Models: WDS to O-ISS (Detritiation Stream, Buffered)",
    color="#2ca02c",
    linestyle="--",
    linewidth=2.0,
)
ax1.set_title("1. O-ISS 进料流量对比 (WDS to O-ISS & TES to O-ISS)", fontsize=13, fontweight="bold", pad=8)
ax1.set_ylabel("氚进料流率 (g/h)", fontsize=11)
ax1.grid(True, linestyle=":", alpha=0.6)
ax1.legend(loc="center right", fontsize=10, framealpha=0.9)
ax1.set_ylim(-0.5, 11.0)

# ------------------------------------------------------------------------------
# Panel 2: O-ISS Output to SDS Comparison
# ------------------------------------------------------------------------------
ax2.plot(
    df_orig["time"],
    df_orig["o_iss.to_SDS[1]"],
    label="Original Model (Single 0-D Proxy, 稳态 ~9.06 g/h)",
    color="#d62728",
    linestyle="--",
    linewidth=2.2,
)
ax2.plot(
    df_coupled["time"],
    df_coupled["o_iss.to_SDS[1]"],
    label="Coupled Model (Wang 2022 3-Column Cascade, 稳态 ~9.29 g/h)",
    color="#1f77b4",
    linewidth=2.4,
)
ax2.set_title("2. O-ISS 产氚输出流量对比 (O-ISS to SDS)", fontsize=13, fontweight="bold", pad=8)
ax2.set_ylabel("产氚流率 (g/h)", fontsize=11)
ax2.grid(True, linestyle=":", alpha=0.6)
ax2.legend(loc="lower right", fontsize=10, framealpha=0.9)
ax2.set_ylim(-0.5, 10.5)

# ------------------------------------------------------------------------------
# Panel 3: SDS Tritium Inventory Comparison
# ------------------------------------------------------------------------------
ax3.plot(
    df_orig["time"],
    df_orig["sds.I[1]"],
    label="Original Model (5000h 末盘存: 1937.18 g)",
    color="#d62728",
    linestyle="--",
    linewidth=2.2,
)
ax3.plot(
    df_coupled["time"],
    df_coupled["sds.I[1]"],
    label="Coupled Model (5000h 末盘存: 3353.97 g, 自持增殖 +1416.79 g)",
    color="#1f77b4",
    linewidth=2.4,
)
ax3.set_title("3. SDS 系统储氚库存动态对比 (SDS Tritium Inventory)", fontsize=13, fontweight="bold", pad=8)
ax3.set_xlabel("仿真时间 (Time / h)", fontsize=11)
ax3.set_ylabel("储氚库存 (g)", fontsize=11)
ax3.grid(True, linestyle=":", alpha=0.6)
ax3.legend(loc="upper left", fontsize=10, framealpha=0.9)

plt.tight_layout()
chart_path = base_dir / "comparison_chart.png"
plt.savefig(chart_path, dpi=300)
print(f"Unified comparison chart saved to: {chart_path}")

# Print summary table
ss_coupled = df_coupled[df_coupled["time"] >= 4000]
ss_orig = df_orig[df_orig["time"] >= 4000]

print("\n" + "=" * 76)
print("             两个模型全流程核心物理数据对比表 (稳态 4000h~5000h)")
print("=" * 76)
print(f"{'对比物理量':<34} | {'Coupled (Wang 2022)':<18} | {'Original 对照组':<18}")
print("-" * 76)
print(f"{'TES to O-ISS 氚进料 (g/h)':<30} | {ss_coupled['tes.to_O_ISS[1]'].mean():<18.4f} | {ss_orig['tes.to_O_ISS[1]'].mean():<18.4f}")
print(f"{'WDS to O-ISS 氚进料 (g/h)':<30} | {ss_coupled['wds.to_O_ISS[1]'].mean():<18.4f} | {ss_orig['wds.to_O_ISS[1]'].mean():<18.4f}")
print(f"{'O-ISS to SDS 产氚流率 (g/h)':<29} | {ss_coupled['o_iss.to_SDS[1]'].mean():<18.4f} | {ss_orig['o_iss.to_SDS[1]'].mean():<18.4f}")
print(f"{'SDS 5000h 末储氚总盘存 (g)':<30} | {df_coupled['sds.I[1]'].iloc[-1]:<18.2f} | {df_orig['sds.I[1]'].iloc[-1]:<18.2f}")
print("=" * 76)
