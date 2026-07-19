from flask import Flask, render_template, request, jsonify, render_template_string
import os
import re
import time
import json
import base64
import requests
from datetime import datetime
from google import genai
from google.genai import types
import markdown 

app = Flask(__name__)

# --- משתנה הדיבאג הגלובלי ---
DEBUG_MODE = 1  # 0 = כבוי (מערכת רגילה), 1 = מצב דיבאג פעיל

# שליפת מפתחות API ומשתני סביבה
gemini_api_key = os.environ.get("GEMINI_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# הגדרה ישירה של ה-Repository שלך
GITHUB_REPO = "arie5981/terminal"

# משתנים גלובליים לנתונים
LINKS_DICTIONARY = {}   
TERMINAL_CONTENT = ""   
CACHE_NAME = None  # ישמור את המזהה הייחודי של ה-Cache בשרתי גוגל

# הגדרת נתיבים לתיקיית הדאטה ולקבצים (משמש לטעינה ראשונית בלבד)
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
CACHE_INFO_FILE = os.path.join(DATA_DIR, "cache_info.json")

# יצירת תיקיית data באופן אוטומטי בשרת אם אינה קיימת
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# הנחיות המערכת הקבועות
SYSTEM_INSTRUCTION = (
    "אתה עוזר דיגיטלי מקצועי, אדיב, ענייני וממוקד של אתר מייצגים בגביה של הביטוח הלאומי.\n"
    "תפקידך לענות בצורה ישירה וברורה על השאלה שנשאלת, מתוך הסתמכות מלאה על קובץ הנהלים המצורף למטה.\n\n"
    "🎯 חוק הניסוח הענייני, הממוקד והתפעולי:\n"
    "1. ענה בצורה עניינית וישירה. אם המשתמש שואל 'איך לבצע' פעולה מסוימת (נתיב או שלבי עבודה), התמקד אך ורק בשלבים התפעוליים המעשיים הנדרשים לביצועה.\n"
    "2. שמור על תמציות: אל תפרט תנאי סף, מגבלות חוקיות, אחוזי הפחתה, תיאור מסלולים חלופיים או הסברים תיאורטיים נלווים המופיעים בנוהל, אלא אם כן המשתמש שאל עליהם במפורש.\n"
    "3. שמור על טון מקצועי ואדיב. נסח את התשובה כמשפט זורם וברור ולא כמילה בודדת (לדוגמה: 'הטלפון למוקד מקצועי הוא...').\n\n"
    "⛔ חוק איסור פרשנות והמצאת עובדות:\n"
    "1. הצמד אך ורק לעובדות הכתובות בדף הרלוונטי. אל תפרש, אל תסביר את הלוגיקה, ואל תוסיף מידע או שלבים שלא מופיעים בטקסט במפורש.\n"
    "2. ⚠️ קריטי: אל תעתיק תיאורי מיקום, הכוונות או סוגריים (כמו 'שמאל למעלה') מנוהל אחד למשנהו! הצג את נתיב הניווט (מיקום השירות) בדיוק כפי שהוא כתוב בנוהל הספציפי של השאלה הנוכחית, ללא שום תוספת פרשנית.\n"
    "3. אם המשתמש שואל אם משהו אפשרי, וקיימת דרך לבצע זאת, פתח מיד בהנחיות המעשיות לביצוע.\n\n"
    "🚫 חוק איסור שלבי כניסה והתחברות:\n"
    "1. חל איסור מוחלט לפתוח במשפטים כגון: 'היכנס לאתר', 'התחבר למערכת' וכדומה. הנחת היסוד היא שהמשתמש כבר בפנים.\n"
    "2. התחל את השלב הראשון ישירות מהפעולה המעשית הראשונה בתוך האתר.\n\n"
    "✨ חוק הדגשה והבלטה:\n"
    "1. חובה להדגיש באמצעות כוכביות כפולות (לדוגמה: **שלב 1: גישה לרשימה**) כותרות שלבים או מונחי מפתח תפעוליים חשובים (שמות כפתורים, סטטוסים, או אזהרות כמו **שים לב:**).\n\n"
    "🔗 חוקי קישורים וסוגריים מרובעים:\n"
    "- ודא שכל שם של טופס, אתר, מערכת, מוקד או כתובת מייל שמופיעים בטקסט, עטופים בדיוק בסוגריים מרובעים כפי שהם מופיעים בנהלים."
)

def clean_html_for_history(text):
    """מנקה תגיות HTML מהיסטוריית השיחה בצורה בטוחה ומנועת קריסות"""
    if not text or not isinstance(text, str):
        return ""
    if "<br><hr>" in text:
        text = text.split("<br><hr>")[0]
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()

def append_line_to_github_file(repo_filepath, new_line_content):
    """פונקציית עזר שמוסיפה שורה חדשה לקובץ ישירות בתוך ה-Repository ב-GitHub"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("🚨 חסרים פרטי הזדהות של GITHUB_TOKEN או GITHUB_REPO בשרת.")
        return False
        
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{repo_filepath}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        res = requests.get(url, headers=headers)
        current_content = ""
        sha = None
        
        if res.status_code == 200:
            file_data = res.json()
            sha = file_data.get("sha")
            current_content = base64.b64decode(file_data.get("content")).decode("utf-8")
        elif res.status_code == 404:
            print(f"⚠️ הקובץ {repo_filepath} לא נמצא ב-GitHub. ננסה ליצור אותו.")
        else:
            print(f"⚠️ שגיאה במשיכת קובץ מ-GitHub (סטטוס {res.status_code}): {res.text}")
            return False

        if current_content and not current_content.endswith("\n"):
            current_content += "\n"
        updated_content = current_content + new_line_content

        payload = {
            "message": f"🤖 מערכת דיבאג: עדכון אוטומטי של {repo_filepath}",
            "content": base64.b64encode(updated_content.encode("utf-8")).decode("utf-8")
        }
        if sha:
            payload["sha"] = sha
            
        put_res = requests.put(url, headers=headers, json=payload)
        if put_res.status_code in [200, 201]:
            print(f"✅ הקובץ {repo_filepath} עודכן בהצלחה ב-GitHub.")
            return True
        else:
            print(f"🚨 שגיאה בכתיבה ל-GitHub (סטטוס {put_res.status_code}): {put_res.text}")
            return False
            
    except Exception as e:
        print(f"🚨 שגיאה חריגה בתקשורת מול GitHub API: {e}")
        return False

def read_all_lines_from_github_file(repo_filepath):
    """קורא את כל התוכן של קובץ מתוך GitHub"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return ""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{repo_filepath}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            file_data = res.json()
            return base64.b64decode(file_data.get("content")).decode("utf-8")
    except Exception as e:
        print(f"Error reading from GitHub: {e}")
    return ""

def load_terminal_data_directly():
    """טעינת הקישורים מתוך קובץ info.txt בנפרד, וטעינת הנהלים מתוך Terminal.txt"""
    global LINKS_DICTIONARY, TERMINAL_CONTENT
    
    info_path = os.path.join(DATA_DIR, 'info.txt')
    if os.path.exists(info_path):
        with open(info_path, 'r', encoding='utf-8') as f:
            info_content = f.read()
        link_matches = re.findall(r'>>([^:]+):\s*([^\s<<]+)<<', info_content)
        for name, url in link_matches:
            LINKS_DICTIONARY[name.strip()] = url.strip()
        print(f"✅ Loaded {len(LINKS_DICTIONARY)} links/phones from info.txt")

    terminal_path = os.path.join(DATA_DIR, 'Terminal.txt')
    if os.path.exists(terminal_path):
        with open(terminal_path, 'r', encoding='utf-8') as f:
            content = f.read()
        TERMINAL_CONTENT = content.replace('\r\n', '\n').replace('\r', '\n')
        print("✅ Loaded Terminal.txt content for Gemini.")

load_terminal_data_directly()

def get_or_create_context_cache(client):
    """מנהל את יצירת או שליפת ה-Context Cache לטווח של שעה"""
    global CACHE_NAME
    
    if not CACHE_NAME and os.path.exists(CACHE_INFO_FILE):
        try:
            with open(CACHE_INFO_FILE, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
                CACHE_NAME = saved_data.get("cache_name")
        except Exception as e:
            print(f"⚠️ שגיאה בקריאת קובץ cache_info.json: {e}")
    
    if CACHE_NAME:
        try:
            existing_cache = client.caches.get(name=CACHE_NAME)
            if hasattr(existing_cache, 'state') and str(existing_cache.state) not in ["STATE_ACTIVE", "ACTIVE"]:
                CACHE_NAME = None
            else:
                return existing_cache
        except Exception:
            CACHE_NAME = None

    full_cache_text = (
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"=== קובץ הנהלים הרשמי והמלא (CONTEXT) ===\n{TERMINAL_CONTENT}\n=========================================\n"
    )
    
    cache = client.caches.create(
        model='gemini-2.5-flash',
        config=types.CreateCachedContentConfig(
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=full_cache_text)])],
            ttl="3600s"
        )
    )
    CACHE_NAME = cache.name
    
    try:
        with open(CACHE_INFO_FILE, "w", encoding="utf-8") as f:
            json.dump({"cache_name": CACHE_NAME, "created_at": time.time()}, f)
    except Exception as e:
        print(f"⚠️ שגיאה בשמירת מזהה ה-Cache לקובץ: {e}")
        
    return cache

