from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from musicanalyser import DEFAULT_DATA_PATH, find_json_files, load_json_records


ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"
TIME_FORMAT = "%Y-%m-%d %H:%M"


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, TIME_FORMAT)
    except ValueError:
        return None


def minutes(ms_played: int | float) -> float:
    return ms_played / 1000 / 60


def build_analysis(data_path: Path, top_limit: int = 40) -> dict[str, Any]:
    artist_stats: dict[str, dict[str, float | int | str]] = {}
    track_stats: Counter[str] = Counter()
    track_minutes: defaultdict[str, float] = defaultdict(float)
    track_artists: dict[str, str] = {}
    track_last_play: dict[str, datetime] = {}
    skipped_tracks: Counter[str] = Counter()
    artist_tracks: defaultdict[str, Counter[str]] = defaultdict(Counter)
    monthly_minutes: defaultdict[str, float] = defaultdict(float)
    hourly_plays: Counter[int] = Counter()
    weekday_hour: defaultdict[str, int] = defaultdict(int)
    play_events: list[dict[str, Any]] = []

    total_ms = 0
    record_count = 0
    skipped_count = 0
    first_play: datetime | None = None
    last_play: datetime | None = None

    for json_file in find_json_files(data_path):
        for record in load_json_records(json_file):
            artist = str(record.get("artistName") or "Unknown Artist")
            track = str(record.get("trackName") or "Unknown Track")
            ms_played = int(record.get("msPlayed") or 0)
            played_at = parse_time(record.get("endTime"))

            artist_record = artist_stats.setdefault(
                artist,
                {"artist": artist, "plays": 0, "minutes": 0.0},
            )
            artist_record["plays"] = int(artist_record["plays"]) + 1
            artist_record["minutes"] = float(artist_record["minutes"]) + minutes(ms_played)

            track_key = f"{track} - {artist}"
            track_stats[track_key] += 1
            track_minutes[track_key] += minutes(ms_played)
            track_artists[track_key] = artist
            artist_tracks[artist][track] += 1
            if ms_played < 30000:
                skipped_tracks[track_key] += 1
                skipped_count += 1
            total_ms += ms_played
            record_count += 1

            if played_at:
                play_events.append(
                    {
                        "playedAt": played_at,
                        "msPlayed": ms_played,
                        "skipped": ms_played < 30000,
                    }
                )
                if track_key not in track_last_play or played_at > track_last_play[track_key]:
                    track_last_play[track_key] = played_at
                monthly_minutes[played_at.strftime("%Y-%m")] += minutes(ms_played)
                hourly_plays[played_at.hour] += 1
                weekday_hour[f"{played_at.weekday()}-{played_at.hour}"] += 1
                first_play = played_at if first_play is None else min(first_play, played_at)
                last_play = played_at if last_play is None else max(last_play, played_at)

    artists = sorted(
        artist_stats.values(),
        key=lambda item: (float(item["minutes"]), int(item["plays"])),
        reverse=True,
    )
    recommendations = build_recommendations(
        track_stats=track_stats,
        track_minutes=track_minutes,
        skipped_tracks=skipped_tracks,
        track_artists=track_artists,
        track_last_play=track_last_play,
        latest_play=last_play,
        limit=12,
    )
    session_insights = build_session_insights(play_events, hourly_plays)

    return {
        "summary": {
            "records": record_count,
            "totalMinutes": round(minutes(total_ms), 2),
            "firstPlay": first_play.strftime("%Y-%m-%d") if first_play else None,
            "lastPlay": last_play.strftime("%Y-%m-%d") if last_play else None,
            "artistCount": len(artist_stats),
            "trackCount": len(track_stats),
            "skippedCount": skipped_count,
            "skipRate": round((skipped_count / record_count) * 100, 1) if record_count else 0,
        },
        "artists": [
            {
                "artist": str(item["artist"]),
                "plays": int(item["plays"]),
                "minutes": round(float(item["minutes"]), 2),
            }
            for item in artists[:top_limit]
        ],
        "tracks": [
            {"track": track, "plays": plays}
            for track, plays in track_stats.most_common(top_limit)
        ],
        "skippedTracks": [
            {
                "track": track,
                "skips": skips,
                "plays": track_stats[track],
                "skipRate": round((skips / track_stats[track]) * 100, 1),
            }
            for track, skips in skipped_tracks.most_common(top_limit)
        ],
        "artistTracks": {
            str(item["artist"]): [
                {"track": track, "plays": plays}
                for track, plays in artist_tracks[str(item["artist"])].most_common(12)
            ]
            for item in artists[:top_limit]
        },
        "recommendations": recommendations,
        "sessionInsights": session_insights,
        "monthly": [
            {"month": month, "minutes": round(total, 2)}
            for month, total in sorted(monthly_minutes.items())
        ],
        "hourly": [
            {"hour": hour, "plays": hourly_plays.get(hour, 0)}
            for hour in range(24)
        ],
        "weekdayHour": [
            {"weekday": weekday, "hour": hour, "plays": weekday_hour.get(f"{weekday}-{hour}", 0)}
            for weekday in range(7)
            for hour in range(24)
        ],
    }


