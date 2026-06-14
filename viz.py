"""
Minimap + control bar + goal-reached overlays inside the MuJoCo viewer.

Overlays pushed via viewer.set_images() each tick:
  1. Minimap      (300×300) — bottom-right corner, above the control bar.
  2. Control bar  (full-width × 52 px) — bottom edge: play/pause | progress | time+dist.
  3. Goal banner  (fullscreen) — shown for 3 s then fades out on goal.

All rendered headlessly with matplotlib Agg.  Space bar toggles pause.
"""

from __future__ import annotations

import base64
import io
from math import cos, sin

import numpy as np


# ── Right-panel boundary detection ────────────────────────────────────────────
_PANEL_START_VP: int | None = None   # cached viewport-x where right panel begins


def _detect_panel_start(vp_width: int, vp_height: int) -> int:
    """Find where the MuJoCo right gray panel starts in viewport coordinates.

    Reads pixel colours from the GLFW window's Win32 DC via GetPixel, then
    binary-searches from the right edge leftward until the 3D scene colour is
    found.  The result is scaled back to viewport coordinates.

    The gray panel has roughly uniform RGB ≈ (50–90, 50–90, 50–90).
    Returns vp_width (no panel detected) on any failure.
    """
    import ctypes

    user32 = ctypes.windll.user32
    gdi32  = ctypes.windll.gdi32

    # ── Locate the GLFW window ────────────────────────────────────────────────
    user32.FindWindowW.restype  = ctypes.c_void_p
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    hwnd = user32.FindWindowW("GLFW30", None)
    if not hwnd:
        return vp_width

    # Client rect gives us physical pixel dimensions (GLFW is DPI-aware).
    class RECT(ctypes.Structure):
        _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                    ('right', ctypes.c_long), ('bottom', ctypes.c_long)]
    rc = RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rc))
    phys_w = rc.right - rc.left
    phys_h = rc.bottom - rc.top
    if phys_w <= 0 or phys_h <= 0:
        return vp_width

    # Scale factor: viewport coords → physical pixels
    scale = phys_w / vp_width

    def _is_panel(phys_x: int) -> bool:
        """True if the pixel at (phys_x, mid) looks like the gray panel."""
        probe_y = phys_h // 2
        dc = user32.GetDC(hwnd)
        cr = gdi32.GetPixel(dc, phys_x, probe_y)
        user32.ReleaseDC(hwnd, dc)
        if cr == 0xFFFFFFFF:            # CLR_INVALID
            return False
        r, g, b = cr & 0xFF, (cr >> 8) & 0xFF, (cr >> 16) & 0xFF
        # Uniform dark-gray: each channel 40–100, channels differ by < 15
        return 40 <= r <= 100 and abs(r - g) < 15 and abs(g - b) < 15

    # Confirm that the rightmost pixel is actually in the panel.
    if not _is_panel(phys_w - 4):
        return vp_width   # right panel not visible

    # Binary search: find leftmost x that is still panel-colored.
    lo_phys = phys_w * 2 // 3   # panel can't be more than 1/3 of window
    hi_phys = phys_w - 4
    for _ in range(12):          # 12 steps → sub-pixel precision
        mid = (lo_phys + hi_phys) // 2
        if _is_panel(mid):
            hi_phys = mid
        else:
            lo_phys = mid

    panel_start_phys = (lo_phys + hi_phys) // 2
    # Convert back to viewport coordinates
    return int(panel_start_phys / scale)


def _panel_start(viewer) -> int:
    """Cached call to _detect_panel_start."""
    global _PANEL_START_VP
    if _PANEL_START_VP is None:
        vp = viewer.viewport
        _PANEL_START_VP = _detect_panel_start(vp.width, vp.height)
    return _PANEL_START_VP


# ── Control bar ────────────────────────────────────────────────────────────────
# _BAR_H is the final viewport height of the bar in pixels.
# BASE_W × _BAR_H is rendered directly (no vertical rescaling), so font sizes
# map 1-to-1 to final pixels.  Only the width is PIL-resized to vp.width.
_BAR_H    = 80    # final bar height in viewport pixels
_BAR_BASE = 1200  # base render width (PIL-resized horizontally to vp.width)

