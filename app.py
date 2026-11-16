from flask import Flask, render_template, request, jsonify, render_template_string
import os
import re
import time
import json
import base64
import requests
import threading
from datetime import datetime
from google import genai
from google.genai import types
import markdown

app = Flask(__name__)

# שליפת מפתחות API ומשתני סביבה
gemini_api_key = os.environ.get("GEMINI_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = "arie5981/terminal"

# משתנים גלובליים לנתונים ולניהול ה-Cache
LINKS_DICTIONARY = {}
TERMINAL_CONTENT = ""
CACHE_NAME = None
CACHE_DISABLED_UNTIL = 0
LAST_CACHE_ERROR = ""

CACHE_MODEL_NAME = "models/gemini-2.5-flash"
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
CACHE_INFO_FILE = os.path.join(DATA_DIR, "cache_info.json")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# הנחיות המערכת הקבועות שלך
SYSTEM_INSTRUCTION = (
    "אתה עוזר דיגיטלי מקצועי, אדיב, ענייני וממוקד של אתר מייצגים בגביה של הביטוח הלאומי.\n"
    "תפקידך לענות בצורה ישירה וברורה על השאלה שנשאלת, מתוך הסתמכות מלאה על קובץ הנהלים המצורף למטה.\n\n"
    "🎯 חוק הניסוח הענייני, הממוקד והתפעולי:\n"
    "1. ענה בצורה עניינית וישירה. אם המשתמש שואל 'איך לבצע' פעולה מסוימת (נתיב או שלבי עבודה), התמקד אך ורק בשלבים התפעוליים המעשיים הנדרשים לביצועה.\n"
    "2. שמור על תמציות: אל תפרט תנאי סף, מגבלות חוקיות, אחוזי הפחתה, תיאור מסלולים חלופיים או הסברים תיאורטיים נלווים המופיעים בנוהל, אלא אם כן המשתמש שאל עליהם במפורש.\n"
    "3. 🔀 חוק מסלול ברירת מחדל (פיצול תהליכים): אם בנוהל מופיעים מספר מסלולים לביצוע אותה פעולה (כגון: 'עם כרטיס אשראי' / 'ללא כרטיס אשראי'):\n"
    "   - הצג אך ורק את המסלול הראשי והשכיח ביותר.\n"
    "   - בסוף התשובה הוסף שורה קצרה אחת בלבד: 'למקרים של [תיאור המקרה החריג, למשל: חוסר בכרטיס אשראי] - יש לפעול לפי [שם המסלול/הפתרון הקצר]'.\n"
    "4. שמור על טון מקצועי ואדיב. נסח את התשובה כמשפט זורם וברור ולא כמילה בודדת (לדוגמה: 'הטלפון למוקד מקצועי הוא...').\n"
    "5. ⚠️ חובה להכליל הערות קריטיות: אם בנוהל הרלוונטי מופיעה התייחסות המוגדרת כ-'חשוב!:' (או סייג מרכזי), חובה לכלול התייחסות זו בתשובה ולהדגישה (לדוגמה: '**שים לב:** אישור מרכז לא כולל אישור מילואים...').\n\n"
    "⛔ חוק איסור פרשנות והמצאת עובדות:\n"
    "1. הצמד אך ורק לעובדות הכתובות בדף הרלוונטי. אל תפרש, אל תסביר את הלוגיקה, ואל תוסיף מידע או שלבים שלא מופיעים בטקסט במפורש.\n"
    "2. ⚠️ קריטי: אל תעתיק תיאורי מיקום, הכוונות או סוגריים (כמו 'שמאל למעלה') מנוהל אחד למשנהו! הצג את נתיב הניווט (מיקום השירות) בדיוק כפי שהוא כתוב בנוהל הספציפי של השאלה הנוכחית, ללא שום תוספת פרשנית.\n"
    "3. אם המשתמש שואל אם משהו אפשרי, וקיימת דרך לבצע זאת, פתח מיד בהנחיות המעשיות לביצוע.\n\n"
    "🚫 חוק איסור שלבי כניסה והתחברות:\n"
    "1. חל איסור מוחלט לפתוח במשפטים כגון: 'היכנס לאתר', 'התחבר למערכת' וכדומה. הנחת היסוד היא שהמשתמש כבר בפנים.\n"
    "2. התחל את השלב הראשון ישירות מהפעולה המעשית הראשונה בתוך האתר.\n\n"
    "🎨 חוקי עיצוב, קריאות וריווח (Markdown):\n"
    "1. הפרדה בין סעיפים/מסלולים: חובה להפריד בין סעיפים ראשיים ברשימה באמצעות קו מפריד (---) או שורות ריקות כפולות.\n"
    "2. הזחת תבליטים (Indentation): הקפד על הזחה של 3 רווחים לפחות בתחילת שורת תבליט השייכת לסעיף ממוספר, כדי ליצור היררכיה חזותית ברורה.\n"
    "3. תמציתיות בשורת שלב: צרף את תיאור השלב באותה השורה של כותרת השלב (דוגמה: '* **שלב 1: גישה למסך** — עבור אל...').\n\n"
    "✨ חוק הדגשה והבלטה:\n"
    "1. חובה להדגיש באמצעות כוכביות כפולות (לדוגמה: **שלב 1: גישה לרשימה**) כותרות שלבים או מונחי מפתח תפעוליים חשובים (שמות כפתורים, סטטוסים, או אזהרות כמו **שים לב:**).\n\n"
    "🔗 חוקי קישורים, סוגריים מרובעים, סרטונים ומספרים:\n"
    "1. ודא שכל שם של טופס, אתר, מערכת, מוקד או כתובת מייל שמופיעים בטקסט, עטופים בדיוק בסוגריים מרובעים כפי שהם מופיעים בנהלים.\n"
    "2. 📞 מספרי טלפון/מוקד עם כוכבית: מספרי מוקד הכוללים כוכבית (כמו `6050*`) נתווסף סביבם קוד נקי בפורמט `6050*` כדי למנוע שיבושי תצוגה.\n"
    "3. 🎬 סרטוני הדרכה: אם בנוהל הרלוונטי מופיע אזכור לסרטון (כגון 'סרטון: ... [שם הסרטון]'), חובה להוסיף בסוף התשובה שורה נפרדת בדיוק בנוסח: 'סרטון הדרכה: [שם הסרטון]' תוך שמירה מדויקת על השם בתוך הסוגריים המרובעים."
)

def get_gemini_client():
    """יוצר מופע של Gemini Client עם v1beta לתמיכה מלאה ב-Context Caching"""
    return genai.Client(
        api_key=gemini_api_key,
        http_options={'api_version': 'v1beta'}
    )

def get_debug_mode():
    content = read_all_lines_from_github_file("data/debug.txt")
    if content and content.strip() in ["1", "0"]:
        return int(content.strip())
    return 0

def write_debug_mode_to_github(mode_value):
    return write_full_file_to_github("data/debug.txt", str(mode_value), f"🤖 מערכת דיבאג: עדכון סטטוס ל-{mode_value}")

def get_voice_mode():
    content = read_all_lines_from_github_file("data/voice.txt")
    if content and content.strip() in ["1", "0"]:
        return int(content.strip())
    return 1

def write_voice_mode_to_github(mode_value):
    return write_full_file_to_github("data/voice.txt", str(mode_value), f"🎤 מערכת בקרה: עדכון סטטוס קול ל-{mode_value}")

def clean_html_for_history(text):
    if not text or not isinstance(text, str):
        return ""
    if "<br><hr>" in text:
        text = text.split("<br><hr>")[0]
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()

def append_line_to_github_file(repo_filepath, new_line_content):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return False
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{repo_filepath}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers)
        current_content = ""
        sha = None
        if res.status_code == 200:
            file_data = res.json()
            sha = file_data.get("sha")
            current_content = base64.b64decode(file_data.get("content")).decode("utf-8")

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
        return put_res.status_code in [200, 201]
    except Exception:
        return False

