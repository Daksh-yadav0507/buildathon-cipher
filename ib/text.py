"""Words (section 7.1): fold every spelling to one, tokens, highlighting, Indian amounts and dates, India time.

fold("paisa") == fold("pese") == fold("paise") == fold("पैसे") == "pes"
fold("bhai") == fold("bhaii") == fold("भाई") == "be";  fold("kal") == fold("कल") == "kal"
"""
from __future__ import annotations

import calendar
import html
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")
DAY_MS = 86_400_000

# ============================================================== Devanagari to Roman

try:  # optional: better transliteration when installed
    from indic_transliteration import sanscript as _sanscript  # type: ignore
    from indic_transliteration.sanscript import transliterate as _translit  # type: ignore
except Exception:  # not installed: the table and the letter rules below do the job
    _sanscript = None
    _translit = None

# about 70 common Hindi words, written the way people type them in Roman letters
HINDI_WORDS = {
    "पैसे": "paise", "पैसा": "paisa", "कल": "kal", "आज": "aaj", "परसों": "parson", "भाई": "bhai",
    "भैया": "bhaiya", "माल": "maal", "बिस्कुट": "biscuit", "पुलिस": "police", "रेड": "raid",
    "छापा": "chhapa", "ठीक": "theek", "हाँ": "haan", "हां": "haan", "नहीं": "nahi", "नही": "nahi",
    "क्या": "kya", "है": "hai", "हैं": "hain", "था": "tha", "थी": "thi", "थे": "the", "और": "aur",
    "मैं": "main", "मुझे": "mujhe", "तुम": "tum", "आप": "aap", "हम": "hum", "यह": "yeh", "वह": "woh",
    "कहाँ": "kahan", "कहां": "kahan", "कब": "kab", "कौन": "kaun", "किसने": "kisne", "किसको": "kisko",
    "भेजा": "bheja", "भेज": "bhej", "भेजो": "bhejo", "दिया": "diya", "लिया": "liya", "मिल": "mil",
    "मिला": "mila", "गए": "gaye", "गये": "gaye", "गया": "gaya", "अभी": "abhi", "जल्दी": "jaldi",
    "सोना": "sona", "चाय": "chai", "पानी": "pani", "डॉक्टर": "doctor", "डाक्टर": "doctor",
    "साहब": "sahab", "पैकेट": "packet", "टोकन": "token", "लाख": "lakh", "हज़ार": "hazaar",
    "हजार": "hazaar", "करोड़": "crore", "रुपये": "rupaye", "रुपए": "rupaye", "फोन": "phone",
    "फ़ोन": "phone", "मत": "mat", "करना": "karna", "कर": "kar", "करो": "karo", "दो": "do", "बात": "baat",
    "घर": "ghar", "खाना": "khana", "सुबह": "subah", "रात": "raat", "शाम": "shaam", "नमस्ते": "namaste",
    "धन्यवाद": "dhanyavaad", "शुक्रिया": "shukriya", "अच्छा": "accha", "बहुत": "bahut", "पक्का": "pakka",
    "चलो": "chalo", "देखो": "dekho", "एयरपोर्ट": "airport", "कार्गो": "cargo", "फ्लाइट": "flight",
    "डिलीट": "delete", "खबर": "khabar", "ख़बर": "khabar", "दुबई": "dubai", "गोल्ड": "gold", "कैश": "cash",
    "हवाला": "hawala", "पैकेट्स": "packets", "माँ": "maa", "मां": "maa", "बेटा": "beta", "जी": "ji",
}

_VIRAMA, _NUKTA = "्", "़"
_CONS = dict(zip(
    "कखगघङचछजझञटठडढणतथदधनपफबभमयरलळवशषसह",
    ["k", "kh", "g", "gh", "n", "ch", "chh", "j", "jh", "n", "t", "th", "d", "dh", "n", "t", "th", "d", "dh",
     "n", "p", "ph", "b", "bh", "m", "y", "r", "l", "l", "v", "sh", "sh", "s", "h"]))
