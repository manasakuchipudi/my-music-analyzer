"""Regression coverage using only fictional listening records."""
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
from musicanalyser import load_json_records
from music_ui import MusicUIHandler, build_analysis


def record(time="2025-01-01 08:00", duration=180000):
    return dict(endTime=time, artistName="Example Artist", trackName="Example Track", msPlayed=duration)


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "history.json"

    def write(self, records):
        self.path.write_text(json.dumps(records), encoding="utf-8")
        return self.path

    def test_totals_and_skip_boundary(self):
        data = build_analysis(self.write([record(duration=29999), record(duration=30000)]))
        self.assertEqual(data["summary"]["records"], 2)
        self.assertEqual(data["summary"]["skippedCount"], 1)
        self.assertEqual(data["summary"]["skipRate"], 50)
        self.assertEqual(data["summary"]["totalMinutes"], 1)
        self.assertEqual(len(data["weekdayHour"]), 168)

    def test_session_gap_and_streak(self):
        rows = [record("2025-01-01 08:00"), record("2025-01-01 08:30"),
                record("2025-01-01 09:01"), record("2025-01-02 08:00")]
        data = build_analysis(self.write(list(reversed(rows))))
        self.assertEqual(data["sessionInsights"]["totalSessions"], 3)
        self.assertEqual(data["sessionInsights"]["longestListeningStreakDays"], 2)
        self.assertEqual(data["sessionInsights"]["averageSessionMinutes"], 4)

    def test_empty_history(self):
        data = build_analysis(self.write([]))
        self.assertEqual(data["summary"]["records"], 0)
        self.assertEqual(data["sessionInsights"]["highestSkipSessionRate"], 0)
        self.assertEqual(data["recommendations"], [])

    def test_invalid_timestamp_preserves_totals(self):
        data = build_analysis(self.write([record("invalid")]))
        self.assertEqual(data["summary"]["totalMinutes"], 3)
        self.assertEqual(data["monthly"], [])
        self.assertEqual(data["sessionInsights"]["totalSessions"], 0)

    def test_recommendations_require_replays_and_low_skip_rate(self):
        self.assertEqual(build_analysis(self.write([record()] * 2))["recommendations"], [])
        data = build_analysis(self.write([record()] * 3))
        self.assertAlmostEqual(data["recommendations"][0]["score"], 13.5)
        self.assertEqual(build_analysis(self.write([record(duration=1000)] * 3))["recommendations"], [])

    def test_reject_invalid_records(self):
        for row in [None, {}, record(duration=-1), record(duration=True), record(duration="1000")]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                load_json_records(self.write([row]))

    def test_malformed_json(self):
        self.path.write_text("[broken")
        with self.assertRaises(ValueError):
            build_analysis(self.path)

    def test_cli_demo_and_invalid_limit(self):
        result = subprocess.run([sys.executable, str(ROOT / "code/musicanalyser.py"), "--top", "3"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Total records: 720", result.stdout)
        result = subprocess.run([sys.executable, str(ROOT / "code/musicanalyser.py"), "--top", "0"], capture_output=True)
        self.assertEqual(result.returncode, 2)

    def test_http_routes_and_errors(self):
        self.write([record()])
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(MusicUIHandler, data_path=self.path))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + "/") as response:
                self.assertIn(b"Music Listening Analyzer", response.read())
            with urlopen(base + "/api/analysis?top=1") as response:
                self.assertEqual(json.load(response)["summary"]["records"], 1)
            for query in ["abc", "0", "501"]:
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + "/api/analysis?top=" + query)
                self.assertEqual(error.exception.code, 400)
                error.exception.close()
            self.path.write_text("invalid")
            with self.assertRaises(HTTPError) as error:
                urlopen(base + "/api/analysis")
            self.assertEqual(error.exception.code, 422)
            error.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
