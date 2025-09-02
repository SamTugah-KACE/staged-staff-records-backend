from datetime import datetime
import json
import re
from typing import Optional, Set, Iterable

import pandas as pd
import math

from fastapi import Request, HTTPException
from typing import Any, Dict, List, TypeVar, Union

T = TypeVar("T")


def extract_attachments(data: dict) -> list[dict]:
    """
    Only consider items whose key contains 'path' as attachments.
    Values may be:
      - dict of {filename: url}
      - JSON‐encoded dict strings
    """
    attachments = []
    for key, val in data.items():
        if "path" not in key.lower():
            continue

        # Case 1: native dict
        if isinstance(val, dict):
            for fn, url in val.items():
                attachments.append({"filename": fn, "url": url})
            continue

        # Case 2: JSON‐encoded dict string
        if isinstance(val, str) and val.strip().startswith("{") and val.strip().endswith("}"):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    for fn, url in parsed.items():
                        attachments.append({"filename": fn, "url": url})
                    continue
            except json.JSONDecodeError:
                pass

    return attachments




def extract_items(param: Union[Dict[Any, T], List[T], T]) -> T:
    """
    Normalize an incoming parameter into a single value.

    - If param is a dict, return its first value.
    - If param is a list, return its first element.
    - If param is a string (or any other scalar), return it as-is.

    Raises:
        HTTPException: if the dict or list is empty.
    """
    # Strings are iterable, so check them before lists
    if isinstance(param, str):
        return param  # return the string unchanged

    if isinstance(param, dict):
        try:
            return next(iter(param.values()))
        except StopIteration:
            raise HTTPException(status_code=400, detail="Dict parameter is empty")

    if isinstance(param, list):
        try:
            return param[0]
        except IndexError:
            raise HTTPException(status_code=400, detail="List parameter is empty")

    # For any other type (int, float, custom object, etc.), return as-is
    return param


def get_create_user_url(request: Request) -> str:
    """
    Returns the backend host URL with `/api/users/create` appended.
    Example: if the base URL is http://example.com/, returns http://example.com/api/users/create.
    """
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/api/users/create"

def sanitize_row_data(row_data: dict) -> dict:
    """
    Recursively replace any NaN values in the dictionary with None.
    """
    sanitized = {}
    for key, value in row_data.items():
        if isinstance(value, dict):
            sanitized[key] = sanitize_row_data(value)
        elif isinstance(value, list):
            sanitized[key] = [sanitize_row_data(item) if isinstance(item, dict) else (None if pd.isna(item) else item) for item in value]
        else:
            # Check for NaN (works for both float('nan') and numpy.nan)
            sanitized[key] = None if pd.isna(value) else value
    return sanitized