def inject_hyperlinks(text):
    """מזריק את הנתונים מתוך info.txt לתשובה הסופית שחוזרת מג'מיני"""
    if not text:
        return ""
        
    for name, url in LINKS_DICTIONARY.items():
        placeholder = f"[{name}]"
        if placeholder in text:
            if re.match(r'^[\d\-]+$', url):
                text = text.replace(placeholder, url)
                continue
            if "@" in url and not url.startswith("http"):
                hyperlink = f'<a href="mailto:{url}" style="color: #007bff; text-decoration: underline; font-weight: bold;">{name}</a>'
                text = text.replace(placeholder, hyperlink)
            else:
                hyperlink = f'<a href="{url}" style="color: #007bff; text-decoration: underline; font-weight: bold;" target="_blank">{name}</a>'
                text = text.replace(placeholder, hyperlink)
                
    return text
    
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json or {}
    user_question = data.get('question', '')
    user_question = user_question.strip() if user_question else ""
    chat_history = data.get('history', [])

    if not user_question:
        return jsonify({"response": "לא התקבלה שאלה תקינה."})

    if not TERMINAL_CONTENT:
        return jsonify({"response": "מערכת הנתונים של הטרמינל אינה טעונה בשרת."})

    trimmed_history = chat_history[-10:] if len(chat_history) > 10 else chat_history

    formatted_contents = []
    for msg in trimmed_history:
        if not msg:
            continue
        role = msg.get("role")
        gemini_role = "user" if role == "user" else "model"
        
        content_text = clean_html_for_history(msg.get("content", ""))
        if not content_text: 
            continue

        formatted_contents.append(
            types.Content(
                role=gemini_role,
                parts=[types.Part.from_text(text=content_text)]
            )
        )

    formatted_contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=f"השאלה הנוכחית של המשתמש: {user_question}")]
        )
    )

    max_retries = 3
    retry_delay = 1.5

    for attempt in range(max_retries):
        try:
            client = genai.Client(api_key=gemini_api_key)
            cache_content = get_or_create_context_cache(client)

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=formatted_contents,
                config=types.GenerateContentConfig(
                    cached_content=cache_content.name,
                    temperature=0.0
                )
            )
            
            if not response or not response.text:
                raise ValueError("התשובה שהתקבלה מגוגל ריקה.")
                
            raw_answer = response.text
            html_answer = markdown.markdown(raw_answer, extensions=['nl2br'])
            final_answer = inject_hyperlinks(html_answer)
            
            p_tokens = 0
            c_tokens = 0
            o_tokens = 0
            
            if response.usage_metadata:
                p_tokens = response.usage_metadata.prompt_token_count
                c_tokens = response.usage_metadata.cached_content_token_count
                o_tokens = response.usage_metadata.candidates_token_count
            
            usage_info = {
                "prompt_tokens": p_tokens,
                "cached_tokens": c_tokens,
                "output_tokens": o_tokens
            }

            if DEBUG_MODE == 1:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log_entry = (
                    f"[{timestamp}] השאלה: {user_question} | "
                    f"קלט: {p_tokens}, מתוך ה-Cache: {c_tokens}, פלט: {o_tokens}\n"
                )
                append_line_to_github_file("data/questions.txt", log_entry)
            
            return jsonify({
                "response": final_answer,
                "debug": DEBUG_MODE,
                "original_question": user_question,
                "usage": usage_info
            })

        except Exception as e:
            error_str = str(e)
            if "503" in error_str or "500" in error_str or "UNAVAILABLE" in error_str:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
            
            friendly_message = (
                "העוזר הדיגיטלי חווה כרגע עומס רגעי זמני בשרתי גוגל. אנא נסה שנית."
            )
            return jsonify({
                "response": friendly_message,
                "debug": DEBUG_MODE,
                "original_question": user_question
            })

