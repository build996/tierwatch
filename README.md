# tierwatch

Tells you when a free tier or pricing page you depend on changes — in facts, not in HTML diffs.

Free-tier limits change quietly, on a docs page nobody re-reads. Cerebras's rate-limits page went
from a "Free" tier at 30 requests/min to a "Free Trial" at 5 requests/min with a $5 credit that
needs a verified payment method; Brave Search
replaced "2,000 free queries a month" with "$5 of monthly credits". If a side project or a
client's site runs on one of those plans, you usually find out when it starts returning 429s.

tierwatch keeps a snapshot of each page you list, has an open-weight model (Gemma 4) pull the
limits out as structured facts, throws away every fact whose quoted evidence is not actually on
the page, and diffs the facts against the previous snapshot. A second model call turns the diff
into a few sentences about what it means for *your* use, from a one-line note you write.

## Run it

Python 3.9+, standard library only.

```bash
export GEMINI_API_KEY=...        # Google AI Studio key; Gemma 4 is served there
export OPENROUTER_API_KEY=...    # optional fallback host
export NVIDIA_API_KEY=...        # optional fallback host

python tierwatch.py                       # snapshot + diff every page in watchlist.json
python tierwatch.py --only "Brave Search API"
python tierwatch.py --wayback 20260113061705   # use the Wayback Machine capture nearest that time
python tierwatch.py --compare             # diff the two newest saved snapshots, no fetching
python tierwatch.py --out report.md       # also write the report to a file
```

Run it from cron once a day and pipe the output wherever you read things. Snapshots live in
`state/<page>/<timestamp>.json`.

`watchlist.json`:

```json
[
  {"name": "Brave Search API",
   "url": "https://brave.com/search/api/",
   "care": "my client's site search calls the Brave Search API on the free plan, about 1,500 queries a month"}
]
```

`care` is the only thing the model sees about you. It is used for the summary, never for extraction.

## Demo

`demo/` holds the real output of two replays, each comparing an old Wayback Machine capture with a
newer page:

- `demo/cerebras-report.md` — Cerebras rate-limits page, 2026-02-12 vs 2026-10-06
- `demo/brave-report.md` — Brave Search API page, 2026-01-13 vs live on 2026-10-13
- `demo/state/` — the extracted snapshots, including facts that were dropped as unverified

## How it works

1. **Fetch** the page (or a Wayback capture) and convert it to text. Table rows stay on one line
   as `cell | cell | cell`, and `<sup>` footnote markers become `^1`, so the model can tell which
   number sits under which header.
2. **Extract** with Gemma 4: `{free_offering, requires_payment_method, facts: [{key, value, quote}]}`.
   On the second run, the previous snapshot's keys go into the prompt so the same fact gets the same key.
3. **Verify** every fact in code: the quote must appear in the page text, and the value must
   appear in the quote (for a table row, it must be one whole cell). Facts that fail are kept in
   `dropped_unverified` but never reported.
4. **Diff** the verified facts by key. Whole groups that appear or vanish together (a model removed
   from a plan) collapse into one row.
5. **Summarise** the diff for the developer's `care` note.

### Same weights, several hosts

`PROVIDERS` lists Gemma 4 on Google AI Studio (26B A4B and 31B), OpenRouter, and NVIDIA NIM.
Each is retried on connection drops and 5xx, then the next host is tried. Because the weights are
open, falling back to another host does not change which model reads your page. All requests
stream, so slow answers (Gemma thinks before answering) do not get cut by proxies.

## Known limits

- **The quote check proves a number is on the page, not that it was read under the right
  header.** Before table rows were kept on one line, Gemma read a footnote marker as a rate limit
  and the check still passed. Keeping table structure fixed that case; it does not make it impossible.
- **The summary can overstate.** In the Cerebras demo it says "daily/hourly limits have been
  removed"; the table shows only the request-per-hour/day columns went, token-per-hour/day stayed.
  Trust the table.
- **Values without their unit on the same line get dropped.** Brave prints `$5` and
  `per 1,000 requests` as separate elements; Gemma quoted only the second half, so the price was
  dropped as unverified. Missing a fact is the intended failure mode; inventing one is not.
- **Key drift.** Gemma named Brave's free plan `free_ai.api.*` in January and `free.*` in October.
  The diff is still readable (old group gone, new fact added) but it is not a clean "changed" row.
- Pages rendered only by JavaScript come back nearly empty. Both demo pages are server-rendered.
- Free hosted Gemma is not reliable: during the demo runs Google returned 500s, 429s and empty
  streams, OpenRouter's free Gemma was rate-limited upstream, and NVIDIA answered one extraction
  after 91 seconds. The retries and fallbacks are there because they were needed.
- Not a product yet: no email/Slack delivery, no scheduling, no web UI.

## License

MIT
