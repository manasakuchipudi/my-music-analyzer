# Contributing

Use Python 3.10+; no package installation is required. Run the dashboard with `python3 code/music_ui.py` and tests with `python3 -m unittest discover -s tests -v`.

Keep changes focused. For analysis changes, add a regression test with small fictional records and explain any changed metric definitions in the relevant documentation. For UI changes, check search, ranking, artist selection, empty data, and narrow screens in a browser.

Pull requests should describe the problem, resulting behavior, and validation performed. Include screenshots for visual changes, using only the synthetic demo. Do not commit personal listening exports, credentials, or environment files.
