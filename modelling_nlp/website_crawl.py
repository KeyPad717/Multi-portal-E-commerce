import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

BASE_URLS = [
    "https://cse.iiitb.ac.in/",
    "https://dhss.iiitb.ac.in/",
    "https://dsai.iiitb.ac.in/",
    "https://ece.iiitb.ac.in/",
    "https://www.iiitb.ac.in/centre-for-applied-sciences",
    "https://www.iiitb.ac.in/btech",
    "https://www.iiitb.ac.in/integrated-mtech",
    "https://www.iiitb.ac.in/mtech",
    "https://www.iiitb.ac.in/academics/research-programmes/phd",
    "https://www.iiitb.ac.in/academics/masters-programmes/pg-diploma-in-digital-product-design-and-management",
    "https://www.iiitb.ac.in/academics/masters-programmes/msc-digital-society",
    "https://www.iiitb.ac.in/fellowships",
    "https://www.iiitb.ac.in/courses/btech-integrated-mtech",
    "https://www.iiitb.ac.in/master-of-technology-cse-ece",
    "https://www.iiitb.ac.in/courses/master-of-science-by-researchdoctor-of-philosophy",
    "https://www.iiitb.ac.in/courses/post-graduate-diploma-2",
    "https://www.iiitb.ac.in/computer-science",
    "https://www.iiitb.ac.in/data-sciences",
    "https://www.iiitb.ac.in/software-engineering",
    "https://www.iiitb.ac.in/mathematics-and-basic-sciences",
    "https://www.iiitb.ac.in/networking-communication-and-signal-processing",
    "https://www.iiitb.ac.in/vlsi-systems",
    "https://www.iiitb.ac.in/digital-society",
    "https://www.iiitb.ac.in/exchange-program",
    "https://www.iiitb.ac.in/verification-process",
    "https://www.iiitb.ac.in/curriculum",
    "https://www.iiitb.ac.in/programme-outcomes",
    "https://www.iiitb.ac.in/academic-calendar-3",
    "https://www.iiitb.ac.in/online-education",
    "https://www.iiitb.ac.in/academics/continuing-professional-education/long-term-programmes-1114-months-2",
    "https://www.iiitb.ac.in/academics/continuing-professional-education/short-term-programme-5-8-months",
    "https://www.iiitb.ac.in/ehealth-research-centre-ehrc",
    "https://www.iiitb.ac.in/machine-intelligence-robotics-coe-minro",
    "https://www.iiitb.ac.in/centre-for-it-public-policy-citapp",
    "https://cognitive.iiitb.ac.in/",
    "https://cags.iiitb.ac.in/",
    "https://comet.iiitb.ac.in/",
    "https://ic.iiitb.ac.in/",
    "https://www.mosip.io/",
    "https://coss.org.in/",
    "https://cdpi.dev/",
    "https://www.iiitb.ac.in/sarl/sarl.html",
    "https://www.iiitb.ac.in/labs/scads-lab/scads-lab",
    "https://www.iiitb.ac.in/gvcl/",
    "https://wsl.iiitb.ac.in/",
    "http://mpl.iiitb.ac.in/",
    "https://sealiiitb.github.io/",
    "https://www.iiitb.ac.in/hides/hides.html",
    "https://www.iiitb.ac.in/ncl/",
    "https://sclab.iiitb.ac.in/",
    "https://www.iiitb.ac.in/indian-knowledge-system-iks-lab",
    "https://www.iiitb.ac.in/smart-city-lab",
    "https://www.iiitb.ac.in/labs/ascend-studio/ascend-studio",
    "https://www.iiitb.ac.in/labs/radar-sensing-lab/radar-sensing-lab",
    "https://www.iiitb.ac.in/cssmp/",
    "https://www.iiitb.ac.in/labs/advanced-wireless-communications-lab/about-us-2",
    "https://www.iiitb.ac.in/labs/speech-lab/speech-lab",
    "https://sites.google.com/view/cdwl/home",
    "https://www.iiitb.ac.in/samvaad",
    "https://rise.iiitb.ac.in/",
    "https://avalokana.karnataka.gov.in/DataLake/DataLake",
    "https://www.iiitb.ac.in/summer-internship",
    "https://www.iiitb.ac.in/publications",
    "https://www.iiitb.ac.in/policy",
    "https://www.iiitb.ac.in/placement-statistics",
    "https://www.iiitb.ac.in/recruiting-companies",
    "https://www.iiitb.ac.in/to-recruit-degree-programmes",
    "https://www.iiitb.ac.in/to-recruit-on-campus-pgd-programmes",
    "https://www.iiitb.ac.in/placement-team",
    "https://www.iiitb.ac.in/committees-clubs",
    "https://www.iiitb.ac.in/events-and-festivals",
    "https://www.iiitb.ac.in/cafeteria",
    "https://www.iiitb.ac.in/library-collection",
    "https://www.iiitb.ac.in/faculty-articles",
    "https://www.iiitb.ac.in/iiitb-in-the-press", 
    "https://www.iiitb.ac.in/annual-reports",
    "https://www.iiitb.ac.in/media-press-releases",
    "https://www.iiitb.ac.in/media-kit",
    "https://www.iiitb.ac.in/faculty",
    "https://www.iiitb.ac.in/iiitb-innovation-center",
    "https://www.iiitb.ac.in/iiitb-comet-foundation",
    "https://www.iiitb.ac.in/iiitb-mosip",
    "https://www.iiitb.ac.in/iiitb-ehrc",
    "https://www.iiitb.ac.in/iiitb-minro",
    "https://www.iiitb.ac.in/ms-by-research-scholars",
    "https://www.iiitb.ac.in/research-scholars",
    "https://www.iiitb.ac.in/integrated-phd-scholars",
    "https://www.iiitb.ac.in/alumni",
    "https://www.iiitb.ac.in/code-of-conduct",
    "https://www.iiitb.ac.in/explore-iiitb",
    "https://www.iiitb.ac.in/governing-body",
    "https://www.iiitb.ac.in/administration",
    "https://www.iiitb.ac.in/industry-advisory-board",
    "https://www.iiitb.ac.in/institute-industry-interaction-cell",
    "https://www.iiitb.ac.in/partnership",
    "https://www.iiitb.ac.in/aicte-mandatory-disclosure",
    "https://www.iiitb.ac.in/holiday-list",
    "https://www.iiitb.ac.in/nirf",
    "https://www.iiitb.ac.in/iqac"
]

