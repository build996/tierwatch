#!/usr/bin/env python3
"""tierwatch - notice when a free tier or pricing page you depend on changes.

Fetches each page on your watchlist, asks an open-weight model (Gemma 4) to pull
out the limits as structured facts, keeps only the facts whose quoted evidence
really appears on the page, and diffs those facts against the last snapshot.

Standard library only. See README.md.
"""
import argparse
import datetime as dt
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

UA = "Mozilla/5.0 (tierwatch; +https://github.com/build996/tierwatch)"
MAX_PAGE_CHARS = 40000

# The same open-weight model, served by several hosts. If one host is down,
# the next one answers with the same weights - that is the point of open weights.
PROVIDERS = [
    {"name": "google-ai-studio", "kind": "gemini", "model": "gemma-4-26b-a4b-it", "key": "GEMINI_API_KEY"},
    {"name": "google-ai-studio", "kind": "gemini", "model": "gemma-4-31b-it", "key": "GEMINI_API_KEY"},
    {"name": "openrouter", "kind": "openai", "model": "google/gemma-4-31b-it:free", "key": "OPENROUTER_API_KEY",
     "url": "https://openrouter.ai/api/v1/chat/completions"},
    {"name": "nvidia-nim", "kind": "openai", "model": "google/gemma-4-31b-it", "key": "NVIDIA_API_KEY",
     "url": "https://integrate.api.nvidia.com/v1/chat/completions"},
]


# ---------------------------------------------------------------- fetching

def http_get(url, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip" or body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        return body.decode("utf-8", errors="replace")


def fetch(url, wayback=None, retries=3):
    """Live page, or the Wayback Machine capture closest to `wayback` (YYYYMMDDhhmmss)."""
    target = f"http://web.archive.org/web/{wayback}id_/{url}" if wayback else url
    last = None
    for i in range(retries):
        try:
            return http_get(target)
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"could not fetch {target}: {last}")


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "template"}

    """HTML -> text. Table rows stay on one line as `cell | cell | cell`, so the model
    can tell which number sits under which header (pricing pages are mostly tables)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.depth, self.cell = [], 0, 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
        if tag in ("td", "th"):
            self.cell += 1
        elif tag == "sup" and self.cell:
            self.out.append(" ^")  # footnote marker, not a value
            return
        self.out.append(" " if self.cell else "\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1
        if tag in ("td", "th") and self.cell:
            self.cell -= 1
            self.out.append(" | ")
        elif tag == "tr":
            self.out.append("\n")
        elif not self.cell:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.depth:
            self.out.append(data)


def page_text(raw_html):
    p = _Text()
    p.feed(raw_html)
    t = "".join(p.out).replace("​", "")
    lines = [re.sub(r"\s+", " ", l).strip() for l in t.splitlines()]
    return "\n".join(l for l in lines if l)


def norm(s):
    return re.sub(r"\s+", " ", s.replace("​", "")).strip().lower()


# ---------------------------------------------------------------- model

def _sse(url, body, headers, timeout=120):
    """POST and read a server-sent-event stream. Streaming keeps bytes moving on slow
    answers, so proxies and load balancers don't drop a request that thinks for 90 s."""
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json", "User-Agent": UA, **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for line in r:
            line = line.decode("utf-8", errors="replace").strip()
            if line.startswith("data:") and line[5:].strip() not in ("", "[DONE]"):
                yield json.loads(line[5:])


def _call(p, prompt):
    key = os.environ.get(p["key"])
    if not key:
        raise RuntimeError(f"{p['key']} not set")
    out = []
    if p["kind"] == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{p['model']}:streamGenerateContent?alt=sse"
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0}}
        for d in _sse(url, body, {"x-goog-api-key": key}):
            for x in d.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                if not x.get("thought"):  # Gemma 4 streams its reasoning as thought parts
                    out.append(x.get("text", ""))
        return "".join(out)
    body = {"model": p["model"], "temperature": 0, "max_tokens": 6000, "stream": True,
            "messages": [{"role": "user", "content": prompt}]}
    for d in _sse(p["url"], body, {"Authorization": f"Bearer {key}"}):
        if d.get("choices"):
            out.append(d["choices"][0].get("delta", {}).get("content") or "")
    return "".join(out)


