# entscheid-radar

Daily digest of new decisions of the Swiss Federal Supreme Court (Bundesgericht)
and new federal consultations (Vernehmlassungen) on constitutional law, legal
methodology and legal theory. Runs on GitHub Actions and opens one GitHub Issue
per day when there is something new.

## How it works

1. Every morning, GitHub Actions runs `radar.py`.
2. It searches [entscheidsuche.ch](https://entscheidsuche.ch) for Bundesgericht
   decisions from the last 60 days that contain a topic from `topics.txt`.
3. It asks Fedlex open data for consultations opened in the same period and
   keeps those on the constitution or a listed topic.
4. Anything already reported (`seen.json`) is skipped.
5. If an Anthropic API key is set, Claude writes a short summary of each decision.
6. Results go into one issue titled `Radar YYYY-MM-DD`.

## Set up your own

1. Fork or copy this repo.
2. Edit `topics.txt`.
3. Optional: add `ANTHROPIC_API_KEY` under Settings → Secrets and variables → Actions.
4. Actions → radar → Run workflow → mode `seed` (marks today's state as seen).
5. From then on it runs daily. Mode `check` prints raw source data for debugging.

## Credits

Court decisions: [entscheidsuche.ch](https://entscheidsuche.ch). Please credit
them and keep request volume low. Consultations: Fedlex, Swiss Federal
Chancellery, open reuse licence. Decisions remain subject to the conditions of
their original sources.

## License

Code: MIT.