def get_organization_acronym_(org_name: str, stopwords: Optional[Set[str]] = None) -> str:
    """
    Generate an acronym for an organization name.

    Rules:
      - Split the name into tokens by whitespace.
      - The first token (primary) is processed separately:
          • If it contains a hyphen, split it into sub-tokens and take the first letter of each sub-token (in uppercase).
          • Otherwise, take the first letter (uppercase).
      - For the remaining tokens (secondary):
          • If there are 2 or fewer tokens, use them all in order:
              - For each token, if it is a stopword (e.g. "of", "the", etc.), use its first letter in lowercase.
                Otherwise, use its first letter in uppercase.
          • If there are more than 2 secondary tokens, filter out the stopwords and then take at most the first 4 tokens 
            from the remaining (using their first letters in uppercase).
      - If there is a secondary group and the primary token was hyphenated, join primary and secondary with a hyphen.
        Otherwise, simply concatenate.

    Examples:
      "Ministry of Communication" -> "MoC"
      "Accra-Boys Scout Corporation" -> "AB-SC"
      "Ghana-India Kofi Annan Centre of Excellence in ICT" -> "GI-KACE"

    Args:
        org_name (str): The organization name.
        stopwords (Optional[Set[str]]): A set of words to ignore (case-insensitive). 
            Defaults to {"of", "the", "and", "for", "in", "at", "by", "a", "an"}.

    Returns:
        str: The generated acronym.
        
    Raises:
        ValueError: If org_name is not a nonempty string.
    """

    if not isinstance(org_name, str) or not org_name.strip():
        raise ValueError("Organization name must be a nonempty string.")

   
    # Default stopwords (all lowercase).
    if stopwords is None:
        stopwords = {"of", "the", "and", "for", "in", "at", "by", "a", "an"}
    
    

    # Split the organization name by whitespace.
    tokens = org_name.strip().split()
    if not tokens:
        return ""
    
    #if org_name is a single token or the token is hyphenated, return its entire word with first letter capitalized.
    # If there's only one token, return it with first letter capitalized.
    # If the token is hyphenated, return the first letter of each part capitalized.
    if len(tokens) == 0:
        return ""
    # If there's only one token, return it with first letter capitalized.
    if len(tokens) == 1:
        return tokens[0][0].upper() + tokens[0][1:].lower()
    
    #if the token is two but hyphenated, return the entire word with first letter capitalized.
    if len(tokens) == 2 and "-" in tokens[0]:
        # Split on hyphen and take first letters of each part.
        sub_tokens = [sub for sub in tokens[0].split("-") if sub]
        return "".join(sub[0].upper() for sub in sub_tokens)
    

    # Process the primary token (first token)
    first_token = tokens[0]
    first_has_hyphen = "-" in first_token
    if first_has_hyphen:
        # Split on hyphen and take first letters of each part.
        sub_tokens = [sub for sub in first_token.split("-") if sub]
        primary = "".join(sub[0].upper() for sub in sub_tokens)
    else:
        primary = first_token[0].upper()

    # Process secondary tokens (tokens[1:])
    secondary_tokens = tokens[1:]
    secondary = ""
    if not secondary_tokens:
        return primary

    if len(secondary_tokens) <= 2:
        # Use all tokens.
        letters = []
        for token in secondary_tokens:
            word = token.strip(" ,.;:-")
            if not word:
                continue
            if word.lower() in stopwords:
                letters.append(word[0].lower())
            else:
                letters.append(word[0].upper())
        secondary = "".join(letters)
    else:
        # More than 2 tokens: filter out stopwords and take up to first 4 tokens.
        filtered = [token for token in secondary_tokens if token.strip(" ,.;:-").lower() not in stopwords and token.strip(" ,.;:-")]
        if not filtered:
            # Fallback to using all tokens if filtering removes all.
            filtered = [token for token in secondary_tokens if token.strip(" ,.;:-")]
        filtered = filtered[:4]
        secondary = "".join(token.strip(" ,.;:-")[0].upper() for token in filtered)

    # Return result.
    if first_has_hyphen:
        return f"{primary}-{secondary}"
    else:
        return primary + secondary






from typing import Optional, Set

DEFAULT_STOPWORDS = {"of", "the", "and", "for", "in", "at", "by", "a", "an"}


def get_organization_acronym2(
    org_name: str,
    *,
    stopwords: Optional[Set[str]] = None,
    max_original_length: int = 10,
    max_original_tokens: int = 2,
    max_acronym_secondary: int = 4,
) -> str:
    """
    Return a user-friendly label for an organization name:
      - If the name is a single “short” word (<= max_original_length chars),
        returns it title-cased (e.g. "pixar" -> "Pixar").
      - If the name is 2 words or fewer (<= max_original_tokens) and its total
        length is <= max_original_length * max_original_tokens,
        returns title-cased original (e.g. "acme corp" -> "Acme Corp").
      - Otherwise, generates an acronym, stripping common stopwords.

    Args:
        org_name: Raw organization name.
        stopwords: Words to ignore in acronym (defaults to common small words).
        max_original_length: Max chars for a “short” single word.
        max_original_tokens: Max words to keep as original title.
        max_acronym_secondary: Max non-stopword tokens for acronym.

    Returns:
        A cleaned title or an acronym (all in ASCII letters).
    """
    if not isinstance(org_name, str) or not org_name.strip():
        raise ValueError("Organization name must be a nonempty string.")

    stopwords = stopwords or DEFAULT_STOPWORDS

    # Normalize whitespace
    parts = org_name.strip().split()
    total_length = len(org_name.strip())

    # 1) Short single word → Title-case
    if len(parts) == 1 and len(parts[0]) <= max_original_length:
        return parts[0].capitalize()

    # 2) Very short multi-word name → Title-case full name
    if len(parts) <= max_original_tokens and total_length <= max_original_length * max_original_tokens:
        return " ".join(p.capitalize() for p in parts)

    # 3) Fallback to acronym
    return _make_acronym(parts, stopwords, max_acronym_secondary)


