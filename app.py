from flask import Flask, render_template, request, jsonify
import os
import re
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

# הנחיות המערכת הקבועות (חוקי הניסוח וההתנהגות)
SYSTEM_INSTRUCTION = (
    "אתה עוזר דיגיטלי מקצועי, שירותי, ענייני ומדויק לחלוטין של אתר מייצגים בגביה של הביטוח הלאומי.\n"
    "תפקידך להנדס את המידע מתוך קובץ הנהלים המלא שמצורף לך ב-Context, ולנסח תשובה נקייה, אסתטית, מרווחת, וללא מילים מיותרות או פרשנות עצמית.\n\n"
    "⛔ חוק איסור פרשנות והמצאת עובדות (קריטי ומעל הכל):\n"
    "1. מצא את דף המייצגים הרלוונטי לשאלת המשתמש מתוך קובץ הנהלים המלא.\n"
    "2. אם אין נוהל ביטול אקטיבי (כמו כפתור ביטול), חל איסור מוחלט להמציא כפתורים כגון 'ביטול עיקול' או שלבי ביצוע שלא כתובים במפורש!\n"
    "3. הצמד אך ורק לעובדות: אם כתוב שהביטול אוטומטי, כתוב שהוא אוטומטי. אל תנסה 'לעזור' למשתמש על ידי המצאת שלבים במערכת.\n"
    "4. אל תפרש, אל תסביר את הלוגיקה מאחורי הנהלים, ואל תוסיף משפטי הקדמה או שלבים שלא מופיעים בטקסט במפורש!\n"
    "5. חל איסור מוחלט לערבב בין נהלים שונים! אל תשלב תנאים, חלופות או מגבלות מדפים אחרים.\n"
    "6. אם המשתמש שואל אם משהו אפשרי, וקיימת בנהלים דרך מסוימת לבצע זאת, פתח מיד ובאופן חיובי בהנחיות המעשיות לביצוע (לדוגמה: 'כדי לקבל את הקוד חד פעמי לאימייל, יש לבצע את הפעולות הבאות:').\n\n"
    "🚫 חוק איסור שלבי כניסה והתחברות:\n"
    "1. חל איסור מוחלט לפתוח את התשובה או את השלב הראשון במשפטים כגון: 'היכנס לאתר מייצגים', 'התחבר למערכת', 'היכנס לאתר' וכדומה. הנחת היסוד היא שהמשתמש כבר נמצא בתוך המערכת או באתר המייצגים!\n"
    "2. התחל את השלב הראשון ישירות מהפעולה המעשית הראשונה בתוך האתר (לדוגמה: 'באתר מייצגים, לחץ על...', 'בתחתית הדף, לחץ על...').\n\n"
    "✨ חוק הדגשה והבלטה:\n"
    "1. חובה להדגיש באמצעות כוכביות כפולות (לדוגמה: **שלב 1: גישה לרשימת דיווחים**) את כל כותרות השלבים, כותרות האפשרויות, או כותרות הסיכום.\n"
    "2. חובה להדגיש מונחי מפתח תפעוליים חשובים בתוך הטקסט (כמו שמות של כפתורים עליהם צריך ללחוץ, סטטוסים של טפסים כגון **'שלח טופס'**, או אזהרות כמו **שים לב:**).\n\n"
    "🧱 חוקי מבנה וארכיטקטורה דינמית:\n"
    "1. חוק הפרדת מסכים ומקורות: אם המידע בתשובה מבוסס על יותר מדף אחד בנהלים, חל איסור מוחלט לאחד אותם לרצף שלבים אחד! עליך לפצל את התשובה באופן ברור ומובחן באמצעות כותרות ראשיות המציינות את שם המסך או הנושא של אותו דף.\n"
    "2. אבחנה מוחלטת בין שלבים לאפשרויות:\n"
    "   - השתמש במילה '**שלב**' אך ורק עבור פעולות כרונולוגיות חובה.\n"
    "   - אם הטקסט מתאר דרכים חלופיות, השתמש אך ורק בכותרות כגון: '**אפשרות חלופית: [שם האפשרות]**'.\n"
    "3. חוק ה-2 עד 4: חלוק את התשובה למינימום 2 ומקסימום 4 חלקים מרכזיים בלבד.\n"
    "4. תתי-סעיפים (בוליטים): מתחת לכל כותרת ראשית, פרט את המידע בשורות קצרות באמצעות נקודות (•).\n"
    "5. כותרת סיכום דינמית: בסיום הפירוט, השתמש ב-'**סיום התהליך:**' או '**זמני טיפול:**' בהתאם למה שרלוונטי.\n"
    "6. דגשים מיוחדים: הערות חשובות יוצגו בשורה נפרדת וממודגשת (למשל: '**שים לב:**').\n\n"
    "🎯 חוקי ניסוח, פתיח וסיום:\n"
    "1. גישה ישירה לעניין: אסור בהחלט להשתמש במשפטי פתיחה שבלוניים ומתישים.\n"
    "2. איסור סוגריים מרובעים בשיחה: לעולם אל תשים את משפטי הפתיחה או הסיום שלך בתוך סוגריים מרובעים!\n"
    "3. סיום נקי: אל תוסיף משפטי סיום רובוטיים קבועים.\n\n"
    "🔗 חוקי קישורים וסוגריים מרובעים:\n"
    "- עליך לוודא שכל שם של טופס, אתר, מערכת או כתובת מייל שמופיעים בטקסט, עטופים בדיוק בסוגריים מרובעים כפי שהם מופיעים בנהלים."
)

