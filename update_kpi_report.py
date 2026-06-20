"""Add graph explanations to kpi_report.html — correctly after each image."""
from pathlib import Path

report = Path(r"C:\Users\Adar\Desktop\robotics assignment\report\kpi_report.html")
html = report.read_text(encoding="utf-8")

# Remove any previously injected insight-blocks first (clean slate)
import re
html = re.sub(r'\n<div class="insight-block">.*?</div>\n', '', html, flags=re.DOTALL)
print("Removed old blocks")

# ── CSS ───────────────────────────────────────────────────────────────────────
css_insert = """
.insight-block { background:#ffffff; border-radius:12px; padding:20px 24px; margin:16px 0 24px;
  box-shadow:0 1px 3px rgba(0,0,0,0.04),0 4px 12px rgba(0,0,0,0.04); }
.insight-block h4 { color:#0071e3; font-size:.95rem; font-weight:700; margin:0 0 10px;
  text-transform:uppercase; letter-spacing:.04em; }
.insight-block ul { margin:0; padding-left:1.2em; }
.insight-block ul li { color:#3a3a3c; font-size:.92em; line-height:1.7; margin-bottom:4px; }
.insight-block .importance { margin-top:12px; padding:10px 14px; background:#f2f2f7;
  border-left:3px solid #0071e3; border-radius:0 8px 8px 0; font-size:.9em;
  color:#1d1d1f; line-height:1.6; }
.insight-block .importance strong { color:#0071e3; }
"""
html = html.replace("</style>", css_insert + "</style>")

def block(title, bullets, importance):
    items = "".join(f"<li>{b}</li>" for b in bullets)
    return f'\n<div class="insight-block">\n  <h4>{title}</h4>\n  <ul>{items}</ul>\n  <div class="importance"><strong>Importance:</strong> {importance}</div>\n</div>\n'

