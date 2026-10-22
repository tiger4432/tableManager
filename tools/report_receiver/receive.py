"""Takes the AI report's HTML file on the mail relay PC (owner 10-23: a report with every picture inside may be too
big for the mail server's request, so the file goes over first and the relay mails it). One route:

    POST /reports/<name>.html     body = the file's bytes        -> {"path", "bytes", "sha256"}

The body is written to disk as it arrives (never held whole in memory), as <name>.html.part, then renamed - a file
in the inbox is always whole. The same name again replaces it (a report made again).

Run on the relay PC, from this folder:
    uvicorn receive:app --host 0.0.0.0 --port 8765
REPORT_INBOX sets the folder the files land in (default: ./inbox next to this file)."""
import asyncio
import hashlib
import os
import re

from fastapi import FastAPI, HTTPException, Request

INBOX = os.environ.get("REPORT_INBOX") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "inbox")
#: A name is one file in the inbox - word characters (Korean too), «.», «-», ending in .html. No folder part.
NAME = re.compile(r"[\w.-]+\.html")

app = FastAPI()


@app.post("/reports/{name}")
async def receive(name: str, request: Request):
    if not NAME.fullmatch(name):
        raise HTTPException(400, "name is letters, digits, «_ . -» ending in .html - got %r" % name)
    os.makedirs(INBOX, exist_ok=True)
    path = os.path.join(INBOX, name)
    digest, size = hashlib.sha256(), 0
    out = await asyncio.to_thread(open, path + ".part", "wb")
    try:
        async for chunk in request.stream():
            # the disk write leaves the event loop, so a big file does not stop other requests
            await asyncio.to_thread(out.write, chunk)
            digest.update(chunk)
            size += len(chunk)
    finally:
        await asyncio.to_thread(out.close)
    await asyncio.to_thread(os.replace, path + ".part", path)
    return {"path": path, "bytes": size, "sha256": digest.hexdigest()}
