התבלבלתי. תכתוב לי app.pyמלא.  זה ה app.py הנוכחי.
from flask import Flask, render_template, request, jsonify
import os
import re
import numpy as np
from openai import OpenAI
from rapidfuzz import fuzz

app = Flask(__name__)

# אתחול קליינט OpenAI (ימשוך את ה-API Key אוטומטית ממשתני הסביבה ב-Fly.io)
client = OpenAI()

# משתנים גלובליים שישמרו בזיכרון השרת עם העלייה
LINKS_DICTIONARY = {}  # מילון קישורים מפרק 1
CHUNKS_TEXTS = []      # טקסט גולמי של המנות (פרק 2 + פרק 3)
CHUNKS_EMBEDDINGS = None # מערך הוקטורים בזיכרון

def load_and_parse_terminal_data():
    """
    טעינה וניתוח של קובץ הנהלים Terminal.txt וחלוקתו לפרקים ומנות
    """
    global LINKS_DICTIONARY, CHUNKS_TEXTS, CHUNKS_EMBEDDINGS
    
    file_path = os.path.join(os.path.dirname(__file__), 'data', 'Terminal.txt')
    
    if not os.path.exists(file_path):
        print(f"⚠️ Warning: {file_path} not found. Running with empty data.")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # --- פירוק ראשוני לפי פרקים ---
    # נחפש את כותרות הפרקים באמצעות ביטויים רגולריים
    parts = re.split(r'-+\s*(פרק \d+.*?)-+', content)
    
    chapter_1_text = ""
    chapter_2_text = ""
    chapter_3_text = ""

    for i in range(1, len(parts), 2):
        title = parts[i]
        body = parts[i+1] if i+1 < len(parts) else ""
        
        if "פרק 1" in title:
            chapter_1_text = body
        elif "פרק 2" in title:
            chapter_2_text = body
        elif "פרק 3" in title:
            chapter_3_text = body

    # --- 1. עיבוד פרק 1: הגדרות קישורים גלובליות ---
    # מחפש תבניות של >>טקסט: קישור<<
    link_matches = re.findall(r'>>([^:]+):\s*(https?://[^\s<]+)<<', chapter_1_text)
    for name, url in link_matches:
        LINKS_DICTIONARY[name.strip()] = url.strip()
    print(f"Loaded {len(LINKS_DICTIONARY)} global links from Chapter 1.")

    # --- 2. עיבוד פרק 2: שאלות ותשובות נפוצות ---
    # מחלק לפי המילה "שאלה:" כדי לבודד כל בלוק של שאלה+ניסוחים+תשובה
    qna_blocks = re.split(r'(?=שאלה:)', chapter_2_text)
    for block in qna_blocks:
        block_clean = block.strip()
        if block_clean and "תשובה:" in block_clean:
            CHUNKS_TEXTS.append(block_clean)

    # --- 3. עיבוד פרק 3: תיאור אתר מייצגים ---
    # מחלק לפי הביטוי "דף מייצגים - "
    page_blocks = re.split(r'(?=דף מייצגים - )', chapter_3_text)
    for block in page_blocks:
        block_clean = block.strip()
        if block_clean:
            CHUNKS_TEXTS.append(block_clean)

    print(f"Total structured chunks extracted: {len(CHUNKS_TEXTS)}")

    # --- 4. וקטוריזציה מראש (Embedding) של כל המנות ---
    if CHUNKS_TEXTS:
        try:
            response = client.embeddings.create(
                input=CHUNKS_TEXTS,
                model="text-embedding-3-small"
            )
            # שמירת הוקטורים בתוך מערך numpy בזיכרון השרת בשביל מהירות מירבית
            CHUNKS_EMBEDDINGS = np.array([item.embedding for item in response.data])
            print("Successfully generated embeddings for all chunks. Backend is ready!")
        except Exception as e:
            print(f"❌ Error generating initial embeddings: {e}")

# הפעלת הפונקציה מיד עם טעינת ה-App (פעם אחת בלבד בזמן ה-Boot)
load_and_parse_terminal_data()

def get_embedding(text):
    """הפיכת טקסט בודד (שאלת המשתמש) לוקטור"""
    response = client.embeddings.create(
        input=[text],
        model="text-embedding-3-small"
    )
    return response.data[0].embedding