def write_full_file_to_github(repo_filepath, full_content, commit_message):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return False
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{repo_filepath}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers)
        sha = res.json().get("sha") if res.status_code == 200 else None
        payload = {
            "message": commit_message,
            "content": base64.b64encode(full_content.encode("utf-8")).decode("utf-8")
        }
        if sha:
            payload["sha"] = sha
        put_res = requests.put(url, headers=headers, json=payload)
        return put_res.status_code in [200, 201]
    except Exception:
        return False

def read_all_lines_from_github_file(repo_filepath):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return ""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{repo_filepath}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            return base64.b64decode(res.json().get("content")).decode("utf-8")
    except Exception:
        pass
    return ""

def load_terminal_data_directly():
    global LINKS_DICTIONARY, TERMINAL_CONTENT
    info_path = os.path.join(DATA_DIR, 'info.txt')
    if os.path.exists(info_path):
        with open(info_path, 'r', encoding='utf-8') as f:
            info_content = f.read()
        link_matches = re.findall(r'>>([^:]+):\s*([^\s<<]+)<<', info_content)
        for name, url in link_matches:
            LINKS_DICTIONARY[name.strip()] = url.strip()

    terminal_path = os.path.join(DATA_DIR, 'Terminal.txt')
    if os.path.exists(terminal_path):
        with open(terminal_path, 'r', encoding='utf-8') as f:
            content = f.read()
        TERMINAL_CONTENT = content.replace('\r\n', '\n').replace('\r', '\n')