def hour_label(hour: int) -> str:
    suffix = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    return f"{display_hour}:00 {suffix}"


def session_type(hour: int) -> str:
    if 5 <= hour < 12:
        return "Morning"
    if 12 <= hour < 17:
        return "Afternoon"
    if 17 <= hour < 22:
        return "Evening"
    return "Late night"


def build_session_insights(
    play_events: list[dict[str, Any]],
    hourly_plays: Counter[int],
) -> dict[str, Any]:
    if not play_events:
        return {
            "averageSessionMinutes": 0,
            "mostCommonHour": "No data",
            "highestSkipSessionType": "No data",
            "highestSkipSessionRate": 0,
            "longestListeningStreakDays": 0,
            "deepSessions": 0,
            "browsingSessions": 0,
            "mixedSessions": 0,
            "totalSessions": 0,
        }

    sorted_events = sorted(play_events, key=lambda item: item["playedAt"])
    sessions: list[list[dict[str, Any]]] = []
    current_session: list[dict[str, Any]] = []

    for event in sorted_events:
        if not current_session:
            current_session.append(event)
            continue

        previous_time = current_session[-1]["playedAt"]
        if event["playedAt"] - previous_time > timedelta(minutes=30):
            sessions.append(current_session)
            current_session = [event]
        else:
            current_session.append(event)

    if current_session:
        sessions.append(current_session)

    session_lengths: list[float] = []
    type_skips: defaultdict[str, int] = defaultdict(int)
    type_plays: defaultdict[str, int] = defaultdict(int)
    deep_sessions = 0
    browsing_sessions = 0
    mixed_sessions = 0

    for session in sessions:
        total_minutes = sum(minutes(event["msPlayed"]) for event in session)
        skip_count = sum(1 for event in session if event["skipped"])
        skip_rate = skip_count / len(session)
        start_hour = session[0]["playedAt"].hour
        label = session_type(start_hour)

        session_lengths.append(total_minutes)
        type_skips[label] += skip_count
        type_plays[label] += len(session)

        if total_minutes >= 20 and skip_rate <= 0.30:
            deep_sessions += 1
        elif skip_rate >= 0.60 or total_minutes < 5:
            browsing_sessions += 1
        else:
            mixed_sessions += 1

    listening_days = sorted({event["playedAt"].date() for event in sorted_events})
    longest_streak = 1
    current_streak = 1

    for index in range(1, len(listening_days)):
        if listening_days[index] - listening_days[index - 1] == timedelta(days=1):
            current_streak += 1
        else:
            longest_streak = max(longest_streak, current_streak)
            current_streak = 1

    longest_streak = max(longest_streak, current_streak)
    common_hour = hourly_plays.most_common(1)[0][0] if hourly_plays else 0
    highest_skip_type = max(
        type_plays,
        key=lambda label: type_skips[label] / type_plays[label],
    )

    return {
        "averageSessionMinutes": round(sum(session_lengths) / len(session_lengths), 1),
        "mostCommonHour": hour_label(common_hour),
        "highestSkipSessionType": highest_skip_type,
        "highestSkipSessionRate": round((type_skips[highest_skip_type] / type_plays[highest_skip_type]) * 100, 1),
        "longestListeningStreakDays": longest_streak,
        "deepSessions": deep_sessions,
        "browsingSessions": browsing_sessions,
        "mixedSessions": mixed_sessions,
        "totalSessions": len(sessions),
    }


