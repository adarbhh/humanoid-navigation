"""
Pure-pursuit local controller.

Given a list of (x, y) waypoints and the robot's current pose (x, y, theta),
returns (vx, vy, yaw_rate) velocity commands in the robot body frame.

vx       = forward velocity  (m/s)
vy       = lateral velocity  (m/s) — kept 0 (forward locomotion only)
yaw_rate = turning rate      (rad/s)
"""

from __future__ import annotations

import numpy as np


class PurePursuitController:
    def __init__(
        self,
        lookahead:  float = 0.8,   # lookahead distance (m)
        max_vx:     float = 0.35,  # max forward speed  (m/s)
        max_yaw:    float = 1.0,   # max yaw rate       (rad/s)
        goal_tol:   float = 0.35,  # goal-reached radius (m)
        slow_angle: float = 0.6,   # start slowing when heading error > this (rad)
    ) -> None:
        self.lookahead  = lookahead
        self.max_vx     = max_vx
        self.max_yaw    = max_yaw
        self.goal_tol   = goal_tol
        self.slow_angle = slow_angle

        self._waypoints: list[tuple[float, float]] = []
        self._wp_idx: int = 0

    def set_path(self, waypoints: list[tuple[float, float]]) -> None:
        self._waypoints = waypoints
        self._wp_idx    = 0

    @property
    def goal_reached(self) -> bool:
        if not self._waypoints:
            return True
        gx, gy = self._waypoints[-1]
        return False  # checked inside step(); caller uses return value

    def step(
        self,
        x: float,
        y: float,
        theta: float,
        lidar_ranges: "np.ndarray | None" = None,
        lidar_angles: "np.ndarray | None" = None,
    ) -> tuple[float, float, float]:
        """
        Returns (vx, vy, yaw_rate).  Returns (0, 0, 0) when goal is reached
        or path is empty.

        lidar_ranges / lidar_angles are accepted for API compatibility but are
        no longer used for reactive corrections — the A* path is pre-centred in
        corridors so no reactive steering is needed.
        """
        if not self._waypoints:
            return 0.0, 0.0, 0.0

        # Goal reached?
        gx, gy = self._waypoints[-1]
        if np.hypot(x - gx, y - gy) < self.goal_tol:
            return 0.0, 0.0, 0.0

        # Advance _wp_idx once the robot has passed the current waypoint.
        # Two conditions (either triggers advancement):
        #   1. d_to_wp < lookahead  — robot is close enough to the waypoint.
        #   2. proj > 0 AND perp < 0.7 m — robot has crossed the waypoint's
        #      perpendicular plane while staying within the corridor width.
        #      The perp guard prevents advancing when the robot is far to the
        #      side of the segment (e.g. still in a perpendicular corridor).
        while self._wp_idx < len(self._waypoints) - 1:
            wx, wy = self._waypoints[self._wp_idx]
            nx, ny = self._waypoints[self._wp_idx + 1]
            seg_len = np.hypot(nx - wx, ny - wy)
            if seg_len < 1e-6:
                self._wp_idx += 1
                continue
            d_to_wp = np.hypot(x - wx, y - wy)
            if d_to_wp < self.lookahead:
                self._wp_idx += 1
                continue
            proj = ((x - wx) * (nx - wx) + (y - wy) * (ny - wy)) / seg_len
            perp = abs((x - wx) * (ny - wy) - (y - wy) * (nx - wx)) / seg_len
            if proj > 0 and perp < 0.7:
                self._wp_idx += 1
            else:
                break

        # Steer toward the current target waypoint
        tx, ty = self._waypoints[self._wp_idx]
        target_angle = np.arctan2(ty - y, tx - x)
        err = target_angle - theta
        err = (err + np.pi) % (2 * np.pi) - np.pi  # wrap to [-π, π]

        yaw_rate = float(np.clip(err * 2.5, -self.max_yaw, self.max_yaw))

        # Smoothly blend forward speed with heading error — never fully stop.
        # At |err| = 0   → full speed; at |err| = π → 15% speed.
        # cos² gives a natural bell that drops quickly past 90° yet keeps
        # the robot creeping forward so it never stalls mid-turn.
        turn_factor = max(0.25, np.cos(err / 2) ** 2)
        vx = self.max_vx * turn_factor

        return vx, 0.0, yaw_rate

    def _wall_react(
        self,
        vx: float,
        yaw_rate: float,
        ranges: "np.ndarray",
        angles: "np.ndarray",
        pivoting: bool,
    ) -> tuple[float, float]:
        """
        Two LiDAR-driven corrections applied on top of pure pursuit:

        1. Forward slowdown: reduce speed when a wall is close ahead so the
           robot has time to turn rather than crashing into it.

        2. Corridor centering: compare left-side vs right-side wall distance
           and add a small yaw nudge to keep the robot in the middle.
           Only active when not pivoting and both side walls are visible.
        """
        NO_HIT = 9.9  # rangefinder returns ~cutoff when nothing is in range

        # ── 1. Forward obstacle slowdown ─────────────────────────────────────
        if not pivoting:
            fwd_mask = np.abs(angles) < np.deg2rad(20)
            fwd = ranges[fwd_mask]
            fwd = fwd[(fwd > 0.15) & (fwd < NO_HIT)]
            if fwd.size:
                min_fwd = float(fwd.min())
                SLOW_START = 0.6   # begin slowing at this distance (m)
                STOP_DIST  = 0.35
                if min_fwd < SLOW_START:
                    scale = max(0.2, (min_fwd - STOP_DIST) / (SLOW_START - STOP_DIST))
                    vx *= scale

        # ── 2. Corridor centering ─────────────────────────────────────────────
        # Rays near ±90° (sideways); skip during hard turns to avoid fighting corners.
        if not pivoting and abs(yaw_rate) < 0.5 * self.max_yaw:
            tol = np.deg2rad(25)
            right_mask = (angles > -(np.pi / 2 + tol)) & (angles < -(np.pi / 2 - tol))
            left_mask  = (angles >  (np.pi / 2 - tol)) & (angles <  (np.pi / 2 + tol))

            r_raw = ranges[right_mask]
            l_raw = ranges[left_mask]
            r_valid = r_raw[(r_raw > 0.15) & (r_raw < 2.0)]
            l_valid = l_raw[(l_raw > 0.15) & (l_raw < 2.0)]

            if r_valid.size and l_valid.size:
                r_dist = float(r_valid.mean())
                l_dist = float(l_valid.mean())
                # Positive error: right wall closer → nudge left (positive yaw).
                # Gain doubled (0.4→0.8) and cap raised so the correction is
                # strong enough to re-centre before the robot touches the wall.
                center_err = r_dist - l_dist
                correction = float(np.clip(center_err * 0.8, -0.4, 0.4))
                yaw_rate   = float(np.clip(
                    yaw_rate + correction, -self.max_yaw, self.max_yaw))

        return vx, yaw_rate

    def _lookahead_point(
        self, x: float, y: float
    ) -> tuple[float, float]:
        """First waypoint at or beyond lookahead distance, or the last waypoint."""
        for i in range(self._wp_idx, len(self._waypoints)):
            wx, wy = self._waypoints[i]
            if np.hypot(x - wx, y - wy) >= self.lookahead:
                return wx, wy
        return self._waypoints[-1]
