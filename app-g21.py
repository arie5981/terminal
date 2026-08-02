import os
import time
import base64
import requests
from flask import Flask, render_template_string, request, jsonify
import google.generativeai as genai

app = Flask(__name__)

# ==========================================
# הגדרות ומפתחות מתוך משתני סביבה
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# פונקציות עזר לעבודה מול GitHub API
# ==========================================
def get_github_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

def read_all_lines_from_github_file(file_path):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return ""
    
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}?ref={GITHUB_BRANCH}"
    response = requests.get(url, headers=get_github_headers())
    
    if response.status_code == 200:
        data = response.json()
        content = base64.b64decode(data['content']).decode('utf-8')
        return content
    return ""

def write_full_file_to_github(file_path, content, commit_message):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return False
        
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"
    headers = get_github_headers()
    
    sha = None
    get_res = requests.get(f"{url}?ref={GITHUB_BRANCH}", headers=headers)
    if get_res.status_code == 200:
        sha = get_res.json().get('sha')
        
    encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    payload = {
        "message": commit_message,
        "content": encoded_content,
        "branch": GITHUB_BRANCH
    }
    if sha:
        payload["sha"] = sha
        
    put_res = requests.put(url, json=payload, headers=headers)
    return put_res.status_code in [200, 201]

def append_line_to_github_file(file_path, new_line, commit_message):
    current_content = read_all_lines_from_github_file(file_path)
    if current_content and not current_content.endswith('\n'):
        updated_content = current_content + "\n" + new_line
    else:
        updated_content = current_content + new_line
    return write_full_file_to_github(file_path, updated_content, commit_message)

def get_debug_mode():
    content = read_all_lines_from_github_file("data/debug.txt")
    if content.strip() == "1":
        return 1
    return 0

def write_debug_mode_to_github(mode_value):
    return write_full_file_to_github("data/debug.txt", str(mode_value), f"🤖 עדכון מצב דיבאג ל-{mode_value}")

# ==========================================
# נתיבי האפליקציה (Routes)
# ==========================================