_NUKTA_CONS = {"क": "k", "ख": "kh", "ग": "g", "ज": "z", "ड": "r", "ढ": "rh", "फ": "f", "य": "y"}
_VOWELS = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ii", "उ": "u", "ऊ": "uu", "ऋ": "ri", "ए": "e", "ऐ": "ai",
           "ओ": "o", "औ": "au", "ऑ": "o", "ऍ": "e"}
_MATRAS = {"ा": "aa", "ि": "i", "ी": "ii", "ु": "u", "ू": "uu", "ृ": "ri",
           "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o", "ॅ": "e"}
_DEV_DIGITS = {chr(0x0966 + i): str(i) for i in range(10)}
_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")


def _deva_key(word: str) -> str:
    w = unicodedata.normalize("NFC", word).replace("ँ", "ं")  # chandrabindu -> anusvara
    return w


_HINDI_KEYS = {_deva_key(k): v for k, v in HINDI_WORDS.items()}
_HINDI_KEYS.update({_deva_key(k).replace(_NUKTA, ""): v for k, v in HINDI_WORDS.items()})


def _deva_letters(word: str) -> str:
    """Letter-by-letter Devanagari to Roman, with the usual Hindi dropping of the silent 'a'."""
    chars = list(unicodedata.normalize("NFD", word))
    units: list[list] = []  # [consonant_part, vowel_part, inherent?]
    i, n = 0, len(chars)
    while i < n:
        c = chars[i]
        if c in _CONS:
            base = _CONS[c]
            if i + 1 < n and chars[i + 1] == _NUKTA:
                base = _NUKTA_CONS.get(c, base)
                i += 1
            nxt = chars[i + 1] if i + 1 < n else ""
            if nxt == _VIRAMA:
                units.append([base, "", False])
                i += 2
                continue
            if nxt in _MATRAS:
                units.append([base, _MATRAS[nxt], False])
                i += 2
                continue
            units.append([base, "a", True])
            i += 1
            continue
        if c in _VOWELS:
            units.append(["", _VOWELS[c], False])
        elif c in ("ं", "ँ"):
            units.append(["n", "", False])
        elif c == "ः":
            units.append(["h", "", False])
        elif c in _DEV_DIGITS:
            units.append([_DEV_DIGITS[c], "", False])
        elif c == _NUKTA:
            pass
        else:
            units.append([c, "", False])
        i += 1
    # silent 'a': at the end of a word of more than one unit, and between two sounded syllables
    if len(units) > 1 and units[-1][2]:
        units[-1][1] = ""
        units[-1][2] = False
    k = 1
    while k < len(units) - 1:
        cur, nxt = units[k], units[k + 1]
        if cur[2] and nxt[0] and nxt[1] and units[k - 1][1]:
            cur[1] = ""
            cur[2] = False
            k += 2
            continue
        k += 1
    return "".join(u[0] + u[1] for u in units)


def deva_to_roman(word: str) -> str:
    """One Devanagari word in Roman letters ('पैसे' -> 'paise'). Other words come back unchanged."""
    if not _DEVANAGARI_RE.search(word):
        return word
    key = _deva_key(word)
    if key in _HINDI_KEYS:
        return _HINDI_KEYS[key]
    stripped = key.replace(_NUKTA, "")
    if stripped in _HINDI_KEYS:
        return _HINDI_KEYS[stripped]
    if _translit is not None:
        try:
            out = _translit(word, _sanscript.DEVANAGARI, _sanscript.ITRANS)
            out = re.sub(r"[^A-Za-z0-9]", "", out).lower()
            if out:
                return out
        except Exception:
            pass
    return _deva_letters(word)


# ============================================================== folding

_REPLACEMENTS = [("ph", "f"), ("w", "v"), ("z", "j"), ("q", "k"), ("ck", "k"), ("kh", "k"), ("gh", "g"),
                 ("sh", "s"), ("th", "t"), ("dh", "d"), ("bh", "b"), ("ee", "i"), ("ii", "i"), ("oo", "u"),
                 ("uu", "u"), ("aa", "a"), ("ai", "e"), ("ay", "e"), ("ei", "e"), ("ey", "e")]
_REPEAT_RE = re.compile(r"([a-z])\1+")
_NUMBER_RE = re.compile(r"^\d+(?:,\d+)*(?:\.\d+)?$")

