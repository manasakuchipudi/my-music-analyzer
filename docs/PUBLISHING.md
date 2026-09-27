# Before publishing

Personal Spotify exports were tracked in earlier commits. Removing them from the current tree and adding ignore rules does not remove them from Git history or an existing remote.

1. Review `git status` and `git diff --cached --stat`; the current tracked tree should contain only fictional example data.
2. Decide how to handle the existing history before publishing. A new repository created from a reviewed copy without `.git` avoids carrying old history forward. Preserving history requires a deliberate history rewrite and coordinated updates to any existing remote/clones. Neither action is performed automatically by this cleanup.
3. If exports were already public, treat that data as previously disclosed; rewriting history cannot recall copies.
4. Run `python3 code/music_ui.py` and `python3 -m unittest discover -s tests -v`. Capture a dashboard screenshot using the synthetic dataset if you want a visual portfolio preview.
5. Add a GitHub description such as: “Local Spotify listening analytics with Python, JavaScript, session insights, and explainable song rediscovery.” Suggested topics: `python`, `javascript`, `spotify`, `data-analysis`, `data-visualization`.
6. Choose a license before inviting reuse. No license is selected automatically because this is an ownership decision.

For internship applications, describe the implementation you can explain and defend: JSON validation, aggregation with counters, session segmentation, a local JSON API, Canvas visualizations, and regression tests. Avoid claims of machine learning or measured user impact without evidence.
