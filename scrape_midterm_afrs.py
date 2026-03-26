# scrape_midterm_afrs.py
import re
import csv
from datetime import datetime
import requests
from bs4 import BeautifulSoup

START_URL = "https://resources.evans-legal.com/?p=2591"  # 2026 page with "Other Years"
OUT_CSV = "AFRs Table.CSV"

MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

def get_text(url: str) -> str:
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    # convert to text with newlines so regex can parse table rows
    return soup.get_text("\n")

def discover_year_pages(start_url: str) -> dict[int, str]:
    r = requests.get(start_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    year_to_url: dict[int, str] = {}
    for a in soup.find_all("a"):
        t = (a.get_text() or "").strip()
        if re.fullmatch(r"\d{4}", t) and a.get("href"):
            year_to_url[int(t)] = a["href"]

    # include the current page year (2026 here)
    year_to_url[2026] = start_url
    return dict(sorted(year_to_url.items()))

def normalize_month_token(tok: str, year: int) -> str:
    tok = tok.strip().replace("*", "")
    # handle e.g. "Sept." -> "Sep."
    tok = tok.replace("Sept", "Sep")
    # drop trailing punctuation
    tok = tok.strip().strip(".")
    # if token has a year suffix (Jan-94, Jan-2014), keep only month part
    if "-" in tok:
        left, right = tok.split("-", 1)
        if right[:1].isdigit():
            tok = left
        # Jan-Jun / Jul-Dec: keep left part (Jan / Jul)
        elif right[:1].isalpha():
            tok = left
    tok3 = tok[:3].upper()
    if tok3 not in MONTH_MAP:
        raise ValueError(f"Unrecognized month token '{tok}' in year {year}")
    mm = MONTH_MAP[tok3]
    return f"{mm:02d}/01/{year:04d}"

def extract_midterm_rows(year: int, url: str) -> list[dict]:
    text = get_text(url)

    # Find Mid Term section and slice until Long Term
    m = re.search(rf"Mid\s*Term\s*Rates\s*for\s*{year}", text, flags=re.IGNORECASE)
    if not m:
        raise RuntimeError(f"Could not find Mid Term section for {year} at {url}")
    tail = text[m.start():]

    end = re.search(rf"Long\s*Term\s*Rates\s*for\s*{year}", tail, flags=re.IGNORECASE)
    if end:
        tail = tail[:end.start()]

    # Row regex: month token + 4 percent rates (often glued together)
    row_re = re.compile(
        r"(?P<month>[A-Za-z][A-Za-z\.]*(?:-[A-Za-z]{3})?(?:-\d{2,4})?\*?)\s*"
        r"(?P<a>\d+\.\d+%)\s*(?P<s>\d+\.\d+%)\s*(?P<q>\d+\.\d+%)\s*(?P<m>\d+\.\d+%)"
    )

    rows = []
    for match in row_re.finditer(tail):
        month_tok = match.group("month")
        month_date = normalize_month_token(month_tok, year)
        rows.append({
            "Month[MM/DD/YYYY]": month_date,
            "Annual": match.group("a"),
            "Semiannual": match.group("s"),
            "Quaterly": match.group("q"),
            "Monthly": match.group("m"),
        })

    # Special case: 1984 uses Jan-Jun / Jul-Dec blocks (still matches)
    if not rows:
        raise RuntimeError(f"No Mid Term rows parsed for {year} at {url}")

    # de-dup (some pages have repeated labels)
    seen = set()
    out = []
    for r in rows:
        key = r["Month[MM/DD/YYYY]"]
        if key in seen:
            continue
        seen.add(key)
        out.append(r)

    # sort by date
    out.sort(key=lambda r: datetime.strptime(r["Month[MM/DD/YYYY]"], "%m/%d/%Y"))
    return out

def main():
    year_pages = discover_year_pages(START_URL)
    all_rows = []

    for year, url in year_pages.items():
        rows = extract_midterm_rows(year, url)
        all_rows.extend(rows)
        print(f"{year}: {len(rows)} rows")

    # global sort
    all_rows.sort(key=lambda r: datetime.strptime(r["Month[MM/DD/YYYY]"], "%m/%d/%Y"))

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Month[MM/DD/YYYY]", "Annual", "Semiannual", "Quaterly", "Monthly"])
        w.writeheader()
        w.writerows(all_rows)

    print(f"Wrote {OUT_CSV} with {len(all_rows)} rows.")

if __name__ == "__main__":
    main()
