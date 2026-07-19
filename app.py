from flask import Flask, render_template, request, jsonify, render_template_string
import os
import re
import time
import json
from datetime import datetime
from google import genai
from google.genai import types
import markdown 

app = Flask(__name__)

# --- משתנה הדיבאג הגלובלי ---
DEBUG_MODE = 1  # 0 = כבוי (מערכת רגילה), 1 = מצב דיבאג פעיל

# שליפת מפתח ה-API של ג'מיני
gemini_api_key = os.environ.get("GEMINI_API_KEY")

# משתנים גלובליים לנתונים
LINKS_DICTIONARY = {}   
TERMINAL_CONTENT = ""   
CACHE_NAME = None  # ישמור את המזהה הייחודי של ה-Cache בשרתי גוגל

# הגדרת נתיבים לתיקיית הדאטה ולקבצים
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.txt")
REMARKS_FILE = os.path.join(DATA_DIR, "remarks.txt")
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

def load_terminal_data_directly():
    """טעינת הקישורים מתוך קובץ info.txt בנפרד, וטעינת הנהלים מתוך Terminal.txt"""
    global LINKS_DICTIONARY, TERMINAL_CONTENT
    
    if not gemini_api_key:
        print("🚨 חסר מפתח API של Gemini.")
        return
        
    # 1. טעינת קובץ המידע והקישורים ( info.txt )
    info_path = os.path.join(DATA_DIR, 'info.txt')
    if os.path.exists(info_path):
        with open(info_path, 'r', encoding='utf-8') as f:
            info_content = f.read()
        link_matches = re.findall(r'>>([^:]+):\s*([^\s<<]+)<<', info_content)
        for name, url in link_matches:
            LINKS_DICTIONARY[name.strip()] = url.strip()
        print(f"✅ Loaded {len(LINKS_DICTIONARY)} links/phones from info.txt")
    else:
        print(f"⚠️ הקובץ info.txt לא נמצא בכתובת {info_path}!")

    # 2. טעינת קובץ הנהלים הראשי ( Terminal.txt )
    terminal_path = os.path.join(DATA_DIR, 'Terminal.txt')
    if os.path.exists(terminal_path):
        with open(terminal_path, 'r', encoding='utf-8') as f:
            content = f.read()
        TERMINAL_CONTENT = content.replace('\r\n', '\n').replace('\r', '\n')
        print("✅ Loaded Terminal.txt content for Gemini.")
    else:
        print(f"⚠️ הקובץ Terminal.txt לא נמצא בכתובת {terminal_path}!")

# טעינת הנתונים בעת הפעלת השרת
load_terminal_data_directly()