def _make_acronym(tokens: list[str], stopwords: Set[str], max_secondary: int) -> str:
    """
    Build an acronym from token list:
      - Take first letter of first token (hyphenated → each sub-piece).
      - From remaining tokens, drop stopwords, take up to max_secondary,
        first letters only.
      - Join with hyphen if the first token was hyphenated.
    """
    # Primary
    first = tokens[0]
    if "-" in first:
        subtoks = [s for s in first.split("-") if s]
        primary = "".join(s[0].upper() for s in subtoks)
        hyphenated = True
    else:
        primary = first[0].upper()
        hyphenated = False

    # Secondary
    second_tokens = tokens[1:]
    # Filter stopwords
    filtered = [
        t for t in second_tokens
        if t.strip(" ,.;:-").lower() not in stopwords and t.strip(" ,.;:-")
    ]
    if not filtered:
        filtered = [t for t in second_tokens if t.strip(" ,.;:-")]

    secondary_letters = [t.strip(" ,.;:-")[0].upper() for t in filtered[:max_secondary]]
    secondary = "".join(secondary_letters)

    if not secondary:
        return primary
    if hyphenated:
        return f"{primary}-{secondary}"
    return primary + secondary





def get_organization_acronym_1(
    org_name: str,
    *,
    stopwords: Optional[Set[str]] = None,
    max_length: int = 15,
) -> str:
    """
    Generate a smart, URL-safe acronym for an organization name.
    
    Rules:
    - Short names (≤10 chars, ≤2 words): Keep as title case
    - Medium names: Smart acronym with hyphens for hyphenated words
    - Long names: Full acronym
    - Preserves hyphens in original hyphenated words
    - Filters out common stopwords
    - URL-safe output
    
    Args:
        org_name: Raw organization name
        stopwords: Words to ignore (default: common small words)
        max_length: Maximum length of the acronym (default: 15)
    
    Returns:
        A smart acronym or title-cased name
        
    Examples:
        "Pixar" -> "Pixar"
        "Freddie Co." -> "Freddie Co."
        "Ministry of Communication" -> "MoC"
        "Ministry of Health & Social Services" -> "MoH-SS"
        "Ghana-India Kofi Annan Centre" -> "GI-KAC"
        "University of Technology" -> "UoT"
    """
    if not isinstance(org_name, str) or not org_name.strip():
        raise ValueError("Organization name must be a nonempty string.")

    stopwords = stopwords or DEFAULT_STOPWORDS
    
    # Clean and normalize the input
    cleaned_name = org_name.strip()
    
    # Remove special characters except alphanumeric, spaces, and hyphens
    cleaned_name = re.sub(r'[^A-Za-z0-9\s\-]', '', cleaned_name)
    
    # Split into words, preserving hyphenated words
    words = []
    for word in cleaned_name.split():
        if '-' in word:
            # Keep hyphenated words as single units
            words.append(word)
        else:
            words.append(word)
    
    if not words:
        raise ValueError("Organization name must contain alphanumeric characters.")
    
    # Calculate total length and word count
    total_length = len(cleaned_name)
    word_count = len(words)
    
    # Rule 1: Short names (≤10 chars or ≤2 words) - keep as title case
    if total_length <= 10 or word_count <= 2:
        # Clean up the original name for display, but preserve periods
        display_name = re.sub(r'[^A-Za-z0-9\s\-\.]', '', org_name.strip())
        # Title case each word
        title_words = []
        for word in display_name.split():
            if '-' in word:
                # Handle hyphenated words
                hyphenated_parts = [part.capitalize() for part in word.split('-')]
                title_words.append('-'.join(hyphenated_parts))
            else:
                title_words.append(word.capitalize())
        return ' '.join(title_words)
    
    # Rule 2: Medium to long names - generate smart acronym
    acronym_parts = []
    
    # Process words, including stopwords for better acronyms
    for i, word in enumerate(words):
        if '-' in word:
            # Handle hyphenated words: take first letter of each part
            hyphenated_parts = word.split('-')
            hyphen_acronym = '-'.join([part[0].upper() for part in hyphenated_parts if part])
            acronym_parts.append(hyphen_acronym)
        else:
            # For regular words, include stopwords if they help create better acronyms
            if word.lower() in stopwords and i > 0:
                # Include stopwords in the middle for better readability
                acronym_parts.append(word[0].lower())
            else:
                # Regular word: take first letter
                acronym_parts.append(word[0].upper())
    
    # Join acronym parts
    if not acronym_parts:
        # Fallback: use first word
        first_word = words[0]
        if '-' in first_word:
            parts = first_word.split('-')
            return '-'.join([part[0].upper() for part in parts if part])
        else:
            return first_word[0].upper()
    
    # Special handling for specific patterns
    if len(acronym_parts) == 2:
        # Two words: join normally
        acronym = ''.join(acronym_parts)
    elif len(acronym_parts) == 3:
        # Three words: MoC, UoT, etc.
        acronym = ''.join(acronym_parts)
    elif len(acronym_parts) == 4:
        # Four words: MoH-SS (Ministry of Health & Social Services)
        acronym = ''.join(acronym_parts[:2]) + '-' + ''.join(acronym_parts[2:])
    elif len(acronym_parts) == 5:
        # Five words: MoH-SS (Ministry of Health & Social Services)
        acronym = ''.join(acronym_parts[:2]) + '-' + ''.join(acronym_parts[2:])
    else:
        # More than 5 words: use first few letters
        acronym = ''.join(acronym_parts[:4])
    
    # Handle hyphenated words in the result
    if '-' in acronym and len(acronym.split('-')) > 2:
        # If we have too many hyphens, simplify
        parts = acronym.split('-')
        if len(parts) == 3:
            # G-IK-AC -> GI-KAC
            acronym = parts[0] + parts[1] + '-' + parts[2]
        elif len(parts) == 4:
            # G-I-K-A-C -> GI-KAC
            acronym = parts[0] + parts[1] + '-' + parts[2] + parts[3]
    
    # Ensure we don't exceed max_length
    if len(acronym) > max_length:
        acronym = acronym[:max_length]
    
    return acronym


