import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

normal = [3,6,5,9,7,4,3,4,4,3,3,4,5,7,6,7,5,5,4,3,1,0,3,4,5,4,4,3,3,4,7,6,5,0]
faulty = [4,7,6,9,8,6,5,6,5,6,6,5,7,6,7,6,7,7,6,7,6,5,7,9,7,6,6,5,4,5,6,5,5,5,4,5,6,4,4,5,4,3]

t_normal = [i*5 for i in range(len(normal))]
t_faulty = [i*5 for i in range(len(faulty))]

fig, ax = plt.subplots(figsize=(10, 4.5))
fig.patch.set_facecolor('#FAFAFA')
ax.set_facecolor('#FAFAFA')

ax.plot(t_normal, normal, color='#378ADD', linewidth=2, label='Normal run')
ax.plot(t_faulty, faulty, color='#E24B4A', linewidth=2, label='Faulty run')

overlap_normal = normal
overlap_faulty = faulty[:len(normal)]
diff = [max(0, f - n) for f, n in zip(overlap_faulty, overlap_normal)]
ax.fill_between(t_normal, overlap_normal, [n + d for n, d in zip(overlap_normal, diff)],
                alpha=0.15, color='#E24B4A', label='Excess (faulty − normal)')

extra_t = t_faulty[len(normal):]
extra_v = faulty[len(normal):]
ax.fill_between(extra_t, 0, extra_v, alpha=0.10, color='#E24B4A')

ax.set_xlabel('Time (s)', fontsize=12, color='#444')
ax.set_ylabel('Collisions / 5 s', fontsize=12, color='#444')
ax.set_title('Wall collision rate: normal vs faulty run', fontsize=14, fontweight='bold', color='#222', pad=12)
ax.set_ylim(0, 10.5)
ax.set_xlim(0, 210)
ax.tick_params(colors='#666')
for spine in ax.spines.values():
    spine.set_edgecolor('#DDD')
ax.grid(axis='y', color='#DDD', linewidth=0.5, linestyle='--')
ax.legend(fontsize=11, framealpha=0.7)

plt.tight_layout()
plt.savefig(r'C:\Users\Adar\Desktop\robotics assignment\report\chart_collision_rate_comparison.png', dpi=150, bbox_inches='tight')
print("Saved.")
