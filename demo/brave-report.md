## Brave Search API
https://brave.com/search/api/

Compared **2026-01-13 (Wayback)** with **2026-10-13** (3 vs 4 verified facts; extracted by google-ai-studio:gemma-4-31b-it).

The free plan no longer provides 2,000 free queries per month. Instead, new users now receive $5 in monthly credits. The developer should check if these credits cover their 1,500 monthly queries.

| fact | before | now |
|---|---|---|
| `answers.*` | not on the page | 2 limits |
| `free.monthly_credits` | — | $5 |
| `free_ai.api.*` | 3 limits | gone from the page |
| `search.qps` | — | 50 queries per second |

_Model calls: google-ai-studio:gemma-4-26b-a4b-it URLError: <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of ; google-ai-studio:gemma-4-26b-a4b-it ValueError: empty answer; google-ai-studio:gemma-4-26b-a4b-it HTTP 429; google-ai-studio:gemma-4-31b-it URLError: <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of ; google-ai-studio:gemma-4-31b-it ValueError: empty answer; google-ai-studio:gemma-4-31b-it ok 146.0s; google-ai-studio:gemma-4-26b-a4b-it ValueError: empty answer; google-ai-studio:gemma-4-26b-a4b-it URLError: <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of ; google-ai-studio:gemma-4-26b-a4b-it RemoteDisconnected: Remote end closed connection without response; google-ai-studio:gemma-4-31b-it HTTP 500; google-ai-studio:gemma-4-31b-it RemoteDisconnected: Remote end closed connection without response; google-ai-studio:gemma-4-31b-it ok 34.3s_
