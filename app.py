import os, time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI
import io
from PyPDF2 import PdfReader

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
ASSISTANT_ID   = os.environ["PATTI_ASSISTANT_ID"]

client = OpenAI(api_key=OPENAI_API_KEY)

app = Flask(__name__, static_url_path="", static_folder="static")
CORS(app)

@app.post("/upload")
def upload_pdf():
    # expects multipart/form-data with fields: file, threadId
    if "file" not in request.files:
        return jsonify({"error": "no_file"}), 400
    thread_id = request.form.get("threadId")
    if not thread_id:
        return jsonify({"error": "missing_threadId"}), 400

    f = request.files["file"]
    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "invalid_type"}), 400

    try:
        pdf_bytes = io.BytesIO(f.read())
        reader = PdfReader(pdf_bytes)
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        if not text:
            text = "(No extractable text found in the PDF.)"

        # keep it sane—trim giant PDFs
        MAX_CHARS = 12000
        clipped = text[:MAX_CHARS]
        if len(text) > MAX_CHARS:
            clipped += "\n\n[...truncated for length in demo...]"

        # Post as context into the same thread
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=f"Context from uploaded PDF:\n{clipped}"
        )

        return jsonify({"ok": True, "chars": len(clipped)})
    except Exception as e:
        return jsonify({"error": f"parse_failed: {e}"}), 500


@app.post("/session")
def create_session():
    thread = client.beta.threads.create()
    return jsonify({"threadId": thread.id})

@app.post("/message")
def message():
    data = request.get_json(force=True)
    thread_id = data["threadId"]
    content   = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "empty message"}), 400

    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=content
    )

    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID,
        additional_instructions=(
            "Demo mode: no CRM or inventory calls. "
            "Reply as a dealership assistant. Be concise, friendly, and decisive. "
            "Offer a clear CTA with this link: https://pattersonautos.com/schedule"
        )
    )

    terminal = {"completed","failed","cancelled","expired"}
    while True:
        r = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if r.status in terminal:
            break
        time.sleep(0.8)

    msgs = client.beta.threads.messages.list(thread_id=thread_id, order="desc", limit=5)
    reply_text = "(no reply)"
    for m in msgs.data:
        if m.role == "assistant":
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