# a token: a number (with Indian or Western commas and decimals) or a word (letters, then letters/digits)
_DEV_MARKS = "ऀ-ःऺ-ॏ॑-ॗॢॣ"
_TOKEN_RE = re.compile(
    r"\d+(?:,\d+)*(?:\.\d+)?"
    rf"|(?:[^\W\d_]|[{_DEV_MARKS}])(?:[^\W_]|[{_DEV_MARKS}̀-ͯ])*"
)


def fold(word: str) -> str:
    """One spelling for every way a word is written (section 7.1). Numbers lose commas and '.00'."""
    if not word:
        return ""
    w = word.strip()
    if _NUMBER_RE.match(w):
        w = w.replace(",", "")
        if "." in w:
            whole, frac = w.split(".", 1)
            w = whole if set(frac) <= {"0"} else whole + "." + frac
        return w
    if _DEVANAGARI_RE.search(w):
        w = deva_to_roman(w)
    w = w.lower()
    w = unicodedata.normalize("NFKD", w)
    w = "".join(ch for ch in w if not unicodedata.combining(ch) and ch.isalnum())
    if not w:
        return ""
    if w.isdigit():
        return w
    for a, b in _REPLACEMENTS:
        if a in w:
            w = w.replace(a, b)
    w = _REPEAT_RE.sub(r"\1", w)
    if len(w) > 3 and w[-1] in "aei":
        w = w[:-1]
    return w


def tokens(text: str | None) -> list[str]:
    """The words and numbers of a text, as written."""
    if not text:
        return []
    return _TOKEN_RE.findall(text)


def fold_tokens(text: str | None) -> list[str]:
    """Folded words of a text, in order (repeats kept)."""
    out = []
    for t in tokens(text):
        f = fold(t)
        if f:
            out.append(f)
    return out


def fold_text(text: str | None) -> str:
    """Folded words joined by spaces: what goes into events.folded and the search index."""
    return " ".join(fold_tokens(text))


def fts_query(words, op: str = "AND", prefix: bool = False, column: str | None = None) -> str:
    """A safe FTS5 MATCH string from words (folded here): fts_query(["paisa","bheja"]) -> '"pes" AND "beja"'.

    Every word is quoted, so nothing the officer types can break the query. column="folded" limits it.
    """
    parts = []
    seen = set()
    for w in words if not isinstance(words, str) else [words]:
        for f in fold_tokens(w):
            if f in seen:
                continue
            seen.add(f)
            term = '"' + f.replace('"', '""') + '"' + ("*" if prefix else "")
            parts.append(f"{column}:{term}" if column else term)
    return f" {op} ".join(parts)


# ============================================================== stop words (English and Hinglish)

_STOP_RAW = """kya kisne kisko ko ne hai tha the who what did whom whose which when where why how is was were are
am be been do does done has have had a an and or of in on at to for from by with about any some this that these
those it its me my mine i we our you your he she him her his they them their there here ka ki ke se mein me main
aur ya bhi to toh hi kaun kab kahan kaise kitna kitne kitni kis koi kuch ye yeh vo woh wo hain thi tell show give
please all every can could would should will shall""".split()
STOP_WORDS = frozenset(fold(w) for w in _STOP_RAW)


def content_words(text: str | None) -> list[str]:
    """Folded words that carry meaning (stop words dropped), each once, in order."""
    out, seen = [], set()
    for f in fold_tokens(text):
        if f in STOP_WORDS or f in seen:
            continue
        seen.add(f)
        out.append(f)
    return out


# ============================================================== highlighting and snippets

esc = html.escape


def _as_fold_set(words) -> set[str]:
    if isinstance(words, str):
        words = [words]
    out = set()
    for w in words or []:
        out.update(fold_tokens(w))
    return out


def _match(tok: str, wanted: set[str], exact: bool, prefix: bool) -> bool:
    if exact:
        return tok.lower() in wanted
    f = fold(tok)
    if not f:
        return False
    if f in wanted:
        return True
    return prefix and any(f.startswith(w) for w in wanted if len(w) >= 2)


