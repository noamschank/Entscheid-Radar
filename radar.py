"""entscheid-radar: daily digest of new Swiss federal court decisions and
federal consultations (Vernehmlassungen) on chosen topics.

Run modes:
  python radar.py            normal run: find new items, open a GitHub Issue
  python radar.py --dry-run  print the digest instead of opening an issue
  python radar.py --check    print raw answers from the sources (debugging)
  python radar.py --seed     mark everything currently found as seen, post nothing
"""

import html
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

HERE = Path(__file__).parent
TOPICS_FILE = HERE / "topics.txt"
SEEN_FILE = HERE / "seen.json"

UA = {"User-Agent": "entscheid-radar (github.com/noamschank/entscheid-radar)"}

ES_SEARCH = "https://entscheidsuche.ch/_search.php"
ES_DOCS = "https://entscheidsuche.ch/docs/"
# Bundesgericht: all decisions and published leading decisions (BGE).
SPIDERS = {"CH_BGE": "Leitentscheide (BGE)", "CH_BGer": "Weitere BGer-Urteile"}
LOOKBACK_DAYS = 60  # BGer publishes with delay; seen.json prevents repeats

FEDLEX_SPARQL = "https://fedlex.data.admin.ch/sparqlendpoint"
DEADLINE_WARN_DAYS = 14

MODEL = "claude-haiku-5-5"


# ---------- small helpers ----------

def load_topics():
    lines = TOPICS_FILE.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


def load_seen():
    if SEEN_FILE.exists():
        return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    return {"decisions": [], "consultations": [], "warned": []}


def save_seen(seen):
    for k in seen:
        seen[k] = sorted(set(seen[k]))[-5000:]  # keep the file small
    SEEN_FILE.write_text(json.dumps(seen, indent=1, ensure_ascii=False), encoding="utf-8")


def pick_lang(value):
    """entscheidsuche stores texts as {"de": "...", "fr": "..."}."""
    if isinstance(value, dict):
        for lang in ("de", "fr", "it"):
            if value.get(lang):
                return value[lang]
        return next(iter(value.values()), "")
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return value or ""


def strip_html(text):
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


# ---------- source 1: court decisions (entscheidsuche.ch) ----------

def es_query(topics, size=200):
    phrases = " OR ".join('"%s"' % t.replace('"', "") for t in topics)
    since = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    indices = ["entscheidsuche.v2-" + s.lower() for s in SPIDERS]
    return {
        "size": size,
        "query": {"bool": {
            "must": [{"query_string": {"query": phrases, "default_operator": "OR"}}],
            "filter": [
                {"terms": {"_index": indices}},
                {"range": {"date": {"gte": since}}},
            ],
        }},
        "sort": [{"date": {"order": "desc"}}],
    }


def fetch_decisions(topics):
    r = requests.post(ES_SEARCH, json=es_query(topics), headers=UA, timeout=60)
    r.raise_for_status()
    hits = r.json().get("hits", {}).get("hits", [])
    out = []
    for h in hits:
        src = h.get("_source", {})
        index = h.get("_index", "")
        spider = next((s for s in SPIDERS if index.endswith(s.lower())), "CH_BGer")
        att = src.get("attachment") or {}
        ref = src.get("reference") or src.get("Num") or []
        full = strip_html(att.get("content") or "")
        low = full.lower()
        out.append({
            "id": src.get("id") or h.get("_id"),
            "spider": spider,
            "date": src.get("date", ""),
            "ref": ", ".join(ref) if isinstance(ref, list) else str(ref),
            "title": strip_html(pick_lang(src.get("title"))),
            "abstract": strip_html(pick_lang(src.get("abstract"))),
            "url": att.get("content_url") or "",
            "text": full[:24000],
            "matched": [t for t in topics if t.lower() in low],
        })
    return out


def decision_text(d, limit=24000):
    """Full text for the summary. Falls back to the abstract."""
    if d.get("text"):
        return d["text"][:limit]
    if not d["url"]:
        return d["abstract"]
    try:
        r = requests.get(d["url"], headers=UA, timeout=60)
        r.raise_for_status()
        if "html" in r.headers.get("content-type", "") or d["url"].endswith(".html"):
            return strip_html(r.text)[:limit]
    except requests.RequestException:
        pass
    return d["abstract"]


# ---------- source 2: consultations (Fedlex open data) ----------

