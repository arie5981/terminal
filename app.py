from flask import Flask, render_template, request, jsonify
import os
import re
import numpy as np
from openai import OpenAI
from rapidfuzz import fuzz
import markdown 

app = Flask(__name__)

# שליפת מפתח ה-API
openai_api_key = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key)

# משתנים גלובליים
LINKS_DICTIONARY = {}   
CHUNKS_TEXTS = []       
CHUNKS_EMBEDDINGS = None 

def clean_html_for_history(text):
    """
    מנקה את תגיות ה-HTML ובלוק המטא-דאטה מהיסטוריית השיחה
    כדי שהמודל יקבל היסטוריית טקסט נקייה לחלוטין ולא יתבלבל.
    """
    if not text:
        return ""
    if "<br><hr>" in text:
        text = text.split("<br><hr>")[0]
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()

def load_and_parse_terminal_data():
    """
    טעינה וניתוח של קובץ הנהלים Terminal.txt לפי סימני ===פרק X===
    חסין לרווחים ותקלות פורמט קלות
    """
    global LINKS_DICTIONARY, CHUNKS_TEXTS, CHUNKS_EMBEDDINGS
    
    if not openai_api_key:
        print("🚨 חסר מפתח API של OpenAI.")
        return

    file_path = os.path.join(os.path.dirname(__file__), 'data', 'Terminal.txt')
    if not os.path.exists(file_path):
        print(f"⚠️ הקובץ בכתובת {file_path} לא נמצא!")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    content = content.replace('\r\n', '\n').replace('\r', '\n')
    parts = re.split(r'===(פרק \d+)===', content)
    
    chapter_1_text = ""
    chapter_2_text = ""
    chapter_3_text = ""
    
    for i in range(1, len(parts), 2):
        header = parts[i]
        body = parts[i+1] if i+1 < len(parts) else ""
        
        if "פרק 1" in header:
            chapter_1_text = body
        elif "פרק 2" in header:
            chapter_2_text = body
        elif "פרק 3" in header:
            chapter_3_text = body

    # --- 1. עיבוד פרק 1: חילוץ קישורים ומיילים ---
    link_matches = re.findall(r'>>([^:]+):\s*([^\s<<]+)<<', chapter_1_text)
    for name, url in link_matches:
        LINKS_DICTIONARY[name.strip()] = url.strip()
    print(f"Loaded {len(LINKS_DICTIONARY)} global links.")

    # --- 2. עיבוד פרק 2: שאלות ותשובות נפוצות ---
    qna_blocks = re.split(r'(?=שאלה\s*:\s*)', chapter_2_text)
    for block in qna_blocks:
        block_clean = block.strip()
        if block_clean:
            if re.search(r'תשובה\s*:\s*', block_clean):
                CHUNKS_TEXTS.append(block_clean)

    # --- 3. עיבוד פרק 3: תיאור אתר מייצגים (מתוקן וחסין לרווחים כפולים בדף 142) ---
    page_blocks = re.split(r'(?=דף מייצגים\s*-\s*+\d+)', chapter_3_text)
    for block in page_blocks:
        block_clean = block.strip()
        if block_clean:
            if "נושא:" in block_clean or "הסבר והנחיות:" in block_clean:
                CHUNKS_TEXTS.append(block_clean)

    print(f"Total structured chunks extracted: {len(CHUNKS_TEXTS)}")

    # --- 4. וקטוריזציה מראש ---
    if CHUNKS_TEXTS:
        try:
            response = client.embeddings.create(
                input=CHUNKS_TEXTS,
                model="text-embedding-3-small"
            )
            CHUNKS_EMBEDDINGS = np.array([item.embedding for item in response.data])
            print("Successfully generated embeddings. System is live!")
        except Exception as e:
            print(f"❌ Error generating embeddings: {e}")

load_and_parse_terminal_data()