def ask(prompt, log):
    """Try each host of the open-weight model in turn. Returns (text, provider label)."""
    failures = []
    for p in PROVIDERS:
        label = f"{p['name']}:{p['model']}"
        for attempt in range(3):
            t0 = time.time()
            try:
                out = _call(p, prompt)
                if not out.strip():
                    raise ValueError("empty answer")
                log.append({"provider": label, "ok": True, "seconds": round(time.time() - t0, 1)})
                return out, label
            except urllib.error.HTTPError as e:
                err = f"HTTP {e.code}"
                retry = e.code >= 500 or (e.code == 429 and p["kind"] == "gemini")
                if e.code == 429 and retry:
                    time.sleep(30)  # per-minute token quota: waiting is enough
            except RuntimeError as e:  # missing key: no point retrying
                err, retry = str(e), False
            except Exception as e:  # dropped connection, timeout, odd payload
                err, retry = type(e).__name__ + ": " + str(e)[:80], True
            log.append({"provider": label, "ok": False, "error": err})
            failures.append(f"{label} {err}")
            if not retry:
                break
            time.sleep(4 * (attempt + 1))
    raise RuntimeError("every provider failed: " + "; ".join(failures))


def parse_json(text):
    text = re.sub(r"(?s)<think>.*?</think>", "", text)
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start:end + 1])


EXTRACT_PROMPT = """You extract the free-tier and pricing limits from a web page so a
developer can be told when they change.

Return ONLY a JSON object:
{{
  "free_offering": "one sentence: what a new user gets without paying, as the page states it",
  "requires_payment_method": true | false | null,
  "facts": [
    {{"key": "stable_snake_case_id", "value": "the limit as written, e.g. 60K or $5/month",
      "quote": "a short span copied character-for-character from the page that contains the value"}}
  ]
}}

Rules:
- Only facts that matter to someone on the free or cheapest plan: quotas, rate limits,
  credits, trial length, card requirements, sleep/idle rules, which plans exist.
- Every quote must be copied exactly from the page text below. If you cannot quote it, leave the fact out.
- Tables appear one row per line with cells separated by " | ". For a table value, quote the
  whole row exactly as it appears, and read the header row above it to know which column is which.
  A "^" before a number marks a footnote, not a value.
- Put the plan/tier and the model or resource in the key, e.g. free_trial.gpt_oss_120b.rpm.
- Do not invent limits that are not on the page.
{reuse}
PAGE ({name}):
<<<
{text}
>>>"""


def extract(name, text, prev_keys, log):
    reuse = ""
    if prev_keys:
        reuse = ("- A previous snapshot used these keys. Reuse the SAME key when the same fact appears, "
                 "so the two snapshots can be compared: " + ", ".join(sorted(prev_keys)) + "\n")
    out, provider = ask(EXTRACT_PROMPT.format(reuse=reuse, name=name, text=text[:MAX_PAGE_CHARS]), log)
    data = parse_json(out)
    page = norm(text)
    kept, dropped = [], []
    for f in data.get("facts", []):
        q = norm(str(f.get("quote", "")))
        v = norm(str(f.get("value", "")))
        if "|" in q:  # a table row: the value must be one whole cell, not part of one
            in_quote = v in [c.strip() for c in q.split("|")]
        else:
            in_quote = bool(v) and re.search(r"(?<![\w.])" + re.escape(v) + r"(?![\w])", q) is not None
        if q and q in page and v and in_quote:
            kept.append({"key": f["key"], "value": str(f["value"]), "quote": f["quote"]})
        else:
            dropped.append(f)
    return {"provider": provider, "free_offering": data.get("free_offering"),
            "requires_payment_method": data.get("requires_payment_method"),
            "facts": kept, "dropped_unverified": dropped}