def _truncate_if_needed(text: str, max_len: int) -> str:
    """
    Truncate text to max_len and append '...' if it exceeds.
    """
    if max_len and len(text) > max_len:
        return text[:max_len] + '...'
    return text


def _make_acronym(tokens: List[str], stopwords: Set[str], max_secondary: int) -> str:
    """
    Build an acronym from token list:
      - Take first letter(s) of the first token (handle hyphens as multiple letters).
      - For secondary tokens: always include the first secondary (index 1) lowercase if stopword,
        then include up to max_secondary-1 additional uppercase letters from non-stopword tokens.
      - If the first token was hyphenated, insert a hyphen between primary and secondary block.
    """
    # Primary (handle hyphenation)
    first = tokens[0]
    if '-' in first:
        sub_pieces = [part for part in first.split('-') if part]
        primary = ''.join(piece[0].upper() for piece in sub_pieces)
        hyphenated = True
    else:
        primary = first[0].upper()
        hyphenated = False

    # Secondary: include first secondary token always, then non-stopwords
    secondary_letters = []
    # If there's at least one secondary token:
    if len(tokens) > 1:
        sec = tokens[1].strip(' ,.;:-')
        if sec:
            # lowercase if stopword, else uppercase
            secondary_letters.append(sec[0].lower() if sec.lower() in stopwords else sec[0].upper())
    # Now fill with non-stopwords up to max_secondary
    for tok in tokens[2:]:
        if len(secondary_letters) >= max_secondary:
            break
        clean = tok.strip(' ,.;:-')
        if not clean or clean.lower() in stopwords:
            continue
        secondary_letters.append(clean[0].upper())

    if not secondary_letters:
        return primary

    secondary = ''.join(secondary_letters)
    return f"{primary}-{secondary}" if hyphenated else primary + secondary



class Validator:
    @staticmethod
    def is_valid_email(email: str) -> bool:
        return re.match(r"[^@]+@[^@]+\.[^@]+", email) is not None

    @staticmethod
    def is_valid_dob(dob: datetime) -> bool:
        today = datetime.today()
        return dob < today and (today.year - dob.year) <= 120

def get_smtp_config():
        """Provides SMTP configuration for email."""
        return {
            "host": "smtp.gmail.com",  # Example SMTP host
            "port": 587,
            "username": "dev.aiti.com.gh@gmail.com",
            "password": "palvpbokbnisspps",
            "from_email": "dev.aiti.com.gh@gmail.com",
        }


# -------- New Advanced Organization Acronym Function --------
import unicodedata

