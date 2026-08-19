function setStatus(message, isError = false) {
    const status = document.getElementById("status");
    status.textContent = message;
    status.classList.toggle("error", isError);
    status.classList.toggle("success", !isError);
}

async function parseJsonResponse(response) {
    const text = await response.text();
    if (!text) return {};

    try {
        return JSON.parse(text);
    } catch {
        return { message: text };
    }
}

function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function renderMarkdown(text) {
    const escaped = escapeHtml(text || "");

    const codeBlocks = [];
    let processed = escaped.replace(/```([\s\S]*?)```/g, (match, code) => {
        const trimmed = code.replace(/^\n|\n$/g, "");
        codeBlocks.push(trimmed);
        return `[[CODEBLOCK_${codeBlocks.length - 1}]]`;
    });

    processed = processed
        .replace(/^###### (.+)$/gm, '<h6>$1</h6>')
        .replace(/^##### (.+)$/gm, '<h5>$1</h5>')
        .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>');

    processed = processed.replace(/((?:^[-*+] .+(?:\n|$))+)/gm, (block) => {
        const items = block.trim().split(/\n/).map((line) => line.replace(/^[-*+] /, ""));
        return `<ul><li>${items.join("</li><li>")}</li></ul>`;
    });

    processed = processed.replace(/((?:^\d+\. .+(?:\n|$))+)/gm, (block) => {
        const items = block.trim().split(/\n/).map((line) => line.replace(/^\d+\. /, ""));
        return `<ol><li>${items.join("</li><li>")}</li></ol>`;
    });

    processed = processed
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\*([^\*]+)\*/g, '<em>$1</em>')
        .replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" rel="noreferrer noopener">$1</a>');

    processed = processed
        .replace(/\n{2,}/g, '</p><p>')
        .replace(/\n/g, '<br />');

    processed = `<p>${processed}</p>`;
    processed = processed.replace(/<p><(h\d|ul|ol|pre)/g, '<$1');
    processed = processed.replace(/<\/((h\d|ul|ol|pre))><\/p>/g, '</$1>');

    processed = processed.replace(/\[\[CODEBLOCK_(\d+)\]\]/g, (match, index) => {
        const code = codeBlocks[Number(index)] || "";
        return `<div class="code-block"><button class="copy-code" type="button">Copy</button><pre><code>${code}</code></pre></div>`;
    });

    return processed;
}

function addMessage(type, text) {
    const messages = document.getElementById("messages");

    const msg = document.createElement("div");
    msg.className = `msg ${type}`;

    if (type === "assistant") {
        msg.innerHTML = renderMarkdown(text);
    } else {
        msg.textContent = text;
    }

    messages.appendChild(msg);
    messages.scrollTop = messages.scrollHeight;

    return msg;
}

async function sendMessage() {
    const apiKey = document.getElementById("apiKey").value;
    const provider = document.getElementById("provider").value;
    const model = document.getElementById("model").value.trim();
    const promptBox = document.getElementById("prompt");
    const prompt = promptBox.value.trim();

    if (!prompt) return;

    promptBox.value = "";

    addMessage("user", prompt);

    const assistantMsg = addMessage("assistant", "Thinking...");

    setStatus("Sending message...");

    document.querySelectorAll("button").forEach(btn => btn.disabled = true);

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                apiKey,
                provider,
                model: model || undefined,
                prompt
            })
        });

        const data = await parseJsonResponse(response);

        if (!response.ok) {
            throw new Error(data.message || `HTTP ${response.status}`);
        }

        assistantMsg.textContent =
            data.reply ||
            data.message ||
            "No reply returned.";

        setStatus("Message sent.");

    } catch (err) {

        assistantMsg.textContent =
            "❌ " + (err.message || err);

        setStatus(
            "Message failed: " + (err.message || err),
            true
        );

    } finally {

        document.querySelectorAll("button").forEach(btn => btn.disabled = false);

        document.getElementById("messages").scrollTop =
            document.getElementById("messages").scrollHeight;
    }
}

async function checkConnection() {

    const apiKey = document.getElementById("apiKey").value;
    const provider = document.getElementById("provider").value;
    const model = document.getElementById("model").value.trim();

    setStatus("Checking connection...");

    try {

        const response = await fetch("/api/check", {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                apiKey,
                provider,
                model: model || undefined
            })

        });

        const data = await parseJsonResponse(response);

        setStatus(
            data.message || "Connection successful.",
            !data.connected
        );

    } catch (err) {

        setStatus(
            "Connection failed: " + (err.message || err),
            true
        );
    }
}

function clearChat() {
    const messages = document.getElementById("messages");
    messages.innerHTML = "";
    setStatus("Chat cleared.");
}

document.addEventListener("DOMContentLoaded", () => {

    const provider = document.getElementById("provider");
    const apiKey = document.getElementById("apiKey");
    const model = document.getElementById("model");

    function updateProvider() {

        if (provider.value === "local") {

            apiKey.value = "";
            apiKey.disabled = true;
            apiKey.placeholder = "Not required for Ollama";

            if (!model.value)
                model.value = "qwen2.5-coder:1.5b";

        } else {

            apiKey.disabled = false;
            apiKey.placeholder = "Enter your API key";
        }
    }

    provider.addEventListener("change", updateProvider);

    updateProvider();

    document.getElementById("sendButton")
        .addEventListener("click", sendMessage);

    document.getElementById("checkButton")
        .addEventListener("click", checkConnection);

    document.getElementById("clearButton")
        .addEventListener("click", clearChat);

    document.getElementById("prompt")
        .addEventListener("keydown", e => {

            if (e.key === "Enter" && !e.shiftKey) {

                e.preventDefault();

                sendMessage();
            }

        });

    document.getElementById("messages").addEventListener("click", async (event) => {
        const button = event.target.closest(".copy-code");
        if (!button) return;

        const codeBlock = button.parentElement.querySelector("pre code");
        if (!codeBlock) return;

        try {
            await navigator.clipboard.writeText(codeBlock.textContent || "");
            button.textContent = "Copied!";
            setTimeout(() => {
                button.textContent = "Copy";
            }, 1500);
        } catch (err) {
            button.textContent = "Error";
            setTimeout(() => {
                button.textContent = "Copy";
            }, 1500);
        }
    });
});

const provider = document.getElementById("provider");
const model = document.getElementById("model");
const apiKey = document.getElementById("apiKey");

function updateProvider() {

    switch (provider.value) {

        case "openai":
            model.value = "gpt-4o-mini";
            apiKey.disabled = false;
            apiKey.placeholder = "Enter OpenAI API Key";
            break;

        case "gemini":
            model.value = "gemini-2.5-flash";
            apiKey.disabled = false;
            apiKey.placeholder = "Enter Gemini API Key";
            break;

        case "claude":
            model.value = "claude-3-5-haiku-latest";
            apiKey.disabled = false;
            apiKey.placeholder = "Enter Claude API Key";
            break;

        case "local":
        case "ollama":
            model.value = "qwen2.5-coder:1.5b";
            apiKey.value = "";
            apiKey.disabled = true;
            apiKey.placeholder = "Not required for Ollama";
            break;
    }
}

provider.addEventListener("change", updateProvider);
updateProvider();