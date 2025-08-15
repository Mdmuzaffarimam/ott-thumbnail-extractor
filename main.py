import os
import re
import json
import threading
import time
from typing import Dict, Optional, List
import requests
from flask import Flask, render_template, request, jsonify

# Telegram imports (v13)
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

app = Flask(__name__)

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

PATTERNS = [
    r'(https://akamaividz\\.zee5\\.com/image/upload/[^\\s"\\'<>]+pr_[^\\s"\\'<>]+)',
    r'(https://img1\\.hotstar\\.com/image/upload/[^\\s"\\'<>]+pr_[^\\s"\\'<>]+)',
    r'(https://img\\.hotstar\\.com/image/upload/[^\\s"\\'<>]+pr_[^\\s"\\'<>]+)',
    r'(https://shimageapi\\.sonyliv\\.com/[^\\s"\\'<>]+?\\.jpg[^\\s"\\'<>]*)',
    r'(https://setimages\\.sonyliv\\.com/[^\\s"\\'<>]+?\\.jpg[^\\s"\\'<>]*)',
    r'(https://jiocinemacdn\\.jiocinema\\.com/[^\\s"\\'<>]+?\\.jpg[^\\s"\\'<>]*)',
    r'(https://jiocinemaimages-a\\.akamaihd\\.net/[^\\s"\\'<>]+?\\.jpg[^\\s"\\'<>]*)',
    r'(https://v3img\\.voot\\.com/[^\\s"\\'<>]+?\\.jpg[^\\s"\\'<>]*)',
    r'(https://images\\.dangalplay\\.com/[^\\s"\\'<>]+?\\.jpg[^\\s"\\'<>]*)',
    r'(https://assets-airtelxstream\\.in/[^\\s"\\'<>]+?\\.jpg[^\\s"\\'<>]*)',
]

def _extract_pr_urls_from_html(html: str) -> List[str]:
    found = []
    for pat in PATTERNS:
        for m in re.finditer(pat, html):
            url = m.group(1).rstrip('").,>]}')
            if url not in found:
                found.append(url)
    return found

def _normalize(url: str) -> str:
    import re
    if "akamaividz.zee5.com" in url:
        url = re.sub(r"w_\\d+", "w_1920", url)
        url = re.sub(r"h_\\d+", "h_1080", url)
        if "/image/upload/" in url and "w_1920" not in url and "h_1080" not in url:
            url = url.replace("/image/upload/", "/image/upload/w_1920,h_1080,c_scale/")
    if "hotstar.com" in url and "/image/upload/" in url and "f_auto" not in url:
        url = url.replace("/image/upload/", "/image/upload/f_auto,")
    return url