# ---------------------------------------------------------------- diffing

def diff(old, new):
    a = {f["key"]: f for f in old["facts"]}
    b = {f["key"]: f for f in new["facts"]}
    changes = []
    for k in sorted(a.keys() | b.keys()):
        if k in a and k not in b:
            changes.append({"key": k, "type": "removed", "old": a[k]["value"], "new": None,
                            "old_quote": a[k]["quote"]})
        elif k in b and k not in a:
            changes.append({"key": k, "type": "added", "old": None, "new": b[k]["value"],
                            "new_quote": b[k]["quote"]})
        elif norm(a[k]["value"]) != norm(b[k]["value"]):
            changes.append({"key": k, "type": "changed", "old": a[k]["value"], "new": b[k]["value"],
                            "old_quote": a[k]["quote"], "new_quote": b[k]["quote"]})
    if old.get("requires_payment_method") != new.get("requires_payment_method"):
        changes.append({"key": "requires_payment_method", "type": "changed",
                        "old": old.get("requires_payment_method"), "new": new.get("requires_payment_method")})
    return changes


IMPACT_PROMPT = """A developer watches this page because: {care}

These limits changed on {name} between {old_when} and {new_when} (verified against the page text):
{changes}

Free offering before: {old_offer}
Free offering now: {new_offer}

In at most 4 short sentences, plain English: what changed that matters to this developer,
and what they should check or do. Only use the facts above. No preamble."""


def impact(entry, old, new, changes, log):
    lines = "\n".join(f"- {c['key']}: {c['old']} -> {c['new']}" for c in changes[:40])
    out, _ = ask(IMPACT_PROMPT.format(care=entry.get("care", "they use the free tier"), name=entry["name"],
                                      old_when=old["when"], new_when=new["when"], changes=lines,
                                      old_offer=old.get("free_offering"), new_offer=new.get("free_offering")), log)
    return out.strip()


def report(entry, old, new, changes, summary):
    r = [f"## {entry['name']}", f"{entry['url']}", "",
         f"Compared **{old['when']}** with **{new['when']}** "
         f"({len(old['facts'])} vs {len(new['facts'])} verified facts; extracted by {new['provider']}).", ""]
    if not changes:
        r.append("No change in the verified facts.")
        return "\n".join(r)
    r += [summary, "", "| fact | before | now |", "|---|---|---|"]
    for c in collapse(changes, old, new):
        r.append(f"| `{c['key']}` | {c['old'] if c['old'] is not None else '—'} | "
                 f"{c['new'] if c['new'] is not None else '—'} |")
    return "\n".join(r)


def collapse(changes, old, new):
    """When every fact under a prefix (e.g. free.llama3_1_8b.*) appeared or vanished
    together, show one row for the group instead of one row per limit."""
    def prefix(k):
        return k.rsplit(".", 1)[0] if "." in k else None

    def count(snap, p):
        return sum(1 for f in snap["facts"] if prefix(f["key"]) == p)

    groups = {}
    for c in changes:
        p = prefix(c["key"])
        if p and c["type"] in ("added", "removed"):
            groups.setdefault((p, c["type"]), []).append(c)
    out, done = [], set()
    for c in changes:
        p = prefix(c["key"])
        g = groups.get((p, c["type"]))
        whole = g and len(g) > 1 and (count(new, p) == 0 if c["type"] == "removed" else count(old, p) == 0)
        if not whole:
            out.append(c)
        elif (p, c["type"]) not in done:
            done.add((p, c["type"]))
            if c["type"] == "removed":
                out.append({"key": p + ".*", "old": f"{len(g)} limits", "new": "gone from the page"})
            else:
                out.append({"key": p + ".*", "old": "not on the page", "new": f"{len(g)} limits"})
    return out


