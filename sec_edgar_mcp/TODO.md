Short answer: You’re close. As an MCP “facts API,” it already retrieves the right sources. To support LLM agents screening derivative shareholder cases reliably and efficiently, add a few focused tools, tighten outputs, and standardize schemas. No Elasticsearch needed.
Executive Summary

The server already: finds filings, fetches text, surfaces 8‑K items and proxy sections, returns financials and insider activity.
Needed next: targeted governance exhibits, stronger 8‑K flags, structured proxy snapshot, beneficial owners table, event-window aggregator, compact/parametrized outputs, and small doc‑level search.
What It Can Do Today

Company/CIK enrichment: get_cik_by_ticker, get_company_info, search_companies (sec_edgar_mcp/server.py
,
,
).
Filings access: get_recent_filings, get_filing_content (sec_edgar_mcp/server.py
,
).
8‑K analysis (basic items + press release check): analyze_8k (sec_edgar_mcp/server.py
).
Proxy sections (presence + spans): analyze_proxy_def14a (sec_edgar_mcp/server.py
; sec_edgar_mcp/tools/proxy_tools.py).
Financials/XBRL/segments/metrics: get_financials, get_xbrl_concepts, etc. (sec_edgar_mcp/server.py
–414).
Insider filings: transactions, summaries, details, sentiment (sec_edgar_mcp/server.py
–533).
Gaps Blocking Derivative-Suit Screening

Governance exhibits: No tool to fetch/parse bylaws/certificate/charters where exclusive forum and DGCL 102(b)(7) exculpation actually reside.
8‑K critical flags: No explicit booleans/snippets for 4.02 non‑reliance (restatement), 4.01 auditor change with disagreements, 5.02 departures with disputes, 8.01 investigations.
Proxy structure: No board roster/independence/committee memberships snapshot; only section presence.
Beneficial owners: No structured ≥5% holders table (names, shares, percent).
Event window: No “one call” fact pack around a case date combining 8‑K signals, insider activity, proxy snapshot, and governance exhibits.
Token hygiene: Proxy analyzer returns large spans by default; no knobs to keep outputs compact when LLM only needs booleans/brief excerpts.
Proposed New Tools (minimal infra, high value)

get_exhibit_text(identifier, accession, exhibit_regex)
Purpose: Fetch and normalize governance exhibits (e.g., “Exhibit 3.1”, “Bylaws”, “Restated Certificate”).
Output: {matches:[{exhibit_id, title, url, text_len, excerpts:[…]}]} with content optionally capped.
Location: new sec_edgar_mcp/tools/exhibits.py; register in sec_edgar_mcp/server.py.
search_in_filing(identifier, accession, terms, context_chars=200, max_hits=20)
Purpose: In‑document, keyword-based search with short excerpts for forum, 102(b)(7), non‑reliance, etc.
Output: {hits:[{term, count, samples:[{start, end, excerpt}]}]}.
proxy_structured_summary(identifier, accession=None)
Purpose: Extract board roster, independence flags, committee memberships, and detect mention of forum clause in the proxy.
Output: {board:[{name, role, independent}], committees:{audit:[…], comp:[…], nomgov:[…]}, forum_clause_mentioned
, evidence_snippets:[…]}.
get_beneficial_owners(identifier, accession, threshold=0.05)
Purpose: Parse the beneficial ownership table to structured rows.
Output: {owners:[{holder, shares, percent, footnotes?}], source_url}.
event_window_pack(identifier, event_date, window_days=60)
Purpose: Aggregate facts around a case date.
Output: {window:{start,end}, eightk_flags:{…}, insider_summary:{…}, proxy_snapshot:{…}, exhibits_hits:{…}, urls:[…]}.
Enhancements to Existing Tools

analyze_8k (sec_edgar_mcp/server.py
; sec_edgar_mcp/tools/filings.py)
Add booleans for: restatement_402, auditor_disagreement_401, departures_dispute_502, investigation_801.
Include 1–2 short evidence excerpts + the exact SEC URL for each flag.
analyze_proxy_def14a (sec_edgar_mcp/server.py
; sec_edgar_mcp/tools/proxy_tools.py)
Add parameters: summary_only: bool=false, max_section_chars: int=4000.
Improve heading detection: also index HTML h1–h6/strong tags; if no headings, return fixed windows around cue matches.
Return a small sections_present map when summary_only=true.
get_recent_filings (sec_edgar_mcp/tools/filings.py)
Use filing_date arg in edgar.get_filings(filing_date='>=YYYY-MM-DD', form=...) to reduce index scan for global queries.
Keep per-call limits and cutoff filtering; never touch per-filing properties that trigger fetches.
API Contract & Schemas

Deterministic JSON:
All tools return {success, data|error, filing_reference?}. Include filing_reference:{form, accession, date, url, identifier} when applicable.
Define Pydantic models in sec_edgar_mcp/core/models.py for new outputs (ExhibitHit, EightKFlags, ProxySummary, BeneficialOwner, EventWindowPack).
Stable field names:
Use snake_case; keep “present” booleans separate from “text/excerpts”.
Evidence discipline:
For every boolean flag, include a short evidence_excerpt and sec_url.
Token & Rate Hygiene

Output controls:
Add summary*only/max*\*\_chars params; default to compact outputs for analyzers.
Request bounds:
Enforce sensible limit and days caps server-side; reject oversized requests cleanly.
No global FTS:
Keep searches in-document or in-exhibit; no corpus-wide scans.
Caching:
In-memory TTL (e.g., 10–15 min) for: company CIKs (already), recent filings queries, fetched filing/exhibit text.
Error Handling & Telemetry

Structured errors:
Return {success:false, code:'TIMEOUT|NOT_FOUND|RATE_LIMIT', message} rather than free-form strings.
Observability:
Log network calls count per tool call; log bytes_in/out, duration, and early exits.
Differentiate transport success from domain success in logs.
Security & Compliance

Identity:
Continue setting SEC_EDGAR_USER_AGENT and edgartools identity; document requirement prominently.
Rate limits:
Respect SEC patterns; throttle global queries; avoid per-filing storms (fixed already).
Input sanitization:
Validate identifier, accession, regex inputs for exhibits; cap regex complexity.
Rollout Plan

Phase 1 (fast wins):
Add summary_only/max_section_chars to analyze_proxy_def14a.
Enhance analyze_8k with restatement/auditor/dispute/investigation flags + snippets.
Implement get_exhibit_text and search_in_filing.
Phase 2:
Implement proxy_structured_summary and get_beneficial_owners.
Add event_window_pack.
Phase 3:
Tighten get_recent_filings with filing_date filtering.
Add TTL caches and structured error codes across tools.
Write unit tests for each tool; smoke tests using known filings.
Example LLM Workflow (Case Screening)

Identify target/date: From the case description.
Pull event pack:
event_window_pack(identifier, event_date) → eightk_flags, insider_summary, proxy_snapshot, exhibits_hits.
If missing governance details:
get_exhibit_text(..., '(?i)bylaws|certificate') → search_in_filing for “exclusive forum”, “102(b)(7)”.
If needed:
proxy_structured_summary(...) for board independence and committees.
Agent applies legal logic externally, citing only returned excerpts/URLs.
If you want, I can start with Phase 1 (adds the least code and delivers the biggest screening lift) and keep outputs compact by default.