def sparql(query):
    r = requests.post(
        FEDLEX_SPARQL,
        data={"query": query},
        headers={**UA, "Accept": "application/sparql-results+json"},
        timeout=90,
    )
    r.raise_for_status()
    return r.json()["results"]["bindings"]


# Consultations opened in the last LOOKBACK_DAYS, with German title and deadline.
# Uses the JOLux vocabulary that Fedlex publishes. Verify with --check.
CONSULTATION_QUERY = """
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?c ?start ?end ?title WHERE {
  ?c a jolux:Consultation ;
     jolux:hasSubTask ?t .
  ?t jolux:eventStartDate ?start .
  OPTIONAL { ?t jolux:eventEndDate ?end . }
  OPTIONAL { ?c jolux:eventTitle ?title . FILTER(lang(?title) = "de") }
  FILTER(?start >= "%s"^^xsd:date)
}
"""


def fetch_consultations():
    since = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    rows = sparql(CONSULTATION_QUERY % since)
    by_uri = {}
    for row in rows:
        uri = row["c"]["value"]
        item = by_uri.setdefault(uri, {
            "id": uri,
            "start": row["start"]["value"][:10],
            "end": "",
            "title": "",
            "url": uri.replace("fedlex.data.admin.ch", "www.fedlex.admin.ch") + "/de",
        })
        if "end" in row:
            item["end"] = max(item["end"], row["end"]["value"][:10])
        if "title" in row and not item["title"]:
            item["title"] = row["title"]["value"]
    return list(by_uri.values())


def matches(text, topics):
    low = text.lower()
    return any(t.lower() in low for t in topics)


# ---------- summaries (Claude API, optional) ----------

PROMPT = """Fasse diesen Entscheid des Schweizerischen Bundesgerichts für einen \
Verfassungsrechtler zusammen. Höchstens vier kurze Sätze, auf Deutsch:
1. Die Rechtsfrage. 2. Das Ergebnis. 3. Die tragenden Erwägungen mit Nummer.
Nur was im Text steht. Keine Wertung, keine Spekulation.

{ref} vom {date}

{text}"""


