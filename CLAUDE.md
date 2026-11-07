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

## Status (2026-11-07)
- Live and verified. First real run opened issue #1 (17 decisions, all
  summarized, 2 consultations). seen.json is committed back by the workflow.
- entscheidsuche: fields confirmed (id, date, title, reference,
  attachment.content_url, attachment.content = full text). The search hit
  already carries the full text; no second download needed. CH_BGE returned
  0 hits in the 60-day window on the first check; CH_BGer works.
- Fedlex: jolux:Consultation has eventTitle (DE/FR/IT) and eventDescription;
  the dates sit on the sub-task (jolux:hasSubTask → eventStartDate,
  eventEndDate).
- Haiku 5.5 thinks before answering: max_tokens must leave room (2000 now).
  With 300 it returned only a thinking block.
- Topics: "Auslegung" alone matched 26 of 38 decisions; replaced by narrower
  terms. Each decision in the digest shows which topics matched ("Treffer"),
  to make tuning easy. Mode `check` prints counts per topic.

## Rules
- Secrets only from env (ANTHROPIC_API_KEY, GITHUB_TOKEN). Never in code.
- Be polite to entscheidsuche.ch: few requests, generic User-Agent, no email
  in headers, credit in README.
- If a source fails, still post what worked and list the failure in the issue.
- Dependencies: requests, anthropic. Nothing else unless needed.
- The radar must not depend on any claude.ai account feature (no scheduled
  tasks, no artifacts). Everything lives in this repo.