load_terminal_data_directly()

def reset_cache_state():
    """מנקה את מזהה ה-Cache מהזיכרון ומהקובץ המקומי"""
    global CACHE_NAME
    CACHE_NAME = None
    if os.path.exists(CACHE_INFO_FILE):
        try:
            os.remove(CACHE_INFO_FILE)
        except Exception:
            pass

def get_or_create_context_cache(client):
    """יוצר או שולף Context Cache מול v1beta ללא לולאות מיותרות"""
    global CACHE_NAME, CACHE_DISABLED_UNTIL, LAST_CACHE_ERROR

    if time.time() < CACHE_DISABLED_UNTIL:
        return None

    if not CACHE_NAME and os.path.exists(CACHE_INFO_FILE):
        try:
            with open(CACHE_INFO_FILE, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
                CACHE_NAME = saved_data.get("cache_name")
        except Exception:
            reset_cache_state()

    if CACHE_NAME:
        try:
            existing_cache = client.caches.get(name=CACHE_NAME)
            if hasattr(existing_cache, 'state') and str(existing_cache.state) not in ["STATE_ACTIVE", "ACTIVE"]:
                reset_cache_state()
            else:
                LAST_CACHE_ERROR = ""
                return existing_cache
        except Exception:
            reset_cache_state()

    full_cache_text = (
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"=== קובץ הנהלים הרשמי והמלא (CONTEXT) ===\n{TERMINAL_CONTENT}\n=========================================\n"
    )

    try:
        cache = client.caches.create(
            model=CACHE_MODEL_NAME,
            config=types.CreateCachedContentConfig(
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=full_cache_text)]
                    )
                ],
                ttl="3600s"
            )
        )
        CACHE_NAME = cache.name
        LAST_CACHE_ERROR = ""
        try:
            with open(CACHE_INFO_FILE, "w", encoding="utf-8") as f:
                json.dump({"cache_name": CACHE_NAME, "created_at": time.time()}, f)
        except Exception:
            pass
        return cache
    except Exception as e:
        CACHE_DISABLED_UNTIL = time.time() + 600
        LAST_CACHE_ERROR = str(e)
        reset_cache_state()
        return None

def inject_hyperlinks(text):
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
            else:
                hyperlink = f'<a href="{url}" style="color: #007bff; text-decoration: underline; font-weight: bold;" target="_blank">{name}</a>'
            text = text.replace(placeholder, hyperlink)
    return text

