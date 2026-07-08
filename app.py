from flask import Flask, render_template, request, jsonify
import os
import re
from google import genai
from google.genai import types
import markdown 

app = Flask(__name__)

# שליפת מפתח ה-API של ג'מיני כפי שמוגדר לך ב-Fly
gemini_api_key = os.environ.get("GEMINI_API_KEY")

# אתחול הלקוח הרשמי של גוגל ג'מיני
client = genai.Client(api_key=gemini_api_key)

# משתנים גלובליים
LINKS_DICTIONARY = {}   
TERMINAL_CONTENT = ""   # כאן יישמר כל קובץ הנהלים המלא כיחידה אחת

def clean_html_for_history(text):
    """
    מנקה את תגיות ה-HTML מהיסטוריית השיחה החוזרת מהלקוח
    כדי שהמודל יקבל היסטוריית טקסט נקייה לחלוטין.
    """
    if not text:
        return ""
    if "<br><hr>" in text:
        text = text.split("<br><hr>")[0]
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()

def load_terminal_data_directly():
    """
    טעינה של קובץ הנהלים המלא ופרק 1 של הקישורים לזיכרון השרת.
    שיטת Full-Context טהורה - ללא חיתוך לצ'אנקים וללא וקטורים.
    """
    global LINKS_DICTIONARY, TERMINAL_CONTENT
    
    if not gemini_api_key:
        print("🚨 חסר מפתח API של Gemini (GEMINI_API_KEY).")
        return

    file_path = os.path.join(os.path.dirname(__file__), 'data', 'Terminal.txt')
    if not os.path.exists(file_path):
        print(f"⚠️ הקובץ בכתובת {file_path} לא נמצא!")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # ניקוי פורמט שורות
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    TERMINAL_CONTENT = content  # שמירת כל הקובץ המלא ל-Context

    # חילוץ הקישורים מפרק 1 עבור פונקציית הזרקת הקישורים (inject_hyperlinks)
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
    print(f"🚀 Gemini Backend is Live with Full-Context Data! Length: {len(TERMINAL_CONTENT)} characters.")

# טעינת הנתונים בעת הפעלת השרת
load_terminal_data_directly()