@app.route('/')
def home():
    html_template = """
    <!DOCTYPE html>
    <html lang="he" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ממשק צ'אט AI</title>
        <style>
            body { font-family: system-ui, sans-serif; background-color: #121212; color: #e0e0e0; margin: 0; padding: 20px; display: flex; flex-direction: column; align-items: center; }
            .container { max-width: 700px; width: 100%; background: #1e1e1e; padding: 20px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }
            h1 { text-align: center; color: #4da6ff; }
            #chat-box { height: 350px; overflow-y: auto; border: 1px solid #333; padding: 10px; border-radius: 5px; background: #181818; margin-bottom: 15px; }
            .msg { margin-bottom: 10px; padding: 8px 12px; border-radius: 6px; line-height: 1.4; }
            .user { background-color: #005c99; align-self: flex-start; }
            .bot { background-color: #2d3748; }
            .input-area { display: flex; gap: 10px; }
            input[type="text"] { flex: 1; padding: 10px; border-radius: 5px; border: 1px solid #444; background: #252525; color: #fff; }
            button { padding: 10px 20px; border: none; border-radius: 5px; background: #007acc; color: white; cursor: pointer; font-weight: bold; }
            button:hover { background: #005999; }
            .links { margin-top: 15px; display: flex; gap: 15px; justify-content: center; }
            a { color: #4da6ff; text-decoration: none; font-size: 0.9em; }
            a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>💬 עוזר אישי AI</h1>
            <div id="chat-box"></div>
            <div class="input-area">
                <input type="text" id="user-input" placeholder="רשום את השאלה שלך כאן..." onkeydown="if(event.key === 'Enter') sendQuestion()">
                <button onclick="sendQuestion()">שלח</button>
            </div>
            <div class="links">
                <a href="/view_log" target="_blank">📋 צפה ביומן</a>
                <a href="/debug_on" target="_blank">🐞 הפעל דיבאג</a>
                <a href="/debug_off" target="_blank">🚫 כבה דיבאג</a>
            </div>
        </div>

        <script>
            async function sendQuestion() {
                const input = document.getElementById('user-input');
                const chatBox = document.getElementById('chat-box');
                const text = input.value.trim();
                if (!text) return;

                chatBox.innerHTML += `<div class="msg user"><b>אתה:</b> ${text}</div>`;
                input.value = '';
                chatBox.scrollTop = chatBox.scrollHeight;

                try {
                    const response = await fetch('/ask', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ question: text })
                    });
                    const data = await response.json();
                    chatBox.innerHTML += `<div class="msg bot"><b>בוט:</b> ${data.response}</div>`;
                    chatBox.scrollTop = chatBox.scrollHeight;
                } catch (err) {
                    chatBox.innerHTML += `<div class="msg bot" style="color:#ff6b6b;">שגיאה בתקשורת עם השרת.</div>`;
                }
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template)

@app.route('/ask', methods=['POST'])
def ask():
    data = request.get_json() or {}
    question = data.get("question", "").strip()
    
    if not question:
        return jsonify({"response": "אנא הכנס שאלה תקינה."})

    max_retries = 3
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            input_tokens = model.count_tokens(question).total_tokens
            
            response = model.generate_content(question)
            output_text = response.text
            output_tokens = model.count_tokens(output_text).total_tokens

            if get_debug_mode() == 1:
                log_entry = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Q: {question} | In-Tokens: {input_tokens} | Out-Tokens: {output_tokens}"
                append_line_to_github_file("data/questions.txt", log_entry, "🤖 תיעוד שאלה ומדדי טוקנים")

            return jsonify({"response": output_text})

        except Exception as e:
            error_str = str(e)
            if "503" in error_str or "500" in error_str or "UNAVAILABLE" in error_str:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
            return jsonify({"response": f"אירעה שגיאה בתקשורת מול מודל ה-AI: {error_str}"})

@app.route('/debug_on', methods=['GET', 'POST'])
def debug_on():
    success = write_debug_mode_to_github(1)
    if success:
        return "<h1>מצב דיבאג הופעל בהצלחה (1). השאלות והטוקנים יתועדו ב-GitHub.</h1>"
    return "<h1>שגיאה בהפעלת מצב דיבאג ב-GitHub.</h1>", 500

@app.route('/debug_off', methods=['GET', 'POST'])
def debug_off():
    success = write_debug_mode_to_github(0)
    if success:
        return "<h1>מצב דיבאג כובה בהצלחה (0). תיעוד השאלות הופסק.</h1>"
    return "<h1>שגיאה בכיבוי מצב דיבאג ב-GitHub.</h1>", 500

@app.route('/get_debug_status', methods=['GET'])
def get_debug_status():
    current_mode = get_debug_mode()
    return jsonify({"debug": current_mode})

@app.route('/view_log', methods=['GET'])
def view_log():
    content = read_all_lines_from_github_file("data/questions.txt")
    if not content:
        return "<pre>קובץ הבלוגים ריק או שלא ניתן לקרוא אותו מ-GitHub.</pre>"
    
    lines = [line for line in content.split("\n") if line.strip()]
    reversed_lines = list(reversed(lines))
    formatted_content = "\n".join(reversed_lines)
    
    html_template = """
    <!DOCTYPE html>
    <html lang="he" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>יומן שאלות ומדדי טוקנים</title>
        <style>
            body { font-family: monospace; background-color: #1e1e1e; color: #d4d4d4; padding: 20px; direction: rtl; }
            h2 { color: #569cd6; }
            pre { background-color: #252526; padding: 15px; border-radius: 5px; overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; }
            a { color: #4ec9b0; text-decoration: none; }
        </style>
    </head>
    <body>
        <h2>📋 יומן שאלות ומדדי טוקנים (מהחדש לישן)</h2>
        <p><a href="/">⬅ חזרה לצ'אט</a></p>
        <pre>{{ log_content }}</pre>
    </body>
    </html>
    """
    return render_template_string(html_template, log_content=formatted_content)

@app.route('/clear_log', methods=['GET', 'POST'])
def clear_log():
    success = write_full_file_to_github("data/questions.txt", "", "🤖 ניקוי יומן שאלות")
    if success:
        return "<h1>יומן השאלות נוקה בהצלחה!</h1><p><a href='/view_log'>צפה ביומן</a> | <a href='/'>חזרה לצ'אט</a></p>"
    return "<h1>שגיאה בניקוי יומן השאלות ב-GitHub.</h1>", 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
