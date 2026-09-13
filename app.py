import os
import sqlite3
import uuid
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "memories.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_FILE_SIZE = 8 * 1024 * 1024  # 8 MB per image
MAX_IMAGES = 5

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE * MAX_IMAGES + 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def index():
    conn = db()
    posts = conn.execute("""
        SELECT id, author, body, created_at
        FROM posts
        ORDER BY id DESC
    """).fetchall()

    result = []
    for post in posts:
        images = conn.execute(
            "SELECT filename FROM images WHERE post_id = ? ORDER BY id",
            (post["id"],)
        ).fetchall()
        result.append({
            "id": post["id"],
            "author": post["author"],
            "body": post["body"],
            "created_at": post["created_at"],
            "images": [x["filename"] for x in images]
        })

    conn.close()
    return render_template("index.html", posts=result)

@app.route("/post", methods=["POST"])
def create_post():
    body = request.form.get("body", "").strip()
    name = request.form.get("name", "").strip()
    anonymous = request.form.get("anonymous") == "on"

    if not body and not request.files.getlist("images"):
        flash("Write something or add a picture first. ♡", "error")
        return redirect(url_for("index"))

    author = "Anonymous" if anonymous else (name or "Someone")

    files = [f for f in request.files.getlist("images") if f and f.filename]
    if len(files) > MAX_IMAGES:
        flash(f"You can upload up to {MAX_IMAGES} pictures.", "error")
        return redirect(url_for("index"))

    for f in files:
        if not allowed_file(f.filename):
            flash("Only PNG, JPG, JPEG, GIF, and WEBP pictures are allowed.", "error")
            return redirect(url_for("index"))

    conn = db()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO posts (author, body, created_at) VALUES (?, ?, ?)",
        (author, body, now)
    )
    post_id = cur.lastrowid

    for f in files:
        ext = f.filename.rsplit(".", 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        f.save(os.path.join(UPLOAD_FOLDER, filename))
        conn.execute(
            "INSERT INTO images (post_id, filename) VALUES (?, ?)",
            (post_id, filename)
        )

    conn.commit()
    conn.close()

    flash("Your memory has been shared. ♡", "success")
    return redirect(url_for("index"))
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))

        flash("Incorrect username or password.", "error")

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
def admin_dashboard():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    conn = db()

    posts = conn.execute("""
        SELECT id, author, body, created_at
        FROM posts
        ORDER BY id DESC
    """).fetchall()

    result = []

    for post in posts:
        images = conn.execute(
            "SELECT filename FROM images WHERE post_id = ? ORDER BY id",
            (post["id"],)
        ).fetchall()

        result.append({
            "id": post["id"],
            "author": post["author"],
            "body": post["body"],
            "created_at": post["created_at"],
            "images": [x["filename"] for x in images]
        })

    conn.close()

    return render_template("admin.html", posts=result)
    
    @app.route("/admin/delete/<int:post_id>", methods=["POST"])
def delete_post(post_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    conn = db()

    images = conn.execute(
        "SELECT filename FROM images WHERE post_id = ?",
        (post_id,)
    ).fetchall()

    for image in images:
        file_path = os.path.join(UPLOAD_FOLDER, image["filename"])

        if os.path.exists(file_path):
            os.remove(file_path)

    conn.execute("DELETE FROM images WHERE post_id = ?", (post_id,))
    conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))

    conn.commit()
    conn.close()

    flash("Post deleted successfully.", "success")

    return redirect(url_for("admin_dashboard"))

from flask import session
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.errorhandler(413)
def too_large(_):
    flash("That upload is too large. Please use smaller pictures.", "error")
    return redirect(url_for("index"))

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