@app.route('/save_remark', methods=['POST'])
def save_remark():
    if DEBUG_MODE != 1:
        return jsonify({"status": "error", "message": "Debug mode is off"}), 403
        
    try:
        data = request.json
        remark_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "author": data.get("author", "").strip() or "אנונימי",
            "remark": data.get("remark", "").strip(),
            "question": data.get("question", "").strip(),
            "response": data.get("response", "").strip()
        }

        remark_line = json.dumps(remark_entry, ensure_ascii=False) + "\n"
        append_line_to_github_file("data/remarks.txt", remark_line)

        return jsonify({"status": "success", "message": "ההערה נשמרה בהצלחה"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/remarks', methods=['GET'])
def show_remarks():
    # 1. קריאת הערות (remarks.txt)
    remarks_list = []
    github_remarks = read_all_lines_from_github_file("data/remarks.txt")
    if github_remarks:
        for line in github_remarks.splitlines():
            if line.strip():
                try:
                    remarks_list.append(json.loads(line.strip()))
                except Exception:
                    continue
    remarks_list.reverse()

    # 2. קריאת שאלות (questions.txt)
    questions_list = []
    github_questions = read_all_lines_from_github_file("data/questions.txt")
    if github_questions:
        for line in github_questions.splitlines():
            if line.strip():
                questions_list.append(line.strip())
    questions_list.reverse()

    return render_template_string(
        REMARKS_HTML_TEMPLATE, 
        remarks=remarks_list, 
        questions=questions_list
    )

# --- תבנית ה-HTML לעמוד ה-Remarks המורחב עם לשוניות ---
REMARKS_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ניהול ומעקב דיבאג - מייצגים</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f6f9; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 1300px; margin: 0 auto; }
        h1 { color: #1e3a8a; border-bottom: 3px solid #1e3a8a; padding-bottom: 10px; margin-bottom: 20px; font-size: 24px; }
        
        /* עיצוב לשוניות */
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; border-bottom: 2px solid #ccd0d5; padding-bottom: 10px; }
        .tab-button { background-color: #e4e6eb; border: none; padding: 10px 20px; font-size: 16px; font-weight: bold; border-radius: 6px; cursor: pointer; color: #4b5563; transition: all 0.2s; }
        .tab-button.active { background-color: #1e3a8a; color: white; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .summary-badge { background-color: #1e3a8a; color: white; padding: 4px 12px; border-radius: 12px; font-size: 14px; display: inline-block; margin-bottom: 15px; }
        .table-container { background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); overflow: hidden; }
        table { width: 100%; border-collapse: collapse; text-align: right; table-layout: fixed; }
        th { background-color: #1e3a8a; color: white; padding: 12px 15px; font-weight: bold; font-size: 15px; }
        td { padding: 12px 15px; border-bottom: 1px solid #e4e6eb; font-size: 14px; vertical-align: top; line-height: 1.5; word-wrap: break-word; }
        tr:hover { background-color: #f8fafc; }
        
        .timestamp { color: #666; font-size: 12px; white-space: nowrap; }
        .author { font-weight: bold; color: #007bff; }
        .remark-text { background-color: #fff9db; padding: 6px 10px; border-right: 3px solid #fcc419; border-radius: 4px; font-weight: 500; }
        .box-content { max-height: 200px; overflow-y: auto; background-color: #f8f9fa; padding: 8px; border-radius: 4px; font-size: 13px; white-space: pre-line; }
        .no-remarks { text-align: center; padding: 40px; color: #666; font-size: 16px; }
        
        /* יומן שאלות פשוט */
        .questions-list { background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 15px; }
        .question-item { padding: 12px; border-bottom: 1px solid #e4e6eb; font-family: monospace; font-size: 14px; direction: ltr; text-align: left; }
        .question-item:last-child { border-bottom: none; }
    </style>
</head>
<body>
<div class="container">
    <h1>📝 מרכז בקרה ודיבאג - אתר מייצגים</h1>
    
    <div class="tabs">
        <button class="tab-button active" onclick="switchTab('remarks-tab')">💬 הערות ופידבק משתמשים</button>
        <button class="tab-button" onclick="switchTab('questions-tab')">📊 יומן שאלות וטוקנים (questions.txt)</button>
    </div>

    <!-- לשונית הערות -->
    <div id="remarks-tab" class="tab-content active">
        <div class="summary-badge">סה"כ הערות שנאספו: {{ remarks|length }}</div>
        <div class="table-container">
            {% if remarks %}
            <table>
                <thead>
                    <tr>
                        <th style="width: 15%;">זמן ומעיר</th>
                        <th style="width: 25%;">ההערה שנכתבה</th>
                        <th style="width: 25%;">השאלה המקורית</th>
                        <th style="width: 35%;">תשובת הבוט (מורחב)</th>
                    </tr>
                </thead>
                <tbody>
                    {% for r in remarks %}
                    <tr>
                        <td>
                            <div class="timestamp">{{ r.timestamp }}</div>
                            <div class="author">{{ r.author }}</div>
                        </td>
                        <td>
                            <div class="remark-text">{{ r.remark }}</div>
                        </td>
                        <td>
                            <div class="box-content">{{ r.question }}</div>
                        </td>
                        <td>
                            <div class="box-content" style="background-color: #f1f5f9;">{{ r.response | striptags }}</div>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="no-remarks">טרם נרשמו הערות במערכת.</div>
            {% endif %}
        </div>
    </div>

    <!-- לשונית שאלות -->
    <div id="questions-tab" class="tab-content">
        <div class="summary-badge">סה"כ שאלות ביומן: {{ questions|length }}</div>
        <div class="questions-list">
            {% if questions %}
                {% for q in questions %}
                    <div class="question-item">{{ q }}</div>
                {% endfor %}
            {% else %}
                <div class="no-remarks">יומן השאלות ריק כרגע.</div>
            {% endif %}
        </div>
    </div>
</div>

<script>
    function switchTab(tabId) {
        // הסתרת כל הלשוניות
        document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.tab-button').forEach(el => el.classList.remove('active'));
        
        // הצגת הלשונית הנבחרת
        document.getElementById(tabId).classList.add('active');
        event.currentTarget.classList.add('active');
    }
</script>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
