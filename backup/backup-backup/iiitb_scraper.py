import re
import json
import time
import logging
import os
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

URLS_FILE       = "unique_urls.txt"
OUTPUT_DIR      = "output"
MAX_WORKERS     = 12        # concurrent threads
REQUEST_TIMEOUT = 12
DELAY           = 0.15      # seconds between requests per thread
RETRY_COUNT     = 2
OUTPUT_INDENT   = 2

SKIP_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".tar", ".gz", ".jpg", ".jpeg", ".png",
    ".gif", ".svg", ".webp", ".ico", ".mp4", ".mp3", ".css",
    ".js", ".woff", ".woff2", ".ttf", ".eot",
}

os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(OUTPUT_DIR, "scrape_log.txt"), mode="w")
    ]
)
log = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; IIITBScraper/2.0)"})


# loading urls and deduplicating them
"""
    /academics/integrated-mtech/faculty
    /academics/continuing-professional-education/faculty
    /research-scholars/faculty
"""
def load_urls(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]

def has_bad_extension(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in SKIP_EXTENSIONS)

# defining a unique key for each URL
def canonical_slug(url: str) -> str:
    
    p = urlparse(url)
    path = p.path.rstrip("/") or "/"
    segments = [s for s in path.split("/") if s]

    # Person-profile pages: keep full path as key
    PERSON_PREFIXES = {
        "faculty", "staff", "research-scholars",
        "ms-by-research-scholars", "scheme-1", "scheme-2",
        "integrated-phd-scholars",
    }
    if len(segments) >= 2 and segments[-2] in PERSON_PREFIXES:
        return f"{p.netloc}::{'/'.join(segments[-2:])}"

    # For all other www.iiitb.ac.in pages: deduplicate on (netloc, last-slug)
    if p.netloc in ("www.iiitb.ac.in", "iiitb.ac.in"):
        last = segments[-1] if segments else "home"
        return f"{p.netloc}::{last}"

    # Subdomains / external: full path is the key
    return f"{p.netloc}::{path}"

# keeping shortest URL per key
def deduplicate(urls: list[str]) -> list[str]:
    """Keep the SHORTEST URL per canonical key (avoids /academics/... mirrors)."""
    best: dict[str, str] = {}
    for url in urls:
        key = canonical_slug(url)
        if key not in best or len(url) < len(best[key]):
            best[key] = url
    return list(best.values())