def get_or_create_context_cache(client):
    """מנהל את יצירת או שליפת ה-Context Cache לטווח של שעה ושומר מזהה פיזית לקובץ"""
    global CACHE_NAME
    
    if not CACHE_NAME and os.path.exists(CACHE_INFO_FILE):
        try:
            with open(CACHE_INFO_FILE, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
                CACHE_NAME = saved_data.get("cache_name")
                print(f"📂 נטען מזהה Cache מהקובץ המקומי: {CACHE_NAME}")
        except Exception as e:
            print(f"⚠️ שגיאה בקריאת קובץ cache_info.json: {e}")
    
    if CACHE_NAME:
        try:
            existing_cache = client.caches.get(name=CACHE_NAME)
            if hasattr(existing_cache, 'state') and str(existing_cache.state) not in ["STATE_ACTIVE", "ACTIVE"]:
                print(f"🔄 ה-Cache קיים אך בסטטוס לא פעיל ({existing_cache.state}), מייצר מחדש...")
                CACHE_NAME = None
            else:
                print("🎯 נמצא Cache פעיל ותקין בשרת גוגל. משתמשים בו.")
                return existing_cache
        except Exception:
            print("🔄 ה-Cache לא נמצא בגוגל או שפג תוקפו החוזי (שעה אחת), מייצר אחד חדש...")
            CACHE_NAME = None

    print("🚀 מייצר Context Cache חדש לטווח קצר בשרתי גוגל (שעה אחת)...")
    
    full_cache_text = (
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"=== קובץ הנהלים הרשמי והמלא (CONTEXT) ===\n{TERMINAL_CONTENT}\n=========================================\n"
    )
    
    cache = client.caches.create(
        model='gemini-2.5-flash',
        config=types.CreateCachedContentConfig(
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=full_cache_text)])],
            ttl="3600s"  # שמירה לשעה אחת בלבד למניעת זליגת עלויות
        )
    )
    CACHE_NAME = cache.name
    
    try:
        with open(CACHE_INFO_FILE, "w", encoding="utf-8") as f:
            json.dump({"cache_name": CACHE_NAME, "created_at": time.time()}, f)
        print("💾 מזהה ה-Cache החדש נשמר בהצלחה בקובץ הפיזי.")
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

    if DEBUG_MODE == 1 and user_question:
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(QUESTIONS_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {user_question}\n")
        except Exception as e:
            print(f"Error writing to questions.txt: {e}")

    formatted_contents = []
    for msg in chat_history:
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
                finish_reason = "Unknown"
                if response and response.candidates:
                    finish_reason = response.candidates[0].finish_reason
                raise ValueError(f"התשובה שהתקבלה מגוגל ריקה. (סיבת סיום: {finish_reason})")
                
            raw_answer = response.text
            html_answer = markdown.markdown(raw_answer, extensions=['nl2br'])
            final_answer = inject_hyperlinks(html_answer)
            
            # שליפת מטא-דטה של טוקנים מתוך התשובה הרשמית של גוגל
            usage_info = {}
            if response.usage_metadata:
                usage_info = {
                    "prompt_tokens": response.usage_metadata.prompt_token_count,
                    "cached_tokens": response.usage_metadata.cached_content_token_count,
                    "output_tokens": response.usage_metadata.candidates_token_count
                }
            
            return jsonify({
                "response": final_answer,
                "debug": DEBUG_MODE,
                "original_question": user_question,
                "usage": usage_info
            })

        except Exception as e:
            error_str = str(e)
            print(f"❌ שגיאה בניסיון {attempt + 1}: {error_str}")
            
            if "503" in error_str or "500" in error_str or "UNAVAILABLE" in error_str:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
            
            friendly_message = (
                "העוזר הדיגיטלי חווה כרגע עומס רגעי זמני בשרתי גוגל ולא הצליח לעבד את התשובה. "
                "אנא המתן מספר שניות ונסה לשלוח את השאלה שוב.<br>"
                f"<small style='color: #888; font-size: 11px; display: block; margin-top: 5px;'>[אבחון טכני ללא טרמינל: {error_str}]</small>"
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

        with open(REMARKS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(remark_entry, ensure_ascii=False) + "\n")

        return jsonify({"status": "success", "message": "ההערה נשמרה בהצלחה"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/remarks', methods=['GET'])
def show_remarks():
    remarks_list = []
    if os.path.exists(REMARKS_FILE):
        try:
            with open(REMARKS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        remarks_list.append(json.loads(line.strip()))
        except Exception as e:
            print(f"Error reading remarks file: {e}")
            
    remarks_list.reverse()
    return render_template_string(REMARKS_HTML_TEMPLATE, remarks=remarks_list)

# --- תבנית ה-HTML לעמוד ה-Remarks ---
REMARKS_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ניהול הערות דיבאג - מייצגים</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f6f9; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #1e3a8a; border-bottom: 3px solid #1e3a8a; padding-bottom: 10px; margin-bottom: 20px; font-size: 24px; }
        .summary-badge { background-color: #1e3a8a; color: white; padding: 4px 12px; border-radius: 12px; font-size: 14px; display: inline-block; margin-bottom: 15px; }
        .table-container { background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); overflow: hidden; }
        table { width: 100%; border-collapse: collapse; text-align: right; }
        th { background-color: #1e3a8a; color: white; padding: 12px 15px; font-weight: bold; font-size: 15px; }
        td { padding: 12px 15px; border-bottom: 1px solid #e4e6eb; font-size: 14px; vertical-align: top; line-height: 1.5; }
        tr:hover { background-color: #f8fafc; }
        .timestamp { color: #666; font-size: 12px; white-space: nowrap; }
        .author { font-weight: bold; color: #007bff; }
        .remark-text { background-color: #fff9db; padding: 6px 10px; border-right: 3px solid #fcc419; border-radius: 4px; font-weight: 500; }
        .box-content { max-height: 150px; overflow-y: auto; background-color: #f8f9fa; padding: 8px; border-radius: 4px; font-size: 13px; white-space: pre-line; }
        .no-remarks { text-align: center; padding: 40px; color: #666; font-size: 16px; }
        @media (max-width: 768px) {
            table, thead, tbody, th, td, tr { display: block; }
            thead { display: none; }
            tr { background: white; border: 1px solid #ccd0d5; border-radius: 8px; margin-bottom: 15px; padding: 10px; }
            td { border: none; padding: 6px 0; }
            td::before { content: attr(data-label); display: block; font-weight: bold; color: #1e3a8a; font-size: 12px; margin-bottom: 2px; }
        }
    </style>
</head>
<body>
<div class="container">
    <h1>📝 ריכוז הערות דיבאג ופידבק</h1>
    <div class="summary-badge">סה"כ הערות שנאספו: {{ remarks|length }}</div>
    <div class="table-container">
        {% if remarks %}
        <table>
            <thead>
                <tr>
                    <th style="width: 15%;">זמן ומעיר</th>
                    <th style="width: 25%;">ההערה שנכתבה</th>
                    <th style="width: 30%;">השאלה המקורית</th>
                    <th style="width: 30%;">תשובת הבוט</th>
                </tr>
            </thead>
            <tbody>
                {% append r in remarks %}
                <tr>
                    <td data-label="זמן ומעיר">
                        <div class="timestamp">{{ r.timestamp }}</div>
                        <div class="author">{{ r.author }}</div>
                    </td>
                    <td data-label="ההערה">
                        <div class="remark-text">{{ r.remark }}</div>
                    </td>
                    <td data-label="השאלה המקורית">
                        <div class="box-content">{{ r.question }}</div>
                    </td>
                    <td data-label="תשובת הבוט">
                        <div class="box-content">{{ r.response | striptags }}</div>
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
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
