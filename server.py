from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv
import requests, os, json, uuid, time, hmac, hashlib, secrets
from collections import defaultdict

load_dotenv()

app = Flask(__name__)

@app.after_request
def apply_cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
    return response

@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        from flask import Response
        r = Response()
        r.headers["Access-Control-Allow-Origin"]  = "*"
        r.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        r.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
        return r, 204

BASE_URL = "https://api.brawlstars.com/v1"
API_KEY  = os.getenv("BRAWL_STARS_API_KEY")

# ── CMS config ───────────────────────────────────────────────────────────────
# NEVER hardcode the password here. Set CMS_PASSWORD in your .env or hosting env vars.
ADMIN_PASSWORD = os.getenv("CMS_PASSWORD")
if not ADMIN_PASSWORD:
    raise RuntimeError("CMS_PASSWORD environment variable is not set. Server will not start without it.")

NEWS_FILE       = os.path.join(os.path.dirname(__file__), "news_posts.json")
COUNTDOWN_FILE  = os.path.join(os.path.dirname(__file__), "countdowns.json")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTS    = {"png", "jpg", "jpeg", "webp", "gif", "avif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024   # 5 MB

# ── Session store  {token: expires_unix} ─────────────────────────────────────
_sessions: dict[str, float] = {}
SESSION_TTL = 60 * 60 * 6   # 6 hours

# ── Login rate limiting: max 10 attempts per IP per 15 min ───────────────────
_login_attempts: dict[str, list[float]] = defaultdict(list)
LOGIN_MAX      = 10
LOGIN_WINDOW   = 15 * 60   # seconds

def _check_rate_limit(ip: str) -> bool:
    """Returns True if allowed, False if rate-limited."""
    now = time.time()
    attempts = [t for t in _login_attempts[ip] if now - t < LOGIN_WINDOW]
    _login_attempts[ip] = attempts
    if len(attempts) >= LOGIN_MAX:
        return False
    _login_attempts[ip].append(now)
    return True

def bs_headers():
    return {"Authorization": f"Bearer {API_KEY}"}

# ── News helpers ──────────────────────────────────────────────────────────────

def load_posts() -> list:
    if not os.path.exists(NEWS_FILE):
        return []
    try:
        with open(NEWS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_posts(posts: list):
    with open(NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTS

def safe_filename(filename: str) -> str:
    ext = filename.rsplit(".", 1)[1].lower() if "." in filename else "jpg"
    return f"{uuid.uuid4().hex}.{ext}"

def parse_upstream_json(response):
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return {"error": response.text or "Invalid upstream JSON"}

def upstream_jsonify(response):
    data = parse_upstream_json(response)
    if data is None:
        return jsonify({"error": "Empty upstream response"}), response.status_code
    return jsonify(data), response.status_code

# ── Auth helpers ──────────────────────────────────────────────────────────────

def issue_token() -> str:
    token = secrets.token_hex(32)
    _sessions[token] = time.time() + SESSION_TTL
    return token

def is_valid_token(token: str | None) -> bool:
    if not token:
        return False
    exp = _sessions.get(token)
    if exp is None:
        return False
    if time.time() > exp:
        del _sessions[token]
        return False
    return True

def require_auth():
    """Returns None if ok, or a JSON error response tuple."""
    token = request.headers.get("X-Admin-Token") or request.args.get("token")
    if not is_valid_token(token):
        return jsonify({"error": "Unauthorized"}), 401
    return None

# ── CMS: Auth ─────────────────────────────────────────────────────────────────

@app.route("/cms/login", methods=["POST"])
def cms_login():

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    if not _check_rate_limit(ip):
        return jsonify({"error": "Too many login attempts. Try again in 15 minutes."}), 429

    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict() or {}
    data = data or {}
    pw = data.get("password", "")
    if not pw:
        return jsonify({"error": "Missing password"}), 400

    # Constant-time compare to prevent timing attacks
    if not hmac.compare_digest(pw.encode(), ADMIN_PASSWORD.encode()):
        return jsonify({"error": "Wrong password"}), 401

    token = issue_token()
    return jsonify({"token": token})

@app.route("/cms/logout", methods=["POST"])
def cms_logout():
    token = request.headers.get("X-Admin-Token")
    _sessions.pop(token, None)
    return jsonify({"ok": True})

# ── CMS: Posts ────────────────────────────────────────────────────────────────

@app.route("/cms/posts", methods=["GET"])
def cms_list_posts():
    """Public — returns all posts sorted newest-first."""
    posts = load_posts()
    posts.sort(key=lambda p: p.get("createdAt", 0), reverse=True)
    return jsonify(posts)

@app.route("/cms/posts", methods=["POST"])
def cms_create_post():
    err = require_auth()
    if err: return err

    data = request.get_json(silent=True) or {}
    title    = (data.get("title")    or "").strip()
    excerpt  = (data.get("excerpt")  or "").strip()
    body     = (data.get("body")     or "").strip()
    category = (data.get("category") or "news").strip()
    author   = (data.get("author")   or "Admin").strip()
    image    = (data.get("image")    or "").strip()

    if not title or not excerpt or not body:
        return jsonify({"error": "title, excerpt and body are required"}), 400

    post = {
        "id":        uuid.uuid4().hex,
        "title":     title,
        "excerpt":   excerpt,
        "body":      body,
        "category":  category,
        "author":    author,
        "image":     image,
        "createdAt": int(time.time() * 1000),
    }
    posts = load_posts()
    posts.insert(0, post)
    save_posts(posts)
    return jsonify(post), 201

@app.route("/cms/posts/<post_id>", methods=["DELETE"])
def cms_delete_post(post_id):
    err = require_auth()
    if err: return err

    posts = load_posts()
    new_posts = [p for p in posts if p["id"] != post_id]
    if len(new_posts) == len(posts):
        return jsonify({"error": "Post not found"}), 404

    deleted = next(p for p in posts if p["id"] == post_id)
    img = deleted.get("image", "")
    if img.startswith("/static/uploads/"):
        try:
            os.remove(os.path.join(os.path.dirname(__file__), img.lstrip("/")))
        except OSError:
            pass

    save_posts(new_posts)
    return jsonify({"ok": True})

# ── CMS: Image upload ─────────────────────────────────────────────────────────

@app.route("/cms/upload", methods=["POST"])
def cms_upload_image():
    err = require_auth()
    if err: return err

    if "image" not in request.files:
        return jsonify({"error": "No file field named 'image'"}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": f"Allowed types: {', '.join(ALLOWED_EXTS)}"}), 400

    data = file.read()
    if len(data) > MAX_IMAGE_BYTES:
        return jsonify({"error": "Image exceeds 5 MB limit"}), 413

    fname = safe_filename(file.filename)
    dest  = os.path.join(UPLOAD_DIR, fname)
    with open(dest, "wb") as f:
        f.write(data)

    url = f"/static/uploads/{fname}"
    return jsonify({"url": url}), 201

# ── Serve uploaded images ─────────────────────────────────────────────────────

@app.route("/static/uploads/<filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ── Player ────────────────────────────────────────────────────────────────────

@app.route("/player/<path:tag>")
def get_player(tag):
    if not tag.startswith("%23") and not tag.startswith("#"):
        tag = "%23" + tag
    elif tag.startswith("#"):
        tag = "%23" + tag[1:]
    try:
        r = requests.get(f"{BASE_URL}/players/{tag}", headers=bs_headers())
        return upstream_jsonify(r)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Brawlers ──────────────────────────────────────────────────────────────────

@app.route("/brawlers")
def get_brawlers():
    try:
        r = requests.get(f"{BASE_URL}/brawlers", headers=bs_headers())
        return upstream_jsonify(r)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/player/<path:tag>/brawlers")
def get_player_brawlers(tag):
    if not tag.startswith("%23") and not tag.startswith("#"):
        tag = "%23" + tag
    elif tag.startswith("#"):
        tag = "%23" + tag[1:]
    try:
        r = requests.get(f"{BASE_URL}/players/{tag}", headers=bs_headers())
        if not r.ok:
            return upstream_jsonify(r)

        player = parse_upstream_json(r) or {}
        raw_brawlers = player.get("brawlers", [])
        result = []
        for b in raw_brawlers:
            power = b.get("power", 1)
            has_hypercharge = False
            for key in ("hyperCharge","hypercharge","hasHyperCharge","hasHypercharge","hyperChargeUnlocked"):
                if b.get(key): has_hypercharge = True; break
            if not has_hypercharge:
                for g in b.get("gadgets", []):
                    if "HYPER" in g.get("name","").upper(): has_hypercharge = True; break
            if not has_hypercharge:
                for g in b.get("gears", []):
                    if "HYPER" in g.get("name","").upper(): has_hypercharge = True; break
            if not has_hypercharge:
                for sp in b.get("starPowers", []):
                    if "HYPER" in sp.get("name","").upper(): has_hypercharge = True; break
            if not has_hypercharge:
                for key, val in b.items():
                    if "hyper" in key.lower() and val: has_hypercharge = True; break

            if power < 7:         colour = "grey"
            elif power < 9:       colour = "green"
            elif power < 11:      colour = "yellow"
            elif has_hypercharge: colour = "purple"
            else:                 colour = "red"

            result.append({
                "id": b.get("id"), "name": b.get("name"), "power": power,
                "trophies": b.get("trophies",0), "highestTrophies": b.get("highestTrophies",0),
                "rank": b.get("rank",1), "hasHypercharge": has_hypercharge, "colour": colour,
                "gadgets": len(b.get("gadgets",[])), "starPowers": len(b.get("starPowers",[])),
            })
        order = {"purple":0,"red":1,"yellow":2,"green":3,"grey":4}
        result.sort(key=lambda x: (order[x["colour"]], -x["trophies"]))
        return jsonify({"name": player.get("name"), "tag": player.get("tag"), "brawlers": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Rankings ──────────────────────────────────────────────────────────────────

@app.route("/rankings/<country>/players")
def rank_players(country):
    limit = request.args.get("limit", 200)
    try:
        r = requests.get(f"{BASE_URL}/rankings/{country}/players?limit={limit}", headers=bs_headers())
        return upstream_jsonify(r)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/rankings/<country>/clubs")
def rank_clubs(country):
    limit = request.args.get("limit", 200)
    try:
        r = requests.get(f"{BASE_URL}/rankings/{country}/clubs?limit={limit}", headers=bs_headers())
        return upstream_jsonify(r)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/rankings/<country>/brawlers/<int:brawler_id>")
def rank_brawlers(country, brawler_id):
    limit = request.args.get("limit", 200)
    try:
        r = requests.get(f"{BASE_URL}/rankings/{country}/brawlers/{brawler_id}?limit={limit}", headers=bs_headers())
        return upstream_jsonify(r)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Countdown helpers ─────────────────────────────────────────────────────────

def load_countdowns() -> list:
    if not os.path.exists(COUNTDOWN_FILE):
        return []
    try:
        with open(COUNTDOWN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_countdowns(countdowns: list):
    with open(COUNTDOWN_FILE, "w", encoding="utf-8") as f:
        json.dump(countdowns, f, ensure_ascii=False, indent=2)

# ── Countdown routes ──────────────────────────────────────────────────────────

@app.route("/cms/countdowns", methods=["GET"])
def cms_list_countdowns():
    """Public — returns all countdowns sorted by targetMs."""
    countdowns = load_countdowns()
    countdowns.sort(key=lambda c: c.get("targetMs", 0))
    return jsonify(countdowns)

@app.route("/cms/countdowns", methods=["POST"])
def cms_create_countdown():
    err = require_auth()
    if err: return err

    data     = request.get_json(silent=True) or {}
    title    = (data.get("title")   or "").strip()
    desc     = (data.get("desc")    or "").strip()
    targetMs = data.get("targetMs")
    estimate = bool(data.get("estimate", False))

    if not title or not targetMs:
        return jsonify({"error": "title and targetMs are required"}), 400

    countdown = {
        "id":        uuid.uuid4().hex,
        "title":     title,
        "desc":      desc,
        "targetMs":  int(targetMs),
        "estimate":  estimate,
        "createdAt": int(time.time() * 1000),
    }
    countdowns = load_countdowns()
    countdowns.append(countdown)
    save_countdowns(countdowns)
    return jsonify(countdown), 201

@app.route("/cms/countdowns/<cd_id>", methods=["DELETE"])
def cms_delete_countdown(cd_id):
    err = require_auth()
    if err: return err

    countdowns = load_countdowns()
    new_list = [c for c in countdowns if c["id"] != cd_id]
    if len(new_list) == len(countdowns):
        return jsonify({"error": "Countdown not found"}), 404
    save_countdowns(new_list)
    return jsonify({"ok": True})

# ── Health ────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# ── Debug ─────────────────────────────────────────────────────────────────────

@app.route("/debug/player/<path:tag>/brawlers")
def debug_player_brawlers(tag):
    if not tag.startswith("%23") and not tag.startswith("#"):
        tag = "%23" + tag
    elif tag.startswith("#"):
        tag = "%23" + tag[1:]
    try:
        r = requests.get(f"{BASE_URL}/players/{tag}", headers=bs_headers())
        player = parse_upstream_json(r) or {}
        brawlers = player.get("brawlers", [])
        p11 = [b for b in brawlers if b.get("power") == 11]
        all_keys = sorted({k for b in p11 for k in b.keys()})
        return jsonify({"count_p11": len(p11), "all_keys_found": all_keys, "brawlers": p11})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("Brawlmap server running at http://localhost:5000")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)