def clean_html_for_history(text):
    """מנקה תגיות HTML מהיסטוריית השיחה"""
    if not text:
        return ""
    if "<br><hr>" in text:
        text = text.split("<br><hr>")[0]
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()

def load_terminal_data_directly():
    """טעינת קובץ הנהלים המלא לזיכרון השרת"""
    global LINKS_DICTIONARY, TERMINAL_CONTENT
    
    if not gemini_api_key:
        print("🚨 חסר מפתח API של Gemini.")
        return

    file_path = os.path.join(os.path.dirname(__file__), 'data', 'Terminal.txt')
    if not os.path.exists(file_path):
        print(f"⚠️ הקובץ בכתובת {file_path} לא נמצא!")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    content = content.replace('\r\n', '\n').replace('\r', '\n')
    TERMINAL_CONTENT = content  

    # חילוץ קישורים מפרק 1
    parts = re.split(r'===(פרק \d+)===', content)
    chapter_1_text = ""
    for i in range(1, len(parts), 2):
        if "פרק 1" in parts[i]:
            chapter_1_text = parts[i+1] if i+1 < len(parts) else ""
            break

    link_matches = re.findall(r'>>([^:]+):\s*([^\s<<]+)<<', chapter_1_text)
    for name, url in link_matches:
        LINKS_DICTIONARY[name.strip()] = url.strip()
        
    print(f"✅ Loaded {len(LINKS_DICTIONARY)} global links.")

# טעינת הנתונים בעת הפעלת השרת
load_terminal_data_directly()

def get_or_create_context_cache(client):
    """מנהל את יצירת או שליפת ה-Context Cache מול השרתים של גוגל"""
    global CACHE_NAME
    
    if CACHE_NAME:
        try:
            existing_cache = client.caches.get(name=CACHE_NAME)
            return existing_cache
        except Exception:
            print("🔄 ה-Cache פג תוקף בגוגל, מייצר אחד חדש...")
            CACHE_NAME = None

    print("🚀 מייצר Context Cache חדש בשרתי גוגל...")
    
    # ה-Context Cache מכיל רק את קובץ הנהלים הגדול כחלק מהתוכן השמור
    cache_text = f"=== קובץ הנהלים הרשמי והמלא (CONTEXT) ===\n{TERMINAL_CONTENT}\n=========================================\n"
    
    cache = client.caches.create(
        model='gemini-2.5-flash',
        config=types.CreateCachedContentConfig(
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=cache_text)])],
            ttl="86400s"  # שמירה ל-24 שעות
        )
    )
    CACHE_NAME = cache.name
    return cache

def inject_hyperlinks(text):
    """השתלת קישורים על גבי ה-HTML הסופי"""
    for name, url in LINKS_DICTIONARY.items():
        placeholder = f"[{name}]"
        if placeholder in text:
            if "@" in url and not url.startswith("http"):
                href_target = f"mailto:{url}"
            else:
                href_target = url
                
            hyperlink = f'<a href="{href_target}" style="color: #007bff; text-decoration: underline; font-weight: bold;" target="_blank">{name}</a>'
            text = text.replace(placeholder, hyperlink)
    return text

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json or {}
    user_question = data.get('question', '').strip()
    chat_history = data.get('history', [])

    if not user_question:
        return jsonify({"response": "לא התקבלה שאלה תקינה."})

    if not TERMINAL_CONTENT:
        return jsonify({"response": "מערכת הנתונים של הטרמינל אינה טעונה בשרת."})

    # בניית היסטוריית השיחה עבור ג'מיני
    formatted_contents = []
    for msg in chat_history:
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

    # הוספת השאלה הנוכחית של המשתמש
    formatted_contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=f"השאלה הנוכחית של המשתמש: {user_question}")]
        )
    )

    try:
        # אתחול ה-Client מחדש בכל בקשה
        client = genai.Client(api_key=gemini_api_key)
        
        # שליפת הקאש או יצירתו
        cache_content = get_or_create_context_cache(client)

        # פנייה למודל: משלבים את ה-Cache יחד עם ה-system_instruction בנפרד
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=formatted_contents,
            config=types.GenerateContentConfig(
                cached_content=cache_content.name,
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.0
            )
        )
        
        raw_answer = response.text
        html_answer = markdown.markdown(raw_answer, extensions=['nl2br'])
        final_answer = inject_hyperlinks(html_answer)
        
        return jsonify({"response": final_answer})

    except Exception as e:
        # הזרקת השגיאה האמיתית של גוגל ישירות למסך של המשתמש לצורך אבחון מהיר ללא טרמינל
        error_message = f"🚨 שגיאת תקשורת מול גוגל: {str(e)}"
        print(f"❌ Error calling Gemini API: {e}")
        return jsonify({"response": error_message})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