# URL Classification
# Each category maps to: (regex_pattern, priority)
# Patterns are tested in priority order; first match wins.
URL_CATEGORIES = [
    # Person profiles
    ("faculty_profile",         r"iiitb\.ac\.in/faculty/[^/]+$"),
    ("staff_profile",           r"iiitb\.ac\.in/staff/[^/]+$"),
    ("research_scholar",        r"iiitb\.ac\.in/research-scholars/[^/]+$"),
    ("ms_scholar",              r"iiitb\.ac\.in/ms-by-research-scholars/[^/]+$"),
    ("iphd_scholar",            r"iiitb\.ac\.in/integrated-phd-scholars/[^/]+$"),
    ("scheme_scholar",          r"iiitb\.ac\.in/scheme-[12]/[^/]+$"),

    # Listing pages
    ("faculty_list",            r"iiitb\.ac\.in/faculty$"),
    ("staff_list",              r"iiitb\.ac\.in/staff$"),
    ("scholar_list",            r"iiitb\.ac\.in/(research-scholars|ms-by-research-scholars|integrated-phd-scholars|scheme-[12])$"),

    # Academic programmes
    ("program",                 r"iiitb\.ac\.in/(btech|integrated-mtech|mtech|phd|fellowships|"
                                r"courses/|programme-outcomes|curriculum|academic-calendar|"
                                r"exchange-program|online-education|continuing-professional-education"
                                r"|visvesvaraya-phd-scheme|student-merit-scholarship)"),

    # News / Media
    ("news",                    r"iiitb\.ac\.in/(iiitb-in-the-press|media-press-releases|"
                                r"faculty-articles|annual-reports|samvaad|tele-manas)"),
    ("dhss_news",               r"dhss\.iiitb\.ac\.in/"),
    ("cags_event",              r"cags\.iiitb\.ac\.in/"),

    # Research labs / centres (subdomains)
    ("lab_cse",                 r"cse\.iiitb\.ac\.in"),
    ("lab_ece",                 r"ece\.iiitb\.ac\.in"),
    ("lab_dsai",                r"dsai\.iiitb\.ac\.in"),
    ("lab_dhss",                r"dhss\.iiitb\.ac\.in"),
    ("lab_comet",               r"comet\.iiitb\.ac\.in"),
    ("lab_cags",                r"cags\.iiitb\.ac\.in"),
    ("lab_cognitive",           r"cognitive\.iiitb\.ac\.in"),
    ("lab_wsl",                 r"wsl\.iiitb\.ac\.in"),
    ("lab_sclab",               r"sclab\.iiitb\.ac\.in"),
    ("lab_rise",                r"rise\.iiitb\.ac\.in"),
    ("lab_ic",                  r"ic\.iiitb\.ac\.in"),
    ("lab_naviiina",            r"naviiina\.iiitb\.ac\.in"),
    ("lab_mpl",                 r"mpl\.iiitb\.ac\.in"),
    ("lab_seal",                r"sealiiitb\.github\.io"),
    ("lab_sarl",                r"iiitb\.ac\.in/sarl/"),
    ("lab_gvcl",                r"iiitb\.ac\.in/gvcl"),
    ("lab_hides",               r"iiitb\.ac\.in/hides/"),
    ("lab_generic",             r"iiitb\.ac\.in/(ehealth-research-centre|machine-intelligence-robotics"
                                r"|centre-for-it-public-policy|centre-for-applied-sciences"
                                r"|iiitb-innovation-center|iiitb-comet|iiitb-mosip"
                                r"|iiitb-ehrc|iiitb-minro|smart-city-lab|indian-knowledge-system"
                                r"|computer-science|data-sciences|software-engineering"
                                r"|networking-communication|vlsi-systems|digital-society"
                                r"|mathematics-and-basic-sciences)"),

    # External partners
    ("external",                r"(mosip\.io|coss\.org|cdpi\.dev|sites\.google|karnataka\.gov)"),

    # Governance / general
    ("governance",              r"iiitb\.ac\.in/(governing-body|administration|industry-advisory"
                                r"|aicte-mandatory|nirf|iqac|right-to-information|code-of-conduct"
                                r"|diversity-inclusion|internal-committee|institute-industry)"),
    ("placement",               r"iiitb\.ac\.in/(placement|recruiting-companies|summer-internship"
                                r"|to-recruit|policy)"),
    ("student_life",            r"iiitb\.ac\.in/(committees-clubs|events-and-festivals|cafeteria"
                                r"|library|alumni|explore-iiitb)"),
    ("general",                 r".*"),   # catch-all
]

_COMPILED = [(cat, re.compile(pat, re.IGNORECASE)) for cat, pat in URL_CATEGORIES]

# assigning urls some category
def classify_url(url: str) -> str:
    for cat, rx in _COMPILED:
        if rx.search(url):
            return cat
    return "general"


# https fetch
def fetch(url: str) -> tuple[str | None, BeautifulSoup | None]:
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            time.sleep(DELAY)
            r = SESSION.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            if r.status_code != 200:
                log.warning(f"HTTP {r.status_code}: {url}")
                return url, None
            if "text/html" not in r.headers.get("Content-Type", ""):
                return url, None
            return r.url, BeautifulSoup(r.text, "lxml")
        except Exception as e:
            if attempt == RETRY_COUNT:
                log.error(f"FAILED ({attempt}): {url} — {e}")
            else:
                time.sleep(1)
    return url, None