def build_recommendations(
    track_stats: Counter[str],
    track_minutes: defaultdict[str, float],
    skipped_tracks: Counter[str],
    track_artists: dict[str, str],
    track_last_play: dict[str, datetime],
    latest_play: datetime | None,
    limit: int,
) -> list[dict[str, Any]]:
    scored_tracks: list[dict[str, Any]] = []

    for track, plays in track_stats.items():
        if plays < 3:
            continue

        skips = skipped_tracks[track]
        skip_rate = skips / plays
        total_minutes = track_minutes[track]
        days_since_play = 0

        if latest_play and track in track_last_play:
            days_since_play = max((latest_play - track_last_play[track]).days, 0)

        score = (plays * 2.4) + (total_minutes * 0.7) - (skip_rate * 18)
        if 21 <= days_since_play <= 150:
            score += 8
        elif days_since_play > 150:
            score += 3

        if skip_rate >= 0.85:
            continue

        reason = "High replay count with a low skip rate"
        if days_since_play >= 45:
            reason = f"You liked this before, but it has been {days_since_play} days"
        elif skip_rate <= 0.25 and plays >= 10:
            reason = "Frequently replayed and rarely skipped"
        elif total_minutes >= 60:
            reason = "One of your stronger time-spent tracks"

        scored_tracks.append(
            {
                "track": track.rsplit(" - ", 1)[0],
                "artist": track_artists.get(track, "Unknown Artist"),
                "plays": plays,
                "minutes": round(total_minutes, 1),
                "skipRate": round(skip_rate * 100, 1),
                "score": round(score, 2),
                "reason": reason,
            }
        )

    return sorted(scored_tracks, key=lambda item: item["score"], reverse=True)[:limit]


class MusicUIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, data_path: Path, **kwargs: Any) -> None:
        self.data_path = data_path
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)

        if parsed_url.path == "/api/analysis":
            query = parse_qs(parsed_url.query)
            try:
                top_limit = int(query.get("top", ["40"])[0])
                if not 1 <= top_limit <= 500:
                    raise ValueError
            except ValueError:
                self.send_json({"error": "top must be an integer from 1 to 500"}, 400)
                return
            try:
                analysis = build_analysis(self.data_path, top_limit)
            except (OSError, ValueError):
                self.send_json({"error": "Cannot read history. Check the data path and supported JSON format."}, 422)
                return
            self.send_json(analysis)
            return

        if parsed_url.path == "/":
            self.path = "/index.html"

        super().do_GET()

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def run_server(port: int, data_path: Path) -> None:
    def handler(*args: Any, **kwargs: Any) -> MusicUIHandler:
        return MusicUIHandler(*args, data_path=data_path, **kwargs)

    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"Music analyzer UI: http://127.0.0.1:{port}")
    print(f"Reading JSON data from: {data_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the local music listening dashboard.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH,
                        help="JSON file or directory (default: synthetic demo)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        build_analysis(args.data)
        run_server(port=args.port, data_path=args.data)
    except (OSError, ValueError) as error:
        parser.error(str(error))