# Background colour — simulates semi-transparency by being dark but not
# pitch-black.  True per-pixel blending requires framebuffer access which
# MuJoCo's Python API does not expose; this is the closest approximation.
_BAR_BG = "#21213a"   # ~0.7-opacity dark navy over a typical blue-grey scene


def _build_control_bar(
    width:    int,
    paused:   bool,
    progress: float,   # 0.0–1.0 path completion
    sim_time: float,
    dist:     float,
) -> np.ndarray:
    """Return (_BAR_H, width, 3) uint8 control-bar image."""
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.patches import Rectangle
    from PIL import Image

    if width <= 0:
        width = 400

    fig = Figure(figsize=(_BAR_BASE / 100, _BAR_H / 100), dpi=100)
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0, 0, 1, 1])
    fig.patch.set_facecolor(_BAR_BG)
    ax.set_facecolor(_BAR_BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Top separator line
    ax.axhline(y=0.96, color="#4a4a7a", linewidth=2.5, xmin=0, xmax=1)

    # ── Play / pause (left) ───────────────────────────────────────────────────
    sym_char  = "▶" if paused else "⏸"
    sym_color = "#ffd54f" if paused else "#ff8c00"
    status    = "PAUSED"  if paused else "RUNNING"

    ax.text(0.030, 0.50, sym_char,
            ha="center", va="center", fontsize=34, color=sym_color,
            transform=ax.transAxes)
    ax.text(0.065, 0.50, status,
            ha="left", va="center", fontsize=15, color=sym_color,
            fontweight="bold", transform=ax.transAxes)

    # ── Progress bar (middle) ─────────────────────────────────────────────────
    BL, BR = 0.18, 0.70   # left / right edges (axes fraction)
    BB, BT = 0.20, 0.70   # bottom / top  — thick band
    bw = BR - BL
    bh = BT - BB
    prog = float(np.clip(progress, 0.0, 1.0))

    # Track (unfilled background)
    ax.add_patch(Rectangle((BL, BB), bw, bh,
                            transform=ax.transAxes,
                            facecolor="#2e2e52", edgecolor="#5a5a8a",
                            linewidth=1.5, clip_on=False))
    # Filled portion
    if prog > 0.001:
        fill_color = "#ff8c00" if prog < 1.0 else "#81c784"
        ax.add_patch(Rectangle((BL, BB), bw * prog, bh,
                                transform=ax.transAxes,
                                facecolor=fill_color, edgecolor="none",
                                clip_on=False))

    # Percentage label centred in bar
    label_x   = BL + bw / 2
    ax.text(label_x, BB + bh / 2, f"{prog * 100:.0f}%",
            ha="center", va="center", fontsize=14,
            color="#0d1a33", fontweight="bold", transform=ax.transAxes)

    # Caption above bar
    ax.text(label_x, BT + 0.07, "PATH PROGRESS",
            ha="center", va="bottom", fontsize=9,
            color="#7777bb", transform=ax.transAxes)

    # ── Time + distance (right) ───────────────────────────────────────────────
    ax.text(0.735, 0.70, f"t = {sim_time:6.1f} s",
            ha="left", va="center", fontsize=15,
            color="#d0d4ff", fontfamily="monospace",
            transform=ax.transAxes)
    ax.text(0.735, 0.24, f"d = {dist:5.2f} m",
            ha="left", va="center", fontsize=15,
            color="#d0d4ff", fontfamily="monospace",
            transform=ax.transAxes)

    fig.canvas.draw()
    w_act, h_act = fig.canvas.get_width_height()
    buf = np.frombuffer(fig.canvas.buffer_rgba(), dtype=np.uint8)
    # h_act == _BAR_H; PIL resize only adjusts width.
    img = buf.reshape(h_act, w_act, 4)[:, :, :3].copy()
    img = np.array(Image.fromarray(img).resize((width, _BAR_H), Image.LANCZOS))
    return img


# ── Goal-reached banner ────────────────────────────────────────────────────────
_GOAL_SHOW_SECS = 3.0
_GOAL_FADE_SECS = 1.0


def _build_goal_banner(width: int, height: int) -> np.ndarray:
    """Return (height, width, 3) uint8 fullscreen 'GOAL REACHED! ✓' image.

    Rendered directly at (width × height) so font sizes are proportional to
    the actual viewport and the text is guaranteed to fit.
    """
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from PIL import Image

    dpi = 100
    fig = Figure(figsize=(width / dpi, height / dpi), dpi=dpi)
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0, 0, 1, 1])
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#0d1117")
    ax.axis("off")

    # Scale fonts so "GOAL REACHED! ✓" always fits within the viewport width.
    # width // 16 keeps the text to ~65 % of the canvas width at any resolution.
    fs_main = max(28, width // 16)
    fs_sub  = max(14, width // 55)

    ax.text(0.50, 0.57, "GOAL REACHED!  ✓",
            transform=ax.transAxes,
            ha="center", va="center",
            fontsize=fs_main, color="#ffd54f", fontweight="bold",
            clip_on=False)
    ax.text(0.50, 0.37, "navigation complete",
            transform=ax.transAxes,
            ha="center", va="center",
            fontsize=fs_sub, color="#aaaacc",
            clip_on=False)

    fig.canvas.draw()
    w_act, h_act = fig.canvas.get_width_height()
    buf = np.frombuffer(fig.canvas.buffer_rgba(), dtype=np.uint8)
    img = buf.reshape(h_act, w_act, 4)[:, :, :3].copy()

    # PIL resize only if matplotlib rounded the figsize slightly.
    if (w_act, h_act) != (width, height):
        img = np.array(Image.fromarray(img).resize((width, height), Image.LANCZOS))
    return img


class Visualizer:
    """
    Minimap + control bar + goal-reached overlay for the MuJoCo passive viewer.

    Usage::

        viz = Visualizer(model, occ_nav, path, goal_xy)
        # inside viewer loop at UPDATE_HZ:
        viz.update(viewer, x_est, y_est, theta_est, sim_time, paused=False)
        viz.close()
    """

    MAP_SIZE      = 300
    DASH_MAP_SIZE = 500
    MARGIN        = 10
    UPDATE_HZ     = 5

    def __init__(self, model, occ_nav, path, goal_xy) -> None:
        self._occ_nav = occ_nav
        self._path    = path
        self._goal_xy = goal_xy

        # path arrays for fast nearest-waypoint lookup
        if len(path) >= 2:
            self._path_xs = np.array([p[0] for p in path], dtype=float)
            self._path_ys = np.array([p[1] for p in path], dtype=float)
        else:
            self._path_xs = self._path_ys = np.array([])

        self._fig       = None
        self._canvas    = None
        self._map_px    = 0
        self._traj_line = self._robot_dot = self._robot_dir = self._status = None

        self._traj_x: list[float] = []
        self._traj_y: list[float] = []

        self._goal_reached_time: float | None = None
        self._goal_banner:       np.ndarray | None = None
        self._goal_banner_size:  tuple[int, int] = (0, 0)

        self._minimap_b64: str | None = None

        # Separate figure for the browser dashboard (larger, dashboard-styled)
        self._dash_fig          = None
        self._dash_canvas       = None
        self._dash_map_px       = 0
        self._dash_traj_line    = self._dash_robot_dot = self._dash_robot_dir = None

        import mujoco as _mj
        self._mujoco = _mj

    @property
    def minimap_b64(self) -> str | None:
        """Latest minimap frame encoded as JPEG base64, or None before first render."""
        return self._minimap_b64

    def notify_goal(self, sim_time: float) -> None:
        """Call once when the robot reaches the goal."""
        if self._goal_reached_time is None:
            self._goal_reached_time = sim_time

    def _path_progress(self, x: float, y: float) -> float:
        if self._path_xs.size < 2:
            return 0.0
        dists = np.hypot(self._path_xs - x, self._path_ys - y)
        return float(np.argmin(dists)) / (len(self._path_xs) - 1)

    def _build(self, map_px: int) -> None:
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        self._map_px = map_px
        fig = Figure(figsize=(map_px / 100, map_px / 100), dpi=100)
        FigureCanvasAgg(fig)
        ax = fig.add_axes([0, 0, 1, 1])   # fill entire figure, no margins
        fig.patch.set_facecolor("#0f0f23")
        ax.set_facecolor("#0f0f23")

        occ = self._occ_nav
        extent = [
            occ.x_min, occ.x_min + occ.W * occ.res,
            occ.y_min, occ.y_min + occ.H * occ.res,
        ]
        ax.imshow(occ.grid, origin="lower", extent=extent,
                  cmap="gray_r", vmin=0, vmax=100, aspect="equal", alpha=0.85)
        if len(self._path) >= 2:
            px, py = zip(*self._path)
            ax.plot(px, py, color="#4fc3f7", lw=1.5, alpha=0.7, zorder=2)
        gx, gy = self._goal_xy
        ax.scatter([gx], [gy], c="#ffd54f", s=100, marker="*", zorder=4)
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])
        ax.axis("off")   # hide ticks, labels, spines — maze fills the full image
        fs = max(6, map_px // 55)

        self._traj_line, = ax.plot([], [], ".", color="#66bb6a",
                                   markersize=2, alpha=0.5, zorder=3)
        self._robot_dot, = ax.plot([], [], "o", color="#ef5350",
                                   markersize=max(4, map_px // 45), zorder=5)
        self._robot_dir, = ax.plot([], [], "-", color="#ef5350",
                                   lw=max(2, map_px // 120), zorder=5)
        self._status = ax.text(
            0.03, 0.97, "", transform=ax.transAxes,
            fontsize=fs, va="top", color="white",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#0f0f23", alpha=0.75),
            zorder=6,
        )
        self._fig    = fig
        self._canvas = fig.canvas

    def _build_dash(self, map_px: int) -> None:
        """Build a separate, larger matplotlib figure for the browser dashboard."""
        from matplotlib.colors import LinearSegmentedColormap
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        self._dash_map_px = map_px
        fig = Figure(figsize=(map_px / 100, map_px / 100), dpi=100)
        FigureCanvasAgg(fig)
        ax = fig.add_axes([0, 0, 1, 1])

        bg = "#0e1928"   # card background — free space blends into card
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)

        # Custom colormap: free space (0) = card bg, walls (100) = light blue-grey
        maze_cmap = LinearSegmentedColormap.from_list(
            "maze_dash", [bg, "#c5d8f0"], N=256
        )

        occ = self._occ_nav
        extent = [
            occ.x_min, occ.x_min + occ.W * occ.res,
            occ.y_min, occ.y_min + occ.H * occ.res,
        ]
        ax.imshow(occ.grid, origin="lower", extent=extent,
                  cmap=maze_cmap, vmin=0, vmax=100, aspect="equal")
        if len(self._path) >= 2:
            px, py = zip(*self._path)
            ax.plot(px, py, color="#4fc3f7", lw=2.5, alpha=0.6, zorder=2)
        gx, gy = self._goal_xy
        ax.scatter([gx], [gy], c="#ffd54f", s=220, marker="*", zorder=4)
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])
        ax.axis("off")

        self._dash_traj_line, = ax.plot([], [], ".", color="#66bb6a",
                                        markersize=3, alpha=0.6, zorder=3)
        self._dash_robot_dot, = ax.plot([], [], "o", color="#ef5350",
                                        markersize=max(8, map_px // 35), zorder=5)
        self._dash_robot_dir,     = ax.plot([], [], "-", color="#ef5350",
                                            lw=max(3, map_px // 80), zorder=5)
        self._dash_fig    = fig
        self._dash_canvas = fig.canvas

    def update(
        self,
        viewer,
        x_est:       float,
        y_est:       float,
        theta_est:   float,
        sim_time:    float,
        paused:      bool = False,
    ) -> None:
        vp = viewer.viewport

        if self._fig is None or self.MAP_SIZE != self._map_px:
            self._build(self.MAP_SIZE)

        # ── Minimap ───────────────────────────────────────────────────────────
        self._traj_x.append(x_est)
        self._traj_y.append(y_est)
        self._traj_line.set_data(self._traj_x, self._traj_y)
        self._robot_dot.set_data([x_est], [y_est])
        dx, dy = cos(theta_est) * 0.4, sin(theta_est) * 0.4
        self._robot_dir.set_data([x_est, x_est + dx], [y_est, y_est + dy])
        gx, gy = self._goal_xy
        dist = np.hypot(x_est - gx, y_est - gy)
        self._status.set_text(
            f"t={sim_time:.0f}s  d={dist:.1f}m\n"
            f"({x_est:.1f}, {y_est:.1f})"
        )
        self._canvas.draw()
        mw, mh = self._canvas.get_width_height()
        buf = np.frombuffer(self._canvas.buffer_rgba(), dtype=np.uint8)
        map_img = buf.reshape(mh, mw, 4)[:, :, :3].copy()

        # ── Dashboard minimap (separate larger figure, dashboard-styled) ────────
        if self._dash_fig is None or self.DASH_MAP_SIZE != self._dash_map_px:
            self._build_dash(self.DASH_MAP_SIZE)

        self._dash_traj_line.set_data(self._traj_x, self._traj_y)
        self._dash_robot_dot.set_data([x_est], [y_est])
        self._dash_robot_dir.set_data([x_est, x_est + dx], [y_est, y_est + dy])

        self._dash_canvas.draw()
        dw, dh = self._dash_canvas.get_width_height()
        dbuf = np.frombuffer(self._dash_canvas.buffer_rgba(), dtype=np.uint8)
        dash_img = dbuf.reshape(dh, dw, 4)[:, :, :3].copy()

        try:
            from PIL import Image as _PILImage
            _bio = io.BytesIO()
            _PILImage.fromarray(dash_img).save(_bio, format="JPEG", quality=80)
            self._minimap_b64 = base64.b64encode(_bio.getvalue()).decode()
        except Exception:
            pass

        MjrRect = self._mujoco.MjrRect

        # Minimap: upper portion of the right gray panel.
        # Detect the panel's left edge once via pixel-colour binary search,
        # then place the 300×300 map centred horizontally in the panel with
        # a small top margin.
        ps = _panel_start(viewer)
        panel_w = vp.width - ps
        map_left = ps + max(0, (panel_w - mw) // 2)   # centre in panel
        map_rect = MjrRect(
            left   = map_left,
            bottom = vp.height - mh - self.MARGIN,     # upper portion
            width  = mw,
            height = mh,
        )

        # ── Control bar (full width, bottom edge) ─────────────────────────────
        progress = self._path_progress(x_est, y_est)
        bar_img  = _build_control_bar(vp.width, paused, progress, sim_time, dist)
        bh, bw   = bar_img.shape[:2]
        bar_rect = MjrRect(left=0, bottom=0, width=bw, height=bh)

        overlays = [(map_rect, map_img), (bar_rect, bar_img)]

        # ── Goal banner (fullscreen, fades out) ───────────────────────────────
        if self._goal_reached_time is not None:
            elapsed = sim_time - self._goal_reached_time
            if elapsed < _GOAL_SHOW_SECS:
                if self._goal_banner_size != (vp.width, vp.height):
                    self._goal_banner = _build_goal_banner(vp.width, vp.height)
                    self._goal_banner_size = (vp.width, vp.height)

                alpha = 1.0
                fade_start = _GOAL_SHOW_SECS - _GOAL_FADE_SECS
                if elapsed > fade_start:
                    alpha = 1.0 - (elapsed - fade_start) / _GOAL_FADE_SECS

                goal_img  = (self._goal_banner * alpha).astype(np.uint8)
                gh, gw    = goal_img.shape[:2]
                goal_rect = MjrRect(left=0, bottom=0, width=gw, height=gh)
                overlays.append((goal_rect, goal_img))

        try:
            viewer.set_images(overlays)
        except Exception:
            pass

    def close(self) -> None:
        if self._fig is not None:
            try:
                import matplotlib.pyplot as plt
                plt.close(self._fig)
            except Exception:
                pass