# extractors
def t(el) -> str:
    """Safe stripped text."""
    return el.get_text(separator=" ", strip=True) if el else ""


def meta(soup: BeautifulSoup, name: str) -> str:
    tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
    return tag.get("content", "").strip() if tag else ""


def first_text(soup: BeautifulSoup, *selectors) -> str:
    for sel in selectors:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return t(el)
    return ""


# Person profile (faculty / staff / scholar)
def extract_person(url: str, soup: BeautifulSoup, category: str) -> dict:
    slug = urlparse(url).path.strip("/").split("/")[-1]

    # Name: try common heading selectors
    name = (
        first_text(soup,
            "h1.page-title", "h1.entry-title", ".faculty-name",
            ".profile-name", "h1", ".name",
        ) or slug.replace("-", " ").title()
    )

    # Designation
    designation = first_text(soup,
        ".designation", ".faculty-designation", ".title",
        ".profile-title", ".position",
    )

    # Email
    email = ""
    email_tag = soup.find("a", href=re.compile(r"^mailto:", re.I))
    if email_tag:
        email = email_tag["href"].replace("mailto:", "").strip()

    # Research interests / bio
    bio = ""
    for sel in [".research-interests", ".bio", ".about", ".profile-content",
                ".entry-content p", "article p"]:
        paras = soup.select(sel)
        if paras:
            bio = " ".join(t(p) for p in paras[:3])
            break

    # Areas / keywords
    areas: list[str] = []
    for sel in [".areas", ".interests", ".research-areas", ".tags"]:
        tags = soup.select(sel + " li, " + sel + " a, " + sel + " span")
        if tags:
            areas = [t(tg) for tg in tags if t(tg)][:10]
            break

    return {
        "url": url,
        "slug": slug,
        "category": category,
        "name": name,
        "designation": designation,
        "email": email,
        "bio": bio[:800] if bio else "",
        "areas": areas,
    }


# Listing page (e.g. /faculty, /staff)
def extract_listing(url: str, soup: BeautifulSoup, category: str) -> dict:
    title = first_text(soup, "h1", "title", ".page-title") or url
    items: list[dict] = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = t(a)
        if text and len(text) > 3 and not href.startswith(("#", "javascript", "mailto")):
            items.append({"text": text, "href": href})

    return {
        "url": url,
        "category": category,
        "title": title,
        "links": items[:100],
    }


# Academic programme
def extract_program(url: str, soup: BeautifulSoup, category: str) -> dict:
    title = first_text(soup, "h1", ".page-title", "title")
    body_paras = [t(p) for p in soup.select("article p, .entry-content p, .page-content p")
                  if len(t(p)) > 40][:5]

    # Try to find a structured list (eligibility, seats, duration, etc.)
    info: dict[str, str] = {}
    for row in soup.select("table tr, dl dt, .info-row"):
        cells = row.find_all(["td", "th", "dd", "dt"])
        if len(cells) >= 2:
            info[t(cells[0]).strip(": ")] = t(cells[1])

    return {
        "url": url,
        "category": category,
        "title": title,
        "description": " ".join(body_paras),
        "structured_info": info,
    }


# News / Press item
def extract_news(url: str, soup: BeautifulSoup, category: str) -> dict:
    title = (
        first_text(soup, "h1.entry-title", "h1.post-title", "h1", ".page-title")
        or meta(soup, "og:title")
    )
    date = first_text(soup, ".entry-date", "time", ".published", ".date", ".post-date")
    author = first_text(soup, ".author", ".byline", ".entry-author")
    body = " ".join(
        t(p) for p in soup.select("article p, .entry-content p, .post-content p")
        if len(t(p)) > 30
    )[:1200]
    tags = [t(tg) for tg in soup.select(".tags a, .categories a, .post-tags a")]

    return {
        "url": url,
        "category": category,
        "title": title,
        "date": date,
        "author": author,
        "body": body,
        "tags": tags[:10],
    }


