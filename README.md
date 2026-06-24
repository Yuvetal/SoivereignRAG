# Sovereign RAG: Website Chatbot 🔮

Sovereign RAG is a Retrieval-Augmented Generation (RAG) powered website chatbot. You supply a starting URL, and the system recursively crawls the site's pages, splits the text into clean semantic chunks, embeds them into a multi-dimensional vector space, and indexes them into a local persistent database. 

Once indexed, you can chat with the site's content. The chatbot answers questions based **only** on the retrieved database blocks and cites the exact source links to ground its assertions.

---

## 🛠️ Tech Stack & Setup

### Prerequisites
- **Python 3.11+** (Automatically tested and configured)
- **OpenAI API Key** (Optional, falls back to free local execution)

### 1. Installation
Clone the repository and navigate to the project directory:
```bash
# Install dependencies from requirements.txt
python -m pip install -r requirements.txt
```

### 2. Configuration (`.env`)
Copy the configuration template:
```bash
copy .env.example .env
```
Open the `.env` file and input your OpenAI API Key:
```env
OPENAI_API_KEY=sk-...
```
*Note: If you leave `OPENAI_API_KEY` blank, the application will automatically fall back to running the embeddings model locally (`all-MiniLM-L6-v2`) and will simulate the final chat generation.*

---

## 🚀 Running the App

To run the chatbot server:
```bash
python -m uvicorn main:app --port 8000 --reload
```
Once started, open your web browser and navigate to:
👉 **[http://localhost:8000](http://localhost:8000)**

---

## 📖 AI Concepts & Explanations (For Developers New to AI)

If you are coming from a blockchain/general software development background, here is how the core AI steps in this codebase work:

### 1. Recursive Web Scraper (`scraper.py`)
- **What it does:** Starts at a home URL, follows all link tags pointing to the same domain recursively up to a depth limit, download pages, and cleans them.
- **Blockchain Analogy:** Think of this as a **Block Indexer** (like Etherscan). It parses transaction graphs (links) starting from a genesis block (home URL) and extracts only payload data (text) while skipping empty headers or navigation noise.
- **Robustness:** Added politeness delay (0.5s rate-limit between fetches) and Playwright fallback for JS-rendered React/Vue single page apps.

### 2. Semantic Chunking (`rag_manager.py`)
- **What it does:** Splitting text into pieces of ~500 tokens with an overlap of 50 tokens.
- **Why?** An LLM has a "Context Window" limit (equivalent to a **Block Gas Limit**). We cannot feed it a whole 30-page site for one question. Overlapping chunks ensures we don't slice a vital sentence right down the middle, preserving context across boundaries.
- **Method:** We use LangChain's `RecursiveCharacterTextSplitter` configured with the OpenAI `tiktoken` tokenizer (which translates text into numerical byte-pair arrays).

### 3. Vector Embeddings (`rag_manager.py`)
- **What it does:** Translates text chunks into a list of numbers (a vector, e.g., 384 dimensions for local model or 1536 dimensions for OpenAI).
- **The Concept:** Think of this as creating **GPS coordinates** on a map. Instead of latitude and longitude (2 dimensions), we use hundreds of dimensions. Sentences with similar semantic meanings end up physically close to each other. For example: *"How do I transfer token balances?"* and *"What is the transfer function schema?"* will have very similar coordinates, even though they use different words.

### 4. Vector Database (`ChromaDB`)
- **What it does:** Stores the chunk vectors and their metadata (source URLs) in a local SQL-lite style persistent vector engine.
- **Search Method:** When you query the chatbot, we convert your question into a vector and use **Similarity Search** (spatial distance checks like cosine distance) to retrieve the top 4–6 closest text chunks in the database.

### 5. Retrieval-Augmented Generation (The RAG Step)
- **What it does:** Bundles the retrieved context chunks together with the user's question, and sends it to the LLM (GPT-4o-mini).
- **Prompt Guarding:** The model is strictly instructed: *"Answer the user's question based ONLY on the provided chunks. If you cannot find the answer, state 'I don't know based on the available content.'".* This acts as a validation script to stop **Hallucination** (when an AI fabricates false state data).

---

## ⚖️ Architecture Tradeoffs

| Choice | Approach in App | Tradeoffs / Alternatives |
| :--- | :--- | :--- |
| **Frontend UI** | Premium Vanilla HTML/CSS/JS | **Vite/React:** Better for large state-heavy apps, but takes longer to compile. **Streamlit:** Fast to build in Python, but visually restrictive. Vanilla gives total layout freedom with zero load delay. |
| **Vector DB** | ChromaDB (Local SQLite-based) | **Pinecone/Milvus:** Better for scale (billions of vectors), but requires a separate cloud server and api keys. ChromaDB is local, zero-config, and perfect for small projects. |
| **Embeddings** | OpenAI or local SentenceTransformers | **OpenAI API:** High accuracy but costs money. **SentenceTransformers (all-MiniLM-L6-v2):** Local CPU compute, 100% free and private, but takes RAM/CPU to run. |
| **Scraper** | Synchronous requests + delay | **Asynchronous (httpx/aiohttp):** Much faster, but runs the risk of getting rate-limited or IP-blocked by target host firewalls immediately. |
