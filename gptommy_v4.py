#!/usr/bin/env python3
"""gpTommy v4 — Tokenizer (spazi impliciti `▁`, maiuscole a parola/sequenza, riserva a byte UTF-8).

Author & Creator: Thomas Seri (Sentinel) — https://www.sentinelhub.eu

Caratteristiche principali rispetto a v3:
  1. Inizio parola dentro il pezzo (`▁`, U+2581): lo spazio ASCII singolo precede i pezzi con `▁` quando lo
     stato `no_space` è False; i pezzi senza `▁` si attaccano direttamente senza emettere `<|attacca|>`.
  2. Punteggiatura di chiusura e apostrofi/elisioni (`▁l'`, `▁dell'`, `▁c'`, `'s`, `n't`, `.`, `,`, …) gestiti
     direttamente via stato `no_space_after`, azzerando `<|attacca|>` nella prosa.
  3. Maiuscole a parola (`<|maiuscolo_parola|>`), sequenza (`<|maiuscolo_inizio|>…<|maiuscolo_fine|>`),
     iniziale (`<|iniziale_maiuscola|>`) e CamelCase (`<|camel_maiuscola|>` con taglio solo minuscola->Maiuscola
     e prima di `[Maiuscola][minuscola]` negli acronimi, es. `HTTPServer -> HTTP | Server`).
  4. Riserva completa a 256 byte UTF-8 (`<0x00>`..`<0xFF>` agli ID 64..319): qualunque testo Unicode è
     scrivibile e decodificabile senza alcuna perdita (`0 non_scrivibili`, `0 tornati_diversi`).
  5. Tabella ID ordinata e disgiunta (0..31 ruoli chat; 32..63 controlli; 64..319 byte UTF-8; 320..561 caratteri
     singoli con nome == carattere per `_RAW_CONTROL_IDS`; blocco fisso elisioni/operatori; pezzi BPE).

Interfaccia:
  - `carica_vocabolario(percorso)`
  - `encode(testo, pv)`
  - `decode(ids, pv)`
  - `TokenizerError`
  - `ATTACH_ID`, `_RAW_CONTROL_IDS`
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Sequence

# ---------------------------------------------------------------------------
# Eccezione ed ID fissi universali (identici in tutti i vocabolari v4)
# ---------------------------------------------------------------------------

class TokenizerError(ValueError):
    """Errore di codifica/decodifica o formato vocabolario gpTommy v4."""


# Blocco 1: ID 0..31 — Solo ruoli chat e speciali di addestramento (mai emessi su testo normale)
SPECIAL_ROLE_TOKENS: tuple[str, ...] = (
    "<|end|>",           # 0
    "<|bos|>",           # 1
    "<|eos|>",           # 2
    "<|pad|>",           # 3  (compatibile con ignore_index=3)
    "<|unk|>",           # 4
    "<|sep|>",           # 5
    "<|system|>",        # 6
    "<|user|>",          # 7
    "<|assistant|>",     # 8
    "<|tool|>",          # 9
    "<|tool_result|>",   # 10
    "<|tool_call|>",     # 11
    "<|im_start|>",      # 12
    "<|im_end|>",        # 13
    "<|think|>",         # 14
    "<|/think|>",        # 15
    *(f"<|riservato_{i}|>" for i in range(16, 32)),
)
EOS_ID = 2
PAD_ID = 3
UNK_ID = 4

# Blocco 2: ID 32..63 — Controlli di maiuscole, attacco e spaziatura/indentazione
ID_CAPS_WORD = 32
ID_CAP_FIRST = 33
ID_CAPS_START = 34
ID_CAPS_END = 35
ID_CAMEL_CAP = 36
ATTACH_ID = 37
ID_SPACE = 38

CONTROL_TOKENS: tuple[str, ...] = (
    "<|maiuscolo_parola|>",    # 32
    "<|iniziale_maiuscola|>",  # 33
    "<|maiuscolo_inizio|>",    # 34
    "<|maiuscolo_fine|>",      # 35
    "<|camel_maiuscola|>",     # 36
    "<|attacca|>",             # 37
    "<spazio>",                # 38  " "
    "<spazi_2>",               # 39  "  "
    "<spazi_4>",               # 40  "    "
    "<spazi_8>",               # 41  "        "
    "<spazi_12>",              # 42  "            "
    "<spazi_16>",              # 43  "                "
    "<riga>",                  # 44  "\n"
    "<riga_2>",                # 45  "\n\n"
    "<tab>",                   # 46  "\t"
    "<tab_2>",                 # 47  "\t\t"
    "<cr>",                    # 48  "\r"
    "<crlf>",                  # 49  "\r\n"
    "<nbsp>",                  # 50  "\xa0"
    "<riga_spazi_2>",          # 51  "\n  "
    "<riga_spazi_4>",          # 52  "\n    "
    "<riga_spazi_8>",          # 53  "\n        "
    "<riga_spazi_12>",         # 54  "\n            "
    "<riga_spazi_16>",         # 55  "\n                "
    "<riga_tab>",              # 56  "\n\t"
    "<riga_tab_2>",            # 57  "\n\t\t"
    "<riga_tab_3>",            # 58  "\n\t\t\t"
    *(f"<|ctrl_{i}|>" for i in range(59, 64)),
)

_WS_CONTROL_STRINGS: tuple[tuple[int, str], ...] = (
    (38, " "),
    (39, "  "),
    (40, "    "),
    (41, "        "),
    (42, "            "),
    (43, "                "),
    (44, "\n"),
    (45, "\n\n"),
    (46, "\t"),
    (47, "\t\t"),
    (48, "\r"),
    (49, "\r\n"),
    (50, "\xa0"),
    (51, "\n  "),
    (52, "\n    "),
    (53, "\n        "),
    (54, "\n            "),
    (55, "\n                "),
    (56, "\n\t"),
    (57, "\n\t\t"),
    (58, "\n\t\t\t"),
)
_ID_TO_WS: dict[int, str] = dict(_WS_CONTROL_STRINGS)
# Ordine decrescente di lunghezza per match greedy su `\n + indentazione` e `\r\n`
_WS_MATCH_NON_SPACE: tuple[tuple[str, int], ...] = tuple(
    sorted(
        [(s, tid) for tid, s in _WS_CONTROL_STRINGS if " " not in s or "\n" in s],
        key=lambda x: len(x[0]),
        reverse=True,
    )
)
_SPACES_DESC: tuple[tuple[int, int], ...] = (
    (16, 43),
    (12, 42),
    (8, 41),
    (4, 40),
    (2, 39),
    (1, 38),
)

# Blocco 3: ID 64..319 — Riserva a 256 byte UTF-8
BYTE_ID_START = 64
BYTE_TOKENS: tuple[str, ...] = tuple(f"<0x{b:02X}>" for b in range(256))  # 64..319

# Blocco 4: da ID 320 — Caratteri singoli stampabili (nome nel TSV == carattere stesso)
RAW_CHAR_ID_START = 320


def _build_raw_chars() -> tuple[str, ...]:
    """Costruisce la lista deterministica dei caratteri singoli nel Blocco 4."""
    candidati: list[str] = []
    # 94 ASCII stampabili (0x21..0x7E)
    for cp in range(0x21, 0x7F):
        candidati.append(chr(cp))
    # Lettere europee (IT, EN, FR, ES, DE + prestiti europei comuni), minuscole e forme non reversibili
    eu_letters = (
        "àáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿœßı"
        "āēīōūăąćčďđěğĺľłńňőŕřśšşťţůűźżž"
        "ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞŸŒẞİ"
    )
    candidati.extend(eu_letters)
    # Punteggiatura tipografica, virgolette (incluse tedesche/francesi), valute, simboli tecnici,
    # matematici, legali e tutti i caratteri stampabili di v3
    simboli = (
        "’“”„‚‘«»‹›—–−…•·°€£¥¢₹§¶®™©¿¡†‡※′″‰"
        "±×÷≤≥≠≈≡∞√∑∆∂µπΩαβγδεθλσφω"
        "→←↑↓↔⇒⇐∅∴✓✔✗★☆♥♦♣♠"
        "½¼¾⅓⅔№⁺⁻⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃ⁿ˛ʿ´¦"
        "😀🚀🔍🧹📅🐣🏜👼"
    )
    candidati.extend(simboli)
    out: list[str] = []
    seen: set[str] = set()
    for c in candidati:
        if c in seen:
            continue
        if len(c) != 1 or c == "\u2581":  # U+2581 ('▁') riservato come marcatore spazio implicito
            continue
        if c.isspace() or c.strip() != c:
            continue
        if unicodedata.category(c).startswith(("C", "Z", "M")):
            continue
        seen.add(c)
        out.append(c)
    return tuple(out)


RAW_CHAR_LIST: tuple[str, ...] = _build_raw_chars()
RAW_CHAR_SET: frozenset[str] = frozenset(RAW_CHAR_LIST)
_RAW_CONTROL_IDS: dict[str, int] = {c: RAW_CHAR_ID_START + i for i, c in enumerate(RAW_CHAR_LIST)}
_ID_RAW_CONTROL: dict[int, str] = {i: c for c, i in _RAW_CONTROL_IDS.items()}

# Caratteri singoli che sopprimono lo spazio prima del pezzo successivo (no_space_after = True)
_BARE_NO_SPACE_AFTER_CHARS: frozenset[str] = frozenset("([{\"«„‚¡¿/_@$-=&")

# Blocco 5: Elisioni, punteggiatura spaziata, operatori di codice/PLC e coppie di cifre (universali)
ELISION_WORDS: tuple[str, ...] = (
    "l'", "l’",
    "d'", "d’",
    "c'", "c’",
    "qu'", "qu’",
    "un'", "un’",
    "all'", "all’",
    "dell'", "dell’",
    "nell'", "nell’",
    "sull'", "sull’",
    "dall'", "dall’",
    "j'", "j’",
    "m'", "m’",
    "n'", "n’",
    "s'", "s’",
    "t'", "t’",
    "quest'", "quest’",
    "gliel'", "gliel’",
    "sant'", "sant’",
    "bell'", "bell’",
    "grand'", "grand’",
    "nessun'", "nessun’",
    "ciascun'", "ciascun’",
    "alcun'", "alcun’",
    "altr'", "altr’",
    "senz'", "senz’",
    "nient'", "nient’",
    "tutt'", "tutt’",
    "com'", "com’",
    "anch'", "anch’",
    "jusqu'", "jusqu’",
    "lorsqu'", "lorsqu’",
    "puisqu'", "puisqu’",
    "presqu'", "presqu’",
    "quelqu'", "quelqu’",
    "aujourd'", "aujourd’",
)

_PREFIXED_OPEN_PUNCT_NO_SPACE: tuple[str, ...] = (
    "▁(", "▁[", "▁{", "▁«", "▁“", "▁„", "▁‚", "▁‘", '▁"', "▁'",
    "▁¡", "▁¿", "▁/", "▁_", "▁@", "▁$",
)

_PREFIXED_SPACED_SYMBOLS: tuple[str, ...] = (
    "▁—", "▁–", "▁-", "▁+", "▁=", "▁*", "▁&", "▁|", "▁#", "▁%",
    "▁<", "▁>", "▁€", "▁£", "▁¥", "▁¢", "▁₹", "▁•", "▁→", "▁§",
    "▁¶", "▁№", "▁:", "▁;", "▁,", "▁.", "▁?", "▁!", "▁°", "▁«",
    "▁==", "▁!=", "▁<=", "▁>=", "▁===", "▁!==", "▁:=", "▁->", "▁=>",
    "▁//", "▁/*", "▁&&", "▁||", "▁+=", "▁-=", "▁--", "▁++", "▁::", "▁...",
    "▁**", "▁<<", "▁>>",
)

_CONTRACTION_SUFFIXES: tuple[str, ...] = (
    "'s", "’s", "n't", "n’t", "'m", "’m", "'re", "’re",
    "'ve", "’ve", "'ll", "’ll", "'d", "’d", "'t", "’t",
)

_CODE_OPS_NO_SPACE_AFTER: tuple[str, ...] = (
    "https://", "http://", "www.", "://", "</", "<!--", "->", "::", ":=",
)

_CODE_OPS_SPACE_AFTER: tuple[str, ...] = (
    "===", "!==", "==", "!=", "<=", ">=", "=>", "+=", "-=", "*=", "/=",
    "**", "&&", "||", "//", "/*", "*/", "-->", "/>", "();", "();", ");",
    "):", "()", "[]", "{}", "],", "},", "];", "};", "))", "]]",
    '",', '":', '";', "',", "':", "';", "...", "--", "++", "<<", ">>",
    ".json", ".html", ".com", ".org", ".net",
)


# ---------------------------------------------------------------------------
# Reversibilità maiuscole/minuscole
# ---------------------------------------------------------------------------

_IS_REV_UPPER_CACHE: dict[str, bool] = {}
_IS_REV_LOWER_CACHE: dict[str, bool] = {}


def is_rev_upper(c: str) -> bool:
    """True sse c ha una minuscola singola reversibile (c.lower().upper() == c != c.lower())."""
    v = _IS_REV_UPPER_CACHE.get(c)
    if v is not None:
        return v
    lo = c.lower()
    res = len(lo) == 1 and lo != c and lo.upper() == c
    _IS_REV_UPPER_CACHE[c] = res
    return res


def is_rev_lower(c: str) -> bool:
    """True sse c ha una maiuscola singola reversibile (c.upper().lower() == c != c.upper())."""
    v = _IS_REV_LOWER_CACHE.get(c)
    if v is not None:
        return v
    up = c.upper()
    res = len(up) == 1 and up != c and up.lower() == c
    _IS_REV_LOWER_CACHE[c] = res
    return res


def _to_upper_rev(s: str) -> str:
    return "".join(c.upper() if is_rev_lower(c) else c for c in s)


def _to_lower_rev(s: str) -> str:
    return "".join(c.lower() if is_rev_upper(c) else c for c in s)


def _is_pure_rev_lower_core(core: str) -> bool:
    return len(core) > 0 and all(is_rev_lower(c) for c in core)


def _build_universal_multi_tokens() -> tuple[tuple[str, ...], frozenset[str]]:
    tokens: list[str] = []
    no_space_after: set[str] = set()
    seen: set[str] = set()

    def add(tok: str, nsa: bool) -> None:
        if tok in seen or tok in _RAW_CONTROL_IDS:
            return
        seen.add(tok)
        tokens.append(tok)
        if nsa:
            no_space_after.add(tok)

    for el in ELISION_WORDS:
        add("\u2581" + el, True)
    for tok in _PREFIXED_OPEN_PUNCT_NO_SPACE:
        add(tok, True)
    for tok in _PREFIXED_SPACED_SYMBOLS:
        add(tok, tok in no_space_after or tok == "▁«")
    for tok in _CONTRACTION_SUFFIXES:
        add(tok, False)
    for tok in _CODE_OPS_NO_SPACE_AFTER:
        add(tok, True)
    for tok in _CODE_OPS_SPACE_AFTER:
        add(tok, False)
    # 100 coppie di cifre di continuazione + "000" per date, IP, decimali e indirizzi PLC
    for i in range(100):
        add(f"{i:02d}", False)
    add("000", False)
    # Garanzia di chiusura: `▁` + ogni singola cifra o lettera minuscola/canonica del Blocco 4
    # così `_segmenta_dp_inizio` non fallisce mai su nessuna parola o lettera singola (`▁x`, `▁è`, `▁7`).
    for ch in RAW_CHAR_LIST:
        if ("0" <= ch <= "9") or (ch.isalpha() and ch == ch.lower() and not is_rev_upper(ch)):
            add("\u2581" + ch, False)

    return tuple(tokens), frozenset(no_space_after)


UNIVERSAL_MULTI_TOKENS, _MULTI_NO_SPACE_AFTER = _build_universal_multi_tokens()
UNIVERSAL_NO_SPACE_AFTER_TOKENS: frozenset[str] = _BARE_NO_SPACE_AFTER_CHARS | _MULTI_NO_SPACE_AFTER

UNIVERSAL_PREFIX_TOKENS: tuple[str, ...] = (
    *SPECIAL_ROLE_TOKENS,
    *CONTROL_TOKENS,
    *BYTE_TOKENS,
    *RAW_CHAR_LIST,
    *UNIVERSAL_MULTI_TOKENS,
)
UNIVERSAL_PREFIX_LEN = len(UNIVERSAL_PREFIX_TOKENS)

# ---------------------------------------------------------------------------
# Struttura vocabolario & indice veloce
# ---------------------------------------------------------------------------

class VocabV4:
    """Vocabolario gpTommy v4 con tabelle di ricerca veloci per codifica/decodifica."""

    def __init__(
        self,
        *,
        name: str,
        id_to_token: list[str],
        token_to_id: dict[str, int],
        path: Path | None = None,
        has_ws: tuple[bool, ...] = (),
        cores: tuple[str, ...] = (),
        is_pure_rev_lower: tuple[bool, ...] = (),
        no_space_after_ids: frozenset[int] = frozenset(),
        raw_char_ids: dict[str, int] | None = None,
        pref_by_start: dict[str, dict[str, int]] | None = None,
        pref_max_len: dict[str, int] | None = None,
        cont_by_start: dict[str, dict[str, int]] | None = None,
        cont_max_len: dict[str, int] | None = None,
        elision_ids: dict[str, int] | None = None,
        max_elision_len: int = 0,
        ops_pref_by_start: dict[str, list[tuple[str, int]]] | None = None,
        ops_cont_by_start: dict[str, list[tuple[str, int]]] | None = None,
    ) -> None:
        self.name = name
        self.id_to_token = id_to_token
        self.token_to_id = token_to_id
        self.path = path
        self.has_ws = has_ws
        self.cores = cores
        self.is_pure_rev_lower = is_pure_rev_lower
        self.no_space_after_ids = no_space_after_ids
        self.special_role_ids: frozenset[int] = frozenset(range(32))
        self.raw_char_ids = {} if raw_char_ids is None else raw_char_ids
        self.pref_by_start = {} if pref_by_start is None else pref_by_start
        self.pref_max_len = {} if pref_max_len is None else pref_max_len
        self.cont_by_start = {} if cont_by_start is None else cont_by_start
        self.cont_max_len = {} if cont_max_len is None else cont_max_len
        self.elision_ids = {} if elision_ids is None else elision_ids
        self.max_elision_len = max_elision_len
        self.ops_pref_by_start = {} if ops_pref_by_start is None else ops_pref_by_start
        self.ops_cont_by_start = {} if ops_cont_by_start is None else ops_cont_by_start
        self.word_cache: dict[str, tuple[int, ...]] = {}
        self.cont_cache: dict[str, tuple[int, ...]] = {}

    def __len__(self) -> int:
        return len(self.id_to_token)

    @property
    def eos_id(self) -> int:
        return EOS_ID

    @property
    def pad_id(self) -> int:
        return PAD_ID

    @property
    def unk_id(self) -> int:
        return UNK_ID


_STAGE_INDEX_CACHE: dict[int, VocabV4] = {}


def _costruisci_indici(id_to_token: list[str], name: str = "gptommy_v4", path: Path | None = None) -> VocabV4:
    if len(id_to_token) < UNIVERSAL_PREFIX_LEN:
        raise TokenizerError(
            f"vocabolario troppo corto: {len(id_to_token)} < prefisso universale {UNIVERSAL_PREFIX_LEN}"
        )
    token_to_id: dict[str, int] = {}
    has_ws_list: list[bool] = []
    cores_list: list[str] = []
    pure_list: list[bool] = []
    nsa_ids: set[int] = set()
    raw_chars: dict[str, int] = {}
    pref_by_start: dict[str, dict[str, int]] = {}
    pref_max_len: dict[str, int] = {}
    cont_by_start: dict[str, dict[str, int]] = {}
    cont_max_len: dict[str, int] = {}
    elision_ids: dict[str, int] = {}
    max_elision_len = 0
    ops_pref_by_start: dict[str, list[tuple[str, int]]] = {}
    ops_cont_by_start: dict[str, list[tuple[str, int]]] = {}

    elision_set = set(ELISION_WORDS)
    ops_set = set(_PREFIXED_OPEN_PUNCT_NO_SPACE) | set(_PREFIXED_SPACED_SYMBOLS) | set(_CONTRACTION_SUFFIXES) | set(_CODE_OPS_NO_SPACE_AFTER) | set(_CODE_OPS_SPACE_AFTER)

    for tid, tok in enumerate(id_to_token):
        if tok not in token_to_id:
            token_to_id[tok] = tid
        ws = tid >= RAW_CHAR_ID_START and tok.startswith("\u2581")
        core = tok[1:] if ws else tok
        has_ws_list.append(ws)
        cores_list.append(core)
        pure_list.append(tid >= RAW_CHAR_ID_START and _is_pure_rev_lower_core(core))
        if tok in UNIVERSAL_NO_SPACE_AFTER_TOKENS:
            nsa_ids.add(tid)

        if tid < RAW_CHAR_ID_START:
            continue
        if len(tok) == 1 and not ws:
            raw_chars[tok] = tid
        if ws:
            if core in elision_set:
                elision_ids[core] = tid
                if len(core) > max_elision_len:
                    max_elision_len = len(core)
            if tok in ops_set:
                ops_pref_by_start.setdefault(core[0], []).append((core, tid))
            if core:
                d = pref_by_start.setdefault(core[0], {})
                d[core] = tid
                if len(core) > pref_max_len.get(core[0], 0):
                    pref_max_len[core[0]] = len(core)
        else:
            if tok in ops_set:
                ops_cont_by_start.setdefault(tok[0], []).append((tok, tid))
            d = cont_by_start.setdefault(tok[0], {})
            d[tok] = tid
            if len(tok) > cont_max_len.get(tok[0], 0):
                cont_max_len[tok[0]] = len(tok)

    for lst in ops_pref_by_start.values():
        lst.sort(key=lambda x: len(x[0]), reverse=True)
    for lst in ops_cont_by_start.values():
        lst.sort(key=lambda x: len(x[0]), reverse=True)

    return VocabV4(
        name=name,
        id_to_token=id_to_token,
        token_to_id=token_to_id,
        path=path,
        has_ws=tuple(has_ws_list),
        cores=tuple(cores_list),
        is_pure_rev_lower=tuple(pure_list),
        no_space_after_ids=frozenset(nsa_ids),
        raw_char_ids=raw_chars,
        pref_by_start=pref_by_start,
        pref_max_len=pref_max_len,
        cont_by_start=cont_by_start,
        cont_max_len=cont_max_len,
        elision_ids=elision_ids,
        max_elision_len=max_elision_len,
        ops_pref_by_start=ops_pref_by_start,
        ops_cont_by_start=ops_cont_by_start,
    )


def _as_vocab_v4(pv) -> VocabV4:
    if isinstance(pv, VocabV4):
        return pv
    key = id(pv)
    cached = _STAGE_INDEX_CACHE.get(key)
    if cached is not None and len(cached.id_to_token) == len(pv.id_to_token):
        return cached
    v4 = _costruisci_indici(list(pv.id_to_token), getattr(pv, "name", "stage"), getattr(pv, "path", None))
    _STAGE_INDEX_CACHE[key] = v4
    return v4


def carica_vocabolario(percorso: Path | str) -> VocabV4:
    """Carica un vocabolario TSV gpTommy v4 (`codice\\tscheda\\triga\\tid\\tpezzo`)."""
    p = Path(percorso)
    id_to_token: dict[int, str] = {}
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.split("\t")
            if len(parts) < 5:
                continue
            gid = int(parts[3])
            id_to_token[gid] = parts[4]
    if not id_to_token:
        raise TokenizerError(f"vocabolario vuoto: {p}")
    n = max(id_to_token) + 1
    if len(id_to_token) != n:
        missing = sorted(set(range(n)) - set(id_to_token))[:5]
        raise TokenizerError(f"vocabolario con ID mancanti: {missing}")
    tokens = [id_to_token[i] for i in range(n)]
    return _costruisci_indici(tokens, name=p.stem, path=p)


def tokenizer_fingerprint(vocab_path: Path | str) -> str:
    """Impronta SHA-256 combinata di `gptommy_v4.py` e del file vocabolario."""
    h = hashlib.sha256()
    for path in (Path(__file__), Path(vocab_path)):
        h.update(path.name.encode("utf-8"))
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Segmentazione DP ottimale di parole e numeri
# ---------------------------------------------------------------------------

def _segmenta_dp_inizio(word_lower: str, v4: VocabV4) -> tuple[int, ...] | None:
    """Segmenta `"▁" + word_lower` scegliendo i pezzi (1° con `▁`, restanti senza `▁`) con costo minimo."""
    cached = v4.word_cache.get(word_lower)
    if cached is not None:
        return cached

    n = len(word_lower)
    # dp[k] = (num_tokens, neg_first_len_score, tie_id_sum, prev_pos, token_id)
    inf = 10**9
    cost = [inf] * (n + 1)
    id_sum = [inf] * (n + 1)
    prev = [-1] * (n + 1)
    tok_used = [-1] * (n + 1)
    cost[0] = 0
    id_sum[0] = 0

    # Passo 0: primo pezzo DEVE avere `▁`
    pdict0 = v4.pref_by_start.get(word_lower[0])
    if not pdict0:
        return None
    m0 = min(n, v4.pref_max_len[word_lower[0]])
    for j in range(m0, 0, -1):
        tid = pdict0.get(word_lower[:j])
        if tid is not None:
            cost[j] = 1
            id_sum[j] = tid
            prev[j] = 0
            tok_used[j] = tid

    # Passi i >= 1: pezzi di continuazione senza `▁`
    for i in range(1, n):
        ci = cost[i]
        if ci == inf:
            continue
        cdict = v4.cont_by_start.get(word_lower[i])
        if not cdict:
            continue
        mi = min(n, i + v4.cont_max_len[word_lower[i]])
        nc = ci + 1
        si = id_sum[i]
        for j in range(mi, i, -1):
            tid = cdict.get(word_lower[i:j])
            if tid is None:
                continue
            cj = cost[j]
            ns = si + tid
            if nc < cj or (nc == cj and ns < id_sum[j]):
                cost[j] = nc
                id_sum[j] = ns
                prev[j] = i
                tok_used[j] = tid

    if cost[n] == inf:
        return None
    seq: list[int] = []
    cur = n
    while cur > 0:
        seq.append(tok_used[cur])
        cur = prev[cur]
    seq.reverse()
    res = tuple(seq)
    if len(v4.word_cache) < 200_000:
        v4.word_cache[word_lower] = res
    return res


def _segmenta_dp_continuazione(word_lower: str, v4: VocabV4) -> tuple[int, ...] | None:
    """Segmenta `word_lower` usando SOLO pezzi senza `▁`."""
    cached = v4.cont_cache.get(word_lower)
    if cached is not None:
        return cached

    n = len(word_lower)
    inf = 10**9
    cost = [inf] * (n + 1)
    id_sum = [inf] * (n + 1)
    prev = [-1] * (n + 1)
    tok_used = [-1] * (n + 1)
    cost[0] = 0
    id_sum[0] = 0

    for i in range(n):
        ci = cost[i]
        if ci == inf:
            continue
        cdict = v4.cont_by_start.get(word_lower[i])
        if not cdict:
            continue
        mi = min(n, i + v4.cont_max_len[word_lower[i]])
        nc = ci + 1
        si = id_sum[i]
        for j in range(mi, i, -1):
            tid = cdict.get(word_lower[i:j])
            if tid is None:
                continue
            cj = cost[j]
            ns = si + tid
            if nc < cj or (nc == cj and ns < id_sum[j]):
                cost[j] = nc
                id_sum[j] = ns
                prev[j] = i
                tok_used[j] = tid

    if cost[n] == inf:
        return None
    seq: list[int] = []
    cur = n
    while cur > 0:
        seq.append(tok_used[cur])
        cur = prev[cur]
    seq.reverse()
    res = tuple(seq)
    if len(v4.cont_cache) < 200_000:
        v4.cont_cache[word_lower] = res
    return res


# ---------------------------------------------------------------------------
# Classificazione ed estrazione atomi di parola / CamelCase / CAPS span
# ---------------------------------------------------------------------------

def _is_word_alpha_char(c: str, v4: VocabV4) -> bool:
    """True per lettere presenti nel Blocco 4 con minuscola canonica o maiuscola reversibile."""
    if c not in v4.raw_char_ids:
        return False
    if not c.isalpha():
        return False
    return (c == c.lower() and not is_rev_upper(c)) or is_rev_upper(c)


def _split_case_units(atom: str) -> list[tuple[str, str]]:
    """Spezza `atom` in unita' omogenee `(modo, testo)`:
    modo in {'lower', 'title', 'caps_word', 'raw_lower'}.
    - Il taglio CamelCase avviene SOLO minuscola -> Maiuscola oppure prima di `[Maiuscola][minuscola]`
      negli acronimi (`HTTPServer -> [('caps_word','HTTP'), ('title','Server')]`).
    - Lettere minuscole non reversibili (`ß`, `ı`) restano nel blocco `lower`/`title` precedente se compatibili,
      ma rompono eventuali run `ALL-CAPS` così non finiscono dentro `ID_CAPS_WORD`.
    """
    n = len(atom)
    units: list[tuple[str, str]] = []
    i = 0
    while i < n:
        c = atom[i]
        if is_rev_upper(c):
            # Trova il run consecutivo di is_rev_upper
            j = i + 1
            while j < n and is_rev_upper(atom[j]):
                j += 1
            run_u = j - i
            # Caso 1: seguito da lettere minuscole (`c == c.lower() and not is_rev_upper(c)`)
            if j < n and not is_rev_upper(atom[j]):
                # Scansiona tutte le minuscole seguenti
                k = j + 1
                while k < n and not is_rev_upper(atom[k]):
                    k += 1
                if run_u == 1:
                    units.append(("title", atom[i:k]))
                else:
                    # Ultime lettere: l'ultima maiuscola si lega alle minuscole se is_rev_lower(atom[j])!
                    # (Se atom[j] fosse 'ß' non reversibile, teniamo l'acronimo integro e 'ß' staccato)
                    if is_rev_lower(atom[j]):
                        units.append(("caps_word", atom[i : j - 1]))
                        units.append(("title", atom[j - 1 : k]))
                    else:
                        units.append(("caps_word", atom[i:j]))
                        units.append(("raw_lower", atom[j:k]))
                i = k
            else:
                if run_u == 1:
                    units.append(("title", atom[i:j]))
                else:
                    units.append(("caps_word", atom[i:j]))
                i = j
        else:
            j = i + 1
            while j < n and not is_rev_upper(atom[j]):
                j += 1
            # Distinguiamo puro reversibile vs contenente 'ß'/'ı' (entrambe usano lo stesso encoder minuscolo!)
            units.append(("lower", atom[i:j]))
            i = j
    return units


def _trova_caps_span(text: str, start: int) -> int:
    """Se da `start` inizia una sequenza tutta maiuscola (>=3 run maiuscoli disgiunti sulla stessa riga,
    senza minuscole reversibili né maiuscole non reversibili), ritorna l'indice `end` subito dopo
    l'ultima lettera maiuscola valida; altrimenti ritorna `0`."""
    n = len(text)
    if start >= n or not is_rev_upper(text[start]):
        return 0
    runs = 0
    long_runs = 0
    rev_chars = 0
    last_end = 0
    i = start
    while i < n:
        c = text[i]
        if c == "\n" or c == "\r":
            break
        if is_rev_lower(c):
            # Se siamo dentro/subito attaccati a questa parola mista, esclude l'ultima parola non chiusa
            break
        if c != c.lower() and not is_rev_upper(c):
            break
        if is_rev_upper(c):
            j = i + 1
            while j < n and is_rev_upper(text[j]):
                j += 1
            # Se subito dopo `j` c'è una lettera minuscola (`is_rev_lower`), questa parola NON è tutta maiuscola!
            if j < n and is_rev_lower(text[j]):
                break
            rlen = j - i
            runs += 1
            if rlen >= 2:
                long_runs += 1
            rev_chars += rlen
            last_end = j
            i = j
            continue
        i += 1
    if runs >= 3 and (long_runs >= 2 or rev_chars >= 6):
        return last_end
    return 0