# Lab / Center page
def extract_lab(url: str, soup: BeautifulSoup, category: str) -> dict:
    title = (
        first_text(soup, "h1", ".lab-title", ".site-title", ".page-title", "title")
        or meta(soup, "og:title")
    )
    description = " ".join(
        t(p) for p in soup.select(
            "article p, .entry-content p, .about p, main p, .description p"
        ) if len(t(p)) > 30
    )[:1000]

    # People
    people = [t(el) for el in soup.select(
        ".team-member h3, .people-name, .member-name, .person-name, "
        ".faculty-name, h3.name, .card-title"
    ) if t(el)][:30]

    # Projects
    projects = [t(el) for el in soup.select(
        ".project-title, .research-title, h3.project, "
        ".project h3, .project h4, .research-project a"
    ) if t(el)][:20]

    # External links
    links = [
        {"text": t(a), "href": a["href"]}
        for a in soup.find_all("a", href=True)
        if a["href"].startswith("http") and t(a) and len(t(a)) > 3
    ][:25]

    return {
        "url": url,
        "category": category,
        "title": title,
        "description": description,
        "people": people,
        "projects": projects,
        "links": links,
    }


# General / fallback
def extract_general(url: str, soup: BeautifulSoup, category: str) -> dict:
    title = (
        first_text(soup, "h1", ".page-title", "title")
        or meta(soup, "og:title")
    )
    body = " ".join(
        t(p) for p in soup.select("article p, main p, .entry-content p, .page-content p")
        if len(t(p)) > 40
    )[:1000]

    headings = [t(h) for h in soup.select("h2, h3") if t(h)][:10]

    return {
        "url": url,
        "category": category,
        "title": title,
        "headings": headings,
        "body": body,
    }


# Router: pick extractor based on category
PERSON_CATEGORIES = {
    "faculty_profile", "staff_profile", "research_scholar",
    "ms_scholar", "iphd_scholar", "scheme_scholar",
}
LISTING_CATEGORIES = {
    "faculty_list", "staff_list", "scholar_list",
}
NEWS_CATEGORIES = {
    "news", "dhss_news", "cags_event",
}
LAB_CATEGORIES = {
    "lab_cse", "lab_ece", "lab_dsai", "lab_dhss", "lab_comet",
    "lab_cags", "lab_cognitive", "lab_wsl", "lab_sclab", "lab_rise",
    "lab_ic", "lab_naviiina", "lab_mpl", "lab_seal", "lab_sarl",
    "lab_gvcl", "lab_hides", "lab_generic",
}

# identifying which extractor to call per category
def extract(url: str, soup: BeautifulSoup, category: str) -> dict:
    if category in PERSON_CATEGORIES:
        return extract_person(url, soup, category)
    if category in LISTING_CATEGORIES:
        return extract_listing(url, soup, category)
    if category == "program":
        return extract_program(url, soup, category)
    if category in NEWS_CATEGORIES:
        return extract_news(url, soup, category)
    if category in LAB_CATEGORIES:
        return extract_lab(url, soup, category)
    return extract_general(url, soup, category)

# grouping outputs
BUCKET_MAP = {
    "faculty":          PERSON_CATEGORIES & {"faculty_profile"} | {"faculty_list"},
    "staff":            {"staff_profile", "staff_list"},
    "research_scholars":{"research_scholar", "ms_scholar", "iphd_scholar",
                         "scheme_scholar", "scholar_list"},
    "programs":         {"program"},
    "news":             NEWS_CATEGORIES,
    "labs_centers":     LAB_CATEGORIES,
    "external":         {"external"},
    "governance":       {"governance"},
    "placement":        {"placement"},
    "student_life":     {"student_life"},
    "general_pages":    {"general"},
}

# Reverse map: category → bucket
_CAT_TO_BUCKET: dict[str, str] = {}
for bucket, cats in BUCKET_MAP.items():
    for c in cats:
        _CAT_TO_BUCKET[c] = bucket