@app.route('/')
def home():
    current_voice_mode = get_voice_mode()
    return render_template('index.html', voice_mode=current_voice_mode)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json or {}
    user_question = data.get('question', '').strip()
    chat_history = data.get('history', [])

    if not user_question:
        return jsonify({"response": "לא התקבלה שאלה תקינה."})

    if not TERMINAL_CONTENT:
        return jsonify({"response": "מערכת הנתונים של הטרמינל אינה טעונה בשרת."})

    current_debug_mode = get_debug_mode()
    trimmed_history = chat_history[-10:] if len(chat_history) > 10 else chat_history

    history_contents = []
    for msg in trimmed_history:
        if not msg:
            continue
        role = msg.get("role")
        gemini_role = "user" if role == "user" else "model"
        content_text = clean_html_for_history(msg.get("content", ""))
        if content_text:
            history_contents.append(
                types.Content(role=gemini_role, parts=[types.Part.from_text(text=content_text)])
            )

    history_contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=f"השאלה הנוכחית של המשתמש: {user_question}")])
    )

    max_retries = 3
    retry_delay = 1.5

    for attempt in range(max_retries):
        try:
            client = get_gemini_client()
            cache_content = get_or_create_context_cache(client)

            if cache_content and hasattr(cache_content, 'name'):
                response = client.models.generate_content(
                    model=CACHE_MODEL_NAME,
                    contents=history_contents,
                    config=types.GenerateContentConfig(
                        cached_content=cache_content.name,
                        temperature=0.0
                    )
                )
            else:
                direct_contents = [
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=f"{SYSTEM_INSTRUCTION}\n\nקובץ הנהלים:\n{TERMINAL_CONTENT}")]
                    )
                ] + history_contents

                response = client.models.generate_content(
                    model=CACHE_MODEL_NAME,
                    contents=direct_contents,
                    config=types.GenerateContentConfig(temperature=0.0)
                )

            if not response or not response.text:
                raise ValueError("התשובה שהתקבלה מגוגל ריקה.")

            raw_answer = response.text
            html_answer = markdown.markdown(raw_answer, extensions=['nl2br'])
            final_answer = inject_hyperlinks(html_answer)

            p_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
            c_tokens = response.usage_metadata.cached_content_token_count if response.usage_metadata else 0
            o_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0

            usage_info = {
                "prompt_tokens": p_tokens,
                "cached_tokens": c_tokens or 0,
                "output_tokens": o_tokens
            }

            if current_debug_mode == 1:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                err_note = f" | שגיאת Cache: {LAST_CACHE_ERROR}" if LAST_CACHE_ERROR else ""
                log_entry = (
                    f"[{timestamp}] השאלה: {user_question} | "
                    f"קלט: {p_tokens}, מתוך ה-Cache: {c_tokens or 0}, פלט: {o_tokens}{err_note}\n"
                )
                threading.Thread(target=append_line_to_github_file, args=("data/questions.txt", log_entry)).start()

            return jsonify({
                "response": final_answer,
                "debug": current_debug_mode,
                "original_question": user_question,
                "usage": usage_info if current_debug_mode == 1 else {}
            })

        except Exception as e:
            error_str = str(e)
            if "404" in error_str or "NOT_FOUND" in error_str:
                reset_cache_state()
                if attempt < max_retries - 1:
                    continue

            if "503" in error_str or "500" in error_str or "UNAVAILABLE" in error_str:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue

            return jsonify({
                "response": f"שגיאת מערכת מגוגל: {error_str}",
                "debug": current_debug_mode,
                "original_question": user_question
            })

