from flask import Flask, request, render_template, jsonify
import re, requests

app = Flask(__name__)

# ---------- Settings ----------
COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

# Known CDN/image patterns per platform (expandable)
PATTERNS = [
    # ZEE5
    r'(https://akamaividz\.zee5\.com/image/upload/[^\s"\'<>]+pr_[^\s"\'<>]+)',
    # Hotstar
    r'(https://img1\.hotstar\.com/image/upload/[^\s"\'<>]+pr_[^\s"\'<>]+)',
    r'(https://img\.hotstar\.com/image/upload/[^\s"\'<>]+pr_[^\s"\'<>]+)',
    # SonyLiv
    r'(https://shimageapi\.sonyliv\.com/[^\s"\'<>]+?\.jpg[^\s"\'<>]*)',
    r'(https://setimages\.sonyliv\.com/[^\s"\'<>]+?\.jpg[^\s"\'<>]*)',
    # JioCinema
    r'(https://jiocinemacdn\.jiocinema\.com/[^\s"\'<>]+?\.jpg[^\s"\'<>]*)',
    r'(https://jiocinemaimages-a\.akamaihd\.net/[^\s"\'<>]+?\.jpg[^\s"\'<>]*)',
    # Voot (legacy; many titles migrated to JioCinema but old pages still exist)
    r'(https://v3img\.voot\.com/[^\s"\'<>]+?\.jpg[^\s"\'<>]*)',
    r'(https://v3img-a\.akamaihd\.net/[^\s"\'<>]+?\.jpg[^\s"\'<>]*)',
    # Dangal Play
    r'(https://images\.dangalplay\.com/[^\s"\'<>]+?\.jpg[^\s"\'<>]*)',
    # Airtel Xstream (often proxies Hotstar/Zee/Sony images; still try)
    r'(https://assets-airtelxstream\.in/[^\s"\'<>]+?\.jpg[^\s"\'<>]*)',
]

def _extract_pr_urls_from_html(html: str):
    found = []
    for pat in PATTERNS:
        for m in re.finditer(pat, html):
            url = m.group(1).rstrip('").,>]}')
            if url not in found:
                found.append(url)
    return found

def _normalize(url: str) -> str:
    # ZEE5: upgrade to 1920x1080 if possible
    if "akamaividz.zee5.com" in url:
        if "w_" in url or "h_" in url:
            url = re.sub(r"w_\d+", "w_1920", url)
            url = re.sub(r"h_\d+", "h_1080", url)
        else:
            url = url.replace("/image/upload/", "/image/upload/w_1920,h_1080,c_scale/")
    # Hotstar: ensure f_auto present (safe default)
    if "hotstar.com" in url and "/image/upload/" in url and "f_auto" not in url:
        url = url.replace("/image/upload/", "/image/upload/f_auto,")
    return url

def fetch_page(url: str, headers=None, cookies=None, timeout=15):
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

def extract_thumbnails(page_url: str, headers=None, cookies=None):
    html = fetch_page(page_url, headers=headers, cookies=cookies)
    raw = _extract_pr_urls_from_html(html)
    return [_normalize(u) for u in raw]

# ---------- Web UI ----------
@app.route("/", methods=["GET", "POST"])
def home():
    thumbnails = []
    error = None
    url = ""
    adv_headers = ""
    adv_cookies = ""

    if request.method == "POST":
        url = request.form.get("ott_link", "").strip()
        adv_headers = request.form.get("headers_json", "").strip()
        adv_cookies = request.form.get("cookies_json", "").strip()

        headers = {}
        cookies = {}
        try:
            if adv_headers:
                import json
                headers = json.loads(adv_headers)
        except Exception:
            error = "Headers JSON invalid hai. {}"
        try:
            if adv_cookies:
                import json
                cookies = json.loads(adv_cookies)
        except Exception:
            error = "Cookies JSON invalid hai."

        if url and not error:
            try:
                thumbnails = extract_thumbnails(url, headers=headers, cookies=cookies)
                if not thumbnails:
                    error = "Thumbnail nahi mila. Agar page login-protected hai to Cookies JSON use karein."
            except requests.HTTPError as e:
                error = f"HTTP error: {e}"
            except Exception as e:
                error = f"Error: {type(e).__name__}: {e}"

    return render_template("index.html",
                           thumbnails=thumbnails, error=error, url=url,
                           adv_headers=adv_headers, adv_cookies=adv_cookies)

# ---------- JSON API (optional) ----------
@app.route("/api/extract", methods=["POST"])
def api_extract():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
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

if __name__ == "__main__":
    # Render/Gunicorn will use Procfile in production; this is just for local dev.
    app.run(host="0.0.0.0", port=8000, debug=False)
