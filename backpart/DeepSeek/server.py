from flask import Flask, request, jsonify
import sqlite3

app = Flask(__name__)

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
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
        )
    """)
    conn.commit()
    conn.close()

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

    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_history (session_id, user, assistant) VALUES (?, ?, ?)",
                   (session_id, user_message, assistant_message))
    conn.commit()
    conn.close()

    return jsonify({"message": "Chat saved!"})

# Load last 10 messages
@app.route("/load_chat/<int:session_id>", methods=["GET"])
def load_chat(session_id):
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user, assistant FROM chat_history WHERE session_id = ? ORDER BY id ASC LIMIT 10", (session_id,))
    chat_data = cursor.fetchall()
    
    history = []
    for row in chat_data:
        history.append({"role": "user", "content": row[0]})       # User message
        history.append({"role": "assistant", "content": row[1]})  # Assistant response
    # if history:
    #     session_name = history[0]["content"][:20]  # Trim to 20 characters
    #     cursor.execute("UPDATE chat_sessions SET session_name = ? WHERE session_id = ?", (session_name, session_id))
    conn.close()
    return jsonify(history[::-1])
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