def highlight(text: str | None, words, exact: bool = False, prefix: bool = False) -> str:
    """HTML-escaped text with <mark> around every word that folds to one of `words`.

    exact=True marks only the same letters (any case); prefix=True also marks words that start with one.
    """
    if not text:
        return ""
    wanted = {w.lower() for w in tokens(" ".join([words] if isinstance(words, str) else words or []))} \
        if exact else _as_fold_set(words)
    out, last = [], 0
    for m in _TOKEN_RE.finditer(text):
        s, e = m.span()
        out.append(esc(text[last:s]))
        tok = m.group(0)
        out.append(f"<mark>{esc(tok)}</mark>" if wanted and _match(tok, wanted, exact, prefix) else esc(tok))
        last = e
    out.append(esc(text[last:]))
    return "".join(out)


def snippet(text: str | None, words, width: int = 140, exact: bool = False, prefix: bool = False) -> str:
    """About `width` characters around the first matching word, escaped and marked, with … at cut ends."""
    if not text:
        return ""
    text = " ".join(text.split())
    wanted = {w.lower() for w in tokens(" ".join([words] if isinstance(words, str) else words or []))} \
        if exact else _as_fold_set(words)
    first = None
    if wanted:
        for m in _TOKEN_RE.finditer(text):
            if _match(m.group(0), wanted, exact, prefix):
                first = m.start()
                break
    if len(text) <= width:
        return highlight(text, words, exact, prefix)
    start = 0 if first is None else max(0, first - width // 3)
    end = min(len(text), start + width)
    start = max(0, end - width)
    if start > 0:
        sp = text.find(" ", start)
        if 0 <= sp < (first if first is not None else start + 20):
            start = sp + 1
    if end < len(text):
        sp = text.rfind(" ", start, end)
        if sp > (first or start) + 10:
            end = sp
    body = highlight(text[start:end], words, exact, prefix)
    return ("…" if start > 0 else "") + body + ("…" if end < len(text) else "")


def spellings(text: str | None, words) -> list[str]:
    """The distinct spellings (lower case, as written) in text that fold to one of `words`."""
    wanted = _as_fold_set(words)
    out = []
    for t in tokens(text):
        lt = t.lower()
        if lt not in out and fold(t) in wanted:
            out.append(lt)
    return out


# ============================================================== phone numbers

_SENDER_ID_RE = re.compile(r"^[A-Z]{2}-[A-Z0-9]{3,10}$")


def digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def norm_phone(s: str | None, country: str = "91") -> str | None:
    """'+91 98995 12640', '09899512640', '9899512640' -> '+919899512640'. Keeps other country codes.

    Returns None for things that aren't phone numbers (sender IDs like 'AD-BUBANK', short codes).
    """
    if not s:
        return None
    raw = s.strip()
    if raw.lower().startswith("wa:"):
        raw = raw[3:]
    d = digits(raw)
    if len(d) < 6 or re.search(r"[A-Za-z]", raw):
        return None
    if raw.startswith("+"):
        return "+" + d
    if d.startswith("00"):
        return "+" + d[2:]
    if len(d) == 10 and d[0] in "6789":
        return "+" + country + d
    if len(d) == 11 and d.startswith("0"):
        return "+" + country + d[1:]
    if len(d) == 12 and d.startswith(country):
        return "+" + d
    return "+" + d if len(d) > 10 else d


def is_sender_id(s: str | None) -> bool:
    """Bank and shop senders such as 'AD-BUBANK' or 'VM-SPHBNK'."""
    return bool(s) and bool(_SENDER_ID_RE.match(s.strip().upper()))


# ============================================================== Indian amounts

NUMBER_WORDS = {
    "ek": 1, "do": 2, "teen": 3, "tin": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "che": 6,
    "saat": 7, "sat": 7, "aath": 8, "aat": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12, "pandrah": 15,
    "bees": 20, "bis": 20, "pachees": 25, "pachchis": 25, "pachis": 25, "tees": 30, "tis": 30, "chalees": 40,
    "chalis": 40, "pachaas": 50, "pachas": 50, "pachchas": 50, "saath": 60, "sattar": 70, "assi": 80,
    "nabbe": 90, "sau": 100, "dedh": 1.5, "dhai": 2.5, "aadha": 0.5,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10, "twenty": 20, "fifty": 50, "hundred": 100,
}
# words that mean an amount even alone ("pachaas mil gaye" = got the fifty)
STANDALONE_NUMBER_WORDS = frozenset({"pachaas", "pachas", "pachchas", "pachees", "pachchis", "pachis", "bees",
                                     "tees", "chalees", "chalis"})
MULTIPLIERS = {"k": 1e3, "hazaar": 1e3, "hazar": 1e3, "hajar": 1e3, "hajaar": 1e3,
               "thousand": 1e3, "sau": 1e2, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "lakh.": 1e5,
               "crore": 1e7, "crores": 1e7, "cr": 1e7, "karod": 1e7, "karor": 1e7}
MONEY_WORDS = frozenset({"rs", "inr", "rupees", "rupee", "rupaye", "rupaiye", "paisa", "paise", "pese", "pesa",
                         "amount", "payment", "paid", "pay", "transfer", "upi", "imps", "neft", "cash", "hawala",
                         "diya", "de", "dena", "bheja", "bhej", "mil", "mila", "credited", "debited", "lakh",
                         "hazaar", "crore", "token", "advance", "balance", "kharcha", "chai", "pani"})

_MULT_RE = r"(?:k|hazaa?r|hajaa?r|thousand|lakhs?|lacs?|crores?|cr|karo[dr])"
_AMOUNT_RE = re.compile(
    r"(?P<cur>₹|\brs\.?|\binr)?\s*(?P<num>\d+(?:,\d+)*(?:\.\d+)?)(?:\s*(?P<mult>" + _MULT_RE + r")\b)?"
    r"(?:\s*(?P<suf>rupees?|rupaye|rupaiye|rs)\b)?",
    re.IGNORECASE)
_WORD_AMOUNT_RE = re.compile(
    r"\b(?P<w>" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")(?:\s+(?P<mult>" + _MULT_RE + r"))?\b",
    re.IGNORECASE)


def _mult(word: str | None) -> float:
    if not word:
        return 1.0
    w = word.lower().rstrip(".")
    if w in MULTIPLIERS:
        return MULTIPLIERS[w]
    if w.startswith(("haza", "haja")):
        return 1e3
    if w.startswith(("lakh", "lac")):
        return 1e5
    if w.startswith(("crore", "karo")) or w == "cr":
        return 1e7
    return 1.0


def find_amounts(text: str | None) -> list[dict]:
    """Every amount in a text: [{value, text, start, end, explicit}].

    explicit=True when it has ₹/Rs/INR/rupees or lakh/hazaar/crore/k ("Rs 50,000.00", "1.2 lakh", "50k",
    "pachaas hazaar"); bare numbers and "pachaas" alone are explicit=False (the caller decides from context).
    Years, times and phone-like numbers are skipped.
    """
    if not text:
        return []
    found: list[dict] = []
    taken: list[tuple[int, int]] = []
    for m in _AMOUNT_RE.finditer(text):
        num = m.group("num")
        try:
            base = float(num.replace(",", ""))
        except ValueError:
            continue
        cur, mult, suf = m.group("cur"), m.group("mult"), m.group("suf")
        explicit = bool(cur or mult or suf)
        plain = num.replace(",", "").split(".")[0]
        if not explicit:
            nxt = text[m.end():m.end() + 1]
            prv = text[max(0, m.start() - 1):m.start()]
            if len(plain) >= 9 or nxt in (":", "/", "-") or prv in (":", "/", "-", "+") or "," in num and len(plain) < 4:
                continue  # refs, phone numbers, times, dates
            if len(plain) == 4 and 1900 <= base <= 2100:
                continue  # a year
        value = base * _mult(mult)
        s = m.start("cur") if cur else m.start("num")
        found.append({"value": value, "text": text[s:m.end()].strip(), "start": s, "end": m.end(),
                      "explicit": explicit})
        taken.append((s, m.end()))
    for m in _WORD_AMOUNT_RE.finditer(text):
        if any(a <= m.start() < b for a, b in taken):
            continue
        w = m.group("w").lower()
        mult = m.group("mult")
        if not mult and w not in STANDALONE_NUMBER_WORDS:
            continue
        found.append({"value": NUMBER_WORDS[w] * _mult(mult), "text": m.group(0), "start": m.start(),
                      "end": m.end(), "explicit": bool(mult)})
    found.sort(key=lambda a: a["start"])
    return found


def parse_amount(text: str | None) -> float | None:
    """The first amount in a short phrase: '50,000' -> 50000, '1.2 lakh' -> 120000, 'pachaas' -> 50."""
    found = find_amounts(text)
    if not found:
        return None
    best = next((a for a in found if a["explicit"]), found[0])
    return best["value"]


def group_indian(n) -> str:
    """1284 -> '1,284'; 120000 -> '1,20,000'; 1800000 -> '18,00,000'."""
    neg = n < 0
    s = str(abs(int(round(n))))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if neg else "") + s


