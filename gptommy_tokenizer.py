# ============================================================================
# LEGAL NOTICE & WATERMARK: R08 NON-COMMERCIAL RESEARCH & ETHICAL LICENSE v2.0
# Copyright (c) 2026 Thomas Seri (Sentinel). All Rights Reserved.
# Exclusive Jurisdiction: Court of Milan (Sezione Specializzata Impresa), Italy.
# Clean-room reverse engineering, distillation, commercial or military use
# is strictly prohibited and constitutes a breach of contract.
# ============================================================================
__author__ = "Thomas Seri (Sentinel)"
__license__ = "R08-Non-Commercial-Ethical-License-v2.0"
__jurisdiction__ = "Court of Milan, Italy"

#!/usr/bin/env python3
"""gpTommy 32k Tokenizer: Tokenizer nativo ad alta efficienza per la lingua italiana.
Autore & Ideatore: Thomas Seri (Sentinel)
Ecosistema: Sentinel LifeOS (https://www.sentinelhub.eu)
Modelli di riferimento: Sentinel R-08 v7, v7.2, v7.2a

Vocabolario strutturato a schede (SSvvv):
- 32.768 token totali (ID 0..32767)
- 29.775 parole italiane complete (Schede 01..26 per le lettere A..Z)
- 1.925 caratteri singoli, punteggiatura, cifre e simboli matematici
- 1.069 token speciali di dialogo AI (<|user|>, <|assistant|>, <|system|>, <|think|>)
"""
from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

DEFAULT_VOCAB_PATH = Path(__file__).resolve().parent / "gpTommy_vocab_by_id.txt"

WS_PIECES = {"\n": "<riga>", "\t": "<tab>", "\r": "<cr>", "\xa0": "<nbsp>", " ": "<spazio>"}
DECODE_WS = {"<spazio>": " ", "<riga>": "\n", "<tab>": "\t", "<cr>": "\r", "<nbsp>": " "}


class gpTommyTokenizer:
    """Tokenizer compatto e nativo per il vocabolario gpTommy 32k."""

    def __init__(self, vocab_file: Optional[Union[str, Path]] = None):
        self.vocab_file = Path(vocab_file) if vocab_file else DEFAULT_VOCAB_PATH
        if not self.vocab_file.exists():
            raise FileNotFoundError(f"File vocabolario gpTommy non trovato: {self.vocab_file}")

        self.id_to_token: Dict[int, str] = {}
        self.token_to_id: Dict[str, int] = {}
        self.specials: List[str] = []
        self._load_vocab()

        # Token speciali standard
        self.pad_id = self.token_to_id.get("<|pad|>", 3)
        self.eos_id = self.token_to_id.get("<|eos|>", 2)
        self.bos_id = self.token_to_id.get("<|bos|>", 1)
        self.unk_id = self.token_to_id.get("<|unk|>", 4)
        self.sep_id = self.token_to_id.get("<|sep|>", 5)

        # Marcatori di chat / dialoghi
        self.user_id = self.token_to_id.get("<|user|>", 16)
        self.assistant_id = self.token_to_id.get("<|assistant|>", 17)
        self.system_id = self.token_to_id.get("<|system|>", 15)

        self.max_len = max((len(t) for t in self.id_to_token.values() if not t.startswith("<")), default=1)

    def _load_vocab(self) -> None:
        """Carica il file tabellare gpTommy 32k."""
        with open(self.vocab_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.strip().split("\t")
                if len(parts) >= 5:
                    gid = int(parts[3])
                    tok = parts[4]
                    self.id_to_token[gid] = tok
                    self.token_to_id[tok] = gid
                    if tok.startswith("<") and tok.endswith(">"):
                        self.specials.append(tok)
        self.specials.sort(key=len, reverse=True)

    @property
    def vocab_size(self) -> int:
        return len(self.id_to_token)

    def encode(self, text: str, add_special_tokens: bool = False, literal_specials: bool = True) -> List[int]:
        """Codifica secondo il contratto canonico gpTommy."""
        if not text:
            return []

        ids: List[int] = []
        if add_special_tokens and self.bos_id is not None:
            ids.append(self.bos_id)

        n = len(text)
        i = 0
        t2i = self.token_to_id

        while i < n:
            ch = text[i]
            # Gestione Whitespace
            if ch.isspace() or ch in WS_PIECES:
                tid = t2i.get(WS_PIECES.get(ch, "<spazio>"))
                if tid is not None:
                    ids.append(tid)
                i += 1
                continue

            # Gestione speciali letterali <|...|>
            if literal_specials and ch == "<":
                hit = next((sp for sp in self.specials if text.startswith(sp, i)), None)
                if hit is not None:
                    ids.append(t2i[hit])
                    i += len(hit)
                    continue

            # Longest match greedy
            upper = min(n, i + self.max_len)
            tid = None
            j = upper
            while j > i:
                frag = text[i:j]
                tid = t2i.get(frag)
                if tid is None and frag.isalpha():
                    tid = t2i.get(frag.lower())
                if tid is not None:
                    break
                j -= 1

            if tid is not None:
                ids.append(tid)
                i = j
                continue

            # Fallback singolo carattere
            tid = t2i.get(ch)
            if tid is None and ch.isalpha():
                tid = t2i.get(ch.lower())
            ids.append(self.unk_id if tid is None else tid)
            i += 1

        if add_special_tokens and self.eos_id is not None:
            ids.append(self.eos_id)

        return ids

    def decode(self, token_ids: Sequence[int], skip_special_tokens: bool = False) -> str:
        """Decodifica gli ID di token in testo ricostruito (sostituisce i whitespace)."""
        out: List[str] = []
        for tid in token_ids:
            tok = self.id_to_token.get(int(tid), "<|unk|>")
            if skip_special_tokens and tok.startswith("<|") and tok.endswith("|>"):
                continue
            out.append(DECODE_WS.get(tok, tok))
        return "".join(out)

    def batch_encode(self, texts: Sequence[str]) -> List[List[int]]:
        return [self.encode(t) for t in texts]

    def batch_decode(self, batch_ids: Sequence[Sequence[int]], skip_special_tokens: bool = False) -> List[str]:
        return [self.decode(ids, skip_special_tokens=skip_special_tokens) for ids in batch_ids]


if __name__ == "__main__":
    tok = gpTommyTokenizer()
    print(f"=== gpTommy 32k Tokenizer (Vocabolario: {tok.vocab_size} token) ===")
    test_frasi = [
        "ciao, come stai?",
        "qual è la capitale d'italia?",
        "il cuscinetto a sfera radiale riduce l'attrito volvente.",
        "<|user|> spiegami il teorema di pitagora <|assistant|> certo!",
    ]
    for frase in test_frasi:
        ids = tok.encode(frase)
        ricostruita = tok.decode(ids)
        print(f"\nFrase: '{frase}'")
        print(f"Tokens ({len(ids)} ID): {ids[:10]}...")
        print(f"Decodifica: '{ricostruita}'")
        assert frase == ricostruita, f"Mismatch: {frase} != {ricostruita}"
    print("\n✅ Tutti i test di conformità gpTommy 32k sono passati con successo!")
