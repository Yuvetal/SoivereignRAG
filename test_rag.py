from scraper import WebScraper
from rag_manager import RAGManager

def test_rag_flow():
    print("=== Testing RAG Data Ingestion & Retrieval Pipeline ===")
    
    # 1. Scrape quotes sandbox
    test_url = "https://example.com/"
    print(f"Scraping sandbox: {test_url}...")
    scraper = WebScraper(max_depth=0, max_pages=1, delay=0.1)
    pages = scraper.scrape(test_url)
    print(f"Scraped {len(pages)} page(s).")
    
    if not pages:
        print("Failed to scrape any pages. Exiting test.")
        return

    # 2. Initialize RAG Manager
    print("\nInitializing RAG Manager (database folder: ./test_chroma_db)...")
    # We will save to a test database directory to keep it separate
    rag = RAGManager(db_dir="./test_chroma_db")
    
    # Clean previous database run
    rag.clear_database()
    
    # 3. Chunk text
    print("\nChunking scraped text...")
    chunks = rag.chunk_text(pages)
    print(f"First chunk snippet:\n{chunks[0].page_content[:200]}...")
    print(f"First chunk metadata: {chunks[0].metadata}")
    
    # 4. Index documents (Convert to vectors & save to ChromaDB)
    print("\nIndexing chunks into persistent local vector DB...")
    rag.index_documents(chunks)
    
    # 5. Retrieve & Query
    test_question = "What is this domain used for?"
    print(f"\nQuerying RAG system with question: '{test_question}'...")
    result = rag.retrieve_and_generate(test_question, k=3)
    
    print("\n=== RAG Response ===")
    print(f"Answer:\n{result['answer']}")
    print(f"\nCited Sources:\n{result['sources']}")
    
    print("\nTest completed successfully!")

if __name__ == "__main__":
    test_rag_flow()