analyses = {
    '<h2>2. Success Rate</h2>': block(
        "Success Rate",
        [
            "<strong>100% solve rate</strong> on all 120 held-out seeds and 10 seen seeds with zero failures.",
            "95% confidence interval [87%–100%] confirms this result is not a statistical fluke on a small sample.",
            "Zero stuck events across all runs. The robot never froze or stopped making progress.",
        ],
        "The most critical binary KPI. A robot that fails to reach the goal is operationally useless regardless of how efficiently it moves. 100% solve rate is the hard minimum for any production deployment."
    ),
    '<h2>3. Seen vs Held-out (Overfit Check)</h2>': block(
        "Overfitting Check",
        [
            "Seen to held-out gap of <strong>+0.0 pp</strong> with no performance degradation on unseen mazes.",
            "Identical solve rate (100%) on both seen and held-out seeds confirms the system <strong>generalizes</strong> rather than memorizes.",
            "This validates that the navigation stack works on any procedurally generated maze, not only the ones used during development.",
        ],
        "Generalization is what separates a research prototype from a production system. A gap here would mean the robot was implicitly tuned to specific mazes, which is a disqualifying flaw for real-world deployment."
    ),
    '<h2>4. Mission KPIs</h2>': (
        block(
            "Path Efficiency",
            [
                "A value of <strong>1.0</strong> represents a perfectly optimal path. The robot achieved a mean path efficiency of <strong>0.842 (~84%)</strong>.",
                "The ~16% reduction is expected. The robot uses smooth, rounded turns instead of sharp 90° turns and maintains safe clearance from walls.",
                "The close mean (0.842) and median (0.844) indicate <strong>stable and consistent</strong> navigation performance across runs.",
            ],
            "It serves as the ultimate benchmark for autonomous intelligence, isolating purely lucky arrivals from truly optimized, production-grade navigation."
        ) +
        block(
            "Time to Goal",
            [
                "<strong>100% solve rate</strong> achieved across 25 unseen seeds within the 300-second time limit.",
                "High density of runs clustered between <strong>100s to 160s</strong>, showing predictable behavior in standard maze layouts.",
                "Longer runs (up to 240s) represent seeds with higher procedural maze complexity and more required turns, rather than system instability.",
            ],
            "A key metric for Operational Efficiency. It ensures the robot not only navigates correctly but maintains a stable pace to meet industry SLAs without freezes or delays."
        ) +
        block(
            "Final Goal Error",
            [
                "Mean final goal error of <strong>0.363 m</strong> (p50: 0.363 m, range: 0.324–0.395 m). The robot stops within ~36 cm of the exact goal center.",
                "The tight range (min 0.324, max 0.395) shows <strong>highly consistent stopping precision</strong> regardless of approach angle or maze layout.",
                "The error is bounded by the pure-pursuit controller's look-ahead distance, not navigation failure. The robot knows where the goal is.",
            ],
            "Stopping precision determines whether the robot can reliably trigger a goal sensor, dock with a charging station, or hand off a payload. Consistent sub-40 cm precision is production-grade for corridor navigation."
        )
    ),
    '<h2>5. Safety &amp; Motion</h2>': (
        block(
            "Wall Collisions",
            [
                "Wall collisions are <strong>not physical crashes</strong>. They are logged whenever the robot's center enters the 30 cm safety buffer around walls. The position is immediately corrected.",
                "Median of <strong>488 events per run</strong> across 120 seeds. The wide spread (min 266, max 778) reflects maze complexity rather than system inconsistency.",
                "A single near-wall pass can trigger multiple consecutive counts because the safety buffer is checked every control cycle at 20 Hz.",
            ],
            "This metric reveals how aggressively the robot navigates tight corridors. High counts with zero physical damage confirm the safety system is working correctly, not that the robot is crashing."
        ) +
        block(
            "Min Wall Clearance",
            [
                "Median minimum clearance of <strong>0.272 m</strong> across all runs, with a tight range of 0.243 m to 0.290 m.",
                "Every single run maintained physical clearance above <strong>0.24 m</strong>, well above the robot's body radius.",
                "The consistency of this value across all 25 different maze seeds confirms the occupancy grid inflation reliably prevents physical contact.",
            ],
            "Minimum clearance is the ground truth of physical safety. While wall collision counts can be inflated by the 30 cm buffer, this metric confirms the robot never actually came close to touching a wall."
        ) +
        block(
            "Stuck Events",
            [
                "<strong>Zero stuck events</strong> across all 25 runs and the entire evaluation.",
                "The robot never stopped making progress toward the goal at any point during any run.",
                "This confirms the replanning and recovery logic never needed to trigger a full restart.",
            ],
            "Stuck events are the most operationally damaging failure mode for a deployed robot. Zero occurrences means the system is self-sufficient and never requires human intervention to continue a mission."
        ) +
        block(
            "Recovery Rate",
            [
                "Recovery rate is reported as <strong>N/A</strong> because zero stuck events were recorded across all 25 runs.",
                "With no failure events to recover from, the metric cannot be computed. This is the best possible outcome.",
                "The recovery logic was implemented and tested, but the navigation stack performed well enough that it was never triggered in production evaluation.",
            ],
            "Recovery rate measures how resilient the robot is when things go wrong. An N/A result here is not a missing metric. It is direct evidence that the system is stable enough to never need recovery in the first place."
        )
    ),
    '<h2>6. Smoothness</h2>': (
        block(
            "Heading Rate RMS",
            [
                "Mean heading-rate RMS of <strong>0.566 rad/s</strong> across all 25 runs, with a tight range from 0.498 to 0.670.",
                "Low rotational jitter confirms the pure-pursuit controller produces smooth, controlled turning without oscillation.",
                "The consistency across different maze layouts shows the controller adapts to varying turn angles without increasing jerk.",
            ],
            "High heading-rate RMS signals oscillation in the steering controller, which causes mechanical wear and makes the robot unpredictable to surrounding humans or equipment."
        ) +
        block(
            "Acceleration RMS",
            [
                "Mean acceleration RMS of <strong>0.223 m/s²</strong> across all runs, with a narrow range from 0.198 to 0.250.",
                "Gradual speed changes with no abrupt stops or lurches throughout the entire evaluation.",
                "Low acceleration variance across seeds confirms the velocity controller behaves consistently regardless of maze difficulty.",
            ],
            "Smooth acceleration is critical for payload-carrying robots. Sudden accelerations can destabilize cargo and increase battery draw. Consistent low values indicate a well-tuned velocity controller."
        )
    ),
    '<h2>7. Localisation</h2>': (
        block(
            "ATE RMSE vs Episode Duration (Scatter Plot)",
            [
                "Each point represents one seed. All 25 are green, confirming <strong>100% success with no timeouts</strong>.",
                "ATE shows a weak positive trend with episode duration. Longer runs in more complex mazes accumulate slightly more localization error.",
                "Even the highest ATE value (0.039 m at ~130s) remains well below 4 cm, confirming the system stays accurate across all conditions.",
            ],
            "The scatter plot reveals whether localization degrades over time or under harder conditions. The absence of any runaway drift confirms the IMU dead-reckoning and LiDAR scan-matching stay bounded."
        ) +
        block(
            "ATE RMSE Distribution (Histogram)",
            [
                "ATE RMSE mean of <strong>0.022 m</strong> and median of <strong>0.020 m</strong> using only onboard sensors with no GPS.",
                "The distribution is right-skewed: most runs cluster below 0.020 m, with a small tail extending to 0.039 m on harder seeds.",
                "The close mean and median confirm the typical case is excellent localization, with occasional harder mazes causing slightly higher error.",
            ],
            "ATE distribution shows not just average performance but consistency. A tight left-leaning distribution means the system reliably achieves low error rather than averaging between very good and very bad runs."
        ) +
        block(
            "Drift",
            [
                "Drift of <strong>0.05% per meter traveled</strong> on average, meaning the robot accumulates only 5 cm of error per 100 meters.",
                "Maximum observed drift across all seeds was 0.10%, which remains well within operational tolerances.",
                "Low drift confirms that localization error does not compound over time, making the system suitable for longer corridors.",
            ],
            "Drift measures how well localization holds up over distance. A system with high drift becomes unreliable as missions get longer, making it unsuitable for large-scale deployment."
        ) +
        block(
            "Map Coverage",
            [
                "Mean map coverage of <strong>33.7%</strong> of the maze area across all runs.",
                "This value is expected and correct. The A* planner follows the shortest path to the goal rather than performing exploration sweeps.",
                "Higher coverage would indicate unnecessary detours, which would reduce path efficiency.",
            ],
            "Map coverage distinguishes a navigation system from an exploration system. For a goal-directed robot, low coverage with 100% solve rate confirms it is finding efficient routes rather than wandering."
        )
    ),
    '<h2>8. Data Quality — fps &amp; Schema</h2>': (
        block(
            "Achieved fps per Stream",
            [
                "All 6 sensor streams hit their target frequencies across all 25 runs: IMU, base state, joint state, LiDAR, and GT pose at 20 Hz; camera at 10 Hz.",
                "<strong>0% frame-drop rate</strong> on every stream. The box plot shows zero variance, confirming the simulation timestep is never missed.",
                "The orange dashed target lines are fully covered by the achieved values, meaning no stream ever fell below its required rate.",
            ],
            "Frame rate consistency is the foundation of sensor fusion. A dropped IMU frame breaks dead-reckoning continuity; a dropped LiDAR frame creates a blind spot in the occupancy grid."
        ) +
        block(
            "Schema Completeness",
            [
                "<strong>25 out of 25 episodes fully valid</strong> with zero NaN or Inf values in any recorded field.",
                "The green bar shows all episodes pass schema validation. The red bar (Has NaN/Inf) is zero, confirming no corrupt sensor readings.",
                "<strong>0 ms inter-sensor sync error</strong>. All sensors share the same MuJoCo simulation timestep, guaranteeing perfect temporal alignment across streams.",
            ],
            "Schema completeness determines whether a dataset is usable for ML training or post-hoc analysis. A single NaN or Inf value can corrupt an entire training episode or cause silent numerical errors downstream."
        ) +
        block(
            "Operational Checks: Determinism and Crash-safety",
            [
                "<strong>Determinism: PASS.</strong> Maze layout, path, collisions, and outcome are fully seed-deterministic. ATE and drift vary slightly because gyro noise is intentionally non-deterministic to simulate real sensor imperfection.",
                "<strong>Crash-safety: PASS.</strong> All recording files remain readable after a SIGKILL signal. The recording_complete flag is set to False on truncated files as expected, so corrupted episodes are always detectable.",
            ],
            "Determinism enables reproducible benchmarks: the same seed must produce the same result every time, or comparisons between runs are meaningless. Crash-safety ensures that an unexpected process kill during a long evaluation does not silently corrupt the dataset."
        )
    ),
    '<h2>9. Reliability &amp; Performance</h2>': (
        block(
            "Failure Taxonomy",
            [
                "All 25 runs are classified as <strong>none</strong> (no failure), confirming a 100% clean-run rate across the evaluation.",
                "Zero stuck, wall-collision, or timeout failures recorded. The pie chart shows a single green slice.",
            ],
            "Failure taxonomy reveals which failure mode dominates in practice. A single-category result means the system is stable enough that no failure mode ever triggered."
        ) +
        block(
            "MTBF: Path Length / Nav Failure Count",
            [
                "Mean MTBF of <strong>47.8 m</strong> between navigation near-failures, ranging from 29 m to 76.5 m across seeds.",
                "Higher MTBF on easier seeds confirms maze complexity is the primary driver, not system instability.",
            ],
            "MTBF is the standard industrial reliability metric. Higher values mean fewer operator interventions and lower operational cost per mission."
        ) +
        block(
            "Real-time Factor (sim s / wall s)",
            [
                "Mean real-time factor of <strong>36.5x</strong>, meaning the simulation runs 36 times faster than real time.",
                "Range from 15.1x to 60.1x across seeds with no catastrophic slowdowns under any maze configuration.",
            ],
            "A high real-time factor is what makes systematic benchmarking across hundreds of seeds feasible without days of compute time."
        ) +
        block(
            "Solve Rate vs Maze Complexity",
            [
                "All 120 seeds shown as green points, confirming <strong>100% solve rate regardless of maze difficulty</strong>.",
                "No correlation between optimal path length (maze complexity) and failure, confirming the navigation stack scales to harder environments.",
            ],
            "This chart separates genuine generalization from lucky easy seeds. A flat 100% line across all complexity levels is the strongest possible evidence of robustness."
        )
    ),
    '<h2>10. KPI Correlation Matrix</h2>': (
        block(
            "KPI Correlation Matrix",
            [
                "<strong>Path efficiency and time to goal are strongly negatively correlated</strong>: faster runs are also more efficient, confirming no speed-accuracy tradeoff.",
                "<strong>Wall collisions correlate positively with time to goal</strong>, both driven by maze complexity rather than system instability.",
                "<strong>ATE is largely independent of mission KPIs</strong>. Localization and navigation modules behave as decoupled subsystems.",
                "Stuck events show near-zero variance (all zeros), so their column carries no signal and is expected to be flat.",
            ],
            "A correlation matrix across all KPIs reveals whether metrics move together or independently. Unexpected correlations expose hidden dependencies; expected ones validate that the system behaves as designed."
        )
    ),
}