# ---------------------------------------------------------------------------
# Encoder & Decoder principali
# ---------------------------------------------------------------------------

def _flush_pending_space(out: list[int], pending_space: bool, cur_no_space: bool) -> tuple[bool, bool]:
    if pending_space:
        out.append(ID_SPACE)
        return False, True
    return False, cur_no_space


def _emit_unit(
    mode: str,
    unit: str,
    pending_space: bool,
    cur_no_space: bool,
    caps_word_active: bool,
    v4: VocabV4,
    out: list[int],
    in_caps_span: bool = False,
) -> tuple[bool, bool, bool]:
    """Emette una singola unità (`lower`, `title`, `caps_word`, `raw_lower`) aggiornando lo stato.
    Ritorna `(pending_space, cur_no_space, caps_word_active)`."""
    if in_caps_span and mode in {"title", "caps_word"}:
        # In un caps_span i caratteri sono già stati abbassati a lowercase reversibile
        mode = "lower"

    can_implicit = pending_space or cur_no_space
    low = _to_lower_rev(unit) if mode in {"title", "caps_word"} else unit

    if mode in {"lower", "raw_lower"}:
        if can_implicit:
            ids = _segmenta_dp_inizio(low, v4)
            if ids is not None:
                if mode == "raw_lower" and caps_word_active:
                    out.append(ATTACH_ID)
                out.extend(ids)
                last_id = ids[-1]
                new_cw = False
                return False, last_id in v4.no_space_after_ids, new_cw
        else:
            # Nessuno spazio prima e cur_no_space == False (es. dopo `.`): preferisci continuazione senza ATTACH_ID
            c_ids = _segmenta_dp_continuazione(low, v4)
            p_ids = _segmenta_dp_inizio(low, v4)
            if c_ids is not None and (p_ids is None or len(c_ids) <= 1 + len(p_ids)):
                # Evita che caps_word precedente si propaghi su continuazione minuscola!
                if caps_word_active and v4.is_pure_rev_lower[c_ids[0]]:
                    out.append(ATTACH_ID)
                out.extend(c_ids)
                return False, c_ids[-1] in v4.no_space_after_ids, False
            if p_ids is not None:
                out.append(ATTACH_ID)
                out.extend(p_ids)
                return False, p_ids[-1] in v4.no_space_after_ids, False
        # Fallback atomico a caratteri del Blocco 4 (sempre possibile perché raw_char_ids copre unit)
        pending_space, cur_no_space = _flush_pending_space(out, pending_space, cur_no_space)
        for ch in low:
            tid = v4.raw_char_ids[ch]
            if not cur_no_space and caps_word_active and v4.is_pure_rev_lower[tid]:
                out.append(ATTACH_ID)
                caps_word_active = False
            elif not cur_no_space and tid not in v4.cont_by_start.get(ch, {}):
                out.append(ATTACH_ID)
            out.append(tid)
            cur_no_space = tid in v4.no_space_after_ids
            caps_word_active = False
        return False, cur_no_space, False

    if mode == "title":
        p_ids = _segmenta_dp_inizio(low, v4)
        if p_ids is None:
            # Fallback byte/carattere letterale per casi impossibili
            pending_space, cur_no_space = _flush_pending_space(out, pending_space, cur_no_space)
            for ch in unit:
                tid = v4.raw_char_ids[ch]
                out.append(tid)
                cur_no_space = tid in v4.no_space_after_ids
            return False, cur_no_space, False
        if can_implicit:
            out.append(ID_CAP_FIRST)
            out.extend(p_ids)
        else:
            # CamelCase interno (`Thread` | `Pool`): `ID_CAMEL_CAP` sopprime lo spazio e alza la 1ª lettera
            out.append(ID_CAMEL_CAP)
            out.extend(p_ids)
        return False, p_ids[-1] in v4.no_space_after_ids, False

    # mode == "caps_word": almeno 2 lettere is_rev_upper
    p_ids = _segmenta_dp_inizio(low, v4)
    if p_ids is not None and all(v4.is_pure_rev_lower[tid] for tid in p_ids):
        if not can_implicit:
            out.append(ATTACH_ID)
        out.append(ID_CAPS_WORD)
        out.extend(p_ids)
        # Se ci sono stati più pezzi (`caps_word=2` ancora attivo sul 2°+ pezzo), lo segnaliamo al chiamante;
        # anche con un solo pezzo `caps_word` passa a `2` e resta pronto sul token successivo!
        return False, p_ids[-1] in v4.no_space_after_ids, True
    # Fallback esplicito con caratteri maiuscoli/CAP_FIRST
    pending_space, cur_no_space = _flush_pending_space(out, pending_space, cur_no_space)
    for ch in unit:
        lo = ch.lower()
        p1 = v4.token_to_id.get("\u2581" + lo)
        if p1 is not None and (cur_no_space or p1 in v4.no_space_after_ids):
            out.append(ID_CAP_FIRST)
            out.append(p1)
            cur_no_space = False
        elif p1 is not None:
            out.append(ID_CAMEL_CAP)
            out.append(p1)
            cur_no_space = False
        else:
            tid = v4.raw_char_ids[ch]
            out.append(tid)
            cur_no_space = tid in v4.no_space_after_ids
        caps_word_active = False
    return False, cur_no_space, False