def fetch_page(url: str, headers: Optional[Dict]=None, cookies: Optional[Dict]=None, timeout: int = 15) -> str:
    sess = requests.Session()
    h = dict(COMMON_HEADERS)
    if headers and isinstance(headers, dict):
        h.update(headers)
    if cookies and isinstance(cookies, dict):
        jar = requests.cookies.RequestsCookieJar()
        for k, v in cookies.items():
            jar.set(k, v)
        sess.cookies = jar
    r = sess.get(url, headers=h, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r.text

def extract_thumbnails(page_url: str, headers: Optional[Dict]=None, cookies: Optional[Dict]=None) -> List[str]:
    html = fetch_page(page_url, headers=headers, cookies=cookies)
    raw = _extract_pr_urls_from_html(html)
    return [_normalize(u) for u in raw]

# Flask routes (same UI as before)
@app.route("/", methods=["GET", "POST"])
def home():
    thumbnails = []
    error = None
    url = ""
    adv_headers = ""
    cookies_uploaded = False
    cookies_dict = None

    if request.method == "POST":
        url = (request.form.get("ott_link") or "").strip()
        adv_headers = (request.form.get("headers_json") or "").strip()

        headers = {}
        if adv_headers:
            try:
                headers = json.loads(adv_headers)
            except Exception:
                error = "Headers JSON invalid."

        file = request.files.get("cookies")
        if file and file.filename:
            try:
                data = json.load(file)
                if isinstance(data, list):
                    cookies_dict = {c.get("name"): c.get("value") for c in data if "name" in c and "value" in c}
                elif isinstance(data, dict):
                    cookies_dict = data
                else:
                    cookies_dict = None
                cookies_uploaded = cookies_dict is not None
            except Exception as e:
                error = f"Cookies JSON invalid: {e}"

        if url and not error:
            try:
                thumbnails = extract_thumbnails(url, headers=headers, cookies=cookies_dict)
                if not thumbnails:
                    error = "Thumbnail not found. If page is login-protected, try uploading cookies.json."
            except requests.HTTPError as e:
                error = f"HTTP error: {e}"
            except Exception as e:
                error = f"Error: {type(e).__name__}: {e}"

    return render_template("index.html", thumbnails=thumbnails, error=error, url=url, adv_headers=adv_headers, cookies_uploaded=cookies_uploaded)

@app.route("/api/extract", methods=["POST"])
def api_extract():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    headers = data.get("headers") or {}
    cookies = data.get("cookies") or {}
    if not url:
        return jsonify({"ok": False, "error": "Missing 'url'"}), 400
    try:
        thumbs = extract_thumbnails(url, headers=headers, cookies=cookies)
        if not thumbs:
            return jsonify({"ok": False, "error": "No thumbnails found"}), 404
        return jsonify({"ok": True, "count": len(thumbs), "thumbnails": thumbs})
    except Exception as e:
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 500

# Telegram bot polling in background
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ENABLE_BOT = bool(BOT_TOKEN)

if ENABLE_BOT:
    print("⚙️ BOT_TOKEN found in env — starting Telegram bot...")
    from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
    CHAT_COOKIES: Dict[int, Dict[str, str]] = {}

    def start_cmd(update, context):
        update.message.reply_text("👋 Namaste! Send an OTT episode URL and I'll return the thumbnail. Send cookies.json first for login pages.")

    def clearcookies_cmd(update, context):
        chat_id = update.effective_chat.id
        CHAT_COOKIES.pop(chat_id, None)
        update.message.reply_text("✅ Cookies cleared for this chat.")

    def handle_document(update, context):
        chat_id = update.effective_chat.id
        doc = update.message.document
        if not doc.file_name.lower().endswith(".json"):
            update.message.reply_text("Please send a JSON file (cookies.json).")
            return
        f = doc.get_file()
        content = f.download_as_bytearray().decode("utf-8", errors="ignore")
        try:
            data = json.loads(content)
            if isinstance(data, list):
                cookies = {c.get("name"): c.get("value") for c in data if "name" in c and "value" in c}
            elif isinstance(data, dict):
                cookies = data
            else:
                cookies = None
            if not cookies:
                update.message.reply_text("❌ Invalid cookies JSON.")
                return
            CHAT_COOKIES[chat_id] = cookies
            update.message.reply_text("✅ Cookies saved for this chat. Now send an episode URL.")
        except Exception as e:
            update.message.reply_text(f"❌ Failed to parse cookies: {e}")

    def handle_text(update, context):
        chat_id = update.effective_chat.id
        text = (update.message.text or "").strip()
        if not (text.startswith("http://") or text.startswith("https://")):
            update.message.reply_text("Please send a direct episode/page URL.")
            return
        cookies = CHAT_COOKIES.get(chat_id)
        try:
            thumbs = extract_thumbnails(text, cookies=cookies)
            if not thumbs:
                update.message.reply_text("❌ Thumbnail not found. If login page, send cookies.json first.")
                return
            first = thumbs[0]
            try:
                context.bot.send_photo(chat_id=chat_id, photo=first, caption="✅ Thumbnail")
            except Exception:
                update.message.reply_text(f"✅ Thumbnail: {first}")
            if len(thumbs) > 1:
                more = "\\n".join(thumbs[1:])
                update.message.reply_text(f"More:\\n{more}")
        except Exception as e:
            update.message.reply_text(f"❌ Error: {e}")

    def run_bot():
        try:
            updater = Updater(token=BOT_TOKEN, use_context=True)
            dp = updater.dispatcher
            dp.add_handler(CommandHandler("start", start_cmd))
            dp.add_handler(CommandHandler("clearcookies", clearcookies_cmd))
            dp.add_handler(MessageHandler(Filters.document, handle_document))
            dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
            updater.start_polling(drop_pending_updates=True)
            print("✅ Bot connected successfully and polling started.")
            updater.idle()
        except Exception as e:
            print(f"❌ Bot failed to start: {e}")

    threading.Thread(target=run_bot, daemon=True).start()
else:
    print("ℹ️ BOT_TOKEN not provided — Telegram bot is disabled. Set BOT_TOKEN env var to enable it.")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Starting Flask on port {port} ...")
    app.run(host="0.0.0.0", port=port)