@app.route('/save_remark', methods=['POST'])
def save_remark():
    if get_debug_mode() != 1:
        return jsonify({"status": "error", "message": "Debug mode is off"}), 403
    try:
        data = request.json or {}
        remark_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "author": data.get("author", "").strip() or "אנונימי",
            "remark": data.get("remark", "").strip(),
            "question": data.get("question", "").strip(),
            "response": data.get("response", "").strip()
        }
        threading.Thread(target=append_line_to_github_file, args=("data/remarks.txt", json.dumps(remark_entry, ensure_ascii=False) + "\n")).start()
        return jsonify({"status": "success", "message": "ההערה נשלחה לשמירה בהצלחה"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/delete_remark', methods=['POST'])
def delete_remark():
    try:
        index = (request.json or {}).get("index")
        github_remarks = read_all_lines_from_github_file("data/remarks.txt")
        lines = [l for l in github_remarks.splitlines() if l.strip()]
        if index is None or index < 0 or index >= len(lines):
            return jsonify({"status": "error", "message": "הערה לא נמצאה"}), 404
        deleted_line = lines.pop(index)
        append_line_to_github_file("data/deleted_remarks.txt", deleted_line + "\n")
        success = write_full_file_to_github("data/remarks.txt", "\n".join(lines) + ("\n" if lines else ""), "🤖 מערכת דיבאג: מחיקת הערה")
        return jsonify({"status": "success" if success else "error", "message": "ההערה נמחקה בהצלחה"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/update_debug_toggle', methods=['POST'])
def update_debug_toggle():
    new_mode = (request.json or {}).get("debug_mode")
    if new_mode not in [0, 1]:
        return jsonify({"status": "error", "message": "ערך לא תקין"}), 400
    success = write_debug_mode_to_github(new_mode)
    return jsonify({"status": "success" if success else "error", "message": f"מצב דיבאג עודכן ל-{new_mode}"})

@app.route('/update_voice_toggle', methods=['POST'])
def update_voice_toggle():
    new_mode = (request.json or {}).get("voice_mode")
    if new_mode not in [0, 1]:
        return jsonify({"status": "error", "message": "ערך לא תקין"}), 400
    success = write_voice_mode_to_github(new_mode)
    return jsonify({"status": "success" if success else "error", "message": f"הצגת קול עודכנה ל-{new_mode}"})

@app.route('/remarks', methods=['GET'])
def show_remarks():
    remarks_list = []
    github_remarks = read_all_lines_from_github_file("data/remarks.txt")
    if github_remarks:
        for idx, line in enumerate([l for l in github_remarks.splitlines() if l.strip()]):
            try:
                item = json.loads(line)
                item['original_index'] = idx
                remarks_list.append(item)
            except Exception:
                pass
    remarks_list.reverse()

    questions_list = [q.strip() for q in read_all_lines_from_github_file("data/questions.txt").splitlines() if q.strip()]
    questions_list.reverse()

    return render_template_string(
        REMARKS_HTML_TEMPLATE,
        remarks=remarks_list,
        questions=questions_list,
        current_debug_mode=get_debug_mode(),
        current_voice_mode=get_voice_mode()
    )

REMARKS_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>מרכז בקרה ודיבאג - מייצגים</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f6f9; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 1300px; margin: 0 auto; }
        h1 { color: #1e3a8a; border-bottom: 3px solid #1e3a8a; padding-bottom: 10px; margin-bottom: 20px; font-size: 24px; }
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
        .btn-delete { background-color: #ef4444; color: white; border: none; padding: 6px 12px; border-radius: 4px; font-size: 13px; cursor: pointer; transition: background-color 0.2s; }
        .btn-delete:hover { background-color: #dc2626; }
        .questions-list { background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 15px; }
        .question-item { padding: 12px; border-bottom: 1px solid #e4e6eb; font-family: monospace; font-size: 14px; direction: ltr; text-align: left; }
        .question-item:last-child { border-bottom: none; }
        .settings-grid { display: flex; gap: 20px; flex-wrap: wrap; }
        .debug-card { background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 25px; flex: 1; min-width: 320px; max-width: 500px; }
        .status-indicator { font-size: 18px; font-weight: bold; margin-bottom: 20px; display: flex; align-items: center; gap: 8px; }
        .status-active { color: #2f9e44; }
        .status-inactive { color: #e03131; }
        .btn-toggle { background-color: #1e3a8a; color: white; border: none; padding: 12px 24px; font-size: 15px; font-weight: bold; border-radius: 6px; cursor: pointer; transition: background-color 0.2s; }
        .btn-toggle:hover { background-color: #1d4ed8; }
    </style>
</head>
<body>
<div class="container">
    <h1>📝 מרכז בקרה ודיבאג - אתר מייצגים</h1>
    
    <div class="tabs">
        <button class="tab-button active" onclick="switchTab(event, 'remarks-tab')">💬 הערות ופידבק משתמשים</button>
        <button class="tab-button" onclick="switchTab(event, 'questions-tab')">📊 יומן שאלות וטוקנים</button>
        <button class="tab-button" onclick="switchTab(event, 'settings-tab')">⚙️ ניהול הגדרות מערכת (בזמן ריצה)</button>
    </div>

    <div id="remarks-tab" class="tab-content active">
        <div class="summary-badge">סה"כ הערות שנאספו: {{ remarks|length }}</div>
        <div class="table-container">
            {% if remarks %}
            <table>
                <thead>
                    <tr>
                        <th style="width: 14%;">זמן ומעיר</th>
                        <th style="width: 23%;">ההערה שנכתבה</th>
                        <th style="width: 23%;">השאלה המקורית</th>
                        <th style="width: 30%;">תשובת הבוט (מורחב)</th>
                        <th style="width: 10%; text-align: center;">פעולות</th>
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
                        <td style="text-align: center; vertical-align: middle;">
                            <button class="btn-delete" onclick="deleteRemark({{ r.original_index }})">🗑️ מחיקה</button>
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

    <div id="settings-tab" class="tab-content">
        <div class="settings-grid">
            <div class="debug-card">
                <h3>שליטה על סטטוס DEBUG_MODE</h3>
                <p>שינוי המצב כאן יעדכן מיד את קובץ <code>data/debug.txt</code> ב-GitHub וישנה את התנהגות הבוט בזמן אמת ללא צורך ב-Deploy.</p>
                <hr style="border: 0; border-top: 1px solid #e4e6eb; margin: 20px 0;">
                
                <div class="status-indicator">
                    סטטוס נוכחי: 
                    {% if current_debug_mode == 1 %}
                        <span class="status-active">🟢 פעיל (1) - נתוני טוקנים והערות מוצגים</span>
                    {% else %}
                        <span class="status-inactive">🔴 כבוי (0) - הבוט במצב נקי ללא תוספות דיבאג</span>
                    {% endif %}
                </div>

                <button class="btn-toggle" onclick="toggleDebugMode({{ current_debug_mode }})">
                    {% if current_debug_mode == 1 %}
                        החלף למצב רגיל (DEBUG_MODE = 0)
                    {% else %}
                        החלף למצב דיבאג (DEBUG_MODE = 1)
                    {% endif %}
                </button>
            </div>

            <div class="debug-card">
                <h3>🎤 שליטה על הצגת מיקרופון והקראת קול</h3>
                <p>שינוי המצב כאן יעדכן מיד את קובץ <code>data/voice.txt</code> ב-GitHub ויקבע האם כפתור המיקרופון והקראת התשובות יוצגו למשתמשים באתר.</p>
                <hr style="border: 0; border-top: 1px solid #e4e6eb; margin: 20px 0;">
                
                <div class="status-indicator">
                    סטטוס נוכחי: 
                    {% if current_voice_mode == 1 %}
                        <span class="status-active">🟢 פעיל (1) - מיקרופון והקראה מוצגים</span>
                    {% else %}
                        <span class="status-inactive">🔴 כבוי (0) - מיקרופון והקראה מוסתרים</span>
                    {% endif %}
                </div>

                <button class="btn-toggle" onclick="toggleVoiceMode({{ current_voice_mode }})">
                    {% if current_voice_mode == 1 %}
                        הסתר מיקרופון וקול (VOICE = 0)
                    {% else %}
                        הצג מיקרופון וקול (VOICE = 1)
                    {% endif %}
                </button>
            </div>
        </div>
    </div>
</div>

<script>
    function switchTab(event, tabId) {
        document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.tab-button').forEach(el => el.classList.remove('active'));
        document.getElementById(tabId).classList.add('active');
        event.currentTarget.classList.add('active');
    }

    function deleteRemark(originalIndex) {
        if(!confirm('האם אתה בטוח שברצונך למחוק הערה זו? היא תועבר לקובץ deleted_remarks.txt.')) return;

        fetch('/delete_remark', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ index: originalIndex })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                alert(data.message);
                location.reload();
            } else {
                alert('שגיאה: ' + data.message);
            }
        });
    }

    function toggleDebugMode(currentMode) {
        const newMode = currentMode === 1 ? 0 : 1;
        if(!confirm(`האם אתה בטוח שברצונך לשנות את ה-DEBUG_MODE ל-${newMode}?`)) return;

        fetch('/update_debug_toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ debug_mode: newMode })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                alert(data.message);
                location.reload();
            }
        });
    }

    function toggleVoiceMode(currentMode) {
        const newMode = currentMode === 1 ? 0 : 1;
        if(!confirm(`האם אתה בטוח שברצונך לשנות את הצגת המיקרופון והקול ל-${newMode}?`)) return;

        fetch('/update_voice_toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ voice_mode: newMode })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                alert(data.message);
                location.reload();
            }
        });
    }
</script>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
