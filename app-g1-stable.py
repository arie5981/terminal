from flask import Flask, render_template, request, jsonify
import os
import re
import time
from google import genai
from google.genai import types
import markdown 

app = Flask(__name__)

# שליפת מפתח ה-API של ג'מיני
gemini_api_key = os.environ.get("GEMINI_API_KEY")

# משתנים גלובליים לנתונים
LINKS_DICTIONARY = {}   
TERMINAL_CONTENT = ""   
CACHE_NAME = None  # ישמור את המזהה הייחודי של ה-Cache בשרתי גוגל

# הנחיות המערכת הקבועות - מעודכנות לתשובות אנושיות, מנומסות אך ממוקדות
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

    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    
    # 1. טעינת קובץ המידע והקישורים ( info.txt ) - לא נשלח לג'מיני כדי למנוע חסימות אבטחה
    info_path = os.path.join(data_dir, 'info.txt')
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
    terminal_path = os.path.join(data_dir, 'Terminal.txt')
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
    """מנהל את יצירת או שליפת ה-Context Cache ומוודא שהסטטוס שלו ACTIVE בשרתי גוגל"""
    global CACHE_NAME
    
    if CACHE_NAME:
        try:
            existing_cache = client.caches.get(name=CACHE_NAME)
            if hasattr(existing_cache, 'state') and str(existing_cache.state) not in ["STATE_ACTIVE", "ACTIVE"]:
                print(f"🔄 ה-Cache קיים אך בסטטוס לא פעיל ({existing_cache.state}), מייצר מחדש...")
                CACHE_NAME = None
            else:
                return existing_cache
        except Exception:
            print("🔄 ה-Cache לא נמצא או פג תוקף בגוגל, מייצר אחד חדש...")
            CACHE_NAME = None

    print("🚀 מייצר Context Cache חדש בשרתי גוגל (מבוסס Terminal.txt נקי)...")
    
    full_cache_text = (
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"=== קובץ הנהלים הרשמי והמלא (CONTEXT) ===\n{TERMINAL_CONTENT}\n=========================================\n"
    )
    
    cache = client.caches.create(
        model='gemini-2.5-flash',
        config=types.CreateCachedContentConfig(
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=full_cache_text)])],
            ttl="86400s"  # שמירה ל-24 שעות
        )
    )
    CACHE_NAME = cache.name
    return cache

def inject_hyperlinks(text):
    """
    מזריק את הנתונים מתוך info.txt לתשובה הסופית שחוזרת מג'מיני:
    - אם הערך הוא טלפון/פקס: מציג אותו כטקסט נקי ומדויק עם מקף (בלי לינק).
    - אם הערך הוא מייל או אתר: מציג כקישור כחול ולחיץ.
    """
    if not text:
        return ""
        
    for name, url in LINKS_DICTIONARY.items():
        placeholder = f"[{name}]"
        if placeholder in text:
            
            # בדיקה אם מדובר בטלפון או פקס (מכיל רק מספרים ומקפים)
            if re.match(r'^[\d\-]+$', url):
                # החלפה ישירה למספר הנקי (למשל: 02-6709970) כטקסט פשוט על המסך
                text = text.replace(placeholder, url)
                continue
            
            # בדיקה אם מדובר בכתובת מייל
            if "@" in url and not url.startswith("http"):
                hyperlink = f'<a href="mailto:{url}" style="color: #007bff; text-decoration: underline; font-weight: bold;">{name}</a>'
                text = text.replace(placeholder, hyperlink)
            
            # קישור אינטרנט רגיל
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
    
    # הגנה מפני ערך ריק בשאלת המשתמש
    user_question = data.get('question', '')
    user_question = user_question.strip() if user_question else ""
    
    chat_history = data.get('history', [])

    if not user_question:
        return jsonify({"response": "לא התקבלה שאלה תקינה."})

    if not TERMINAL_CONTENT:
        return jsonify({"response": "מערכת הנתונים של הטרמינל אינה טעונה בשרת."})

    # בניית היסטוריית השיחה עבור ג'מיני
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

    # הוספת השאלה הנוכחית
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
            
            # הגנה מפני תשובה ריקה
            if not response or not response.text:
                finish_reason = "Unknown"
                if response and response.candidates:
                    finish_reason = response.candidates[0].finish_reason
                raise ValueError(f"התשובה שהתקבלה מגוגל ריקה. (סיבת סיום: {finish_reason})")
                
            raw_answer = response.text
            html_answer = markdown.markdown(raw_answer, extensions=['nl2br'])
            final_answer = inject_hyperlinks(html_answer)
            
            return jsonify({"response": final_answer})

        except Exception as e:
            error_str = str(e)
            print(f"❌ שגיאה בניסיון {attempt + 1}: {error_str}")
            
            # במקרה של עומס זמני (503/500), נמתין מעט וננסה שוב בלולאה
            if "503" in error_str or "500" in error_str or "UNAVAILABLE" in error_str:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
            
            friendly_message = (
                "העוזר הדיגיטלי חווה כרגע עומס רגעי זמני בשרתי גוגל ולא הצליח לעבד את התשובה. "
                "אנא המתן מספר שניות ונסה לשלוח את השאלה שוב.<br>"
                f"<small style='color: #888; font-size: 11px; display: block; margin-top: 5px;'>[אבחון טכני ללא טרמינל: {error_str}]</small>"
            )
            return jsonify({"response": friendly_message})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
