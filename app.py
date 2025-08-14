from flask import Flask, render_template, request
import requests
import json
import os

app = Flask(__name__)

def fetch_thumbnail(url, cookies=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    if cookies:
        response = requests.get(url, headers=headers, cookies=cookies)
    else:
        response = requests.get(url, headers=headers)

    response.raise_for_status()
    html = response.text

    # ----- HOTSTAR -----
    if "hotstar.com" in url:
        if '"posterImage":{"url":"' in html:
            thumb = html.split('"posterImage":{"url":"')[1].split('"')[0]
            return thumb.replace("\\u0026", "&")

    # ----- JIOCINEMA -----
    if "jiocinema.com" in url:
        if '"thumbnail":"https:' in html:
            thumb = html.split('"thumbnail":"')[1].split('"')[0]
            return thumb.replace("\\u0026", "&")

    # ----- SONYLIV -----
    if "sonyliv.com" in url:
        if '"imageUri":"' in html:
            thumb = html.split('"imageUri":"')[1].split('"')[0]
            return thumb.replace("\\u0026", "&")

    # ----- ZEE5 -----
    if "zee5.com" in url:
        if '"image_url":"https' in html:
            thumb = html.split('"image_url":"')[1].split('"')[0]
            return thumb.replace("\\u0026", "&")

    # ----- AIRTEL XSTREAM -----
    if "airtelxstream.in" in url:
        if '"poster":"https' in html:
            thumb = html.split('"poster":"')[1].split('"')[0]
            return thumb.replace("\\u0026", "&")

    # ----- DANGAL PLAY -----
    if "dangalplay.com" in url:
        if '"image":"https' in html:
            thumb = html.split('"image":"')[1].split('"')[0]
            return thumb.replace("\\u0026", "&")

    raise Exception("Thumbnail not found or platform not supported yet.")

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url").strip()
        cookies_file = request.files.get("cookies")

        cookies = None
        if cookies_file and cookies_file.filename:
            try:
                cookies_data = json.load(cookies_file)
                cookies = {c["name"]: c["value"] for c in cookies_data}
            except:
                return render_template("index.html", error="Invalid cookies.json format")

        try:
            thumbnail_url = fetch_thumbnail(url, cookies)
            return render_template("index.html", thumbnail_url=thumbnail_url, url=url)
        except Exception as e:
            return render_template("index.html", error=str(e))

    return render_template("index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