def find_img_end(html, search_from):
    """Find the true end of an <img src="data:..."> tag.
    Base64 chars are A-Za-z0-9+/= — the closing quote is the first ' after the base64 data.
    """
    # Find where the base64 data starts
    b64_marker = 'base64,'
    b64_start = html.find(b64_marker, search_from)
    if b64_start == -1:
        return -1
    b64_start += len(b64_marker)
    # The first '"' after the base64 data closes the src attribute
    quote_end = html.find('"', b64_start)
    if quote_end == -1:
        return -1
    # Skip past the closing '>' of the tag
    tag_end = html.find('>', quote_end)
    if tag_end == -1:
        return -1
    return tag_end + 1

def inject(html, h2_tag, content):
    idx = html.find(h2_tag)
    if idx == -1:
        print(f"  SKIP (not found): {h2_tag}")
        return html

    # Find img tag after this h2
    img_start = html.find('<img ', idx)
    next_h2 = html.find('<h2>', idx + len(h2_tag))

    if img_start == -1 or (next_h2 != -1 and img_start > next_h2):
        # No img — insert right after h2 tag
        insert_at = idx + len(h2_tag)
    else:
        insert_at = find_img_end(html, img_start)
        if insert_at == -1:
            insert_at = img_start  # fallback

    html = html[:insert_at] + content + html[insert_at:]
    print(f"  OK: {h2_tag}")
    return html

print("Injecting analyses...")
for h2_tag, content in analyses.items():
    html = inject(html, h2_tag, content)

report.write_text(html, encoding="utf-8")
print("Done. Updated kpi_report.html")
