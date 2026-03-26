import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
from urllib.parse import urljoin
import logging

# ✅ Selenium imports (fixed)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ================= LOGGING =================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://www.iiitb.ac.in"
HEADERS = {'User-Agent': 'Mozilla/5.0'}


class IIITBangaloreScraper:

    def __init__(self):
        self.data = {
            "metadata": {
                "institution": "IIIT Bangalore",
                "scraped_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            "institution_info": {},
            "programs": [],
            "faculty": [],
            "research": [],
            "facilities": []
        }

    # ================= FETCH (BS4) =================
    def fetch_page(self, url):
        try:
            logger.info(f"Fetching: {url}")
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                logger.warning(f"Failed: {url}")
                return None
            time.sleep(1)
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            logger.error(f"Error: {e}")
            return None

    # ================= INSTITUTION =================
    def scrape_institution(self):
        soup = self.fetch_page(BASE_URL)
        if not soup:
            return

        title = soup.find("title")
        if title:
            self.data["institution_info"]["name"] = title.text.strip()

        meta = soup.find("meta", {"name": "description"})
        if meta:
            self.data["institution_info"]["description"] = meta.get("content")

    # ================= PROGRAMS =================
    def scrape_programs(self):
        soup = self.fetch_page(f"{BASE_URL}/academics")
        if not soup:
            return

        programs = []
        links = soup.find_all("a", href=True)

        for link in links:
            text = link.text.strip().lower()

            if any(x in text for x in ["b.tech", "m.tech", "phd", "msc"]):
                programs.append({"name": link.text.strip()})

        self.data["programs"] = list({p["name"]: p for p in programs}.values())

    # ================= FACULTY (SELENIUM) =================
    def scrape_faculty(self):
        logger.info("Scraping Faculty (FINAL CORRECT VERSION)")

        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service)

            driver.get("https://www.iiitb.ac.in/faculty")
            time.sleep(5)

            faculty = []

            # ✅ Extract all headings (THIS IS KEY FIX)
            elements = driver.find_elements(By.XPATH, "//h1 | //h2 | //h3")

            for e in elements:
                name = e.text.strip()

                # ✅ Filter only real names
                if (
                    len(name) > 5 and
                    len(name) < 50 and
                    not any(x in name.lower() for x in ["faculty", "home", "people"])
                ):
                    faculty.append({"name": name})

            driver.quit()

            # remove duplicates
            self.data["faculty"] = list({f["name"]: f for f in faculty}.values())

            logger.info(f"Faculty extracted: {len(self.data['faculty'])}")

        except Exception as e:
            logger.error(f"Selenium error: {e}")
    # ================= RESEARCH =================
    def scrape_research(self):
        soup = self.fetch_page(f"{BASE_URL}/research")
        if not soup:
            logger.warning("[FAILED] Could not fetch programs page")
            return

        research = []
        links = soup.find_all("a", href=True)

        for link in links:
            text = link.text.strip()

            if any(x in text.lower() for x in ["lab", "center"]):
                if len(text) > 5:
                    research.append({"name": text})

        self.data["research"] = list({r["name"]: r for r in research}.values())

    # ================= FACILITIES =================
    def scrape_facilities(self):
        soup = self.fetch_page(BASE_URL)
        if not soup:
            return

        facilities = []
        links = soup.find_all("a")

        for link in links:
            text = link.text.strip()

            if not text:
                continue

            if any(x in text.lower() for x in ["lab", "library", "hostel"]):
                if len(text) > 5:
                    facilities.append({"name": text})

        self.data["facilities"] = list({f["name"]: f for f in facilities}.values())

    # ================= RUN =================
    def run(self):
        logger.info("=== START SCRAPING ===")

        self.scrape_institution()
        self.scrape_programs()
        self.scrape_faculty()   # ✅ Selenium used here
        self.scrape_research()
        self.scrape_facilities()

        logger.info("=== DONE ===")

    # ================= SAVE =================
    def save(self):
        with open("iiitb_final.json", "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

        logger.info("Saved → iiitb_final.json")


# ================= MAIN =================
if __name__ == "__main__":
    scraper = IIITBangaloreScraper()
    scraper.run()
    scraper.save()