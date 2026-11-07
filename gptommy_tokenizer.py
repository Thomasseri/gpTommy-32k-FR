#!/usr/bin/env python3
# ============================================================================
# LEGAL NOTICE & WATERMARK: R08 NON-COMMERCIAL RESEARCH & ETHICAL LICENSE v2.0
# Copyright (c) 2026 Thomas Seri (Sentinel). All Rights Reserved.
# Exclusive Jurisdiction: Court of Milan (Sezione Specializzata Impresa), Italy.
# Clean-room reverse engineering, distillation, commercial or military use
# is strictly prohibited and constitutes a breach of contract.
# ============================================================================
from __future__ import annotations

__author__ = "Thomas Seri (Sentinel)"
__license__ = "R08-Non-Commercial-Ethical-License-v2.0"
__jurisdiction__ = "Court of Milan, Italy"
__version__ = "2.0.0"

"""gpTommy 32k Tokenizer v2 (Spazio Implicito + Maiuscole Lossless).
Autore & Ideatore: Thomas Seri (Sentinel)
Ecosistema: Sentinel LifeOS (https://www.sentinelhub.eu)

Novità Tokenizer v2 (default `implicit_space=True`):
- Spazio implicito tra le parole: lo spazio singolo ASCII tra due parole non consuma token
  (riduce i token del ~20,4% sul set di prova: da 75.815 a 60.366 token, 1,85 token/parola);
- ID 10 (`<attaccato>`): emesso solo quando due frammenti sono concatenati senza spazio;
- ID 9 (`<spazi_extra>`): emesso solo per spazi multipli o a inizio/fine sequenza;
- Conservazione 100% lossless delle maiuscole tramite prefissi di caso:
  ID 6 = Iniziale Maiuscola (TitleCase, es. "Il", "Thomas"), ID 5 = TUTTO MAIUSCOLO (es. "R08");
- Compatibilità v1 opzionale (`implicit_space=False`) per i checkpoint storici.
"""

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

DEFAULT_VOCAB_PATH = Path(__file__).resolve().parent / "gpTommy_vocab_by_id.txt"

CASE_UPPER_ID = 5        # Prefisso MAIUSCOLO per il pezzo successivo
CASE_TITLE_ID = 6        # Prefisso Iniziale Maiuscola per il pezzo successivo
EXTRA_SPACE_ID = 9       # Spazio esplicito extra
ATTACH_ID = 10           # <attaccato> in v2 (sopprime lo spazio implicito) / <spazio> in v1
NEWLINE_ID = 11          # \n
TAB_ID = 12              # \t
CR_ID = 13               # \r
NBSP_ID = 14             # \xa0
EOS_ID = 2
UNK_ID = 4

_WS_IDS = {"\n": NEWLINE_ID, "\t": TAB_ID, "\r": CR_ID, "\xa0": NBSP_ID}
_ID_WS = {NEWLINE_ID: "\n", TAB_ID: "\t", CR_ID: "\r", NBSP_ID: "\xa0"}

_RAW_CONTROL_IDS = {
    "\b": 7, "\f": 8,
    "’": 15, "“": 16, "”": 17, "⁺": 18, "˛": 19, "⁶": 20, "®": 21,
}
_ID_RAW_CONTROL = {value: key for key, value in _RAW_CONTROL_IDS.items()}

WS_PIECES_V1 = {
    " ": "<spazio>",
    "\n": "<riga>",
    "\t": "<tab>",
    "\r": "<cr>",
    "\xa0": "<nbsp>",
}
DECODE_WS_V1 = {v: k for k, v in WS_PIECES_V1.items()}


