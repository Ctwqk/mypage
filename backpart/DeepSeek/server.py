from flask import Flask, request, jsonify, send_file
import sqlite3
import base64
import os
import shutil

app = Flask(__name__)
media_path = "./deepseek_media"

def delete_folder(folder_path):
    if os.path.exists(folder_path) and os.path.isdir(folder_path):
        shutil.rmtree(folder_path)
        print(f"Deleted folder: {folder_path}")

def init_db():
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_name TEXT NOT NULL,
            user_id TEXT NOT NULL,  -- Can be a UUID if needed
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            user TEXT NOT NULL,
            assistant TEXT NOT NULL,
            image_base64 TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
        )
    """)
    conn.commit()
    conn.close()
    os.makedirs(media_path, exist_ok = True)
init_db()

@app.route("/")
def index():
    return render_template("index.html")  # Serve the HTML page

import uuid

@app.route("/create_session", methods = ["post"])
def create_session():
    data = request.json
    session_name = data.get("session_name")
    user_id = data.get("user_id", str(uuid.uuid4()))

    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_sessions (session_name, user_id) VALUES (?, ?)", (session_name, user_id))
    conn.commit()
    session_id = cursor.lastrowid
    conn.close()
    folder_path = os.path.join(media_path, str(session_id))
    os.makedirs(folder_path, exist_ok=True)
    return jsonify({"session_id": session_id, "user_id": user_id})

@app.route("/get_session", methods=["GET"])
def get_sessions():
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, session_name FROM chat_sessions ORDER BY id DESC")
    sessions = [{"session_id": row[0], "session_name": row[1]} for row in cursor.fetchall()]
    conn.close()
    return jsonify(sessions)

@app.route("/delete_session", methods=["POST"])
def delete_sessions():
    conn = sqlite3.connect("chat.db")
    data = request.json
    session_id = data.get("session_id")
    if not session_id:
        return jsonify()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM chat_history where session_id = ? ", (session_id,))

        cursor.execute("DELETE FROM chat_sessions where id = ?", (session_id,))
        conn.commit()
        folder_path = os.path.join(media_path, str(session_id))
        delete_folder(folder_path)
        return jsonify({"message": f"Session {session_id} deleted successfully!"})
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# Save chat message
@app.route("/save_chat", methods=["POST"])
def save_chat():
    data = request.json
    session_id = data.get("session_id")
    user_message = data.get("user")
    assistant_message = data.get("assistant")
    images = data.get("images", "")
    print(images)

    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_history (session_id, user, assistant, image_base64) VALUES (?, ?, ?, ?)",
                   (session_id, user_message, assistant_message, images))
    conn.commit()
    conn.close()
    print(images)
    return jsonify({"message": "Chat saved!"})

# Load last 10 messages
@app.route("/load_chat/<int:session_id>", methods=["GET"])
def load_chat(session_id):
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user, assistant, image_base64 FROM chat_history WHERE session_id = ? ORDER BY id ASC LIMIT 10", (session_id,))
    chat_data = cursor.fetchall()
    
    history = []
    for row in chat_data:
        history.append({"role": "user", "content": row[0], "images": row[2]})       # User message
        history.append({"role": "assistant", "content": row[1], "images": None})  # Assistant response
    # if history:
    #     session_name = history[0]["content"][:20]  # Trim to 20 characters
    #     cursor.execute("UPDATE chat_sessions SET session_name = ? WHERE session_id = ?", (session_name, session_id))
    conn.close()
    return jsonify(history[::-1])
  

@app.route("/get_base64/<int:session_id>", methods=['POST'])
def get_base64(session_id):
    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400
    image_file = request.files['image']
    image_data = image_file.read()

    # Convert image to base64
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    session_folder = os.path.join(media_path, str(session_id))
    image_path = os.path.join(session_folder, image_file.name)
    image_file.save(image_path)
    return jsonify({"imageBase64": image_base64, "url": image_path})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)



    ## to do list
# 