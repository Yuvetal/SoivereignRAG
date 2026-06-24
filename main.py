import os
import logging
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from scraper import WebScraper
from rag_manager import RAGManager

# Setup basic logging config
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Initialize FastAPI application
app = FastAPI(
    title="RAG-Powered Website Chatbot",
    description="Backend API supporting recursive website crawling, local semantic vector search, and grounded AI chat answers."
)

# Enable CORS (Cross-Origin Resource Sharing) to allow testing from different ports/domains if necessary
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScrapingStateTracker:
    """
    A simple in-memory state store to track the progress of the scraper background task.
    This is read by the frontend polling route `/api/scrape/status`.
    """
    def __init__(self):
        self.is_scraping = False
        self.pages_scraped = 0
        self.status = "Idle"
        self.logs = []
        self.error = None

# Instantiate state tracker and RAG manager
state = ScrapingStateTracker()
rag_manager = RAGManager()

# Input Validation Schemas
class ScrapeRequest(BaseModel):
    url: str
    max_depth: int = 2
    max_pages: int = 30

class ChatRequest(BaseModel):
    question: str


def run_scraping_workflow(url: str, max_depth: int, max_pages: int):
    """
    Executes the long-running scraping, chunking, and embedding workflow.
    Designed to run inside a FastAPI Background Task so it doesn't block the HTTP connection.
    """
    global state
    state.is_scraping = True
    state.pages_scraped = 0
    state.status = "Starting crawler..."
    state.logs = []
    state.error = None
    
    try:
        scraper = WebScraper(max_depth=max_depth, max_pages=max_pages, delay=0.5)
        
        # Callback function triggered by the crawler after each page scrape
        def on_page_scraped(progress_info):
            state.pages_scraped = progress_info["pages_scraped"]
            state.status = progress_info["status"]
            state.logs.append(progress_info["status"])
            logger.info(progress_info["status"])
            
        pages = scraper.scrape(url, status_callback=on_page_scraped)
        
        if not pages:
            state.status = "Failed: No readable HTML content found."
            state.logs.append("No readable HTML pages were found.")
            state.is_scraping = False
            return
            
        state.status = "Splitting text into chunks..."
        state.logs.append("Beginning token-based text chunking...")
        chunks = rag_manager.chunk_text(pages)
        
        state.status = "Indexing vectors into local ChromaDB..."
        state.logs.append("Embedding text chunks and storing in database...")
        rag_manager.index_documents(chunks)
        
        state.status = "Completed"
        state.logs.append("Website content successfully indexed and ready for chat!")
        logger.info("Indexing workflow completed successfully.")
        
    except Exception as e:
        logger.error(f"Error in scraping workflow: {e}")
        state.error = str(e)
        state.status = f"Failed: {e}"
        state.logs.append(f"Failed: {e}")
    finally:
        state.is_scraping = False


# API Routes

@app.post("/api/scrape")
def trigger_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Triggers a background scrape job for a target URL.
    Returns immediately after queueing the task.
    """
    global state
    if state.is_scraping:
        raise HTTPException(
            status_code=400, 
            detail="A scraping workflow is already in progress. Please wait for it to complete."
        )
    
    # Delegate the heavy work to a background thread managed by FastAPI
    background_tasks.add_task(
        run_scraping_workflow, 
        req.url, 
        req.max_depth, 
        req.max_pages
    )
    return {"message": "Scraping and indexing task successfully started."}

@app.get("/api/scrape/status")
def get_scrape_status():
    """
    Poll route for the frontend to retrieve real-time status and crawl log lines.
    """
    return {
        "is_scraping": state.is_scraping,
        "pages_scraped": state.pages_scraped,
        "status": state.status,
        "logs": state.logs,
        "error": state.error
    }

@app.post("/api/chat")
def submit_chat_query(req: ChatRequest):
    """
    RAG endpoint. Converts user question to vector, fetches context from ChromaDB,
    prompts the LLM, and returns citation links.
    """
    try:
        result = rag_manager.retrieve_and_generate(req.question)
        return result
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/clear")
def clear_vector_store():
    """
    Wipes the current local ChromaDB collection clean.
    """
    try:
        rag_manager.clear_database()
        return {"message": "Persistent vector database cleared successfully."}
    except Exception as e:
        logger.error(f"Error clearing vector store: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Mount static directory to serve HTML/CSS/JS frontend
# By default, FastAPI looks for files in the "./static" directory and serves them at the root "/"
# html=True enables serving "index.html" automatically when visiting the homepage.
if os.path.exists("./static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
else:
    logger.warning("Directory './static' not found. Frontend files will not be served.")
