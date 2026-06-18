import os
import re
import json
import requests
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
from openai import OpenAI

# Load local environment variables if available
load_dotenv()

app = Flask(__name__)
# Secure secret key fallback for sessions
app.secret_key = os.getenv("SECRET_KEY", "hermes_secure_session_key_91827364")

# Read configurations
HERMES_PASSWORD = os.getenv("HERMES_PASSWORD")
HERMES_MODE = os.getenv("HERMES_MODE", "online")

# Initialize OpenAI client
api_key = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL", None) # Allows using OpenRouter or local LLMs
model_name = os.getenv("HERMES_MODEL", "gpt-4o-mini") # Lightweight and highly capable at function calling

# We only initialize the client if API Key is available to avoid startup crashes
client = None
if api_key:
    client = OpenAI(api_key=api_key, base_url=base_url)
else:
    print("WARNING: OPENAI_API_KEY is not set. The agent will run in simulation mode.")


# ==========================================
# AGENT TOOLS IMPLEMENTATION
# ==========================================

def web_search(query: str) -> str:
    """
    Search the web for up-to-date information on any topic using DuckDuckGo.
    Returns a text summary containing titles and descriptions of matches.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        # DDG Lite HTML-only search endpoint
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return f"Search failed with status code {response.status_code}."
            
        html = response.text
        
        # Simple extraction of snippets and titles
        snippets = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
        titles = re.findall(r'<a class="result__url"[^>]*>(.*?)</a>', html, re.DOTALL)
        
        if not snippets:
            # Fallback in case DuckDuckGo structure changes: strip HTML and return first 1000 characters
            clean_text = re.sub(r'<[^>]+>', '', html)
            clean_text = ' '.join(clean_text.split())
            return f"Search completed. Preview: {clean_text[:1000]}..."

        results = []
        for i in range(min(5, len(snippets))):
            title = re.sub(r'<[^>]+>', '', titles[i]) if i < len(titles) else "Result"
            snippet = re.sub(r'<[^>]+>', '', snippets[i])
            results.append(f"[{i+1}] Title: {title.strip()}\nSnippet: {snippet.strip()}\n")
            
        return "\n".join(results)
    except Exception as e:
        return f"Web search error: {str(e)}"


def web_browse(url: str) -> str:
    """
    Retrieve the text content of a specific webpage by its URL.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
        
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return f"Failed to retrieve page. Status code: {response.status_code}"
            
        html = response.text
        
        # Remove script and style elements to isolate main content
        html = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>', '', html, flags=re.IGNORECASE)
        
        # Strip HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)
        clean_text = ' '.join(text.split())
        
        return f"Content of {url} (truncated to 3000 chars):\n\n{clean_text[:3000]}..."
    except Exception as e:
        # Provide explanation on how to run a full browser like Playwright
        return (
            f"Error browsing {url}: {str(e)}.\n"
            "Note: This website might require Javascript execution. To support rendering dynamic SPAs, "
            "you can configure Playwright in headless mode in the Dockerfile as documented in the README."
        )


# Tool schemas for OpenAI Function Calling
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for up-to-date information on any topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_browse",
            "description": "Retrieve the text content of a specific webpage by its URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The absolute URL to browse."
                    }
                },
                "required": ["url"]
            }
        }
    }
]

TOOLS_MAP = {
    "web_search": web_search,
    "web_browse": web_browse
}


# ==========================================
# AGENT LOOP DEFINITION
# ==========================================

def run_agent_loop(chat_history):
    """
    Executes the LLM conversational loop with autonomous tool execution.
    Only saves user/assistant final texts to prevent session cookie overflow.
    """
    if not client:
        return (
            "Error: OPENAI_API_KEY is not configured on your server.\n"
            "Please go to your Render environment variables and set your OPENAI_API_KEY.",
            ["[Server Warning] OpenAI Client not initialized."]
        )
        
    messages = list(chat_history)
    steps = []
    
    # Inject core agent directives
    system_instruction = {
        "role": "system",
        "content": (
            "You are Hermes, an autonomous AI agent running online. "
            "You are helpful, analytical, and direct. "
            "You have access to tools: web_search and web_browse. "
            "Use them proactively to research information, answer queries, "
            "and verify details. Always synthesize your findings in your response."
        )
    }
    
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, system_instruction)
        
    max_iterations = 6
    for i in range(max_iterations):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto"
            )
        except Exception as e:
            error_msg = f"Error during model completion: {str(e)}"
            return error_msg, steps + [f"[System Error] {error_msg}"]
            
        assistant_message = response.choices[0].message
        
        # Check if model requested tool execution
        if assistant_message.tool_calls:
            # We must record the assistant call in the local stack
            tool_calls_list = []
            for tc in assistant_message.tool_calls:
                tool_calls_list.append({
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                })
                
            messages.append({
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": tool_calls_list
            })
            
            # Execute tool calls synchronously
            for tc in assistant_message.tool_calls:
                tool_name = tc.function.name
                
                try:
                    tool_args = json.loads(tc.function.arguments)
                except Exception:
                    tool_args = {}
                    
                steps.append(f"Hermes executes tool '{tool_name}' with parameters: {tc.function.arguments}")
                
                tool_func = TOOLS_MAP.get(tool_name)
                if tool_func:
                    try:
                        tool_result = tool_func(**tool_args)
                    except Exception as e:
                        tool_result = f"Error executing tool: {str(e)}"
                else:
                    tool_result = f"Tool '{tool_name}' is not registered."
                    
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tool_name,
                    "content": tool_result
                })
        else:
            # No tool execution needed, final answer received
            final_content = assistant_message.content or ""
            return final_content, steps
            
    return "Hermes hit the maximum tool-calling steps limit before rendering an answer.", steps


# ==========================================
# FLASK WEB SERVER ROUTES
# ==========================================

@app.route("/", methods=["GET", "POST"])
def index():
    # If no password is set in the environment, bypass login for ease of use
    if not HERMES_PASSWORD:
        session['authenticated'] = True
        
    error = None
    if request.method == "POST":
        password = request.form.get("password")
        if password == HERMES_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for("index"))
        else:
            error = "Incorrect password. Please try again."
            
    authenticated = session.get("authenticated", False)
    
    # Initialize history list if authenticated
    if authenticated and "messages" not in session:
        session["messages"] = []
        
    return render_template("index.html", authenticated=authenticated, error=error, has_password=bool(HERMES_PASSWORD))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/clear_chat", methods=["POST"])
def clear_chat():
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized access"}), 401
    session["messages"] = []
    return jsonify({"status": "success"})


@app.route("/chat", methods=["POST"])
def chat():
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized access"}), 401
        
    data = request.json or {}
    user_message = data.get("message")
    
    if not user_message:
        return jsonify({"error": "No message content received."}), 400
        
    # Retrieve chat history from session cookie
    history = session.get("messages", [])
    
    # Append the user's input message
    history.append({"role": "user", "content": user_message})
    
    # Execute agent decision-making loop
    agent_response, steps = run_agent_loop(history)
    
    # Store the final agent answer
    history.append({"role": "assistant", "content": agent_response})
    
    # Save back to cookie
    session["messages"] = history
    session.modified = True
    
    return jsonify({
        "response": agent_response,
        "steps": steps
    })


@app.route("/health", methods=["GET"])
def health():
    """
    Lightweight health check endpoint for Render keep-alive pings.
    """
    return jsonify({
        "status": "ok",
        "mode": HERMES_MODE,
        "api_connected": bool(client)
    })


if __name__ == "__main__":
    # Render binds dynamically to the PORT env variable
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
