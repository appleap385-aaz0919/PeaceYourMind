"""Publication slots; legacy date-only paths remain the morning release."""
from datetime import date, time


def release_key(day: date | str, slot: str = "am") -> str:
    value = day.isoformat() if isinstance(day, date) else date.fromisoformat(day).isoformat()
    if slot not in {"am", "pm", "manual"}:
        raise ValueError("slot must be am, pm, or manual")
    return value if slot == "am" else f"{value}-{slot}"


def publish_clock(slot: str = "am") -> str:
    release_key("2000-01-01", slot)
    if slot == "manual":
        return "immediate publication"
    return "19:00" if slot == "pm" else "07:00"


def cutoff_clock(slot: str = "am") -> time:
    return time(int(publish_clock(slot)[:2]) - 1, 30)


def cutoff_reason(slot: str = "am") -> str:
    return f"missed_{cutoff_clock(slot).strftime('%H%M')}_kst_upload_cutoff"