# Core helpers (generic acronymmer)
_STOPWORDS_EN = {
    "a","an","and","as","at","but","by","for","from","in","into","nor",
    "of","on","or","over","per","the","to","via","with"
}
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[A-Za-z])(?=[A-Z][a-z])|(?<=[a-z])(?=[A-Z])")
_ALNUM_RE = re.compile(r"[0-9A-Za-z\u00C0-\u024F\u1E00-\u1EFF]+")
_ROMAN_RE = re.compile(r"^(?:M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3}))$")

def _strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

def _split_tokens(text: str):
    # Normalize common separators to spaces; keep words/digits; split camelCase
    sep_normalized = re.sub(r"[&+/·•–—/:·]", " ", text).replace("'", "'")
    rough = _ALNUM_RE.findall(sep_normalized)
    for t in rough:
        if t.isupper() and len(t) > 1:  # keep UN/ICT/AI intact
            yield t
            continue
        for p in _CAMEL_BOUNDARY_RE.split(t):
            if p:
                yield p

def _initials(words: Iterable[str], *, drop: set = _STOPWORDS_EN) -> str:
    sig = [w for w in words if w.lower() not in drop]
    if not sig: sig = list(words)
    return "".join(w[0].upper() for w in sig if w)

def _generic_acronym(name: str, *, ascii_only=False, stopwords: Optional[set]=None) -> str:
    if not name or not name.strip():
        return ""
    s = " ".join(name.split())
    if ascii_only: s = _strip_diacritics(s)

    stop = _STOPWORDS_EN if stopwords is None else {w.lower() for w in stopwords}
    letters = []
    for tok in _split_tokens(s):
        low = tok.lower()
        if low in stop: continue
        if tok.isupper() and len(tok) > 1:
            letters.append(tok); continue
        if _ROMAN_RE.match(tok.upper()) and tok.isalpha():
            letters.append(tok.upper()); continue
        ch = tok[0]
        if ascii_only:
            ch = re.sub(r"[^A-Za-z0-9]", "", _strip_diacritics(ch))
            if not ch: continue
        letters.append(ch.upper())
    return "".join(letters)

# Ghana-style rules (algorithmic, no hard-coded orgs)
def _ministry_acronym(after_ministry_of: str) -> str:
    """
    Build Mo* form from the domain after 'Ministry of ...'.
    Split on '&'/'and' into segments; each segment -> initials of significant words.
    Use hyphen when any segment contributes >1 letter (e.g., 'SS' in 'Social Services').
      - 'Health & Social Services' -> MoH-SS
      - 'Communications and Digitalization' -> MoCD
    """
    segs = [seg.strip() for seg in re.split(r"\b(?:&|and)\b", after_ministry_of, flags=re.IGNORECASE) if seg.strip()]
    parts = []
    for seg in segs:
        parts.append(_initials(_split_tokens(seg)))
    needs_hyphen = any(len(p) > 1 for p in parts) or len(parts) > 2
    tail = ("-" if needs_hyphen else "").join(parts)
    return f"Mo{tail}"

def _two_party_prefix(name: str) -> Optional[str]:
    """
    If the name begins with 'X-Y ...' or 'X Y ...' where X and Y are title-cased words,
    return their initials joined (e.g., 'Ghana-India ...' -> 'GI').
    """
    # Hyphenated pair
    m = re.match(r"^\s*([A-Z][a-zA-Z]+)\s*-\s*([A-Z][a-zA-Z]+)\b", name)
    if m:
        return m.group(1)[0].upper() + m.group(2)[0].upper()
    # Space-separated pair (less strict; require next token to be capitalized)
    m2 = re.match(r"^\s*([A-Z][a-zA-Z]+)\s+([A-Z][a-zA-Z]+)\b", name)
    if m2:
        return m2.group(1)[0].upper() + m2.group(2)[0].upper()
    return None

def _centre_of_excellence_block(name_after_prefix: str) -> Optional[str]:
    """
    If we find a '... Centre of Excellence ...' block, produce initials of the phrase
    '[<leading proper names>] Centre of Excellence' (dropping stop-words and 'of'),
    ignoring any trailing 'in <field>' part. E.g., 'Kofi Annan Centre of Excellence in ICT' -> 'KACE'.
    """
    # Trim to '... Centre of Excellence ...' (stop before ' in <...>' if present)
    trunk = re.split(r"\bin\b", name_after_prefix, flags=re.IGNORECASE, maxsplit=1)[0]
    # Find the anchor 'Centre of Excellence'
    m = re.search(r"(.+?)\bCentre\s+of\s+Excellence\b", trunk, flags=re.IGNORECASE)
    if not m:
        return None
    lead = m.group(1)  # e.g., 'Kofi Annan '
    words = list(_split_tokens(lead)) + ["Centre", "of", "Excellence"]
    return _initials(words)