def inject_hyperlinks(text):
    """
    סורק את הטקסט ומחליף סוגריים מרובעים [אתר מייצגים בגביה] 
    בהיפר קישור מעוצב בצבע כחול עם קו תחתון לפי מילון הקישורים מפרק 1
    """
    for name, url in LINKS_DICTIONARY.items():
        placeholder = f"[{name}]"
        if placeholder in text:
            hyperlink = f'<a href="{url}" style="color: #007bff; text-decoration: underline; font-weight: bold;" target="_blank">{name}</a>'
            text = text.replace(placeholder, hyperlink)
    return text

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json or {}
    user_question = data.get('question', '').strip()
    chat_history = data.get('history', []) # היסטוריית השיחה שהגיעה מהדפדפן

    if not user_question:
        return jsonify({"response": "לא התקבלה שאלה תקינה."})

    if not CHUNKS_TEXTS:
        return jsonify({"response": "מערכת הנתונים של הטרמינל אינה טעונה כראוי בשרת."})

    # --- שלב א': חישוב מרחק סמנטי (Cosine Similarity) ---
    user_vector = get_embedding(user_question)
    
    # מכפלה מטריציונית פשוטה ומהירה בין וקטור השאלה לכל וקטורי המנות בזיכרון
    semantic_scores = np.dot(CHUNKS_EMBEDDINGS, user_vector)

    # --- שלב ב': חיפוש מילולי מהיר (Fuzzy Match) ---
    fuzzy_scores = []
    for chunk in CHUNKS_TEXTS:
        # בודק התאמה מילולית בין שאלת המשתמש לטקסט המנה (חזק מאוד לאיתור מספרי דפים ומילים ייחודיות)
        score = fuzz.partial_ratio(user_question, chunk) / 100.0
        fuzzy_scores.append(score)

    # --- שלב ג': שקלול היברידי ---
    # שילוב של הציון הסמנטי (70%) והציון המילולי (30%) כדי לקבל את המנות הכי מדויקות
    combined_scores = (semantic_scores * 0.7) + (np.array(fuzzy_scores) * 0.3)
    
    # שליפת 3 המנות עם הציון המשוקלל הגבוה ביותר
    top_indices = np.argsort(combined_scores)[-3:][::-1]
    retrieved_chunks = [CHUNKS_TEXTS[idx] for idx in top_indices]
    
    # חיבור המנות לבלוק מידע אחד שיוזרק ל-Prompt
    context = "\n\n---\n\n".join(retrieved_chunks)

    # --- שלב ד': בניית ה-Prompt ל-OpenAI בשילוב ה-Chat History ---
    messages = [
        {
            "role": "system", 
            "content": (
                "אתה עוזר דיגיטלי מקצועי וידידותי של אתר מייצגים בגביה של הביטוח הלאומי. "
                "תפקידך לענות לנציגים ולמייצגים בצורה ברורה, תמציתית ומדויקת על בסיס נהלי הטרמינל בלבד.\n\n"
                "הנחיות קשיחות לגבי התשובה:\n"
                "1. ענה אך ורק על סמך המידע הנמצא תחת קטגוריית 'מידע מהנהלים' המצורף מטה.\n"
                "2. אם המידע לא קיים בהקשר המצורף, אמור בעדינות: 'אין לי הנחיה מפורשת בנושא זה בנהלי הטרמינל'. אל תמציא שום עובדה או נוהל!\n"
                "3. אם בתוך קטגוריית 'מידע מהנהלים' מופיע שם של אתר או שירות בתוך סוגריים מרובעים, למשל [אתר מייצגים בגביה], עליך להקפיד לכתוב אותו בדיוק כך בתשובתך עם הסוגריים המרובעים (למשל: [אתר מייצגים בגביה]), כדי שהמערכת האוטומטית תוכל להשתיל שם קישור.\n"
                "4. שמור על שיח ענייני ומקצועי המותאם למייצגים."
            )
        }
    ]

    # הזרקת היסטוריית השיחה הקודמת (חילופי דברים אחרונים) כדי לשמור על הקשר השיחה
    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # הזרקת השאלה הנוכחית יחד עם המידע שנשלה מה-RAG
    messages.append({
        "role": "user",
        "content": f"מידע מהנהלים:\n{context}\n\nהשאלה הנוכחית של המשתמש: {user_question}"
    })

    # --- שלב ה': פנייה ל-gpt-4o-mini לקבלת התשובה ---
    try:
        response = client.choices.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.2 # טמפרטורה נמוכה כדי להבטיח היצמדות מקסימלית לעובדות במסמך
        )
        raw_answer = response.choices[0].message.content

        # --- שלב ו': השתלת היפר-קישורים אוטומטית לפני השליחה למשתמש ---
        final_answer = inject_hyperlinks(raw_answer)

        return jsonify({"response": final_answer})

    except Exception as e:
        print(f"❌ Error calling OpenAI Chat Completion: {e}")
        return jsonify({"response": "מצטער, נתקלתי בשגיאה בתקשורת עם שרת ה-AI. אנא נסה שוב."})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
