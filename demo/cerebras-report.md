## Cerebras Inference rate limits
https://inference-docs.cerebras.ai/support/rate-limits

Compared **2026-02-12 (Wayback)** with **2026-10-06 (Wayback)** (49 vs 14 verified facts; extracted by google-ai-studio:gemma-4-26b-a4b-it).

Rate limits for `gpt_oss_120b` have decreased to 5 requests per minute and 30K tokens per minute, and daily/hourly limits have been removed. The new free offering requires adding a verified payment method to receive $5 in credits. Since you have no card on file, you should check if you can still access the model.

| fact | before | now |
|---|---|---|
| `developer.llama3_1_8b.*` | 2 limits | gone from the page |
| `developer.llama_3_3_70b.*` | 2 limits | gone from the page |
| `developer.pricing_model` | pay-as-you-go | — |
| `developer.qwen_3_235b_a22b_instruct_2507.*` | 2 limits | gone from the page |
| `developer.qwen_3_32b.*` | 2 limits | gone from the page |
| `developer.qwen_3_8_27b.*` | not on the page | 2 limits |
| `developer.zai_glm_4_7.*` | 2 limits | gone from the page |
| `free.gpt_oss_120b.rpd` | 14.4K | — |
| `free.gpt_oss_120b.rph` | 900 | — |
| `free.gpt_oss_120b.rpm` | 30 | 5 |
| `free.gpt_oss_120b.tpm` | 60K | 30K |
| `free.llama3_1_8b.*` | 6 limits | gone from the page |
| `free.llama_3_3_70b.*` | 6 limits | gone from the page |
| `free.qwen_3_235b_a22b_instruct_2507.*` | 6 limits | gone from the page |
| `free.qwen_3_32b.*` | 6 limits | gone from the page |
| `free.qwen_3_8_27b.*` | not on the page | 4 limits |
| `free.zai_glm_4_7.*` | 6 limits | gone from the page |
| `free_trial.*` | not on the page | 2 limits |
| `requires_payment_method` | — | True |

_Model calls: google-ai-studio:gemma-4-26b-a4b-it ValueError: empty answer; google-ai-studio:gemma-4-26b-a4b-it ok 65.5s_
