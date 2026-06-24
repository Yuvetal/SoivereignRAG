import os
import logging
from dotenv import load_dotenv

# LangChain library imports
# LangChain is a framework that helps us orchestrate components for AI applications.
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

# Load environment variables from a .env file if it exists
load_dotenv()

logger = logging.getLogger(__name__)

class RAGManager:
    """
    Manages the RAG (Retrieval-Augmented Generation) pipeline:
    1. Chunking: Splitting text into pieces.
    2. Embeddings: Converting text pieces into numerical vectors (coordinates).
    3. Storage: Saving vectors to a local persistent database (ChromaDB).
    4. Retrieval: Querying the database to find pieces matching the user's question.
    5. Generation: Prompting the LLM (Gemini 1.5 Flash / GPT-4o-mini) to answer based on retrieved context.
    """
    def __init__(self, db_dir="./chroma_db"):
        self.db_dir = db_dir
        self.openai_key = os.getenv("OPENAI_API_KEY")
        # Support both standard LangChain name GOOGLE_API_KEY and general GEMINI_API_KEY name
        self.google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        
        # Initialize Embeddings
        self.embeddings = self._init_embeddings()
        
        # Initialize Vector Database
        # ChromaDB runs locally, storing vectors in the self.db_dir folder.
        # This behaves like a local SQLite database but optimized for spatial vectors.
        self.vector_store = Chroma(
            persist_directory=self.db_dir,
            embedding_function=self.embeddings
        )
        
        # Initialize LLM
        self.llm = self._init_llm()

    def _init_embeddings(self):
        """
        Initializes the embedding model.
        
        AI CONCEPT: EMBEDDINGS
        ----------------------
        An 'embedding' converts text into a list of numbers (a vector).
        This vector acts like a set of GPS coordinates in a high-dimensional 'semantic' space.
        Words/sentences with similar meaning end up physically close to each other.
        
        Tradeoffs:
        - Gemini (text-embedding-004): High-quality, fast, API-based. Needs a Google/Gemini key.
        - OpenAI (text-embedding-3-small): High-quality, fast, API-based. Needs an OpenAI key.
        - sentence-transformers (all-MiniLM-L6-v2): Runs locally on CPU/GPU, completely free, private, 
          but slightly lower accuracy and requires local memory to load the model file.
        """
        if self.google_key:
            logger.info("Initializing Google Gemini Embeddings (models/gemini-embedding-2)...")
            return GoogleGenerativeAIEmbeddings(
                model="models/gemini-embedding-2",
                google_api_key=self.google_key
            )
        elif self.openai_key:
            logger.info("Initializing OpenAI Embeddings (text-embedding-3-small)...")
            return OpenAIEmbeddings(
                model="text-embedding-3-small", 
                openai_api_key=self.openai_key
            )
        else:
            logger.warning("No API keys found. Falling back to local Sentence-Transformers model...")
            # HuggingFaceEmbeddings will automatically download the model from the internet
            # on the first run and store it locally.
            return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    def _init_llm(self):
        """
        Initializes the Large Language Model client.
        If no API key is present, we log a warning and return None (we will mock the generator).
        """
        if self.google_key:
            logger.info("Initializing Google Gemini LLM (gemini-2.5-flash)...")
            return ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                temperature=0.0,  # Makes responses deterministic and focused
                google_api_key=self.google_key
            )
        elif self.openai_key:
            logger.info("Initializing OpenAI LLM (gpt-4o-mini)...")
            return ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.0,
                openai_api_key=self.openai_key
            )
        else:
            logger.warning("No API keys found. LLM responses will be simulated.")
            return None

    def chunk_text(self, pages):
        """
        Splits scraped pages into small overlapping pieces.
        pages: List of dicts: {"url": str, "title": str, "text": str}
        
        AI CONCEPT: CHUNKING & OVERLAP
        ------------------------------
        We cannot feed an entire 30-page website into an LLM because it:
        1. Exceeds the input limits (gas/gas limits equivalent for LLMs: Context Tokens).
        2. Costs more money (we pay per character/token processed).
        3. dilutes the focus, causing the LLM to skip relevant details.
        
        So, we split the text into chunks of ~500 tokens.
        - Why 500? It's large enough to contain a complete thought, but small enough to search efficiently.
        - Why Overlap (50 tokens)? If we cut text at exactly 500 tokens, we might split an important sentence
          right down the middle. Overlap ensures that a sentence cut at the end of chunk A is fully present
          at the start of chunk B, keeping the semantic meaning intact.
        """
        # We use a token-based character splitter using OpenAI's 'tiktoken' encoder
        # to ensure that our chunk sizes correspond accurately to actual token counts.
        text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            model_name="gpt-4o-mini",
            chunk_size=500,
            chunk_overlap=50
        )
        
        documents = []
        for page in pages:
            url = page["url"]
            title = page["title"]
            text = page["text"]
            
            # Split the text of this specific page
            chunks = text_splitter.split_text(text)
            
            for chunk in chunks:
                # Wrap each chunk in a LangChain Document structure.
                # Crucially, we store the URL and title in 'metadata' so we can cite them later.
                doc = Document(
                    page_content=chunk,
                    metadata={"source": url, "title": title}
                )
                documents.append(doc)
                
        logger.info(f"Split {len(pages)} pages into {len(documents)} text chunks.")
        return documents

    def index_documents(self, documents):
        """
        AI CONCEPT: INDEXING / VECTOR STORAGE
        -------------------------------------
        Once we have text chunks, we convert them into vectors (embeddings) and store them in ChromaDB.
        Chroma DB indexes these vectors.
        - This is incremental: calling `add_documents` appends to the database on disk.
        - If we restart the application, the database reads from the local `./chroma_db` folder
          and retains everything previously scraped.
        """
        if not documents:
            logger.warning("No documents provided to index.")
            return
        
        logger.info(f"Saving {len(documents)} chunks to local vector database...")
        self.vector_store.add_documents(documents)
        logger.info("Indexing completed successfully.")

    def retrieve_and_generate(self, question, k=5):
        """
        Performs the RAG search and returns an answer + citations.
        
        AI CONCEPT: SIMILARITY SEARCH & GROUNDED PROMPTING
        -------------------------------------------------
        1. Retrieve:
           - We convert the user's question into a vector (embedding).
           - We search the vector store to find the 'k' closest chunks (using Cosine Similarity / Distance).
           - These closest chunks are the context documents.
        2. Generate (Grounded LLM prompt):
           - We format a prompt: "Use only this context to answer the question: [context]. Question: [question]."
           - This instructs the model to only use the provided facts, preventing it from making up details 
             (which is called 'hallucination').
        """
        # Step 1: Retrieval
        # similarity_search returns LangChain Document objects containing page_content and metadata
        retrieved_docs = self.vector_store.similarity_search(question, k=k)
        
        context_parts = []
        sources = set()
        
        for idx, doc in enumerate(retrieved_docs, 1):
            source_url = doc.metadata.get("source", "Unknown Source")
            sources.add(source_url)
            # Format the text with its source so the LLM knows which context came from where
            context_parts.append(f"--- Context {idx} (Source: {source_url}) ---\n{doc.page_content}")
            
        context_str = "\n\n".join(context_parts)
        
        # Step 2: Prompt formulation
        system_prompt = (
            "You are a helpful, fact-based website assistant chatbot.\n"
            "Answer the user's question based ONLY on the provided chunks of context text below.\n"
            "If the answer cannot be found in the context chunks, say exactly: "
            "'I don't know based on the available content.' and do not attempt to make up an answer.\n"
            "Cite which source URL(s) you used in your answer, referring to them by their URL names.\n\n"
            f"Here is the context:\n{context_str}"
        )
        
        user_message = f"Question: {question}"
        
        # Step 3: Call LLM or Simulate
        if self.llm:
            try:
                # Format messages for the Chat model
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ]
                response = self.llm.invoke(messages)
                answer = response.content
            except Exception as e:
                logger.error(f"Error calling LLM provider: {e}")
                answer = f"Error generating answer from LLM: {e}"
        else:
            # Simulation fallback if no key is configured
            answer = (
                "[SIMULATION ANSWER - NO API KEY CONFIGURED]\n"
                "I retrieved the following pages that might contain the answer:\n"
                + "\n".join(f"- {s}" for s in list(sources)[:3]) + "\n\n"
                "To get a real grounded answer, please add your GEMINI_API_KEY (or OPENAI_API_KEY) in the `.env` file and restart the server."
            )
            
        return {
            "answer": answer,
            "sources": list(sources)
        }

    def clear_database(self):
        """
        Clears the local vector store by deleting the contents of ChromaDB.
        """
        logger.info("Clearing vector database...")
        self.vector_store.delete_collection()
        self.vector_store = Chroma(
            persist_directory=self.db_dir,
            embedding_function=self.embeddings
        )
        logger.info("Vector database cleared.")
