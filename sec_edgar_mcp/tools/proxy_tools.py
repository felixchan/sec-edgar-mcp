import datetime
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup


# We will reuse the existing FilingsTools instance to stay consistent with the edgartools wiring.
# FilingsTools must expose:
#   - get_recent_filings(identifier: str, form_type: Optional[str], days: int, limit: int) -> dict
#   - get_filing_content(identifier: str, accession_number: str) -> dict
#
# The returned dicts should include (or be adapted to include) keys similar to:
#   filings -> List[{"form_type","accession_number","filing_date","url"}]
#   content -> {"html" or "text" or "content", "url", "form_type", "accession_number", "filing_date"}

PROXY_FORMS = {"DEF 14A", "DEFM14A", "PRE 14A", "PREM14A"}

# Headline cues to carve the proxy into the sections the LLM needs.
# We do not "interpret" anything; we only surface text spans that likely contain the facts.
SECTION_CUES = {
    "related_party": [
        "Certain Relationships and Related Transactions",
        "Related Party",
        "Item 404",
        "Transactions with Related Persons",
    ],
    "director_independence": [
        "Director Independence",
        "Independence of the Board",
        "Independent Directors",
    ],
    "board_committees": [
        "Board Committees",
        "Committees of the Board",
        "Audit Committee",
        "Compensation Committee",
        "Nominating and Corporate Governance Committee",
    ],
    "beneficial_ownership": [
        "Security Ownership of Certain Beneficial Owners and Management",
        "Beneficial Ownership",
        "Principal Stockholders",
        "Ownership of Securities",
    ],
    "exclusive_forum": [
        "Exclusive Forum",
        "Forum Selection",
        "Choice of Forum",
        "Exclusive Jurisdiction",
    ],
    "governance_overview": [
        "Corporate Governance",
        "Governance",
        "Board Structure",
        "Classified Board",
        "Dual Class",
        "Stockholder Rights",
        "Supermajority",
        "Bylaws",
        "Certificate of Incorporation",
    ],
}


def _norm(s: str) -> str:
    return " ".join(s.replace("\xa0", " ").split())


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Remove scripts/styles
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    return _norm(text)


def _find_all_headings(text: str) -> List[Tuple[int, str]]:
    """
    Very light-weight heading finder: collect lines that look like headings.
    We keep it conservative and simply index lines that are short and Title-like.
    """
    headings = []
    lines = text.split("\n")
    offset = 0
    for line in lines:
        striped = line.strip()
        if 3 <= len(striped) <= 120:
            # Heuristics: many proxy headings are Title Case or ALL CAPS and not ending with punctuation.
            if striped.isupper() or striped.istitle():
                if not striped.endswith((".", ":", ";", ",")):
                    headings.append((offset, striped))
        offset += len(line) + 1
    # Ensure unique by position
    headings.sort(key=lambda x: x[0])
    return headings


def _slice_by_cues(text: str, headings: List[Tuple[int, str]], cues: List[str]) -> Optional[str]:
    """
    Return the text span starting at the first heading that matches any cue and
    ending at the next heading (or end of document).
    """
    if not headings:
        return None
    lower_text = text.lower()
    # Build list of candidate starts by scanning headings for cue matches
    starts = []
    for pos, title in headings:
        title_l = title.lower()
        for cue in cues:
            if cue.lower() in title_l:
                starts.append(pos)
                break
    if not starts:
        # Fallback: raw substring search on full text if a cue phrase appears inline
        first = None
        for cue in cues:
            idx = lower_text.find(cue.lower())
            if idx != -1:
                first = idx
                break
        if first is None:
            return None
        # Find next heading after this index
        next_positions = [p for (p, _) in headings if p > first]
        end = next_positions[0] if next_positions else len(text)
        return text[first:end].strip()

    start = min(starts)
    # Determine end by next heading after start
    after = [p for (p, _) in headings if p > start]
    end = after[0] if after else len(text)
    return text[start:end].strip()