def get_embedding(text):
    response = client.embeddings.create(
        input=[text],
        model="text-embedding-3-small"
    )
    return response.data[0].embedding

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

    if not CHUNKS_TEXTS or CHUNKS_EMBEDDINGS is None:
        return jsonify({"response": "מערכת הנתונים של הטרמינל אינה טעונה כראוי בשרת."})

    # --- 1. ניקוי ועיבוד היסטוריית השיחה החוזרת מהלקוח ---
    clean_history = []
    for msg in chat_history:
        clean_history.append({
            "role": msg.get("role"),
            "content": clean_html_for_history(msg.get("content", ""))
        })

    # --- 2. 🧠 Query Rewriting: שדרוג שאילתת החיפוש לפי הקשר השיחה ---
    search_query = user_question
    if clean_history:
        try:
            rewriter_messages = [
                {
                    "role": "system",
                    "content": (
                        "תפקידך לקחת שאלת המשך של משתמש ואת היסטוריית השיחה האחרונה, "
                        "ולנסח שאילתת חיפוש קצרה וממוקדת (עד 6 מילים) שתשמש לחיפוש בקובץ הנהלים.\n"
                        "עליך לשלב מילות מפתח מההיסטוריה כדי ששאלת ההמשך תהיה מובנת בפני עצמה.\n"
                        "החזר אך ורק את שאילתת החיפוש המעודכנת, ללא הקדמות או הסברים משום סוג!"
                    )
                }
            ]
            rewriter_messages.extend(clean_history[-2:])
            rewriter_messages.append({"role": "user", "content": f"שאלת המשך: {user_question}"})

            rewrite_response = client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=rewriter_messages,
                temperature=0.0
            )
            search_query = rewrite_response.choices[0].message.content.strip()
            print(f"🔍 שאילתה מקורית: '{user_question}' -> שודרגה לחיפוש: '{search_query}'")
        except Exception as e:
            print(f"⚠️ Error during query rewriting: {e}")
            search_query = user_question

    # --- 3. שליפת המידע מהנהלים (RAG) על בסיס ה-search_query המשודרג ---
    user_vector = get_embedding(search_query)
    semantic_scores = np.dot(CHUNKS_EMBEDDINGS, user_vector)

    fuzzy_scores = []
    for chunk in CHUNKS_TEXTS:
        score = fuzz.partial_ratio(search_query, chunk) / 100.0
        fuzzy_scores.append(score)

    combined_scores = (semantic_scores * 0.7) + (np.array(fuzzy_scores) * 0.3)
    
    # שליפת 3 האינדקסים המובילים בלבד (מונע ערבוב מידע ומסנן רעשים)
    top_indices = np.argsort(combined_scores)[-3:][::-1]
    
    context_elements = []
    for rank, idx in enumerate(top_indices, 1):
        context_elements.append(
            f"--- קטע מידע {rank} (ציון התאמה: {combined_scores[idx]:.4f}) ---\n"
            f"{CHUNKS_TEXTS[idx]}"
        )
    context = "\n\n========================================\n\n".join(context_elements)
  
    # --- 4. הבניית הודעת המערכת (System Prompt) המאוחדת (עם הזחה נכונה בתוך פונקציית chat) ---
    messages = [
        {
            "role": "system", 
            "content": (
                "אתה עוזר דיגיטלי מקצועי, שירותי, ענייני ומדויק לחלוטין של אתר מייצגים בגביה של הביטוח הלאומי.\n"
                "תפקידך להנדס את המידע מהנהלים ולנסח תשובה נקייה, אסתטית, מרווחת, וללא מילים מיותרות או פרשנות עצמית.\n"
                "המידע מהנהלים (Context) מסופק לך כאשר הוא מחולק ל'קטע מידע 1', 'קטע מידע 2' וכו', ומסודר בסדר יורד לפי רמת הרלוונטיות שלו.\n\n"

                "⛔ חוק איסור פרשנות והמצאת עובדות (קריטי ומעל הכל):\n"
                "1. אל תפרש, אל תסביר את הלוגיקה מאחורי הנהלים, ואל תוסיף משפטי הקדמה או שלבים שלא מופיעים בטקסט במפורש!\n"
                "2. אסור להמציא פעולות, כותרות או שלבי ביניים שאינם כתובים בטקסט המקור.\n"
                "3. חל איסור מוחלט לערבב בין נהלים שונים! אם המשתמש שאל על קבלת קוד לנייד (סמס), התבסס אך ורק על הקטע העוסק בנייד. אל תשלב תנאים, חלופות או מגבלות שקשורים לקבלת קוד באימייל!\n"
                "4. אם המשתמש שואל אם משהו אפשרי, וקיימת בנהלים דרך מסוימת לבצע זאת, פתח מיד ובאופן חיובי בהנחיות המעשיות לביצוע (לדוגמה: 'כדי לקבל את הקוד חד פעמי לאימייל, יש לבצע את הפעולות הבאות:').\n\n"

                "🚫 חוק איסור שלבי כניסה והתחברות (mניעת שלבים מיותרים):\n"
                "1. חל איסור מוחלט לפתוח את התשובה או את השלב הראשון במשפטים כגון: 'היכנס לאתר מייצגים', 'התחבר למערכת', 'היכנס לאתר' וכדומה. הנחת היסוד היא שהמשתמש כבר נמצא בתוך המערכת או באתר המייצגים!\n"
                "2. התחל את השלב הראשון ישירות מהפעולה המעשית הראשונה בתוך האתר (לדוגמה: 'באתר מייצגים, לחץ על...', 'בתחתית הדף, לחץ על...').\n\n"

                "✨ חוק הדגשה והבלטה (קריטי לסריקה מהירה של העין):\n"
                "1. חובה להדגיש באמצעות כוכביות כפולות (לדוגמה: **שלב 1: גישה לרשימת דיווחים**) את כל כותרות השלבים, כותרות האפשרויות, או כותרות הסיכום.\n"
                "2. חובה להדגיש מונחי מפתח תפעוליים חשובים בתוך הטקסט (כמו שמות של כפתורים עליהם צריך ללחוץ, סטטוסים של טפסים כגון **'שלח טופס'**, או אזהרות כמו **שים לב:**).\n\n"

                "🧱 חוקי מבנה וארכיטקטורה דינמית:\n"
                "1. חוק הפרדת מסכים ומקורות (קריטי למניעת ערבוב): אם המידע בתשובה מבוסס על יותר מדף אחד בנהלים (למשל, קטע אחד עוסק במסך 'כתובות' וקטע אחר עוסק במסך 'מען הודעה'), חל איסור מוחלט לאחד אותם לרצף שלבים אחד! עליך לפצל את התשובה באופן ברור ומובחן באמצעות כותרות ראשיות המציינות את שם המסך או הנושא של אותו דף (לדוגמה: '**חלק 1: [שם המסך הראשון והדף]**' ולאחר מכן '**חלק 2: [שם המסך השני והדף]**').\n"
                "2. אבחנה מוחלטת בין שלבים לאפשרויות:\n"
                "   - השתמש במילה '**שלב**' (למשל: '**שלב 1: [שם השלב]**') אך ורק בתוך אותו חלק/מסך ספציפי עבור פעולות כרונולוגיות חובה וברורות שמופיעות בטקסט, שבהן המשתמש חייב לבצע את שלב א' כדי להתקדם לשלב ב'.\n"
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
        }
    ]
    
    for msg in clean_history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({
        "role": "user",
        "content": f"מידע מהנהלים (Context):\n{context}\n\nהשאלה הנוכחית של המשתמש: {user_question}"
    })

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.0  
        )
        raw_answer = response.choices[0].message.content
        
        # --- יצירת בלוק מטא-דאטה מוסתר כתושב אקורדיון לחיץ ---
        metadata_lines = [
            '<br><hr>',
            '<details style="margin-top: 15px; font-family: inherit;">',
            '  <summary style="color: #007bff; cursor: pointer; font-weight: bold; user-select: none; font-size: 14px;">',
            '    📊 לחץ כאן להצגת מטא דאטה של המקורות',
            '  </summary>',
            '  <div style="padding: 12px; background-color: #f8f9fa; border-right: 3px solid #007bff; margin-top: 8px; font-size: 14px; border-radius: 4px;">'
        ]
        
        for rank, idx in enumerate(top_indices, 1):
            chunk_text = CHUNKS_TEXTS[idx]
            metadata_lines.append(
                f"    <strong>קטע {rank}:</strong><br>"
                f"    📄 תוכן: {chunk_text[:150]}...<br>"
                f"    🧠 ציון סמנטי: {semantic_scores[idx]:.4f} | "
                f"    🔍 ציון פאזי: {fuzzy_scores[idx]:.4f} | "
                f"    ⚖️ ציון משוקלל: {combined_scores[idx]:.4f}<br>"
                f"    <hr style='border: 0; border-top: 1px dashed #ccd0d5; margin: 8px 0;'><br>"
            )
            
        metadata_lines.append('  </div>')
        metadata_lines.append('</details>')
        metadata_html = "\n".join(metadata_lines)
        
        # המרה תקנית של Markdown ל-HTML של תשובת ה-AI
        html_answer = markdown.markdown(raw_answer, extensions=['nl2br'])
        
        # השתלת הקישורים על גבי ה-HTML הסופי
        final_answer = inject_hyperlinks(html_answer)
        final_answer_with_metadata = final_answer + metadata_html
        
        return jsonify({"response": final_answer_with_metadata})

    except Exception as e:
        print(f"❌ Error calling OpenAI Chat Completion: {e}")
        return jsonify({"response": "מצטער, נתקלתי בשגיאה בתקשורת עם שרת ה-AI. אנא נסה שוב."})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
