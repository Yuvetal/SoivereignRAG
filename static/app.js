document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const scrapeUrlInput = document.getElementById("scrape-url");
    const maxDepthSelect = document.getElementById("max-depth");
    const maxPagesInput = document.getElementById("max-pages");
    const btnScrape = document.getElementById("btn-scrape");
    const txtScrape = document.getElementById("txt-scrape");
    const spinnerScrape = document.getElementById("spinner-scrape");
    
    const progressContainer = document.getElementById("progress-container");
    const progressStatusText = document.getElementById("progress-status-text");
    const progressCount = document.getElementById("progress-count");
    const progressBarFill = document.getElementById("progress-bar-fill");
    const consoleLogs = document.getElementById("console-logs");
    
    const btnClear = document.getElementById("btn-clear");
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const chatMessagesBox = document.getElementById("chat-messages-box");

    let statusPollingInterval = null;
    let loggedLinesCount = 0;

    // Helper: Add log line to console box
    function addConsoleLog(text, type = "system") {
        const line = document.createElement("div");
        line.className = `console-line ${type}`;
        line.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
        consoleLogs.appendChild(line);
        consoleLogs.scrollTop = consoleLogs.scrollHeight;
    }

    // Helper: Add chat bubble to chat box
    function addChatBubble(sender, content, role = "system", sources = []) {
        const messageDiv = document.createElement("div");
        messageDiv.className = `message ${role}-msg`;
        
        let avatar = "🔮";
        if (role === "user") avatar = "👤";
        else if (role === "assistant") avatar = "🤖";
        
        let sourcesHtml = "";
        if (sources && sources.length > 0) {
            sourcesHtml = `
                <div class="citations-box">
                    <div class="citations-title">Verified Citations:</div>
                    <div class="citations-list">
                        ${sources.map(src => `<a href="${src}" target="_blank" class="citation-tag">${src.replace(/^https?:\/\/(www\.)?/, '')}</a>`).join("")}
                    </div>
                </div>
            `;
        }

        messageDiv.innerHTML = `
            <div class="msg-avatar">${avatar}</div>
            <div class="msg-content-wrapper">
                <div class="msg-sender">${sender}</div>
                <div class="msg-body">${content}</div>
                ${sourcesHtml}
            </div>
        `;
        
        chatMessagesBox.appendChild(messageDiv);
        chatMessagesBox.scrollTop = chatMessagesBox.scrollHeight;
    }

    // Helper: Show/Hide typing loader
    function showTypingIndicator() {
        const indicator = document.createElement("div");
        indicator.id = "typing-indicator";
        indicator.className = "message assistant-msg";
        indicator.innerHTML = `
            <div class="msg-avatar">🤖</div>
            <div class="msg-content-wrapper">
                <div class="msg-sender">Oracle Assistant</div>
                <div class="msg-body" style="padding: 10px 16px;">Resolving references...</div>
            </div>
        `;
        chatMessagesBox.appendChild(indicator);
        chatMessagesBox.scrollTop = chatMessagesBox.scrollHeight;
    }

    function removeTypingIndicator() {
        const indicator = document.getElementById("typing-indicator");
        if (indicator) {
            indicator.remove();
        }
    }

    // Poll current scrape status from backend
    async function pollScrapeStatus(maxPagesExpected) {
        try {
            const response = await fetch("/api/scrape/status");
            const data = await response.json();
            
            // Update UI status labels
            progressStatusText.textContent = data.status;
            progressCount.textContent = `${data.pages_scraped}/${maxPagesExpected}`;
            
            // Calculate progress bar fill percentage
            const percentage = Math.min((data.pages_scraped / maxPagesExpected) * 100, 100);
            progressBarFill.style.width = `${percentage}%`;
            
            // Append any new log entries we haven't rendered yet
            if (data.logs && data.logs.length > loggedLinesCount) {
                for (let i = loggedLinesCount; i < data.logs.length; i++) {
                    addConsoleLog(data.logs[i], "system");
                }
                loggedLinesCount = data.logs.length;
            }

            // Stop polling once the background job finishes
            if (!data.is_scraping) {
                clearInterval(statusPollingInterval);
                statusPollingInterval = null;
                
                // Re-enable crawl button
                btnScrape.disabled = false;
                spinnerScrape.classList.add("hidden");
                txtScrape.textContent = "Synchronize Oracle";
                
                if (data.error) {
                    addConsoleLog(`Synchronization failed: ${data.error}`, "error");
                    addChatBubble("System Oracle", `Synchronization encountered an error: ${data.error}`, "system");
                } else {
                    addConsoleLog("Oracle Synchronization Completed Successfully!", "success");
                    addChatBubble(
                        "System Oracle", 
                        `Oracle synchronized successfully. Index contains contents from ${data.pages_scraped} source pages. You may now start query execution.`, 
                        "system"
                    );
                }
            }
        } catch (error) {
            console.error("Error polling scrape status:", error);
            addConsoleLog(`Poll failed: ${error}`, "error");
        }
    }

    // Trigger website scraping task
    btnScrape.addEventListener("click", async () => {
        const targetUrl = scrapeUrlInput.value.trim();
        const maxDepth = parseInt(maxDepthSelect.value);
        const maxPages = parseInt(maxPagesInput.value);

        if (!targetUrl) {
            alert("Please enter a valid URL.");
            return;
        }

        // Show progress box & lock button
        progressContainer.classList.remove("hidden");
        btnScrape.disabled = true;
        spinnerScrape.classList.remove("hidden");
        txtScrape.textContent = "Crawl Synchronizing...";
        
        consoleLogs.innerHTML = ""; // Clear console
        loggedLinesCount = 0;
        addConsoleLog(`Queueing synchronization task for: ${targetUrl}...`);

        try {
            const response = await fetch("/api/scrape", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url: targetUrl, max_depth: maxDepth, max_pages: maxPages })
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || "Scrape failed to queue.");
            }

            addConsoleLog("Synchronization successfully queued on backend. Initializing spider...");
            
            // Poll progress every 1 second
            if (statusPollingInterval) clearInterval(statusPollingInterval);
            statusPollingInterval = setInterval(() => pollScrapeStatus(maxPages), 1000);
            
        } catch (error) {
            addConsoleLog(`Trigger failed: ${error.message}`, "error");
            btnScrape.disabled = false;
            spinnerScrape.classList.add("hidden");
            txtScrape.textContent = "Synchronize Oracle";
        }
    });

    // Clear vector store database
    btnClear.addEventListener("click", async () => {
        if (!confirm("Are you sure you want to delete all indexed data? This will empty the chatbot knowledge database.")) {
            return;
        }
        
        try {
            const response = await fetch("/api/clear", { method: "POST" });
            const data = await response.json();
            
            addConsoleLog("Local database ledger wiped.", "error");
            alert(data.message);
            
            // Clear message feed and show reset notification
            chatMessagesBox.innerHTML = "";
            addChatBubble(
                "System Oracle", 
                "Database ledger cleared. Please synchronize a URL to build a new knowledge vector index.", 
                "system"
            );
        } catch (error) {
            alert("Error clearing vector store: " + error);
        }
    });

    // Submit chat message query
    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const questionText = chatInput.value.trim();
        if (!questionText) return;
        
        // Append user question
        addChatBubble("You", questionText, "user");
        chatInput.value = ""; // Reset input
        
        // Add loading state
        showTypingIndicator();

        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question: questionText })
            });

            if (!response.ok) {
                throw new Error("Failed to receive response from server.");
            }

            const data = await response.json();
            
            // Remove typing bubble and append answer
            removeTypingIndicator();
            addChatBubble("Oracle Assistant", data.answer, "assistant", data.sources);
            
        } catch (error) {
            removeTypingIndicator();
            addChatBubble("Oracle Assistant", `System Error: ${error.message}`, "assistant");
        }
    });
});