def summarize(d):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return ""
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=MODEL,
        max_tokens=2000,  # room for thinking + the answer
        messages=[{"role": "user", "content": PROMPT.format(
            ref=d["ref"] or d["id"], date=d["date"], text=decision_text(d))}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    if not text:
        raise RuntimeError(f"leere Antwort (stop_reason={msg.stop_reason}, "
                           f"blocks={[b.type for b in msg.content]})")
    return text


# ---------- digest ----------

def build_digest(decisions, consultations, deadlines, errors):
    parts = []
    for spider, heading in SPIDERS.items():
        group = [d for d in decisions if d["spider"] == spider]
        if not group:
            continue
        parts.append(f"## {heading}\n")
        for d in group:
            label = d["ref"] or d["id"]
            link = f"[{label}]({d['url']})" if d["url"] else label
            parts.append(f"### {link} ({d['date']})")
            if d.get("matched"):
                parts.append("Treffer: " + ", ".join(d["matched"]))
            parts.append((d.get("summary") or d["abstract"] or "_Keine Zusammenfassung._") + "\n")
    if consultations:
        parts.append("## Neue Vernehmlassungen\n")
        for c in consultations:
            parts.append(f"- [{c['title'] or c['id']}]({c['url']}), Frist {c['end'] or '?'}")
        parts.append("")
    if deadlines:
        parts.append(f"## Fristen in den nächsten {DEADLINE_WARN_DAYS} Tagen\n")
        for c in deadlines:
            parts.append(f"- **{c['end']}**: [{c['title'] or c['id']}]({c['url']})")
        parts.append("")
    if errors:
        parts.append("## Fehler\n")
        parts.extend(f"- {e}" for e in errors)
    if not parts:
        return ""
    parts.append("\n---\nEntscheide via [entscheidsuche.ch](https://entscheidsuche.ch), "
                 "Vernehmlassungen via Fedlex (Open Data).")
    return "\n".join(parts)


def open_issue(title, body):
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    r = requests.post(
        f"https://api.github.com/repos/{repo}/issues",
        json={"title": title, "body": body[:65000]},
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json"},
        timeout=30,
    )
    r.raise_for_status()
    print("Issue opened:", r.json().get("html_url"))


# ---------- modes ----------

def check(topics):
    print("== entscheidsuche.ch: one sample hit per court")
    for spider in SPIDERS:
        body = es_query(topics, size=1)
        body["query"]["bool"]["filter"][0] = {"term": {"_index": "entscheidsuche.v2-" + spider.lower()}}
        try:
            r = requests.post(ES_SEARCH, json=body, headers=UA, timeout=60)
            print(spider, "HTTP", r.status_code)
            print(r.text[:3000])
        except requests.RequestException as e:
            print(spider, "ERROR", e)
    try:
        r = requests.get(ES_DOCS + "Facetten.json", headers=UA, timeout=60)
        names = re.findall(r'"(CH_[A-Za-z]+)"', r.text)
        print("Spider names seen in Facetten.json:", sorted(set(names))[:60])
    except requests.RequestException as e:
        print("Facetten.json ERROR", e)

    print("\n== Topic counts over the last %d days" % LOOKBACK_DAYS)
    try:
        ds = fetch_decisions(topics)
        print("decisions:", len(ds))
        for t in topics:
            print(f"  {sum(t in d['matched'] for d in ds):3d}  {t}")
        if ds:
            print("\n== One summary test")
            try:
                print(repr(summarize(ds[0])) or "(no key)")
            except Exception as e:
                print("SUMMARY ERROR", repr(e))
    except Exception as e:
        print("decisions ERROR", e)

    print("\n== Fedlex: all properties of one known consultation")
    known = "https://fedlex.data.admin.ch/eli/dl/proj/2026/102/cons_1"
    try:
        for row in sparql(f"SELECT ?p ?o WHERE {{ <{known}> ?p ?o }} LIMIT 60"):
            print(row["p"]["value"], "=>", row["o"]["value"][:120])
        print("\n== Fedlex: its sub-task")
        for row in sparql(f"SELECT ?p ?o WHERE {{ <{known}/cons-open> ?p ?o }} LIMIT 40"):
            print(row["p"]["value"], "=>", row["o"]["value"][:120])
        print("\n== Fedlex: result of the consultation query")
        for c in fetch_consultations()[:5]:
            print(c)
    except Exception as e:
        print("Fedlex ERROR", e)


def main():
    args = set(sys.argv[1:])
    topics = load_topics()
    if "--check" in args:
        check(topics)
        return

    seen = load_seen()
    errors = []
    new_decisions, new_consultations, deadlines = [], [], []

    try:
        decisions = fetch_decisions(topics)
        new_decisions = [d for d in decisions if d["id"] not in seen["decisions"]]
    except Exception as e:
        errors.append(f"entscheidsuche.ch: {e}")

    try:
        consultations = fetch_consultations()
        today = date.today()
        # Consultations are reported if the title matches a topic, or if the
        # draft changes the Federal Constitution.
        relevant = [c for c in consultations
                    if matches(c["title"], topics) or "Bundesverfassung" in c["title"]
                    or "Verfassung" in c["title"]]
        new_consultations = [c for c in relevant if c["id"] not in seen["consultations"]]
        for c in relevant:
            if c["end"] and c["id"] not in seen["warned"]:
                left = (date.fromisoformat(c["end"]) - today).days
                if 0 <= left <= DEADLINE_WARN_DAYS:
                    deadlines.append(c)
    except Exception as e:
        errors.append(f"Fedlex: {e}")

    if "--seed" in args:
        seen["decisions"] += [d["id"] for d in new_decisions]
        seen["consultations"] += [c["id"] for c in new_consultations]
        save_seen(seen)
        print(f"Seeded {len(new_decisions)} decisions, {len(new_consultations)} consultations.")
        return

    for d in new_decisions:
        try:
            d["summary"] = summarize(d)
        except Exception as e:
            errors.append(f"Zusammenfassung {d['ref'] or d['id']}: {e}")

    body = build_digest(new_decisions, new_consultations, deadlines, errors)
    if not body:
        print("Nothing new.")
        return
    if "--dry-run" in args or not os.environ.get("GITHUB_TOKEN"):
        print(body)
    else:
        open_issue(f"Radar {date.today().isoformat()}", body)

    seen["decisions"] += [d["id"] for d in new_decisions]
    seen["consultations"] += [c["id"] for c in new_consultations]
    seen["warned"] += [c["id"] for c in deadlines]
    save_seen(seen)


if __name__ == "__main__":
    main()
