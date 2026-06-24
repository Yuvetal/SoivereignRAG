import time
import logging
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup

# Configure logging to display scraping activities
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class WebScraper:
    """
    A recursive web scraper that crawls links starting from a base URL,
    cleans HTML markup, rate-limits requests, and returns structured page contents.
    """
    def __init__(self, max_depth=2, max_pages=30, delay=0.5, timeout=10):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.delay = delay  # Politeness delay in seconds between network requests
        self.timeout = timeout  # Request timeout in seconds
        self.visited = set()
        self.results = []  # Holds list of dicts: {"url": str, "title": str, "text": str}

    def clean_text(self, soup):
        """
        Extracts structural text contents and strips out UI elements
        like headers, footers, sidebars, navigation bars, and ads.
        """
        # Decompose removes elements from the parsed BeautifulSoup tree entirely.
        # This keeps navigation boilerplate from cluttering our search database chunks.
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg"]):
            element.decompose()
        
        # Get page text with newline separators
        text = soup.get_text(separator="\n")
        
        # Standardize whitespace and remove empty lines
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        return "\n".join(chunk for chunk in chunks if chunk)

    def is_valid_url(self, url, base_domain):
        """
        Validates if the URL belongs to the same domain (netloc)
        and uses standard web protocols (HTTP/HTTPS).
        """
        parsed = urlparse(url)
        return parsed.netloc == base_domain and parsed.scheme in ["http", "https"]

    def scrape(self, start_url, status_callback=None):
        """
        Initiates recursion starting from start_url.
        Triggers status_callback with progress metadata dictionary.
        """
        self.visited.clear()
        self.results.clear()
        
        parsed_start = urlparse(start_url)
        base_domain = parsed_start.netloc
        if not base_domain:
            raise ValueError("Invalid starting URL. Please ensure it begins with http:// or https://")

        # Initialize the crawl queue: holds tuples of (url, current_depth)
        queue = [(start_url, 0)]
        
        # Set user agent headers to mimic a normal browser request
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        while queue and len(self.visited) < self.max_pages:
            url, depth = queue.pop(0)
            
            # Remove any fragment identifiers (e.g. #section-1) to avoid scraping duplicates
            url_no_fragment = url.split("#")[0]
            
            if url_no_fragment in self.visited:
                continue
            
            if depth > self.max_depth:
                continue

            self.visited.add(url_no_fragment)
            
            # Send current progress back to caller (e.g. the FastAPI background loop)
            if status_callback:
                status_callback({
                    "current_url": url_no_fragment,
                    "pages_scraped": len(self.visited),
                    "total_queued": len(queue),
                    "status": f"Scraping ({len(self.visited)}/{self.max_pages}): {url_no_fragment}"
                })

            try:
                # Add delay to avoid hammering the host server (rate limiting politeness)
                time.sleep(self.delay)
                
                logger.info(f"Scraping: {url_no_fragment} at depth {depth}")
                response = requests.get(url_no_fragment, headers=headers, timeout=self.timeout)
                
                # Gracefully skip failed status codes
                if response.status_code != 200:
                    logger.warning(f"Skipping {url_no_fragment}: HTTP {response.status_code}")
                    continue
                
                # Ensure we only parse HTML content (skip binaries like PDF, ZIP, PNG, etc.)
                content_type = response.headers.get("Content-Type", "")
                if "text/html" not in content_type:
                    logger.info(f"Skipping non-HTML resource: {url_no_fragment} (Content-Type: {content_type})")
                    continue

                soup = BeautifulSoup(response.text, "html.parser")
                
                title = soup.title.string.strip() if soup.title and soup.title.string else url_no_fragment
                cleaned_text = self.clean_text(soup)
                
                # Check for empty text, which often signals a client-side JavaScript rendered page (SPA)
                if not cleaned_text or len(cleaned_text.strip()) < 100:
                    cleaned_text = self._playwright_fallback(url_no_fragment)
                
                if cleaned_text and len(cleaned_text.strip()) > 50:
                    self.results.append({
                        "url": url_no_fragment,
                        "title": title,
                        "text": cleaned_text
                    })
                
                # Discover links for further traversal
                if depth < self.max_depth:
                    for link in soup.find_all("a", href=True):
                        href = link["href"]
                        full_url = urljoin(url_no_fragment, href)
                        
                        if self.is_valid_url(full_url, base_domain):
                            full_url_no_frag = full_url.split("#")[0]
                            # Check if already visited or already queued
                            if (full_url_no_frag not in self.visited and 
                                    full_url_no_frag not in [q[0] for q in queue]):
                                queue.append((full_url_no_frag, depth + 1))
                                
            except Exception as e:
                logger.error(f"Error occurred while crawling {url_no_fragment}: {e}")
                continue

        return self.results

    def _playwright_fallback(self, url):
        """
        Attempts to load JS-heavy single page apps using Playwright in a headless browser.
        Falls back gracefully if Playwright library or browser binary is not present.
        """
        try:
            from playwright.sync_api import sync_playwright
            logger.info(f"Invoking Playwright browser fallback for: {url}")
            with sync_playwright() as p:
                # Launch headless browser (no visual window)
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=self.timeout * 1000)
                
                # Wait 2 seconds for JS execution/API calls to complete
                page.wait_for_timeout(2000)
                
                content = page.content()
                soup = BeautifulSoup(content, "html.parser")
                cleaned_text = self.clean_text(soup)
                browser.close()
                return cleaned_text
        except Exception as e:
            logger.debug(f"Playwright fallback skipped: {e}")
            return ""