def _encode_slice(
    text: str,
    v4: VocabV4,
    out: list[int],
    cur_no_space: bool,
    pending_space: bool,
    caps_word_active: bool,
    in_caps_span: bool,
) -> tuple[bool, bool, bool]:
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]

        # 1. Spazi e whitespace conosciuti
        if ch == " ":
            j = i + 1
            while j < n and text[j] == " ":
                j += 1
            run_len = j - i
            if run_len == 1 and not pending_space and not cur_no_space and j < n:
                pending_space = True
                i = j
                continue
            pending_space, cur_no_space = _flush_pending_space(out, pending_space, cur_no_space)
            rem = run_len
            for sp_len, sp_id in _SPACES_DESC:
                while rem >= sp_len:
                    out.append(sp_id)
                    rem -= sp_len
            cur_no_space = True
            caps_word_active = False
            i = j
            continue

        matched_ws = False
        if ch in "\n\r\t\xa0":
            for ws_str, ws_id in _WS_MATCH_NON_SPACE:
                if text.startswith(ws_str, i):
                    pending_space, cur_no_space = _flush_pending_space(out, pending_space, cur_no_space)
                    out.append(ws_id)
                    cur_no_space = True
                    caps_word_active = False
                    i += len(ws_str)
                    matched_ws = True
                    break
            if matched_ws:
                continue

        # 2. Controllo sequenza ALL-CAPS (solo se non siamo già dentro un caps_span)
        if not in_caps_span and is_rev_upper(ch):
            # Inizia `caps_span` se il prefisso precedente può assorbire un eventuale spazio o attaccare
            span_end = _trova_caps_span(text, i)
            if span_end > i:
                lowered = _to_lower_rev(text[i:span_end])
                out.append(ID_CAPS_START)
                caps_word_active = False
                cur_no_space, pending_space, caps_word_active = _encode_slice(
                    lowered,
                    v4,
                    out,
                    cur_no_space=cur_no_space,
                    pending_space=pending_space,
                    caps_word_active=False,
                    in_caps_span=True,
                )
                pending_space, cur_no_space = _flush_pending_space(out, pending_space, cur_no_space)
                out.append(ID_CAPS_END)
                caps_word_active = False
                i = span_end
                continue

        # 3. Elisioni (`l'`, `dell'`, `l’`, ..., incluse `L'`, `Dell'`) a inizio parola
        can_implicit = pending_space or cur_no_space
        if v4.max_elision_len and (can_implicit or i == 0 or not _is_word_alpha_char(text[i - 1], v4)):
            # Se il suffisso successivo alla parola apostrofata è tutto reversibile, verifica match elisione
            best_el_len = 0
            best_el_tid = -1
            best_el_mode = ""
            max_try = min(v4.max_elision_len, n - i)
            for el_len in range(max_try, 1, -1):
                sub = text[i : i + el_len]
                if sub[-1] not in ("'", "’"):
                    continue
                head = sub[:-1]
                if not all(is_rev_lower(c) or is_rev_upper(c) for c in head):
                    continue
                tid = v4.elision_ids.get(head.lower() + sub[-1])
                if tid is None:
                    continue
                if all(is_rev_lower(c) for c in head):
                    el_mode = "lower"
                elif is_rev_upper(head[0]) and all(is_rev_lower(c) for c in head[1:]):
                    el_mode = "title"
                elif in_caps_span and all(is_rev_upper(c) for c in head):
                    el_mode = "lower"
                else:
                    continue
                best_el_len = el_len
                best_el_tid = tid
                best_el_mode = el_mode
                break
            if best_el_len:
                if best_el_mode == "lower":
                    if not can_implicit:
                        out.append(ATTACH_ID)
                    out.append(best_el_tid)
                else:
                    out.append(ID_CAP_FIRST if can_implicit else ID_CAMEL_CAP)
                    out.append(best_el_tid)
                pending_space = False
                cur_no_space = True  # tutte le elisioni hanno `no_space_after = True`
                caps_word_active = False
                i += best_el_len
                continue

        # 4. Parole alfabetiche reversibili (incluse `ß`, `ı` gestite da _split_case_units)
        if _is_word_alpha_char(ch, v4):
            j = i + 1
            while j < n and _is_word_alpha_char(text[j], v4):
                j += 1
            atom = text[i:j]
            units = _split_case_units(atom)
            for idx_u, (mode, unit) in enumerate(units):
                pending_space, cur_no_space, caps_word_active = _emit_unit(
                    mode,
                    unit,
                    pending_space=pending_space if idx_u == 0 else False,
                    cur_no_space=cur_no_space,
                    caps_word_active=caps_word_active,
                    v4=v4,
                    out=out,
                    in_caps_span=in_caps_span,
                )
            i = j
            continue

        # 5. Sequenze di cifre ASCII (`0..9`)
        if "0" <= ch <= "9":
            j = i + 1
            while j < n and "0" <= text[j] <= "9":
                j += 1
            digits = text[i:j]
            if can_implicit:
                ids = _segmenta_dp_inizio(digits, v4)
                if ids is not None:
                    out.extend(ids)
                    pending_space = False
                    cur_no_space = ids[-1] in v4.no_space_after_ids
                    caps_word_active = False
                    i = j
                    continue
            else:
                c_ids = _segmenta_dp_continuazione(digits, v4)
                p_ids = _segmenta_dp_inizio(digits, v4)
                if c_ids is not None and (p_ids is None or len(c_ids) <= 1 + len(p_ids)):
                    out.extend(c_ids)
                    cur_no_space = c_ids[-1] in v4.no_space_after_ids
                    caps_word_active = False
                    i = j
                    continue
                if p_ids is not None:
                    out.append(ATTACH_ID)
                    out.extend(p_ids)
                    cur_no_space = p_ids[-1] in v4.no_space_after_ids
                    caps_word_active = False
                    i = j
                    continue
            # Fallback singole cifre Blocco 4
            pending_space, cur_no_space = _flush_pending_space(out, pending_space, cur_no_space)
            for dch in digits:
                tid = v4.raw_char_ids[dch]
                out.append(tid)
                cur_no_space = False
                caps_word_active = False
            i = j
            continue

        # 6. Operatori, contrazioni e punteggiatura multi-carattere (match esatto case-sensitive)
        matched_op = False
        if can_implicit:
            for op_core, op_tid in v4.ops_pref_by_start.get(ch, ()):
                if text.startswith(op_core, i):
                    out.append(op_tid)
                    pending_space = False
                    cur_no_space = op_tid in v4.no_space_after_ids
                    caps_word_active = False
                    i += len(op_core)
                    matched_op = True
                    break
            if matched_op:
                continue
        else:
            for op_tok, op_tid in v4.ops_cont_by_start.get(ch, ()):
                if text.startswith(op_tok, i):
                    # Se `op_tok` inizia con lettera minuscola (es. `n't`, `www.`) e caps_word è attivo,
                    # `op_tok` contiene `'` o `.`? No: `www.` -> `w` è is_pure_rev_lower? NO, `.` rompe `_is_pure_rev_lower_core`!
                    # Ma per sicurezza se `caps_word_active` e `v4.is_pure_rev_lower[op_tid]`, emetti `ATTACH_ID`.
                    if caps_word_active and v4.is_pure_rev_lower[op_tid]:
                        out.append(ATTACH_ID)
                    out.append(op_tid)
                    cur_no_space = op_tid in v4.no_space_after_ids
                    caps_word_active = False
                    i += len(op_tok)
                    matched_op = True
                    break
            if matched_op:
                continue

        # 7. Singolo carattere nel Blocco 4 (prima prova `▁c` se `can_implicit`, poi bare `c`)
        if ch in v4.raw_char_ids:
            if can_implicit:
                # Preferiamo `▁c` se esiste ed è coerente col flusso successivo (non blocca lo spazio che segue a vuoto!)
                pref_tid = v4.token_to_id.get("\u2581" + ch)
                if pref_tid is not None:
                    # Caso fine `▁'` / `▁"` / `▁‘` / `▁“`: se subito dopo c'è uno spazio e cur_no_space è già True,
                    # o per qualsiasi token che imposta `no_space_after` quando seguito da spazio, meglio bare `ch` se pending_space è False!
                    next_is_space = (i + 1 < n and text[i + 1] == " ")
                    if next_is_space and pref_tid in v4.no_space_after_ids and cur_no_space:
                        bare_tid = v4.raw_char_ids[ch]
                        out.append(bare_tid)
                        cur_no_space = bare_tid in v4.no_space_after_ids
                        caps_word_active = False
                        i += 1
                        continue
                    out.append(pref_tid)
                    pending_space = False
                    cur_no_space = pref_tid in v4.no_space_after_ids
                    caps_word_active = False
                    i += 1
                    continue
            pending_space, cur_no_space = _flush_pending_space(out, pending_space, cur_no_space)
            bare_tid = v4.raw_char_ids[ch]
            if not cur_no_space and caps_word_active and v4.is_pure_rev_lower[bare_tid]:
                out.append(ATTACH_ID)
            out.append(bare_tid)
            cur_no_space = bare_tid in v4.no_space_after_ids
            caps_word_active = False
            i += 1
            continue

        # 8. Riserva a byte UTF-8 (ID 64..319): gestisce emoji, ideogrammi, caratteri rari, `▁` letterale, ecc.
        pending_space, cur_no_space = _flush_pending_space(out, pending_space, cur_no_space)
        try:
            raw_bytes = ch.encode("utf-8")
        except UnicodeEncodeError:
            raw_bytes = ch.encode("utf-8", errors="surrogatepass")
        for b in raw_bytes:
            out.append(BYTE_ID_START + b)
        cur_no_space = False
        caps_word_active = False
        i += 1

    return cur_no_space, pending_space, caps_word_active


