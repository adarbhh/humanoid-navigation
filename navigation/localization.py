"""
Dead-reckoning localizer: integrates IMU gyro for heading, commanded
velocities for position.  No ground-truth pose consumed — compliant with
the hard assignment constraint.

Why commanded velocity instead of IMU accelerometer?
  Double-integrating accelerometer readings accumulates ~O(t²) position
  error within seconds.  Commanded velocity is the best odometry source
  available without a wheel encoder.  Gyro (single-integration) is
  accurate enough for heading over a single maze run (~2-5 min).
"""

from __future__ import annotations

import numpy as np


class Localizer:
    def __init__(
        self,
        x0: float = 0.0,
        y0: float = 0.0,
        theta0: float = 0.0,
        gyro_noise_std: float = 0.005,   # rad/s — simulate realistic drift
        rng_seed: int | None = None,     # seed for reproducibility; None = random
    ) -> None:
        self.x     = x0
        self.y     = y0
        self.theta = theta0
        self._gyro_noise_std = gyro_noise_std
        self._rng = np.random.default_rng(rng_seed)

    def update(
        self,
        vx_cmd: float,
        vy_cmd: float,
        yaw_rate_cmd: float,
        gyro_z: float,
        dt: float,
    ) -> None:
        """
        vx_cmd, vy_cmd : commanded velocity in robot frame  (m/s)
        yaw_rate_cmd   : commanded yaw rate                 (rad/s)
        gyro_z         : IMU gyro z reading                 (rad/s)
        dt             : time step                          (s)

        Heading uses the IMU gyro (more reliable than commanded yaw_rate
        for a real robot; adds small noise to simulate sensor imperfection).
        Position uses commanded velocity rotated to world frame.
        """
        # Heading from gyro (with small simulated noise, seeded for reproducibility)
        noisy_gyro = gyro_z + self._rng.normal(0.0, self._gyro_noise_std)
        self.theta += noisy_gyro * dt
        self.theta  = (self.theta + np.pi) % (2 * np.pi) - np.pi

        # Position from commanded velocity in world frame
        cos_t  = np.cos(self.theta)
        sin_t  = np.sin(self.theta)
        self.x += (vx_cmd * cos_t - vy_cmd * sin_t) * dt
        self.y += (vx_cmd * sin_t + vy_cmd * cos_t) * dt

    @property
    def pose(self) -> tuple[float, float, float]:
        """(x, y, theta) — estimated pose in world frame."""
        return self.x, self.y, self.theta

    def reset(self, x: float, y: float, theta: float) -> None:
        self.x, self.y, self.theta = x, y, theta