def format_inr(amount) -> str:
    """'₹50,000', '₹1,20,000', '₹50,000.50'."""
    if amount is None:
        return ""
    a = float(amount)
    whole = group_indian(int(a)) if a >= 0 else "-" + group_indian(int(-a))
    frac = round(abs(a) - int(abs(a)), 2)
    return "₹" + whole + (f"{frac:.2f}"[1:] if frac else "")


def inr_short(amount) -> str:
    """For headlines: '₹6.2 lakh', '₹1.5 crore'; under a lakh, the full amount ('₹50,000')."""
    if amount is None:
        return ""
    a = float(amount)
    if abs(a) >= 1e7:
        v, unit = a / 1e7, "crore"
    elif abs(a) >= 1e5:
        v, unit = a / 1e5, "lakh"
    else:
        return format_inr(round(a))
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return f"₹{s} {unit}"


def plural(n, one: str, many: str | None = None) -> str:
    """plural(1, 'call') -> '1 call'; plural(1284, 'call') -> '1,284 calls'."""
    word = one if n == 1 else (many or one + "s")
    return f"{group_indian(n)} {word}"


# ============================================================== India time

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_MONTH_WORDS = {
    **{m: i + 1 for i, m in enumerate(MONTHS)},
    **{calendar.month_name[i].lower(): i for i in range(1, 13)},
    "sept": 9, "janvari": 1, "january": 1, "farvari": 2, "pharvari": 2, "march": 3, "maarch": 3, "aprail": 4,
    "mai": 5, "june": 6, "joon": 6, "july": 7, "julai": 7, "agast": 8, "agust": 8, "sitambar": 9,
    "sitamber": 9, "aktubar": 10, "aktoobar": 10, "navambar": 11, "navamber": 11, "disambar": 12,
}