# ---------------------------------------------------------------- snapshots

def entry_dir(entry, state_dir):
    return Path(state_dir) / re.sub(r"[^a-z0-9]+", "-", entry["name"].lower())


def snapshot(entry, state_dir, wayback=None, log=None):
    log = log if log is not None else []
    sdir = entry_dir(entry, state_dir)
    sdir.mkdir(parents=True, exist_ok=True)
    stamp = wayback or dt.datetime.now().strftime("%Y%m%d%H%M%S")
    prev = latest(sdir, before=stamp)
    text = page_text(fetch(entry["url"], wayback))
    snap = extract(entry["name"], text, [f["key"] for f in prev["facts"]] if prev else [], log)
    snap["when"] = (dt.datetime.strptime(wayback[:8], "%Y%m%d").date().isoformat() + " (Wayback)"
                    if wayback else dt.date.today().isoformat())
    snap["source"] = f"wayback:{wayback}" if wayback else "live"
    snap["page_chars"] = len(text)
    (sdir / f"{stamp}.json").write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    return prev, snap


def latest(sdir, before=None):
    files = sorted(f for f in Path(sdir).glob("*.json") if before is None or f.stem < before)
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


def compare_and_report(entry, prev, snap, log):
    changes = diff(prev, snap)
    summary = ""
    if changes:
        try:
            summary = impact(entry, prev, snap, changes, log)
        except RuntimeError as e:  # the diff is still worth sending without the prose
            summary = f"(No summary: {str(e)[:120]}...)"
    return report(entry, prev, snap, changes, summary)


def run_entry(entry, state_dir, wayback=None):
    log = []
    prev, snap = snapshot(entry, state_dir, wayback, log)
    if prev is None:
        body = (f"## {entry['name']}\nFirst snapshot: {len(snap['facts'])} verified facts "
                f"({len(snap['dropped_unverified'])} dropped because their quote was not on the page).")
    else:
        body = compare_and_report(entry, prev, snap, log)
    return body, log


def compare_saved(entry, state_dir):
    """Diff the two newest saved snapshots without fetching anything."""
    files = sorted(entry_dir(entry, state_dir).glob("*.json"))
    if len(files) < 2:
        return f"## {entry['name']}\nNeed two snapshots to compare, have {len(files)}.", []
    prev, snap = (json.loads(f.read_text(encoding="utf-8")) for f in files[-2:])
    log = []
    return compare_and_report(entry, prev, snap, log), log


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--watchlist", default="watchlist.json")
    ap.add_argument("--state", default="state")
    ap.add_argument("--only", help="run a single watchlist entry by name")
    ap.add_argument("--wayback", help="use the Wayback capture nearest this timestamp instead of the live page")
    ap.add_argument("--compare", action="store_true",
                    help="don't fetch; diff the two newest saved snapshots of each entry")
    ap.add_argument("--out", help="also write the markdown report here")
    args = ap.parse_args()

    entries = json.loads(Path(args.watchlist).read_text(encoding="utf-8"))
    if args.only:
        entries = [e for e in entries if e["name"] == args.only]
    parts, calls = [], []
    for e in entries:
        try:
            if args.compare:
                body, log = compare_saved(e, args.state)
            else:
                body, log = run_entry(e, args.state, args.wayback)
        except Exception as ex:
            body, log = f"## {e['name']}\nFAILED: {ex}", []
        parts.append(body)
        calls += log
        print(body + "\n", flush=True)
    tried = "; ".join(f"{c['provider']} {'ok ' + str(c['seconds']) + 's' if c['ok'] else c['error']}" for c in calls)
    footer = f"_Model calls: {tried or 'none'}_"
    print(footer)
    if args.out:
        Path(args.out).write_text("\n\n".join(parts) + "\n\n" + footer + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
