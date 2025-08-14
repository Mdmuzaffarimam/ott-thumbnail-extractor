from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import re
import requests
from urllib.parse import urlparse

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# --- Core extractors ---------------------------------------------------------

def extract_pr_urls_from_html(html: str):
    """
    Return all candidate image URLs that contain 'pr_' token from known CDNs.
    """
    patterns = [
        r'(https://akamaividz\.zee5\.com/image/upload/[^\s"\'<>]+pr_[^\s"\'<>]+)',
        r'(https://img1\.hotstar\.com/image/upload/[^\s"\'<>]+pr_[^\s"\'<>]+)',
        r'(https://img\.hotstar\.com/image/upload/[^\s"\'<>]+pr_[^\s"\'<>]+)',
    ]
    found = []
    for pat in patterns:
        for m in re.finditer(pat, html):
            url = m.group(1)
            # Strip trailing punctuation if any
            url = url.rstrip('").,>]}')
            if url not in found:
                found.append(url)
    return found

def try_upgrade_hotstar(url: str):
    """
    Hotstar URLs often include a transform like t_web_16x9_1_5.
    We don't alter transforms here (Hotstar validates), but ensure f_auto present.
    """
    if "hotstar.com" in url and "f_auto" not in url:
        # naive upgrade: insert f_auto at start of params if missing
        url = url.replace("/image/upload/", "/image/upload/f_auto,")
    return url

def normalize_zee5(url: str):
    """
    Allow increasing width/height for Zee5 CDN if present.
    """
    if "akamaividz.zee5.com" in url:
        # If width/height present, bump to 1920x1080; else append
        if "w_" in url or "h_" in url:
            url = re.sub(r"w_\d+", "w_1920", url)
            url = re.sub(r"h_\d+", "h_1080", url)
        else:
            url = url.replace("/image/upload/", "/image/upload/w_1920,h_1080,c_scale/")
    return url

def best_unique(urls):
    out = []
    seen = set()
    for u in urls:
        u = u.strip()
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def extract_from_url(page_url: str, extra_headers=None, cookies=None, timeout=12):
    headers = dict(COMMON_HEADERS)
    if extra_headers and isinstance(extra_headers, dict):
        headers.update(extra_headers)

    session = requests.Session()
    if cookies and isinstance(cookies, dict):
        jar = requests.cookies.RequestsCookieJar()
        for k, v in cookies.items():
            jar.set(k, v)
        session.cookies = jar

    # Fetch page
    resp = session.get(page_url, headers=headers, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    html = resp.text

    # Gather candidate URLs
    candidates = extract_pr_urls_from_html(html)

    # Post-process
    upgraded = []
    for u in candidates:
        u = try_upgrade_hotstar(u)
        u = normalize_zee5(u)
        upgraded.append(u)

    upgraded = best_unique(upgraded)
    return upgraded

# --- Routes ------------------------------------------------------------------

@app.route("/api/extract", methods=["POST"])
def api_extract():
    data = request.get_json(silent=True) or {}
    page_url = data.get("url")
    headers = data.get("headers") or {}
    cookies = data.get("cookies") or {}

    if not page_url or not isinstance(page_url, str):
        return jsonify({"ok": False, "error": "Missing or invalid 'url'"}), 400

    try:
        urls = extract_from_url(page_url, extra_headers=headers, cookies=cookies)
        if not urls:
            return jsonify({"ok": False, "error": "No thumbnail found. Try providing cookies if page requires login."}), 404
        return jsonify({"ok": True, "count": len(urls), "thumbnails": urls})
    except requests.HTTPError as e:
        return jsonify({"ok": False, "error": f"HTTP error: {e}"}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 500

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