def now_ms() -> int:
    return int(time.time() * 1000)


def ist(ms: int) -> datetime:
    """A UTC-milliseconds time as an India-time datetime."""
    return datetime.fromtimestamp(ms / 1000, IST)


def to_ms(dt: datetime) -> int:
    """A datetime (naive means India time) to UTC milliseconds."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return int(dt.timestamp() * 1000)


def parse_ts(value) -> int | None:
    """'2026-09-16T10:07:12+05:30', '2026-09-16 10:07', '2026-09-16', epoch seconds or ms -> UTC ms.

    A time without an offset is read as India time.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return int(v if v > 1e11 else v * 1000)
    s = str(value).strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", s):
        return parse_ts(float(s))
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return to_ms(dt)


def _ampm(dt: datetime) -> str:
    h = dt.hour % 12 or 12
    return f"{h}:{dt.minute:02d} {'am' if dt.hour < 12 else 'pm'}"


def fmt_time(ms: int | None) -> str:
    """'10:05 am' (India time)."""
    return _ampm(ist(ms)) if ms is not None else ""


def fmt_date(ms: int | None) -> str:
    """'16 Sep 2026' (India time)."""
    if ms is None:
        return ""
    d = ist(ms)
    return f"{d.day} {d.strftime('%b')} {d.year}"