visited = set()
queue = list(BASE_URLS)


# remove extra "/" for consistency
def normalize(url):
    parsed = urlparse(url)
    return parsed.scheme + "://" + parsed.netloc + parsed.path.rstrip("/")

# restricting only internal access(domain wise)
def is_internal(url):
    domains = [urlparse(u).netloc for u in BASE_URLS]
    return urlparse(url).netloc in domains

# check for website validity
def is_valid(resp):
    if resp.status_code != 200:
        return False

    text = resp.text.lower()
    if "404" in text or "page not found" in text:
        return False

    return True


def is_inside_allowed(url):
    return any(url.startswith(base) for base in BASE_URLS)


# crawling through bfs
while queue:
    current_url = normalize(queue.pop(0))

    if current_url in visited:
        continue

    visited.add(current_url)

    print(f"Visiting: {current_url}", flush=True)

    try:
        resp = requests.get(current_url, timeout=5)
    except:
        continue

    if not is_valid(resp):
        continue

    soup = BeautifulSoup(resp.text, "lxml")

    for tag in soup.find_all(["header", "footer", "nav"]):
        tag.decompose()

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()

        if href.startswith("javascript") or href.startswith("#"):
            continue

        full_url = normalize(urljoin(current_url, href))

        if not is_internal(full_url):
            continue

        if not is_inside_allowed(full_url):
            continue

        if any(x in full_url for x in [
            "nirf", "iqac", "contact", "privacy",
            "feedback", "sitemap", "careers"
        ]):
            continue

        if "?" in full_url:
            continue

        if full_url not in visited:
            queue.append(full_url)


for url in sorted(visited):
    print(url)


# ONLY ADDITION
with open("unique_urls.txt", "w", encoding="utf-8") as f:
    for url in sorted(visited):
        f.write(url + "\n")