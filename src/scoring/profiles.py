"""Load independent scoring profiles from ``profiles/<name>``."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from src.config import settings


@dataclass(frozen=True)
class ScoringProfile:
    name: str
    description: str
    threshold: float
    max_items: int
    category_groups: dict[str, int]
    analysis_prompt: str
    match_prompt: str


def profiles_root() -> Path:
    configured = Path(settings.scoring_profiles_dir)
    if configured.is_absolute():
        return configured
    return Path(__file__).resolve().parents[2] / configured


def load_profiles() -> dict[str, ScoringProfile]:
    """Discover valid profile directories. Invalid profiles fail fast at startup."""
    root = profiles_root()
    profiles: dict[str, ScoringProfile] = {}
    if not root.exists():
        raise FileNotFoundError(f"Scoring profiles directory does not exist: {root}")

    for config_path in sorted(root.glob("*/profile.toml")):
        profile_dir = config_path.parent
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        name = str(data.get("name") or profile_dir.name)
        categories = {
            str(category): int(limit)
            for category, limit in data.get("category_groups", {}).items()
        }
        if not categories:
            categories = {"Other": int(data.get("max_items", settings.scoring_max_items))}

        profiles[name] = ScoringProfile(
            name=name,
            description=str(data.get("description", "")),
            threshold=float(data.get("threshold", 7.0)),
            max_items=int(data.get("max_items", settings.scoring_max_items)),
            category_groups=categories,
            analysis_prompt=(profile_dir / "analysis.md").read_text(encoding="utf-8"),
            match_prompt=(profile_dir / "match.md").read_text(encoding="utf-8"),
        )

    if not profiles:
        raise ValueError(f"No scoring profiles found under {root}")
    return profiles


def get_profile(name: str, profiles: dict[str, ScoringProfile]) -> ScoringProfile:
    try:
        return profiles[name]
    except KeyError as exc:
        available = ", ".join(sorted(profiles))
        raise ValueError(f"Unknown scoring profile '{name}'. Available: {available}") from exc
