"""
scraper.py -- Fetch and parse the IIITB faculty profile page.
Extracts structured JSON with typed sections for high-quality
semantic enrichment downstream.
"""

import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def scrape(url: str) -> dict:
    """
    Fetch the faculty page and extract all available data
    into a clean, typed dictionary.
    """
    print(f"  [scraper] Fetching: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  [scraper] ERROR fetching page: {e}")
        raise

    soup = BeautifulSoup(r.text, "lxml")

    # -- Remove script/style noise --------------------------
    for tag in soup(["script", "style", "nav",
                     "footer", "header", "noscript"]):
        tag.decompose()

    data = {
        "url": url,
        "name":         _get_name(soup),
        "title":        _get_title(soup),
        "email":        _get_email(soup),
        "phone":        _get_text(soup, [
                            ".phone", ".contact-phone",
                            "[itemprop='telephone']"]),
        "department":   _get_text(soup, [
                            ".department", ".dept",
                            "[itemprop='department']",
                            ".faculty-department"]),
        "research_areas": _get_list(soup, [
                            ".research-areas li",
                            ".research-interest li",
                            ".interests li",
                            ".research li",
                            "#research-areas li"]),
        "education":    _get_list(soup, [
                            ".education li",
                            ".qualification li",
                            ".academic-qualifications li",
                            "#education li"]),
        "publications": _get_publications(soup),
        "projects":     _get_list(soup, [
                            ".projects li",
                            ".project-list li",
                            ".funded-projects li",
                            "#projects li",
                            ".research-projects li"]),
        "awards":       _get_list(soup, [
                            ".awards li",
                            ".honors li",
                            ".achievements li",
                            "#awards li",
                            ".recognition li"]),
        "courses":      _get_list(soup, [
                            ".courses li",
                            ".teaching li",
                            ".courses-taught li",
                            "#courses li"]),
        "students":     _get_list(soup, [
                            ".students li",
                            ".phd-students li",
                            ".guided-students li",
                            ".research-scholars li",
                            "#students li"]),
        "bio":          _get_bio(soup),
        "professional_activities": _get_list(soup, [
                            ".activities li",
                            ".professional li",
                            ".service li",
                            "#activities li"]),
        "raw_sections": _get_raw_sections(soup),
    }

    # Remove empty fields
    cleaned = {k: v for k, v in data.items()
               if v and v != [] and v != ""}

    total_items = sum(
        len(v) if isinstance(v, list) else 1
        for v in cleaned.values()
    )
    print(f"  [scraper] ✓ Extracted {len(cleaned)} fields, "
          f"~{total_items} total items")
    return cleaned


# -- Private helpers ----------------------------------------

def _get_name(soup) -> str:
    selectors = [
        "h1.faculty-name", "h1.profile-name", "h1",
        ".faculty-name", ".profile-name",
        "[itemprop='name']", ".name"
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            t = el.get_text(" ", strip=True)
            if t and len(t) < 100:
                return t
    return ""


def _get_title(soup) -> str:
    # First: try precise CSS selectors.
    # NOTE: ".title" is intentionally excluded -- on IIITB faculty pages
    # it matches publication title elements, not the person's designation.
    selectors = [
        ".designation", ".faculty-title",
        ".profile-designation", "[itemprop='jobTitle']",
        ".position"
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            t = el.get_text(" ", strip=True)
            if t and len(t) < 150:
                return t

    # Second: scan headings for faculty designation patterns only.
    # This avoids accidentally picking up publication titles that
    # also appear in <h2> tags on faculty profile pages.
    _ROLE_PATTERN = re.compile(
        r'\b(Professor|Associate Professor|Assistant Professor|'
        r'Dean|Director|Head of|Lecturer|Adjunct|Visiting|'
        r'Emeritus|Principal|Scientist|Research Fellow|'
        r'Faculty|Instructor|Chair)\b',
        re.IGNORECASE
    )
    for tag in soup.find_all(["h2", "h3", "h4"]):
        t = tag.get_text(" ", strip=True)
        if t and len(t) < 120 and _ROLE_PATTERN.search(t):
            return t

    return ""


def _get_email(soup) -> str:
    # Try mailto links first
    for a in soup.select('a[href^="mailto:"]'):
        href = a.get("href", "")
        email = href.replace("mailto:", "").strip()
        if "@" in email:
            return email
    # Try text pattern
    text = soup.get_text()
    match = re.search(
        r'[\w\.-]+@[\w\.-]+\.\w{2,4}', text)
    if match:
        return match.group(0)
    return ""


def _get_text(soup, selectors: list) -> str:
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            t = el.get_text(" ", strip=True)
            if t:
                return t
    return ""


def _get_list(soup, selectors: list) -> list:
    for sel in selectors:
        items = soup.select(sel)
        if items:
            result = [
                i.get_text(" ", strip=True)
                for i in items
                if i.get_text(strip=True)
            ]
            if result:
                return result
    return []


def _get_publications(soup) -> list:
    selectors = [
        ".publication li", ".pub-list li",
        ".publications li", "ol.pubs li",
        "#publications li", ".journal-papers li",
        ".conference-papers li", ".papers li"
    ]
    for sel in selectors:
        items = soup.select(sel)
        if items:
            return [
                i.get_text(" ", strip=True)
                for i in items
                if len(i.get_text(strip=True)) > 20
            ]

    # Fallback: look for numbered/bulleted text blocks
    # near "publication" heading
    pubs = []
    for heading in soup.find_all(
            ["h2", "h3", "h4"],
            string=re.compile(r"publication|paper|journal",
                              re.I)):
        sibling = heading.find_next_sibling()
        while sibling and sibling.name not in ["h2", "h3"]:
            if sibling.name in ["ol", "ul"]:
                pubs += [
                    li.get_text(" ", strip=True)
                    for li in sibling.find_all("li")
                ]
            sibling = sibling.find_next_sibling()
        if pubs:
            return pubs
    return []


def _get_bio(soup) -> str:
    selectors = [
        ".bio", ".about", ".faculty-bio",
        ".profile-bio", ".summary",
        "[itemprop='description']"
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            t = el.get_text(" ", strip=True)
            if len(t) > 50:
                return t

    # Fallback: first long paragraph
    for p in soup.find_all("p"):
        t = p.get_text(" ", strip=True)
        if len(t) > 100:
            return t
    return ""


def _get_raw_sections(soup) -> list:
    """
    Capture all meaningful text paragraphs as a safety net.
    The LLM enrichment step can extract additional entities
    from these even if CSS selectors missed them.
    """
    sections = []
    # Grab heading + following content pairs
    for heading in soup.find_all(["h2", "h3", "h4"]):
        h_text = heading.get_text(strip=True)
        if not h_text or len(h_text) > 80:
            continue
        content = []
        sibling = heading.find_next_sibling()
        count = 0
        while sibling and count < 5:
            if sibling.name in ["h2", "h3", "h4"]:
                break
            text = sibling.get_text(" ", strip=True)
            if text and len(text) > 15:
                content.append(text)
            sibling = sibling.find_next_sibling()
            count += 1
        if content:
            sections.append({
                "heading": h_text,
                "content": " | ".join(content[:3])
            })
    return sections[:20]  # cap to 20 sections
