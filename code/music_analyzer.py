from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "examples" / "demo-history.json"
SPOTIFY_TIME_FORMAT = "%Y-%m-%d %H:%M"


def load_json_records(path: Path) -> list[dict[str, Any]]:
    """Load records from a JSON file containing either a list or one object."""
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, list):
        return [validate_record(record) for record in data]
    if isinstance(data, dict):
        return [validate_record(data)]

    raise ValueError(f"{path} does not contain JSON objects")


def validate_record(record: Any) -> dict[str, Any]:
    """Reject unsupported exports and invalid durations before aggregation."""
    if not isinstance(record, dict):
        raise ValueError("Each listening record must be an object")
    for field in ("artistName", "trackName", "endTime"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise ValueError(f"Each record requires a nonempty {field} string")
    duration = record.get("msPlayed")
    if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0:
        raise ValueError("msPlayed must be a nonnegative integer")
    return record


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def find_json_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.glob("*.json"))
    raise FileNotFoundError(f"No file or folder found at {path}")


def load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for json_file in find_json_files(path):
        records.extend(load_json_records(json_file))

    return records


def minutes(ms_played: int | float) -> float:
    return ms_played / 1000 / 60


def format_minutes(total_minutes: float) -> str:
    hours, mins = divmod(round(total_minutes), 60)
    if hours:
        return f"{hours:,}h {mins:02d}m"
    return f"{mins}m"


def parse_end_time(record: dict[str, Any]) -> datetime | None:
    end_time = record.get("endTime")
    if not isinstance(end_time, str):
        return None

    try:
        return datetime.strptime(end_time, SPOTIFY_TIME_FORMAT)
    except ValueError:
        return None


def analyze_records(records: list[dict[str, Any]], top_n: int) -> None:
    artist_plays: Counter[str] = Counter()
    track_plays: Counter[str] = Counter()
    artist_minutes: defaultdict[str, float] = defaultdict(float)
    monthly_minutes: defaultdict[str, float] = defaultdict(float)
    hourly_plays: Counter[int] = Counter()

    total_ms = 0
    valid_records = 0
    first_play: datetime | None = None
    last_play: datetime | None = None

    for record in records:
        artist = str(record.get("artistName", "Unknown Artist"))
        track = str(record.get("trackName", "Unknown Track"))
        ms_played = int(record.get("msPlayed") or 0)
        played_at = parse_end_time(record)

        valid_records += 1
        total_ms += ms_played
        artist_plays[artist] += 1
        track_plays[f"{track} - {artist}"] += 1
        artist_minutes[artist] += minutes(ms_played)

        if played_at:
            month_key = played_at.strftime("%Y-%m")
            monthly_minutes[month_key] += minutes(ms_played)
            hourly_plays[played_at.hour] += 1
            first_play = played_at if first_play is None else min(first_play, played_at)
            last_play = played_at if last_play is None else max(last_play, played_at)

    print("\nMusic Listening Analysis")
    print("=" * 24)
    print(f"Total records: {valid_records:,}")
    print(f"Total listening time: {format_minutes(minutes(total_ms))}")

    if first_play and last_play:
        print(f"Date range: {first_play:%Y-%m-%d} to {last_play:%Y-%m-%d}")

    print_section("Top artists by plays", artist_plays.most_common(top_n))
    print_section("Top tracks by plays", track_plays.most_common(top_n))

    top_artist_minutes = sorted(
        artist_minutes.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:top_n]
    print_section(
        "Top artists by listening time",
        [(artist, format_minutes(total)) for artist, total in top_artist_minutes],
    )

    if monthly_minutes:
        monthly_rows = [
            (month, format_minutes(total))
            for month, total in sorted(monthly_minutes.items())
        ]
        print_section("Listening time by month", monthly_rows)

    if hourly_plays:
        busiest_hour, play_count = hourly_plays.most_common(1)[0]
        print(f"\nBusiest hour: {busiest_hour:02d}:00 with {play_count:,} plays")


def print_section(title: str, rows: list[tuple[Any, Any]]) -> None:
    print(f"\n{title}")
    print("-" * len(title))

    if not rows:
        print("No data found.")
        return

    for index, (name, value) in enumerate(rows, start=1):
        print(f"{index:>2}. {name}: {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read JSON music history files and summarize listening data."
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=DEFAULT_DATA_PATH,
        help="JSON file or folder of JSON files to analyze.",
    )
    parser.add_argument(
        "--top",
        type=positive_int,
        default=10,
        help="Number of top artists/tracks to show.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        records = load_records(args.path)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    if not records:
        print(f"No JSON records found in {args.path}")
        return

    analyze_records(records, args.top)


if __name__ == "__main__":
    main()
