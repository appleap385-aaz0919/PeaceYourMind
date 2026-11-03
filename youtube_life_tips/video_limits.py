"""Shared duration limits for the life-tips video and YouTube upload."""

MIN_DURATION_SECONDS = 65
MAX_DURATION_SECONDS = 90


def validate_duration(seconds: float) -> None:
    if not MIN_DURATION_SECONDS <= seconds <= MAX_DURATION_SECONDS:
        raise ValueError(
            f"narration duration {seconds:.1f}s is outside the "
            f"{MIN_DURATION_SECONDS}-{MAX_DURATION_SECONDS}s Short range"
        )
