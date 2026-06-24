from scraper import WebScraper

def test_crawling():
    print("=== Testing Recursive Web Scraper ===")
    
    # We will scrape a sandbox site designed for web scraping testing.
    test_url = "https://quotes.toscrape.com/"
    
    # Initialize the scraper with a depth of 1 (seeds + its links) and max 5 pages for testing.
    scraper = WebScraper(max_depth=1, max_pages=5, delay=0.5)
    
    def on_progress(progress_info):
        print(f"[PROGRESS] {progress_info['status']}")

    print(f"Starting crawler on: {test_url}...")
    pages = scraper.scrape(test_url, status_callback=on_progress)
    
    print("\n=== Scraping Completed ===")
    print(f"Total pages successfully scraped: {len(pages)}")
    
    for idx, page in enumerate(pages, 1):
        print(f"\n--- Page {idx} ---")
        print(f"URL: {page['url']}")
        print(f"Title: {page['title']}")
        # Show first 150 characters of the text snippet
        text_snippet = page['text'][:150].replace('\n', ' ')
        print(f"Content Snippet: {text_snippet}...")
        print("-" * 20)

if __name__ == "__main__":
    test_crawling()
