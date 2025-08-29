SEC_USER_AGENT = "SEC EDGAR MCP/1.0"

FILING_TYPES = {
    "10-K": "Annual report",
    "10-Q": "Quarterly report",
    "8-K": "Current report",
    "DEF 14A": "Proxy statement",
    "DEFM14A": "Definitive proxy statement (amended)",
    "PRE 14A": "Preliminary proxy statement",
    "PREM14A": "Preliminary proxy statement (amended)",
    "S-1": "Registration statement",
    "3": "Initial ownership report",
    "4": "Change in ownership report",
    "5": "Annual ownership report",
    "13F-HR": "Quarterly institutional holdings",
    "SC 13G": "Beneficial ownership report",
    "SC 13D": "Beneficial ownership report with intent",
}

XBRL_NAMESPACES = {
    "dei": "http://xbrl.sec.gov/dei",
    "us-gaap": "http://fasb.org/us-gaap",
    "ifrs": "http://xbrl.ifrs.org/taxonomy",
}