def fmt_when(ms: int | None) -> str:
    """'16 Sep 2026, 10:05 am' (India time)."""
    return f"{fmt_date(ms)}, {fmt_time(ms)}" if ms is not None else ""


def ist_day(ms: int) -> str:
    """'2026-09-16': the India-time day of a time."""
    return ist(ms).strftime("%Y-%m-%d")


def ist_iso(ms: int) -> str:
    """'2026-09-16T10:05:00+05:30'."""
    return ist(ms).isoformat(timespec="seconds")


def day_range(day: str) -> tuple[int, int]:
    """'2026-09-16' -> (start, end) in UTC ms for that India-time day; end is exclusive."""
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=IST)
    return to_ms(d), to_ms(d + timedelta(days=1))


def duration_words(seconds) -> str:
    """252 -> '4 min 12 s'; 45 -> '45 s'; 3720 -> '1 h 2 min'."""
    s = int(seconds or 0)
    if s < 60:
        return f"{s} s"
    if s < 3600:
        m, r = divmod(s, 60)
        return f"{m} min {r} s" if r else f"{m} min"
    h, r = divmod(s, 3600)
    return f"{h} h {r // 60} min" if r // 60 else f"{h} h"


def gap_words(ms) -> str:
    """A time gap in words: 120000 -> '2 minutes'; 5400000 -> '1 hour 30 minutes'; 40000 -> '40 seconds'."""
    s = abs(int(ms or 0)) // 1000
    if s < 60:
        return plural(s, "second")
    m = s // 60
    if m < 60:
        return plural(m, "minute")
    h, m = divmod(m, 60)
    if h < 48:
        return plural(h, "hour") + (" " + plural(m, "minute") if m else "")
    return plural(h // 24, "day")


# ============================================================== date words in questions

_MON = r"(?P<mon{n}>" + "|".join(sorted(_MONTH_WORDS, key=len, reverse=True)) + r")"
_D = r"(?P<d{n}>[0-3]?\d)(?:st|nd|rd|th)?"
_Y = r"(?:[ ,]+(?P<y{n}>20\d\d))?"
_RANGE_RE = re.compile(
    r"\b(?:between\s+)?" + _D.format(n=1) + r"(?:\s+" + _MON.format(n=1) + r")?\s*(?:-|–|to|se|and|aur|till|tak)\s*"
    + _D.format(n=2) + r"\s+" + _MON.format(n=2) + _Y.format(n=2) + r"\b", re.IGNORECASE)
_DAY_MON_RE = re.compile(r"\b" + _D.format(n=1) + r"\s+" + _MON.format(n=1) + _Y.format(n=1) + r"\b", re.IGNORECASE)
_MON_DAY_RE = re.compile(r"\b" + _MON.format(n=1) + r"\s+" + _D.format(n=1) + r"\b" + _Y.format(n=1), re.IGNORECASE)
_NUMERIC_RE = re.compile(r"\b(?P<d>[0-3]?\d)[/.-](?P<m>[01]?\d)(?:[/.-](?P<y>(?:20)?\d\d))?\b")
_ISO_RE = re.compile(r"\b(?P<y>20\d\d)-(?P<m>[01]\d)-(?P<d>[0-3]\d)\b")
_MONTH_ONLY_RE = re.compile(r"\b" + _MON.format(n=1) + _Y.format(n=1) + r"\b", re.IGNORECASE)
_NIGHT_RE = re.compile(r"\b(night|raat|rat|late)\b", re.IGNORECASE)


def _mon(word: str) -> int:
    return _MONTH_WORDS[word.lower()]


def _year(y: str | None, ref: datetime) -> int:
    if not y:
        return ref.year
    y = int(y)
    return y + 2000 if y < 100 else y


def _range_out(start: datetime, end: datetime, words: str) -> dict:
    return {"from": to_ms(start), "to": to_ms(end), "words": words}


def find_date_range(text: str | None, ref_ms: int | None = None) -> dict | None:
    """Dates in a question -> {"from": ms, "to": ms (exclusive), "words": "16 Sep 2026"} or None.

    Understands '16 Sep', 'Sep 16 2026', '16/09/26', '2026-09-16', '14-17 Sep', 'September', 'sitambar',
    'on the night of 15 Sep' / '15 Sep ki raat' (6 pm to 6 am), 'aaj'/'today', 'kal'/'yesterday',
    'parso', 'last week'/'pichle hafte', 'last month'/'pichle mahine', 'last 10 days'.
    ref_ms is "now" for relative words: pass the case's last record time.
    """
    if not text:
        return None
    ref = ist(ref_ms if ref_ms is not None else now_ms())
    t = text.lower()
    night = bool(_NIGHT_RE.search(t))

    def day_out(y: int, m: int, d: int) -> dict | None:
        try:
            start = datetime(y, m, d, tzinfo=IST)
        except ValueError:
            return None
        if night:
            return _range_out(start + timedelta(hours=18), start + timedelta(hours=30), f"night of {d} {MONTHS[m - 1].title()} {y}")
        return _range_out(start, start + timedelta(days=1), f"{d} {MONTHS[m - 1].title()} {y}")

    m = _RANGE_RE.search(t)
    if m:
        mon2 = _mon(m.group("mon2"))
        mon1 = _mon(m.group("mon1")) if m.group("mon1") else mon2
        y = _year(m.group("y2"), ref)
        try:
            a = datetime(y, mon1, int(m.group("d1")), tzinfo=IST)
            b = datetime(y, mon2, int(m.group("d2")), tzinfo=IST) + timedelta(days=1)
            if b > a:
                return _range_out(a, b, f"{a.day} {MONTHS[mon1 - 1].title()} to {int(m.group('d2'))} "
                                        f"{MONTHS[mon2 - 1].title()} {y}")
        except ValueError:
            pass
    m = _ISO_RE.search(t)
    if m:
        out = day_out(int(m.group("y")), int(m.group("m")), int(m.group("d")))
        if out:
            return out
    for rx in (_DAY_MON_RE, _MON_DAY_RE):
        m = rx.search(t)
        if m:
            out = day_out(_year(m.group("y1"), ref), _mon(m.group("mon1")), int(m.group("d1")))
            if out:
                return out
    m = _NUMERIC_RE.search(t)
    if m and 1 <= int(m.group("m")) <= 12:
        out = day_out(_year(m.group("y"), ref), int(m.group("m")), int(m.group("d")))
        if out:
            return out
    m = _MONTH_ONLY_RE.search(t)
    if m and not (m.group("mon1") in ("may", "mai", "mar", "march") and not m.group("y1")):
        mon = _mon(m.group("mon1"))
        y = _year(m.group("y1"), ref)
        a = datetime(y, mon, 1, tzinfo=IST)
        b = datetime(y + (mon == 12), mon % 12 + 1, 1, tzinfo=IST)
        return _range_out(a, b, f"{calendar.month_name[mon]} {y}")
    day0 = ref.replace(hour=0, minute=0, second=0, microsecond=0)
    m = re.search(r"\b(?:last|pichle|pichhle|past)\s+(\d{1,3})\s+(?:days|din)\b", t)
    if m:
        return _range_out(day0 - timedelta(days=int(m.group(1)) - 1), day0 + timedelta(days=1),
                          f"the last {int(m.group(1))} days")
    if re.search(r"\b(last|pichle|pichhle|past)\s+(week|hafte|hafta)\b", t):
        return _range_out(day0 - timedelta(days=6), day0 + timedelta(days=1), "the last 7 days")
    if re.search(r"\b(last|pichle|pichhle)\s+(month|mahine|mahina)\b", t):
        first = day0.replace(day=1)
        prev = (first - timedelta(days=1)).replace(day=1)
        return _range_out(prev, first, f"{calendar.month_name[prev.month]} {prev.year}")
    if re.search(r"\b(parso|parson)\b", t):
        d = day0 - timedelta(days=2)
        return day_out(d.year, d.month, d.day)
    if re.search(r"\b(kal|yesterday)\b", t) or "कल" in t:
        d = day0 - timedelta(days=1)
        return day_out(d.year, d.month, d.day)
    if re.search(r"\b(aaj|today|tonight)\b", t):
        return day_out(day0.year, day0.month, day0.day)
    return None