def encode(testo: str, pv=None) -> list[int]:
    """Codifica senza perdita una stringa `testo` in una lista di ID di `pv` (`VocabV4` o `StageVocab`)."""
    if not isinstance(testo, str):
        raise TokenizerError(f"attesa str in encode, ricevuto {type(testo).__name__}")
    if pv is None:
        raise TokenizerError("vocabolario obbligatorio per encode(testo, pv)")
    v4 = _as_vocab_v4(pv)
    out: list[int] = []
    cur_no_space, pending_space, _ = _encode_slice(
        testo,
        v4,
        out,
        cur_no_space=True,
        pending_space=False,
        caps_word_active=False,
        in_caps_span=False,
    )
    if pending_space:
        out.append(ID_SPACE)
    return out


def decode(ids: Sequence[int], pv=None, *, skip_special_tokens: bool = True) -> str:
    """Decodifica una sequenza di ID nel testo originale esatto."""
    if pv is None:
        raise TokenizerError("vocabolario obbligatorio per decode(ids, pv)")
    v4 = _as_vocab_v4(pv)
    id_to_token = v4.id_to_token
    has_ws_arr = v4.has_ws
    cores_arr = v4.cores
    pure_arr = v4.is_pure_rev_lower
    nsa_ids = v4.no_space_after_ids
    vocab_len = len(id_to_token)

    pieces: list[str] = []
    byte_buf = bytearray()
    no_space = True
    caps_span = False
    caps_word = 0  # 0=off, 1=attesa primo pezzo parola, 2=continua su pure_rev_lower senza `▁`
    cap_first = False

    def flush_bytes() -> None:
        nonlocal no_space
        if not byte_buf:
            return
        try:
            s = bytes(byte_buf).decode("utf-8")
        except UnicodeDecodeError:
            s = bytes(byte_buf).decode("utf-8", errors="surrogatepass")
        byte_buf.clear()
        if caps_span:
            s = _to_upper_rev(s)
        pieces.append(s)
        no_space = False

    for raw_id in ids:
        tid = int(raw_id)
        if not 0 <= tid < vocab_len:
            raise TokenizerError(f"id fuori vocabolario: {tid} (max {vocab_len - 1})")

        if 64 <= tid <= 319:
            caps_word = 0
            cap_first = False
            byte_buf.append(tid - 64)
            continue

        if byte_buf:
            flush_bytes()

        if tid < 32:
            if not skip_special_tokens:
                pieces.append(id_to_token[tid])
            continue

        if tid == ID_CAPS_WORD:
            caps_word = 1
            continue
        if tid == ID_CAP_FIRST:
            caps_word = 0
            cap_first = True
            continue
        if tid == ID_CAMEL_CAP:
            caps_word = 0
            no_space = True
            cap_first = True
            continue
        if tid == ID_CAPS_START:
            caps_word = 0
            cap_first = False
            caps_span = True
            continue
        if tid == ID_CAPS_END:
            caps_word = 0
            cap_first = False
            caps_span = False
            continue
        if tid == ATTACH_ID:
            caps_word = 0
            no_space = True
            continue

        ws_str = _ID_TO_WS.get(tid)
        if ws_str is not None:
            caps_word = 0
            cap_first = False
            pieces.append(ws_str)
            no_space = True
            continue

        if tid < 64:
            # Controlli riservati futuri (59..63)
            if not skip_special_tokens:
                pieces.append(id_to_token[tid])
            continue

        has_ws = has_ws_arr[tid]
        core = cores_arr[tid]
        is_pure = pure_arr[tid]

        if caps_word == 1:
            if is_pure:
                use_caps_word = True
                caps_word = 2
            else:
                use_caps_word = False
                caps_word = 0
        elif caps_word == 2:
            if (not has_ws) and is_pure:
                use_caps_word = True
            else:
                use_caps_word = False
                caps_word = 0
        else:
            use_caps_word = False

        if has_ws and not no_space:
            pieces.append(" ")

        if caps_span or use_caps_word:
            out_core = _to_upper_rev(core)
            cap_first = False
        elif cap_first:
            out_core = (core[0].upper() + core[1:]) if (core and is_rev_lower(core[0])) else core
            cap_first = False
        else:
            out_core = core

        pieces.append(out_core)
        no_space = tid in nsa_ids

    if byte_buf:
        flush_bytes()
    return "".join(pieces)


def assert_roundtrip(testo: str, pv) -> list[int]:
    """Verifica round-trip identico e ritorna gli ID."""
    ids = encode(testo, pv)
    back = decode(ids, pv)
    if back != testo:
        raise TokenizerError(f"round-trip divergente su: {testo[:80]!r}")
    return ids