def bucket_for(category: str) -> str:
    return _CAT_TO_BUCKET.get(category, "general_pages")

# main scraping
def scrape_one(url: str) -> dict | None:
    """Fetch + extract one URL. Returns structured record or None on failure."""
    category = classify_url(url)

    final_url, soup = fetch(url)
    if soup is None:
        return None

    record = extract(final_url, soup, category)
    record["_scraped_at"] = datetime.now().isoformat(timespec="seconds")
    return record


def run():
    log.info("═" * 60)
    log.info("IIITB Scraper v2 — starting")
    log.info("═" * 60)

    # Load & clean
    raw_urls = load_urls(URLS_FILE)
    log.info(f"Loaded {len(raw_urls)} raw URLs from {URLS_FILE}")

    # Drop binary files and junk URLs
    clean_urls = [u for u in raw_urls if not has_bad_extension(u)]
    log.info(f"After extension filter: {len(clean_urls)} URLs")

    # Drop obviously malformed lines (contain spaces, etc.)
    clean_urls = [u for u in clean_urls if " " not in u and u.startswith("http")]
    log.info(f"After sanity filter: {len(clean_urls)} URLs")

    # Deduplicate mirror/ghost URLs
    deduped = deduplicate(clean_urls)
    log.info(f"After deduplication: {len(deduped)} canonical URLs")

    # Category breakdown preview
    cat_counts: dict[str, int] = defaultdict(int)
    for u in deduped:
        cat_counts[classify_url(u)] += 1
    log.info("Category distribution:")
    for cat, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        log.info(f"   {cat:<35} {n}")

    # Concurrent scrape
    buckets: dict[str, list[dict]] = defaultdict(list)
    done = 0

    log.info(f"\nStarting concurrent scrape with {MAX_WORKERS} workers …\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_to_url = {pool.submit(scrape_one, url): url for url in deduped}

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            done += 1
            try:
                record = future.result()
                if record:
                    bucket = bucket_for(record["category"])
                    buckets[bucket].append(record)
                    log.info(f"[{done:>4}/{len(deduped)}] ✓ {record['category']:<25} {url}")
                else:
                    log.warning(f"[{done:>4}/{len(deduped)}] ✗ SKIP  {url}")
            except Exception as e:
                log.error(f"[{done:>4}/{len(deduped)}] ERROR  {url}  —  {e}")

    # Save per-bucket JSON files
    master = {}
    for bucket, records in buckets.items():
        path = os.path.join(OUTPUT_DIR, f"{bucket}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=OUTPUT_INDENT, ensure_ascii=False)
        log.info(f"Saved {len(records):>4} records → {path}")
        master[bucket] = records

    # Master JSON
    master_path = os.path.join(OUTPUT_DIR, "master.json")
    master["_meta"] = {
        "scraped_at": datetime.now().isoformat(timespec="seconds"),
        "total_urls_input": len(raw_urls),
        "total_after_dedup": len(deduped),
        "total_scraped": sum(len(v) for v in buckets.values()),
        "buckets": {k: len(v) for k, v in buckets.items()},
    }
    with open(master_path, "w", encoding="utf-8") as f:
        json.dump(master, f, indent=OUTPUT_INDENT, ensure_ascii=False)
    log.info(f"\nMaster JSON saved → {master_path}")

    # Summary
    log.info("\n" + "═" * 60)
    log.info("SCRAPE COMPLETE")
    log.info("═" * 60)
    for bucket, records in sorted(buckets.items(), key=lambda x: -len(x[1])):
        log.info(f"   {bucket:<30} {len(records)} records")
    log.info(f"\n   Total: {sum(len(v) for v in buckets.values())} records")
    log.info(f"   Output directory: {os.path.abspath(OUTPUT_DIR)}/")


if __name__ == "__main__":
    run()