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

def load_and_parse_terminal_data():
    """
    טעינה וניתוח של קובץ הנהלים Terminal.txt לפי סימני ===פרק X===
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
    qna_blocks = re.split(r'(?=שאלה:)', chapter_2_text)
    for block in qna_blocks:
        block_clean = block.strip()
        if block_clean and "תשובה:" in block_clean:
            CHUNKS_TEXTS.append(block_clean)

    # --- 3. עיבוד פרק 3: תיאור אתר מייצגים ---
    page_blocks = re.split(r'(?=דף מייצגים - \d+)', chapter_3_text)
    for block in page_blocks:
        block_clean = block.strip()
        if block_clean and ("נושא:" in block_clean or "הסבר והנחיות:" in block_clean):
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

    # חיפוש גנרי לחלוטין ללא שום מניפולציה על השאלה
    user_vector = get_embedding(user_question)
    semantic_scores = np.dot(CHUNKS_EMBEDDINGS, user_vector)

    fuzzy_scores = []
    for chunk in CHUNKS_TEXTS:
        score = fuzz.partial_ratio(user_question, chunk) / 100.0
        fuzzy_scores.append(score)

    combined_scores = (semantic_scores * 0.7) + (np.array(fuzzy_scores) * 0.3)
    
    # שליפת 6 צ'אנקים כדי להבטיח מרחב מידע רחב מספיק שמכיל ריבוי אפשרויות אם הן קיימות
    top_indices = np.argsort(combined_scores)[-6:][::-1]
    retrieved_chunks = [CHUNKS_TEXTS[idx] for idx in top_indices]
    context = "\n\n---\n\n".join(retrieved_chunks)

    # 🧠 פרומפט מערכת גנרי ואוניברסלי לניהול ריבוי אפשרויות ועמימות
    messages = [
        {
            "role": "system", 
            "content": (
                "אתה עוזר דיגיטלי מקצועי, שירותי, ענייני ומדויק לחלוטין של אתר מייצגים בגביה של הביטוח הלאומי.\n"
                "תפקידך להנדס את המידע מהנהלים (Context) ולנסח תשובה נקייה, אסתטית ומרווחת, ללא שום פרשנות עצמית.\n\n"
                "🧱 חוק ניהול ריבוי אפשרויות ועמימות (קריטי ואוניברסלי):\n"
                "1. זיהוי חלופות ב-Context: עליך לבחון היטב את המידע שסופק לך. אם ה-Context מכיל יותר מתשובה אחת, נתיב אחד, או סוג אחד של פעולה שמתאימים לשאלת המשתמש, חובה עליך להציג את כולם בתור אפשרויות נפרדות ומקבילות!\n"
                "2. איסור איחוד וערבוב: לעולם אל תערבב מידע של שני תהליכים נפרדים או קטגוריות שונות לתוך רצף שלבים אחד (לדוגמה: אל תבנה 'שלב 1, שלב 2, שלב 3' שמורכב מחצי מידע של נושא א' וחצי מידע של נושא ב').\n"
                "3. מבנה התצוגה בריבוי אפשרויות:\n"
                "   - פתח במשפט פתיחה שמבהיר למשתמש שיש מספר אפשרויות/נתיבים רלוונטיים (לדוגמה: 'בנושא זה קיימות מספר אפשרויות בהתאם למקרה:', או 'באתר קיימים שני מסלולים שונים לבצע זאת:').\n"
                "   - הצג כל אפשרות תחת כותרת מודגשת נפרדת: '**אפשרות 1: [שם האפשרות]**', '**אפשרות 2: [שם האפשרות]**'.\n"
                "   - מתחת לכל אפשרות, פרט את תתי-הסעיפים (השלבים הפנימיים של אותו נתיב) באמצעות בוליטים קצרים ומרווחים (•).\n\n"
                "⛔ חוק איסור פרשנות והמצאת עובדות:\n"
                "1. היצמד אך ורק לעובדות היבשות ב-Context. אל תסביר את הלוגיקה, ואל תוסיף משפטי הקדמה או סתירה שלא מופיעים בטקסט (כמו 'פעולה זו לא ניתנת לביצוע ישיר' וכדומה).\n"
                "2. אם המידע קיים, הצג אותו מיד בצורה מעשית וחיובית.\n\n"
                "🎯 חוקי ניסוח, פתיח וסיום:\n"
                "1. גישה ישירה לעניין: פתח מיד במשפט ענייני המחובר ישירות לשאלת המשתמש. ללא מילים מתישות כמו 'תודה על השאלה!'.\n"
                "2. איסור סוגריים מרובעים בשיחה: לעולם אל תשים את משפטי הפתיחה או הסיום שלך בתוך סוגריים מרובעים.\n"
                "3. סיום נקי: חתום במשפט קצר וטבעי, או סיים ישירות בסיכום המידע ללא שבלונות קבועות.\n\n"
                "🧱 ארכיטקטורה דינמית (כאשר יש רק תשובה אחת ברורה):\n"
                "- השתמש במילה '**שלב 1**' אך ורק אם מדובר בתהליך כרונולוגי חובה של צעד אחר צעד.\n"
                "- הצג חלק סיכום בסוף ('**סיום התהליך:**' או '**זמני טיפול:**') רק אם קיים מידע רלוונטי כזה בנהלים.\n"
                "- דגשים מיוחדים או אזהרות יוצגו בשורה נפרדת ומודגשת (למשל: '**שים לב:**').\n\n"
                "🔗 חוקי קישורים וסוגריים מרובעים:\n"
                "- חובה לעטוף שמות טפסים, אתרים, מערכות או מיילים בסוגריים מרובעים בדיוק כפי שהם מופיעים בנהלים (לדוגמה: [אתר שירות אישי]). אל תשמיט את הסוגריים המרובעים האלו."
            )
        }
    ]
    
    for msg in chat_history:
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
        
        # המרה תקנית של Markdown ל-HTML
        html_answer = markdown.markdown(raw_answer, extensions=['nl2br'])
        
        # השתלת הקישורים על גבי ה-HTML הסופי
        final_answer = inject_hyperlinks(html_answer)
        return jsonify({"response": final_answer})

    except Exception as e:
        print(f"❌ Error calling OpenAI Chat Completion: {e}")
        return jsonify({"response": "מצטער, נתקלתי בשגיאה בתקשורת עם שרת ה-AI. אנא נסה שוב."})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
