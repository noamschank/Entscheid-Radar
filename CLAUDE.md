# entscheid-radar

Daily digest of new Swiss federal court decisions and federal consultations
(Vernehmlassungen) on constitutional law, legal methodology and legal theory.
Owner: Noam Schank. He is not a developer but knows GitHub. Explain each
change in plain words, keep the code small, one Python file (radar.py).

## How it works
- GitHub Actions (.github/workflows/radar.yml) runs radar.py daily at 05:40 UTC.
  Manual runs take a mode: normal, check, seed, dry-run.
- Decisions: POST https://entscheidsuche.ch/_search.php (Elasticsearch body),
  index `entscheidsuche.v2-<spider>`, spiders CH_BGE and CH_BGer, last 60 days,
  topics from topics.txt as an OR of quoted phrases.
- Consultations: Fedlex SPARQL (https://fedlex.data.admin.ch/sparqlendpoint),
  JOLux vocabulary, opened in the last 60 days. Kept if the title mentions the
  constitution or a topic. Deadlines within 14 days get a reminder once.
- seen.json stores reported ids; the workflow commits it back.
- Summaries: Claude API, model claude-haiku-5-5, only if ANTHROPIC_API_KEY is
  set. German, max four sentences, no speculation.
- Output: one GitHub Issue "Radar YYYY-MM-DD"; nothing new → no issue.

## Status
- v1 written and tested offline with fake data (2026-11-07).
- NOT yet verified against the live sources: the entscheidsuche field names
  (id, date, title, abstract, reference, attachment.content_url), the spider
  names, and the Fedlex predicates (jolux:Consultation, eventStartDate,
  hasSubTask/eventEndDate, eventTitle). Run mode `check` and fix radar.py to
  match what the sources actually return.

## Rules
- Secrets only from env (ANTHROPIC_API_KEY, GITHUB_TOKEN). Never in code.
- Be polite to entscheidsuche.ch: few requests, generic User-Agent, no email
  in headers, credit in README.
- If a source fails, still post what worked and list the failure in the issue.
- Dependencies: requests, anthropic. Nothing else unless needed.
- The radar must not depend on any claude.ai account feature (no scheduled
  tasks, no artifacts). Everything lives in this repo.
