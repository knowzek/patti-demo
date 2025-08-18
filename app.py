import os, time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI

# ---- Env vars (already set in Render per you) ----
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
ASSISTANT_ID   = os.environ["PATTI_ASSISTANT_ID"]  # your real Assistants API ID
DEMO_PIN       = os.getenv("DEMO_PIN")             # optional shared passcode

client = OpenAI(api_key=OPENAI_API_KEY)

app = Flask(__name__, static_url_path="", static_folder="static")
CORS(app)

@app.post("/session")
def create_session():
    if DEMO_PIN and request.headers.get("X-DEMO-PIN") != DEMO_PIN:
        return jsonify({"error": "unauthorized"}), 401
    thread = client.beta.threads.create()
    return jsonify({"threadId": thread.id})

@app.post("/message")
def message():
    if DEMO_PIN and request.headers.get("X-DEMO-PIN") != DEMO_PIN:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(force=True)
    thread_id = data["threadId"]
    content   = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "empty message"}), 400

    # 1) append user message
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=content
    )

    # 2) run Patti with a tiny demo guardrail
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID,
        additional_instructions=(
            "Demo mode: no CRM or inventory calls. "
            "Reply as a dealership assistant. Be concise, friendly, and decisive. "
            "Offer a clear CTA with this link: https://pattersonautos.com/schedule"
        )
    )

    # 3) poll until complete
    terminal = {"completed","failed","cancelled","expired"}
    while True:
        r = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if r.status in terminal:
            break
        time.sleep(0.8)

    # 4) grab latest assistant reply
    msgs = client.beta.threads.messages.list(thread_id=thread_id, order="desc", limit=5)
    reply_text = "(no reply)"
    for m in msgs.data:
        if m.role == "assistant":
            # collect all text parts in this message
            parts = []
            for c in m.content:
                if c.type == "text":
                    parts.append(c.text.value)
            if parts:
                reply_text = "\n".join(parts).strip()
                break

    return jsonify({"status": r.status, "reply": reply_text})
    
@app.get("/")
def index():
    return send_from_directory("static", "index.html")