class gpTommyTokenizer:
    """Tokenizer v2 autonomo gpTommy 32k (Spazio Implicito & Maiuscole Lossless)."""

    def __init__(self, vocab_file: Optional[Union[str, Path]] = None, implicit_space: bool = True):
        self.vocab_file = Path(vocab_file) if vocab_file else DEFAULT_VOCAB_PATH
        if not self.vocab_file.exists():
            raise FileNotFoundError(f"File vocabolario non trovato: {self.vocab_file}")

        self.implicit_space = implicit_space
        self.id_to_token: Dict[int, str] = {}
        self.token_to_id: Dict[str, int] = {}
        self.specials: List[str] = []
        self._load_vocab()

        self.pad_id = self.token_to_id.get("<|pad|>", 3)
        self.eos_id = self.token_to_id.get("<|eos|>", 2)
        self.bos_id = self.token_to_id.get("<|bos|>", 1)
        self.unk_id = self.token_to_id.get("<|unk|>", 4)
        self.sep_id = self.token_to_id.get("<|sep|>", 5)
        self.user_id = self.token_to_id.get("<|user|>", 16)
        self.assistant_id = self.token_to_id.get("<|assistant|>", 17)
        self.system_id = self.token_to_id.get("<|system|>", 15)

        self.max_len = max((len(t) for t in self.id_to_token.values() if not t.startswith("<")), default=1)

    def _load_vocab(self) -> None:
        raw_map: Dict[int, str] = {}
        with open(self.vocab_file, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                parts = s.split("\t")
                if len(parts) >= 5:
                    gid = int(parts[3])
                    raw_map[gid] = parts[4]
        n = max(raw_map) + 1 if raw_map else 0
        for i in range(n):
            tok = raw_map.get(i, f"<unk_{i}>")
            self.id_to_token[i] = tok
            self.token_to_id[tok] = i
            if tok.startswith("<") and len(tok) > 1 and tok.endswith(">"):
                self.specials.append(tok)
        self.specials.sort(key=len, reverse=True)

    @property
    def vocab_size(self) -> int:
        return len(self.id_to_token)

    def _encode_atom_v2(self, text: str) -> List[int]:
        if not text:
            return []
        ids = self._encode_v1(text, add_special_tokens=False, literal_specials=False)
        out: List[int] = []
        for n, tid in enumerate(ids):
            if n:
                out.append(ATTACH_ID)
            out.append(tid)
        return out

    def _encode_non_ws_v2(self, text: str, literal_specials: bool = False) -> List[int]:
        out: List[int] = []
        i, n = 0, len(text)
        t2i = self.token_to_id
        reserved = {CASE_UPPER_ID, CASE_TITLE_ID, EXTRA_SPACE_ID, ATTACH_ID, NEWLINE_ID, TAB_ID, CR_ID, NBSP_ID, *_RAW_CONTROL_IDS.values()}
        while i < n:
            if text[i] in _RAW_CONTROL_IDS and text[i] not in t2i:
                if out:
                    out.append(ATTACH_ID)
                out.append(_RAW_CONTROL_IDS[text[i]])
                i += 1
                continue
            if literal_specials and text[i] == "<":
                hit = next((sp for sp in self.specials if text.startswith(sp, i) and sp.startswith("<|") and sp.endswith("|>")), None)
                if hit is not None and t2i[hit] not in reserved:
                    if out:
                        out.append(ATTACH_ID)
                    out.append(t2i[hit])
                    i += len(hit)
                    continue

            alpha = text[i].isalpha()
            j = i + 1
            while j < n and (text[j] not in _RAW_CONTROL_IDS or text[j] in t2i) and text[j].isalpha() == alpha:
                if literal_specials and text[j] == "<":
                    if any(text.startswith(sp, j) for sp in self.specials if sp.startswith("<|") and sp.endswith("|>") and t2i[sp] not in reserved):
                        break
                j += 1
            atom = text[i:j]
            units = [atom]
            if alpha:
                cuts = [0] + [k for k in range(1, len(atom)) if atom[k].isupper()]
                units = [atom[a:b] for a, b in zip(cuts, [*cuts[1:], len(atom)])]
            for unit in units:
                ids = self._encode_atom_v2(unit)
                if alpha:
                    raw = "".join(self.id_to_token[x] for x in ids if x != ATTACH_ID)
                    if unit != raw:
                        if unit == raw.upper():
                            expanded: List[int] = []
                            for tid in ids:
                                if tid != ATTACH_ID:
                                    expanded.append(CASE_UPPER_ID)
                                expanded.append(tid)
                            ids = expanded
                        elif unit[:1].upper() + unit[1:].lower() == unit and raw == raw.lower():
                            ids = [CASE_TITLE_ID, *ids]
                if out:
                    out.append(ATTACH_ID)
                out.extend(ids)
            i = j
        return out

    def encode(self, text: str, add_special_tokens: bool = False, literal_specials: bool = False) -> List[int]:
        """Codifica il testo (v2 a spazio implicito + maiuscole di default; v1 se implicit_space=False)."""
        if not text:
            return []
        if not self.implicit_space:
            return self._encode_v1(text, add_special_tokens=add_special_tokens, literal_specials=literal_specials)

        out: List[int] = []
        if add_special_tokens and self.bos_id is not None:
            out.append(self.bos_id)

        i, n = 0, len(text)
        emitted_regular = False
        while i < n:
            if not text[i].isspace():
                j = i + 1
                while j < n and not text[j].isspace():
                    j += 1
                part = self._encode_non_ws_v2(text[i:j], literal_specials=literal_specials)
                out.extend(part)
                emitted_regular = bool(part)
                i = j
                continue

            j = i + 1
            while j < n and text[j].isspace():
                j += 1
            run = text[i:j]
            next_is_regular = j < n
            if all(ch == " " for ch in run) and emitted_regular and next_is_regular:
                out.extend([EXTRA_SPACE_ID] * (len(run) - 1))
                i, emitted_regular = j, False
                continue
            for ch in run:
                if ch == " ":
                    out.append(EXTRA_SPACE_ID)
                elif ch in _WS_IDS:
                    out.append(_WS_IDS[ch])
                else:
                    out.append(EXTRA_SPACE_ID)
            emitted_regular = False
            i = j

        if add_special_tokens and self.eos_id is not None:
            out.append(self.eos_id)
        return out

    def decode(self, token_ids: Sequence[int], skip_special_tokens: bool = False) -> str:
        """Decodifica gli ID di token in testo ricostruito."""
        if not self.implicit_space:
            return self._decode_v1(token_ids, skip_special_tokens=skip_special_tokens)

        pieces: List[str] = []
        previous = "start"
        attach = False
        extra_spaces = 0
        case_mode: Optional[int] = None

        for value in token_ids:
            tid = int(value)
            if tid == EXTRA_SPACE_ID:
                extra_spaces += 1
                continue
            if tid == ATTACH_ID:
                attach = True
                continue
            if tid in {CASE_UPPER_ID, CASE_TITLE_ID}:
                case_mode = tid
                continue
            if tid in _ID_WS:
                if extra_spaces:
                    pieces.append(" " * extra_spaces)
                    extra_spaces = 0
                pieces.append(_ID_WS[tid])
                previous = "ws"
                attach = False
                case_mode = None
                continue

            if tid in _ID_RAW_CONTROL and _ID_RAW_CONTROL[tid] not in self.token_to_id:
                raw = _ID_RAW_CONTROL[tid]
            else:
                raw = self.id_to_token.get(tid, "<|unk|>")
                if skip_special_tokens and raw.startswith("<|") and raw.endswith("|>"):
                    case_mode = None
                    continue

            if case_mode == CASE_UPPER_ID:
                raw = raw.upper()
            elif case_mode == CASE_TITLE_ID:
                raw = raw[:1].upper() + raw[1:]

            if previous == "regular":
                pieces.append("" if attach else " " * (1 + extra_spaces))
            elif previous in {"start", "ws"} and extra_spaces:
                pieces.append(" " * extra_spaces)
            pieces.append(raw)
            previous, attach, extra_spaces, case_mode = "regular", False, 0, None

        if extra_spaces:
            pieces.append(" " * extra_spaces)
        return "".join(pieces)

    def _encode_v1(self, text: str, add_special_tokens: bool = False, literal_specials: bool = False) -> List[int]:
        ids: List[int] = []
        if add_special_tokens and self.bos_id is not None:
            ids.append(self.bos_id)
        n, i = len(text), 0
        t2i = self.token_to_id
        while i < n:
            ch = text[i]
            if ch.isspace() or ch in WS_PIECES_V1:
                tid = t2i.get(WS_PIECES_V1.get(ch, "<spazio>"))
                if tid is not None:
                    ids.append(tid)
                i += 1
                continue
            if literal_specials and ch == "<":
                hit = next((sp for sp in self.specials if text.startswith(sp, i)), None)
                if hit is not None:
                    ids.append(t2i[hit])
                    i += len(hit)
                    continue
            upper = min(n, i + self.max_len)
            tid, j = None, upper
            while j > i:
                frag = text[i:j]
                tid = t2i.get(frag)
                if tid is None:
                    tid = t2i.get(frag.lower())
                if tid is not None:
                    break
                j -= 1
            if tid is not None:
                ids.append(tid)
                i = j
            else:
                tid = t2i.get(ch) or t2i.get(ch.lower())
                ids.append(self.unk_id if tid is None else tid)
                i += 1
        if add_special_tokens and self.eos_id is not None:
            ids.append(self.eos_id)
        return ids

    def _decode_v1(self, token_ids: Sequence[int], skip_special_tokens: bool = False) -> str:
        out: List[str] = []
        for tid in token_ids:
            tok = self.id_to_token.get(int(tid), "<|unk|>")
            if skip_special_tokens and tok.startswith("<|") and tok.endswith("|>"):
                continue
            out.append(DECODE_WS_V1.get(tok, tok))
        return "".join(out)

    def batch_encode(self, texts: Sequence[str]) -> List[List[int]]:
        return [self.encode(t) for t in texts]

    def batch_decode(self, batch_ids: Sequence[Sequence[int]], skip_special_tokens: bool = False) -> List[str]:
        return [self.decode(ids, skip_special_tokens=skip_special_tokens) for ids in batch_ids]


if __name__ == "__main__":
    tok = gpTommyTokenizer()
    print(f"=== gpTommy 32k Tokenizer v2 (Vocabolario: {tok.vocab_size} token, Spazio Implicito + Maiuscole) ===")
    test_frasi = [
        "Ciao, come stai?",
        "Qual è la capitale d'Italia?",
        "Il cuscinetto a sfere radiale riduce l'attrito volvente nella manutenzione dei cilindri pneumatici.",
        "<|im_start|> Spiegami il funzionamento del PLC Siemens <|im_end|> Certo!",
    ]
    for frase in test_frasi:
        ids = tok.encode(frase, literal_specials=True)
        ricostruita = tok.decode(ids)
        print(f"\nFrase: '{frase}'")
        print(f"Tokens v2 ({len(ids)} ID): {ids[:12]}...")
        print(f"Decodifica: '{ricostruita}'")
        assert frase == ricostruita, f"Mismatch: {frase!r} != {ricostruita!r}"
    print("\n✅ Tutti i test di conformità gpTommy 32k v2 (100% lossless) sono passati con successo!")