def _university_acronym(name: str) -> str:
    """
    University patterns (no hard-coded names):
      A) 'University of <Tail>' -> 'U' + initials(Tail)
      B) '<Proper Names> University of <Tail>' -> initials(Proper Names) + 'U' + initials(Tail)
         (This yields KN + U + ST = KNUST for 'Kwame Nkrumah University of Science & Technology')
    Otherwise fallback to generic.
    """
    # A) Starts with University of ...
    mA = re.match(r"^\s*University\s+of\s+(.+)$", name, flags=re.IGNORECASE)
    if mA:
        tail = mA.group(1)
        return "U" + _initials(_split_tokens(tail))

    # B) Ends with 'University of <Tail>' but has a leading proper-name block
    mB = re.match(r"^\s*(.+?)\s+University\s+of\s+(.+)$", name, flags=re.IGNORECASE)
    if mB:
        prefix, tail = mB.group(1), mB.group(2)
        pre_init = _initials(_split_tokens(prefix))
        return pre_init + "U" + _initials(_split_tokens(tail))

    return _generic_acronym(name, ascii_only=True)

def get_organization_acronym(
    name: str,
    *,
    ascii_only: bool = True,
    max_length: int = 12
) -> str:
    """
    Generate a best-effort, Ghana-style acronym with no hard-coded organization lists.

    Rules (algorithmic):
      • Ministries: 'Mo' + domain initials, hyphenating when a segment yields multi-letter initials.
      • Two-party collaborations at the start (e.g., 'Ghana-India ...'):
          prefix initials (e.g., 'GI') + '-' + block initials if a
          '... Centre of Excellence ...' anchor is present (e.g., 'KACE').
      • Universities:
          - 'University of X Y' -> 'U' + initials(X Y)  (e.g., UENR, UDS)
          - '<Names> University of X Y' -> initials(Names) + 'U' + initials(X Y) (e.g., KNUST)
      • Otherwise: robust generic acronymmer (stop-words, camelCase, diacritics, hyphens, digits).

    Parameters
    ----------
    name : str
        Organization/institution name.
    ascii_only : bool
        If True, strip diacritics to ASCII.
    max_length : int
        Maximum length of the acronym (default: 12).

    Returns
    -------
    str : acronym in uppercase
    """
    if not isinstance(name, str):
        raise ValueError("Organization name must be a string")
    
    if not name.strip():
        raise ValueError("Organization name cannot be empty")

    # Clean the input: remove special characters except alphanumeric, spaces, hyphens, and ampersands
    s = re.sub(r'[^\w\s\-&]', ' ', name.strip())
    s = " ".join(s.split())

    # Ministry pattern
    m = re.match(r"^\s*Ministry\s+of\s+(.+)$", s, flags=re.IGNORECASE)
    if m:
        result = _ministry_acronym(m.group(1))
        return result[:max_length] if len(result) > max_length else result

    # Two-party collab + Centre of Excellence anchor (e.g., GI-KACE)
    two = _two_party_prefix(s)
    if two:
        # remove the initial two words/hyphen from the front
        s2 = re.sub(r"^\s*[A-Z][a-zA-Z]+\s*-?\s*[A-Z][a-zA-Z]+\s*", "", s)
        kace = _centre_of_excellence_block(s2)
        if kace:
            result = f"{two}-{kace}"
            return result[:max_length] if len(result) > max_length else result
        else:
            # If no Centre of Excellence, create acronym from remaining words
            remaining_words = list(_split_tokens(s2))
            if remaining_words:
                remaining_acronym = _initials(remaining_words)
                result = f"{two}-{remaining_acronym}"
                return result[:max_length] if len(result) > max_length else result

    # University patterns
    if re.search(r"\bUniversity\b", s, flags=re.IGNORECASE):
        result = _university_acronym(s)
        return result[:max_length] if len(result) > max_length else result

    # Fallback generic
    result = _generic_acronym(s, ascii_only=ascii_only)
    
    # Ensure we don't exceed max_length
    if len(result) > max_length:
        result = result[:max_length]
    
    return result