class ProxyTools:
    def __init__(self, filings_tools):
        self.filings_tools = filings_tools

    def _resolve_proxy_filing(self, identifier: str, accession_number: Optional[str]) -> Dict:
        """
        Choose the proxy filing to analyze. If accession_number is provided, use it.
        Otherwise pick the most recent DEF 14A/DEFM14A/PRE 14A/PREM14A in the last 400 days.
        """
        if accession_number:
            return {
                "identifier": identifier,
                "accession_number": accession_number,
            }

        recent = self.filings_tools.get_recent_filings(
            identifier=identifier, form_type=None, days=400, limit=200
        )
        filings = recent.get("filings", []) if isinstance(recent, dict) else []
        # Filter to proxy forms
        proxies = [f for f in filings if str(f.get("form_type", "")).upper() in PROXY_FORMS]
        if not proxies:
            return {"error": f"No proxy filings found for {identifier}."}

        # Prefer DEFM14A over DEF 14A, then PREM14A, then PRE 14A, and restrict to ~400 days if possible
        def _rank(form: str) -> int:
            form = form.upper()
            if form == "DEFM14A":
                return 0
            if form == "DEF 14A":
                return 1
            if form == "PREM14A":
                return 2
            if form == "PRE 14A":
                return 3
            return 9

        def _parse_dt(dt_str: Optional[str]) -> Optional[datetime.datetime]:
            if not dt_str:
                return None
            try:
                dt = datetime.datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
                # Normalize to naive UTC for consistent comparisons
                if dt.tzinfo is not None:
                    dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
                return dt
            except Exception:
                return None

        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=400)
        proxies_recent = [p for p in proxies if (_parse_dt(p.get("filing_date")) or cutoff) >= cutoff]
        candidates = proxies_recent if proxies_recent else proxies

        def _sort_key(f: Dict) -> tuple:
            dt = _parse_dt(f.get("filing_date")) or datetime.datetime.min
            rank = -_rank(str(f.get("form_type", "")))  # larger first -> lower rank preferred
            return (dt, rank)

        candidates.sort(key=_sort_key, reverse=True)
        chosen = candidates[0]
        if not chosen.get("accession_number"):
            return {"error": f"Unable to resolve accession number for {identifier}'s proxy filing."}
        return {
            "identifier": identifier,
            "accession_number": chosen.get("accession_number"),
            "filing_date": chosen.get("filing_date"),
            "form_type": chosen.get("form_type"),
            "url": chosen.get("url"),
        }

    def analyze_proxy_def14a(self, identifier: str, accession_number: Optional[str] = None) -> Dict:
        """
        Fetch the proxy, normalize text, expose key sections as raw spans, and return deterministic metadata.
        This method does not perform legal analysis. It only returns text segments and citations the LLM can use.

        Returns:
            {
              "success": true,
              "filing": {"form","accession","date","url","identifier"},
              "sections": {
                 "related_party": {"present": bool, "text": "...", "cue_used": ["..."]},
                 "director_independence": {...},
                 "board_committees": {...},
                 "beneficial_ownership": {...},
                 "exclusive_forum": {...},
                 "governance_overview": {...}
              },
              "full_text_len": int,
              "headings_index": [{"pos": int, "title": str}],
              "disclaimer": "All text extracted directly from SEC EDGAR proxy filing; no external sources."
            }
        """
        selection = self._resolve_proxy_filing(identifier, accession_number)
        if "error" in selection:
            return {"success": False, "error": selection["error"]}

        acc_no = selection["accession_number"]
        content_resp = self.filings_tools.get_filing_content(
            identifier=identifier, accession_number=acc_no, max_chars=None
        )
        if not isinstance(content_resp, dict) or not content_resp.get("success", False):
            return {"success": False, "error": content_resp.get("error", "Filing fetch failed.") if isinstance(content_resp, dict) else "Filing fetch failed."}

        filing_url = content_resp.get("url")
        form_type = content_resp.get("form_type", selection.get("form_type", "DEF 14A"))
        filing_date = content_resp.get("filing_date", selection.get("filing_date"))

        # Support multiple possible keys from FilingsTools: "html", "text", or legacy "content"
        raw_html = content_resp.get("html")
        raw_text = content_resp.get("text")
        if not raw_html and not raw_text:
            legacy_content = content_resp.get("content")
            if legacy_content:
                # Heuristic: treat as HTML if it contains angle-bracket tags
                if "<html" in legacy_content.lower() or "<div" in legacy_content.lower() or "<p" in legacy_content.lower():
                    raw_html = legacy_content
                else:
                    raw_text = legacy_content

        if raw_html:
            full_text = _html_to_text(raw_html)
        elif raw_text:
            full_text = _norm(raw_text)
        else:
            return {"success": False, "error": "No filing text available."}

        headings = _find_all_headings(full_text)

        sections_out = {}
        for key, cues in SECTION_CUES.items():
            span = _slice_by_cues(full_text, headings, cues)
            sections_out[key] = {
                "present": bool(span),
                "text": span if span else None,
                "cue_used": cues,
            }

        return {
            "success": True,
            "filing": {
                "form": form_type,
                "accession": acc_no,
                "date": filing_date,
                "url": filing_url,
                "identifier": identifier,
                "extraction_timestamp_utc": datetime.datetime.utcnow().isoformat() + "Z",
            },
            "sections": sections_out,
            "full_text_len": len(full_text),
            "headings_index": [{"pos": p, "title": t} for (p, t) in headings],
            "disclaimer": "All text extracted directly from the SEC EDGAR proxy filing; no external sources or interpretations.",
        }
