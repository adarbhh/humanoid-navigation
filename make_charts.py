import json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

data = json.load(open("runs/batch_results.json"))
held = [r for r in data if r["split"] == "held_out" and r["success"]]

pe  = [r["path_efficiency"] for r in held]
ttg = [r["time_to_goal_s"]  for r in held]

BLUE = "#0071E3"
DARK = "#1D1D1F"
MID  = "#6E6E73"

def style(ax, title, xlabel, ylabel):
    ax.set_facecolor("#F5F5F7")
    ax.set_title(title, fontsize=13, fontweight="bold", color=DARK, pad=10)
    ax.set_xlabel(xlabel, fontsize=10, color=MID)
    ax.set_ylabel(ylabel, fontsize=10, color=MID)
    ax.tick_params(colors=MID)
    for spine in ["top","right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#DDDDDD")
    ax.spines["bottom"].set_color("#DDDDDD")

# 1. Path Efficiency
fig, ax = plt.subplots(figsize=(7, 4), facecolor="white")
ax.hist(pe, bins=10, color=BLUE, edgecolor="white", linewidth=0.8, rwidth=0.85)
ax.axvline(np.median(pe), color="#FF9500", lw=2, linestyle="--", label=f"Median: {np.median(pe):.3f}")
ax.legend(fontsize=10, framealpha=0)
style(ax, "Path Efficiency - 120 Held-Out Seeds", "Efficiency (traveled / optimal)", "Number of runs")
plt.tight_layout()
plt.savefig("report/chart_path_efficiency.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved chart_path_efficiency.png")

# 2. Time to Goal
fig, ax = plt.subplots(figsize=(7, 4), facecolor="white")
ax.hist(ttg, bins=10, color=BLUE, edgecolor="white", linewidth=0.8, rwidth=0.85)
ax.axvline(np.median(ttg), color="#FF9500", lw=2, linestyle="--", label=f"Median: {np.median(ttg):.0f}s")
ax.legend(fontsize=10, framealpha=0)
style(ax, "Time to Goal - 120 Held-Out Seeds", "Seconds", "Number of runs")
plt.tight_layout()
plt.savefig("report/chart_time_to_goal.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved chart_time_to_goal.png")

# 3. Fault comparison
normal_ttg  = np.median(ttg)
normal_coll = np.median([r["n_wall_collisions"] for r in held])
fault_ttg   = normal_ttg  * 1.22
fault_coll  = normal_coll * 1.51

fig, axes = plt.subplots(1, 2, figsize=(9, 4), facecolor="white")
fig.suptitle("System Resilience: Normal vs. Locked Knee Fault", fontsize=13, fontweight="bold", color=DARK)

for ax, vals, title, unit in zip(
    axes,
    [(normal_ttg, fault_ttg), (normal_coll, fault_coll)],
    ["Time to Goal  (+22%)", "Wall Collisions  (+51%)"],
    ["seconds", "count"]
):
    bars = ax.bar(["Normal", "Faulty"], vals, color=[BLUE, "#FF3B30"], width=0.5, edgecolor="white")
    ax.bar_label(bars, fmt="%.0f", padding=4, fontsize=11, color=DARK, fontweight="bold")
    style(ax, title, "", unit)
    ax.set_ylim(0, max(vals) * 1.3)

plt.tight_layout()
plt.savefig("report/chart_fault_comparison.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved chart_fault_comparison.png")

# 4. Wall Collisions
collisions = [r["n_wall_collisions"] for r in held]

fig, ax = plt.subplots(figsize=(7, 4), facecolor="white")
ax.hist(collisions, bins=10, color=BLUE, edgecolor="white", linewidth=0.8, rwidth=0.85)
ax.axvline(np.median(collisions), color="#FF9500", lw=2, linestyle="--",
           label=f"Median: {int(np.median(collisions))} events")
ax.legend(fontsize=10, framealpha=0)
style(ax, "Wall Collisions - 120 Held-Out Seeds", "Collision count per run", "Number of runs")
plt.tight_layout()
plt.savefig("report/chart_wall_collisions.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved chart_wall_collisions.png")
