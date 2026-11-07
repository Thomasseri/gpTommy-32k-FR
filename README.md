<p align="center">
  <img src="assets/r08_logo.jpg" width="320" alt="Sentinel R08 — Pocket Core" style="border-radius: 16px;" />
</p>

# 🇫🇷 gpTommy-32k-FR — Native 32,768-Token Vocabulary & Tokenizer for Français (French) (Francese)

[![Official Site](https://img.shields.io/badge/Official%20Site-sentinelhub.eu-007acc.svg)](https://www.sentinelhub.eu)
[![Ecosystem](https://img.shields.io/badge/Ecosystem-Sentinel%20LifeOS-purple.svg)](https://www.sentinelhub.eu)
[![Vocabulary](https://img.shields.io/badge/Vocabulary-32,768%20Tokens-blue.svg)](https://github.com/Thomasseri/gpTommy-32k-FR)
[![Language](https://img.shields.io/badge/Language-FR%20Native%2091%25-green.svg)](https://github.com/Thomasseri/gpTommy-32k-FR)
[![Author](https://img.shields.io/badge/Author-Thomas%20Seri%20(Sentinel)-orange.svg)](https://www.sentinelhub.eu)

> **Deterministic 32,768-token (`32k`) lexical vocabulary and tokenizer specifically engineered for the Français (French) (`fr`) language.**  
> **Author & Creator:** Thomas Seri (Sentinel)  
> **Reference Ecosystem:** [Sentinel LifeOS](https://www.sentinelhub.eu) & **Sentinel R-08** Geodesic Model Family

---

## ⚠️ Corrections (7 November 2026)

We re-checked the code published in this repository and found the following errors. Below: what was stated before and what we measured now.

| # | Item | Before (stated) | Now (measured) | Status |
|---|---|---|---|---|
| 1 | `gptommy_tokenizer.py` | Self-contained tokenizer, ready-to-run usage example | The file **could not be imported** on any Python version: `SyntaxError` because `from __future__ import annotations` came after the license header | **Fixed** in this update (only the import line was moved; the license is unchanged) |
| 2 | Lossless round-trip | `decode(encode(text))` returns the original text | It returns the text **fully lowercased** (e.g. `"The bearing…"` → `"the bearing…"`): capital letters are lost | Documented, not yet fixed |
| 3 | Sequence length | Whole words = 1 token each | The space between words is a **separate token** (id 10). On the Italian edition we measured that spaces are 41.1% of all tokens (2.33 tokens per word overall). Not yet measured for this language | Documented |

---

> ### 💼 Investment, Compute Grants & Enterprise Licensing (Investimenti & Partnership Industriali)
> 🇬🇧 **Sentinel** is scaling the **Geodesic Pyramidal Sphere Architecture (`R-08`)** from 50M to **110M–1B+ parameters**, with **a patent application filed at the Italian Patent and Trademark Office (UIBM)**.  
> **Open to Seed / Deep-Tech Investment, GPU/TPU Compute Grants, and Enterprise R&D Partnerships.**  
> 🇮🇹 **Aperto a Investimenti Seed / Deep-Tech, Grant Computazionali GPU/TPU e Licenze Industriali Enterprise.**  
> 📩 **Contact Founder & Inventor Thomas Seri:** 🌐 **[www.sentinelhub.eu](https://www.sentinelhub.eu)** | 🐙 **[GitHub (@Thomasseri)](https://github.com/Thomasseri)** | 🤗 **[Hugging Face (@SentinelHub)](https://huggingface.co/SentinelHub)** | 💬 **[Open an Inquiry / Issue](https://github.com/Thomasseri/R-08/issues/new)**

---

## 🌍 Sentinel gpTommy 32k European Language Suite & R-08 Models

The **gpTommy 32k** family provides native whole-word `SSvvv` vocabularies (`32,768` tokens each, with 100% shared control/space/numeric/alphabet IDs) across the 5 major European languages:

* 🇮🇹 **Italiano (`gpTommy-32k`):** [GitHub](https://github.com/Thomasseri/gpTommy-32k) | [Hugging Face](https://huggingface.co/SentinelHub/gpTommy-32k)
* 🇬🇧 **English (`gpTommy-32k-EN`):** [GitHub](https://github.com/Thomasseri/gpTommy-32k-EN) | [Hugging Face](https://huggingface.co/SentinelHub/gpTommy-32k-EN)
* 🇩🇪 **Deutsch (`gpTommy-32k-DE`):** [GitHub](https://github.com/Thomasseri/gpTommy-32k-DE) | [Hugging Face](https://huggingface.co/SentinelHub/gpTommy-32k-DE)
* 🇫🇷 **Français (`gpTommy-32k-FR`):** [GitHub](https://github.com/Thomasseri/gpTommy-32k-FR) | [Hugging Face](https://huggingface.co/SentinelHub/gpTommy-32k-FR)
* 🇪🇸 **Español (`gpTommy-32k-ES`):** [GitHub](https://github.com/Thomasseri/gpTommy-32k-ES) | [Hugging Face](https://huggingface.co/SentinelHub/gpTommy-32k-ES)

### Related Sentinel R-08 Geodesic Language Models:
* 🤖 **Sentinel R-08 v7 (Pyramid 44.5M):** [GitHub](https://github.com/Thomasseri/R-08) | [Hugging Face](https://huggingface.co/SentinelHub/R-08)
* 🚀 **Sentinel R-08 v7.2 (51.6M with 12 Icosahedral Hubs):** [GitHub](https://github.com/Thomasseri/R-08-v7.2) | [Hugging Face](https://huggingface.co/SentinelHub/R-08-v7.2)
* 🌟 **Sentinel R-08 v7.2a DA ZERO (51.6M 82.51% BLiMP-IT, migliore tra gli R-08):** [GitHub](https://github.com/Thomasseri/R-08-v7.2a) | [Hugging Face](https://huggingface.co/SentinelHub/R-08-v7.2a)

---

## 🎯 Why `gpTommy-32k-FR` is Different from Statistical Subword Tokenizers

Traditional statistical BPE tokenizers fragment words into arbitrary sub-syllables, inflating context length and computational cost while increasing spelling hallucinations in compact neural models.

**gpTommy-32k-FR** adopts a deterministic, structured lexical approach:
* Contains **29,775 complete native Français (French) words and morphemes** (**90.9%** of the vocabulary), covering base lemmas, plurals, conjugated verbs, and scientific/industrial terminology.
* Includes the **complete uppercase/lowercase/accented Latin alphabet (`A..Z`)**, **all single digits (`0..9`) and two-digit numbers (`00..99`)**, **spaces/newlines/tabs (`<spazio>`, `<riga>`, `<tab>`)**, **punctuation and math operators**, and **35 special AI/Chat/Reasoning control tokens (`<|user|>`, `<|assistant|>`, `<|think|>`)** at the exact same fixed IDs as the entire `gpTommy` suite.

---

## 📚 Card-Index Architecture: The 5-Digit `SSvvv` System

The vocabulary uses a deterministic 5-digit index `SSvvv` (`00000` .. `32767`):
* **`SS` (Card / Scheda `00`..`32`)**: Identifies the category or initial alphabet letter (`01`..`26` = **A..Z**).
* **`vvv` (Row `000`..`999`)**: Identifies the specific entry within that card.

| Card (`SS`) | Global ID Range | Primary Content | Token Examples |
| :---: | :---: | :--- | :--- |
| **`00`** | `00000` – `00999` | Special AI tokens, punctuation, digits `0-9`, math symbols | `<\|user\|>`, `<\|assistant\|>`, `<\|think\|>`, `<spazio>`, `+`, `-`, `=`, `*` |
| **`01`** | `01000` – `01999` | Letter **A** (alphabet headers + native French words) | `avec`, `aussi`, `après`, `avoir`, `alors`, `autre`, `automatique` |
| **`03`** | `03000` – `03999` | Letter **C** (includes `Ç/ç`) | `comme`, `cette`, `contre`, `chaque`, `cylindre`, `capteur`, `contrôle` |
| **`19`** | `19000` – `19999` | Letter **S** | `sur`, `sont`, `sans`, `système`, `service`, `sécurité`, `soupape` |
| **`27`** | `27000` – `27999` | French Morphemes & contractions + high-freq words | `-tion`, `-ment`, `-eur`, `-able`, `-ité`, `c'est`, `d'un`, `qu'il`, `aujourd'hui` |
| **`30`** | `30000` – `30999` | Two-digit numbers `00..99`, scientific units & lexicon | `00`..`99`, `€`, `°`, `²`, `³`, `±`, `×`, `÷`, `≠`, `≤`, `≥` |

---

## 📊 Breakdown of the 32,768 Tokens (`32k` = Vocabulary Size)

```
┌─────────────────────────────────────────────────────────────┐
│                  gpTommy-32k-FR   (32,768 IDs)              │
├──────────────────────────────────────┬──────────┬───────────┤
│ Category                             │ Count    │ Share     │
├──────────────────────────────────────┼──────────┼───────────┤
│ Complete Native Words & Morphemes    │   29,775 │     90.9% │
│ Single Characters, Digits & Symbols  │    1,925 │      5.9% │
│ Special AI Control, Space & Chat IDs │    1,068 │      3.2% │
└──────────────────────────────────────┴──────────┴───────────┘
```

---

## 🚀 Quick Usage in Python (Zero External Dependencies)

`gptommy_tokenizer.py` is 100% self-contained and requires no external libraries:

```python
from gptommy_tokenizer import gpTommyTokenizer

# 1. Initialize the tokenizer with gpTommy-32k-FR
tokenizer = gpTommyTokenizer("gpTommy_vocab_by_id.txt")

# 2. Encode a Français (French) sentence into token IDs
text = "Le roulement à billes radial réduit le frottement de roulement dans la maintenance industrielle."
token_ids = tokenizer.encode(text)
print("Token IDs:", token_ids)

# 3. Decode back to the exact original text
decoded = tokenizer.decode(token_ids)
print("Decoded:", decoded)
```

---

## 🛡️ License & Attribution

Released under the **R08 Non-Commercial Research & Ethical License v2.0** (see [`LICENSE.md`](LICENSE.md)), with strict ethical protections (prohibition of military, weapon, surveillance, and harmful uses) and Exclusive Jurisdiction at the **Court of Milan (Italy)**.

All rights to the `SSvvv` card architecture and lexical organization are reserved by **Thomas Seri (Sentinel)** — **[www.sentinelhub.eu](https://www.sentinelhub.eu)**.
