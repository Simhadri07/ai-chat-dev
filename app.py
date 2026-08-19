import mimetypes
import json
import os
import socket
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")


def find_free_port(start_port: int = 8000):
    for port in range(start_port, start_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free port found")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("", "/"):
            path="/index.html"
        file_path=os.path.join(STATIC_DIR,path.lstrip("/"))
        if os.path.exists(file_path) and os.path.isfile(file_path):
            if file_path.endswith(".html"):
                content_type = "text/html; charset=utf-8"
            elif file_path.endswith(".css"):
                content_type = "text/css; charset=utf-8"
            else:
                content_type = "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            with open(file_path, "rb") as fh:
                self.wfile.write(fh.read())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")

    def do_POST(self):
        if self.path not in ("/api/chat", "/api/check"):
            self.send_response(404)
            self.end_headers()
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body or "{}")
        except Exception as exc:
            payload = {}
            parse_error = str(exc)
        else:
            parse_error = None

        try:
            prompt = payload.get("prompt", "")
            api_key = payload.get("apiKey", "") or os.environ.get("OPENAI_API_KEY", "")
            provider = (payload.get("provider") or "openai").lower()
            base_url = self.default_base_url(provider, payload.get("baseUrl"))
            model = (payload.get("model") or os.environ.get("OPENAI_MODEL") or self.default_model(provider)).strip()

            if self.path == "/api/check":
                connected, message = self.check_connection(api_key, provider, base_url, model)
                response_body = {"connected": connected, "message": message}
            else:
                reply = self.generate_reply(api_key, provider, base_url, model, prompt)
                response_body = {"reply": reply}
        except Exception as exc:
            if self.path == "/api/check":
                response_body = {"connected": False, "message": f"Connection check failed: {exc}"}
            else:
                response_body = {"reply": f"Request failed: {exc}"}

        if parse_error:
            if self.path == "/api/check":
                response_body = {"connected": False, "message": f"Connection check failed: invalid JSON payload ({parse_error})"}
            else:
                response_body = {"reply": f"Request failed: invalid JSON payload ({parse_error})"}

        response = json.dumps(response_body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        try:
            self.wfile.write(response)
        except BrokenPipeError:
            # Client disconnected before the response could be delivered.
            return
        except OSError:
            # Ignore any socket errors on write, do not crash the server.
            return

    def default_model(self, provider):
        defaults = {
            "openai": "gpt-4o-mini",
            "gemini": "gemini-2.0-flash",
            "claude": "claude-3-5-haiku-latest",
            "local": "llama3.2:latest",
            "ollama": "llama3.2:latest",
        }
        return defaults.get(provider, "gpt-4o-mini")

    def default_base_url(self, provider, override=None):
        if override:
            return override.strip()
        if provider in ("local", "ollama"):
            return os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
        if provider in ("gemini", "google"):
            return os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").strip()
        if provider == "claude":
            return os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").strip()
        return os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()

    def check_connection(self, api_key, provider, base_url, model):
        if provider in ("local", "ollama"):
            endpoint = base_url.rstrip("/") + "/api/tags"
            try:
                with urllib.request.urlopen(endpoint, timeout=8) as response:
                    json.load(response)
                return True, f"Connected to Ollama at {base_url}."
            except Exception as exc:
                return False, f"Unable to reach Ollama: {exc}"

        if provider in ("gemini", "google"):
            if not api_key:
                return False, "Google AI Studio API key is required for Gemini."
            endpoint = base_url.rstrip("/") + f"/models?key={api_key}"
            try:
                req = urllib.request.Request(endpoint, headers={"Accept": "application/json"}, method="GET")
                with urllib.request.urlopen(req, timeout=15) as response:
                    return True, f"Connected to Gemini endpoint. Status: {response.getcode()}."
            except urllib.error.HTTPError as exc:
                try:
                    detail = json.load(exc)
                except Exception:
                    detail = exc.read().decode("utf-8", "ignore")
                return False, f"Gemini endpoint responded but auth or routing failed: {exc.code} {exc.reason} - {detail}"
            except Exception as exc:
                return False, f"Unable to reach the Gemini endpoint: {exc}"

        if provider == "claude":
            if not api_key:
                return False, "Claude API key is required for Claude."
            endpoint = base_url.rstrip("/") + "/models"
            headers = {"Accept": "application/json", "x-api-key": api_key}
            try:
                req = urllib.request.Request(endpoint, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=15) as response:
                    return True, f"Connected to Claude endpoint. Status: {response.getcode()}."
            except urllib.error.HTTPError as exc:
                try:
                    detail = json.load(exc)
                except Exception:
                    detail = exc.read().decode("utf-8", "ignore")
                return False, f"Claude endpoint responded but auth or routing failed: {exc.code} {exc.reason} - {detail}"
            except Exception as exc:
                return False, f"Unable to reach the Claude endpoint: {exc}"

        endpoint = base_url.rstrip("/") + "/models"
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            req = urllib.request.Request(endpoint, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=15) as response:
                return True, f"Connected. Endpoint replied with status {response.getcode()}."
        except urllib.error.HTTPError as exc:
            try:
                detail = json.load(exc)
            except Exception:
                detail = exc.read().decode("utf-8", "ignore")
            return False, f"Endpoint responded but auth or routing failed: {exc.code} {exc.reason} - {detail}"
        except Exception as exc:
            return False, f"Unable to reach the provider: {exc}"

    def generate_reply(self, api_key, provider, base_url, model, prompt):
        if provider in ("local", "ollama"):
            try:
                payload = json.dumps({
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                }).encode("utf-8")
                endpoint = base_url.rstrip("/") + "/api/generate"
                req = urllib.request.Request(
                    endpoint,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=60) as response:
                    data = json.load(response)
                return data.get("response", "").strip() or "The local model returned an empty response."
            except Exception as exc:
                return f"Local generation failed: {exc}"

        if provider in ("gemini", "google"):
            if not api_key:
                return "No Google AI Studio API key provided."
            try:
                endpoint = base_url.rstrip("/") + f"/models/{model}:generateContent?key={api_key}"
                payload = json.dumps({
                    "contents": [{"parts": [{"text": prompt}]}]
                }).encode("utf-8")
                req = urllib.request.Request(
                    endpoint,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=40) as response:
                    data = json.load(response)
                candidates = data.get("candidates", [])
                if not candidates:
                    return "No response received from Gemini."
                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts:
                    return "Gemini returned an empty response."
                text = ""
                for part in parts:
                    if isinstance(part, dict):
                        text += part.get("text", "")
                return text.strip() or "Gemini returned an empty response."
            except urllib.error.HTTPError as exc:
                try:
                    detail = json.load(exc)
                except Exception:
                    detail = exc.read().decode("utf-8", "ignore")
                return f"Gemini API call failed: {exc.code} {exc.reason} - {detail}"
            except Exception as exc:
                return f"Gemini API call failed: {exc}"

        if provider == "claude":
            if not api_key:
                return "No Claude API key provided."
            try:
                endpoint = base_url.rstrip("/") + "/complete"
                payload = json.dumps({
                    "model": model,
                    "prompt": f"Human: {prompt}\n\nAssistant:",
                    "max_tokens_to_sample": 1000,
                    "temperature": 0.7,
                }).encode("utf-8")
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                }
                req = urllib.request.Request(
                    endpoint,
                    data=payload,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=40) as response:
                    data = json.load(response)
                return data.get("completion", "").strip() or "Claude returned an empty response."
            except urllib.error.HTTPError as exc:
                try:
                    detail = json.load(exc)
                except Exception:
                    detail = exc.read().decode("utf-8", "ignore")
                return f"Claude API call failed: {exc.code} {exc.reason} - {detail}"
            except Exception as exc:
                return f"Claude API call failed: {exc}"

        if not api_key:
            return "No API key provided. Add your API key to the form or set OPENAI_API_KEY."

        try:
            payload = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
            }).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            }
            endpoint = base_url.rstrip("/") + "/chat/completions"
            req = urllib.request.Request(
                endpoint,
                data=payload,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.load(response)
            choices = data.get("choices", [])
            if not choices:
                return "No response received from the API."
            message = choices[0].get("message", {}).get("content", "")
            return message.strip() or "The API returned an empty response."
        except urllib.error.HTTPError as exc:
            try:
                detail = json.load(exc)
            except Exception:
                detail = exc.read().decode("utf-8", "ignore")
            return f"API call failed: {exc.code} {exc.reason} - {detail}"
        except Exception as exc:
            return f"API call failed: {exc}"

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    preferred_port = int(os.environ.get("PORT", "8000"))
    port = find_free_port(preferred_port)
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Python UI server running at http://localhost:{port}/")
    server.serve_forever()
