"""Visual intensity presets. Normal preserves the original montage settings."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Effects:
    shake: float = 1.0
    flashes: float = 1.0
    hitmarkers: float = 1.0
    particles: float = 1.0
    deep_fry: float = 1.0

    def hit_count(self, count):
        return max(1, round(count * self.hitmarkers))

    def particle_count(self, count):
        return round(count * self.particles)


INTENSITIES = {
    "low": Effects(shake=0.3, flashes=0.3, hitmarkers=0.5, particles=0.35, deep_fry=0.35),
    "normal": Effects(),
    "chaos": Effects(shake=1.8, flashes=1.3, hitmarkers=1.75, particles=2.0, deep_fry=1.4),
}