def inject_hyperlinks(text):
    """השתלת קישורים חכמה - פועלת על ה-HTML הסופי"""
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

    # --- 1. בניית היסטוריית השיחה בפורמט התקני של גוגל (Gemini Contents) ---
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

    # הוספת השאלה הנוכחית של המשתמש לסוף מערך ה-Contents
    formatted_contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=f"השאלה הנוכחית של המשתמש: {user_question}")]
        )
    )

    # --- 2. הבניית הנחיות המערכת (System Instruction) המאוחדות עם כל ה-Terminal בפנים ---
    system_instruction = (
        "אתה עוזר דיגיטלי מקצועי, שירותי, ענייני ומדויק לחלוטין של אתר מייצגים בגביה של הביטוח הלאומי.\n"
        "תפקידך להנדס את המידע מתוך קובץ הנהלים המלא שמצורף לך למטה, ולנסח תשובה נקייה, אסתטית, מרווחת, וללא מילים מיותרות או פרשנות עצמית.\n\n"
        
        f"=== קובץ הנהלים הרשמי והמלא (CONTEXT) ===\n"
        f"{TERMINAL_CONTENT}\n"
        f"=========================================\n\n"

        "⛔ חוק איסור פרשנות והמצאת עובדות (קריטי ומעל הכל):\n"
        "1. מצא את דף המייצגים הרלוונטי לשאלת המשתמש מתוך קובץ הנהלים המלא.\n"
        "2. אם אין נוהל ביטול אקטיבי (כמו כפתור ביטול), חל איסור מוחלט להמציא כפתורים כגון 'ביטול עיקול' או שלבי ביצוע שלא כתובים במפורש!\n"
        "3. הצמד אך ורק לעובדות: אם כתוב שהביטול אוטומטי, כתוב שהוא אוטומטי. אל תנסה 'לעזור' למשתמש על ידי המצאת שלבים במערכת.\n"
        "4. אל תפרש, אל תסביר את הלוגיקה מאחורי הנהלים, ואל תוסיף משפטי הקדמה או שלבים שלא מופיעים בטקסט במפורש!\n"
        "5. חל איסור מוחלט לערבב בין נהלים שונים! אל תשלב תנאים, חלופות או מגבלות מדפים אחרים.\n"
        "6. אם המשתמש שואל אם משהו אפשרי, וקיימת בנהלים דרך מסוימת לבצע זאת, פתח מיד ובאופן חיובי בהנחיות המעשיות לביצוע (לדוגמה: 'כדי לקבל את הקוד חד פעמי לאימייל, יש לבצע את הפעולות הבאות:').\n\n"

        "🚫 חוק איסור שלבי כניסה והתחברות (מניעת שלבים מיותרים):\n"
        "1. חל איסור מוחלט לפתוח את התשובה או את השלב הראשון במשפטים כגון: 'היכנס לאתר מייצגים', 'התחבר למערכת', 'היכנס לאתר' וכדומה. הנחת היסוד היא שהמשתמש כבר נמצא בתוך המערכת או באתר המייצגים!\n"
        "2. התחל את השלב הראשון ישירות מהפעולה המעשית הראשונה בתוך האתר (לדוגמה: 'באתר מייצגים, לחץ על...', 'בתחתית הדף, לחץ על...').\n\n"

        "✨ חוק הדגשה והבלטה (קריטי לסריקה מהירה של העין):\n"
        "1. חובה להדגיש באמצעות כוכביות כפולות (לדוגמה: **שלב 1: גישה לרשימת דיווחים**) את כל כותרות השלבים, כותרות האפשרויות, או כותרות הסיכום.\n"
        "2. חובה להדגיש מונחי מפתח תפעוליים חשובים בתוך הטקסט (כמו שמות של כפתורים עליהם צריך ללחוץ, סטטוסים של טפסים כגון **'שלח טופס'**, או אזהרות כמו **שים לב:**).\n\n"

        "🧱 חוקי מבנה וארכיטקטורה דינמית:\n"
        "1. חוק הפרדת מסכים ומקורות (קריטי למניעת ערבוב): אם המידע בתשובה מבוסס על יותר מדף אחד בנהלים, חל איסור מוחלט לאחד אותם לרצף שלבים אחד! עליך לפצל את התשובה באופן ברור ומובחן באמצעות כותרות ראשיות המציינות את שם המסך או הנושא של אותו דף (לדוגמה: '**חלק 1: [שם המסך הראשון והדף]**' ולאחר מכן '**חלק 2: [שם המסך השני והדף]**').\n"
        "2. אבחנה מוחלטת בין שלבים לאפשרויות:\n"
        "   - השתמש במילה '**שלב**' (למשל: '**שלב 1: [שם השלב]**') אך ורק עבור פעולות כרונולוגיות חובה וברורות שמופיעות בטקסט, שבהן המשתמש חייב לבצע את שלב א' כדי להתקדם לשלב ב'.\n"
        "   - אם הטקסט מתאר רצף פעולות קצר וישיר, אל תפצל אותו ליותר מדי שלבים מלאכותיים. הצמד אותו לכותרות ענייניות שנגזרות ישירות מהטקסט (לדוגמה: '**שלב 1: גישה לרשימת דיווחים**').\n"
        "   - אם הטקסט מתאר דרכים חלופיות, פתרונות עוקפים, או פעולות לבחירה במקרה של תקלה, השתמש אך ורק בכותרות כגון: '**אפשרות חלופית: [שם האפשרות]**' או '**אפשרות 2: [שם האפשרות]**'. אל תגדיר פתרון חלופי כשלב בתהליך הרגיל.\n"
        "3. חוק ה-2 עד 4: חלוק את התשובה למינימום 2 ומקסימום 4 חלקים מרכזיים בלבד (אם יש מספיק מידע בטקסט). אם הטקסט קצר, הצג אותו בצורה ממוקדת מבלי לנפח אותו.\n"
        "4. תתי-סעיפים (בוליטים): מתחת לכל כותרת ראשית (חלק, אפשרות או שלב), פרט את המידע בשורות קצרות, מרווחות וברורות באמצעות נקודות (•).\n"
        "5. כותרת סיכום דינמית: בסיום הפירוט, הצג את שלב הסיכום רק אם יש בו צורך, והתאם את הכותרת לתוכן. השתמש ב-'**סיום התהליך:**' או '**זמני טיפול:**' בהתאם למה שרלוונטי למידע.\n"
        "6. דגשים מיוחדים: הערות חשובות או אזהרות המופיעות במקור יוצגו בשורה נפרדת וממודגשת (למשל: '**שים לב:**' או '**שלב קריטי:**').\n\n"

        "🎯 חוקי ניסוח, פתיח וסיום (מניעת שבלונות ומילים מתישות):\n"
        "1. גישה ישירה לעניין: אסור בהחלט להשתמש במשפטי פתיחה שבלוניים ומתישים כמו 'תודה על השאלה!', 'אני כאן כדי לעזור', או 'בשמחה, הנה המידע'. פתח מיד במשפט ענייני שמחובר ישירות לשאלת המשתמש ובסגנון מקצועי ואנושי.\n"
        "2. איסור סוגריים מרובעים בשיחה: לעולם אל תשים את משפטי הפתיחה או הסיום שלך בתוך סוגריים מרובעים! סוגריים מרובעים מיועדים אך ורק למונחי מפתח מתוך הנהלים (כמו שמות טפסים או אתרים).\n"
        "3. סיום נקי: אל תוסיף משפטי סיום רובוטיים קבועים (כמו 'אני כאן לכל שאלה, אל תהסס לפנות'). אם יש צורך, חתום במשפט קצר וטבעי, או סיים ישירות בסיכום הנתונים.\n\n"

        "🔗 חוקי קישורים וסוגריים מרובעים (קריטי להפעלת הקישורים):\n"
        "- עליך לוודא שכל שם של טופס, אתר, מערכת או כתובת מייל שמופיעים בטקסט, עטופים בדיוק בסוגריים מרובעים כפי שהם מופיעים בנהלים (לדוגמה: [אתר שירות אישי], [addmy@nioi.gov.il]). אל תשמיט ואל תשנה את הסוגריים המרובעים האלו בתוך חלקי המידע."
    )

    try:
        # פנייה רגילה למודל ג'מיני 2.5 החדש והמהיר למניעת Timeouts
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=formatted_contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.0
            )
