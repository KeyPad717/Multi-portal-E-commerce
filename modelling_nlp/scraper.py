import requests
from bs4 import BeautifulSoup

def scrape_text_from_url(url: str) -> str:
    """
    Fetches the content of the URL, removes scripts and styles,
    and returns a clean string of text.
    """
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove script and style elements
    for script_or_style in soup(["script", "style", "header", "footer", "nav"]):
        script_or_style.decompose()

    # Get text and collapse whitespace
    text = soup.get_text(separator=' ')
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    clean_text = ' '.join(chunk for chunk in chunks if chunk)
    
    return clean_text

if __name__ == "__main__":
    test_url = "https://www.iiitb.ac.in/faculty"
    print(f"Scraping: {test_url}")
    text = scrape_text_from_url(test_url)
    print(f"Extracted {len(text)} characters.")
    print("Preview:", text[:500])
