from flask import Flask, render_template, request, jsonify
import os
import re
import numpy as np
from openai import OpenAI
from rapidfuzz import fuzz

app = Flask(__name__)

# --- בדיקת מפתח ה-API של OpenAI מתוך משתני הסביבה ---
openai_api_key = os.environ.get("OPENAI_API_KEY")
if not openai_api_key:
    print("🚨 אזהרה קריטית: OPENAI_API_KEY לא מוגדר במערכת!")
else:
    print("✅ מפתח OPENAI_API_KEY זוהה במערכת בהצלחה.")

# אתחול קליינט OpenAI
client = OpenAI(api_key=openai_api_key)

# משתנים גלובליים שישמרו בזיכרון השרת עם העלייה
LINKS_DICTIONARY = {}  # מילון קישורים מפרק 1
CHUNKS_TEXTS = []      # טקסט גולמי של המנות (פרק 2 + פרק 3)
CHUNKS_EMBEDDINGS = None # מערך הוקטורים בזיכרון

def load_and_parse_terminal_data():
    """
    טעינה וניתוח של קובץ הנהלים Terminal.txt בשיטה ישירה וחסינה
    """
    global LINKS_DICTIONARY, CHUNKS_TEXTS, CHUNKS_EMBEDDINGS
    
    if not openai_api_key:
        print("⚠️ עצירת טעינת הנתונים: חסר מפתח API.")
        return

    file_path = os.path.join(os.path.dirname(__file__), 'data', 'Terminal.txt')
    if not os.path.exists(file_path):
        print(f"⚠️ שגיאה: הקובץ בכתובת {file_path} לא נמצא!")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # נירמול ירידות שורה
    content = content.replace('\r\n', '\n')

    # --- מנגנון חיתוך ישיר וחסין ללא תלות במקפים ---
    # מוצאים את המיקומים של כותרות הפרקים בטקסט
    idx_p1 = content.find("פרק 1")
    idx_p2 = content.find("פרק 2")
    idx_p3 = content.find("פרק 3")

    if idx_p1 == -1 or idx_p2 == -1 or idx_p3 == -1:
        print("⚠️ אזהרה: לא כל הפרקים נמצאו בשיטה הישירה, מנסה חיתוך חלופי...")
        # גיבוי קל במקרה של הבדלי רווחים
        idx_p1 = content.find("פרק 1") if idx_p1 != -1 else 0
        idx_p2 = content.find("פרק 2") if idx_p2 != -1 else content.find("שאלות ותשובות")
        idx_p3 = content.find("פרק 3") if idx_p3 != -1 else content.find("תיאור אתר מייצגים")

    # בידוד הטקסט של כל פרק על פי המיקומים
    chapter_1_text = content[idx_p1:idx_p2]
    chapter_2_text = content[idx_p2:idx_p3]
    chapter_3_text = content[idx_p3:]

    # --- 1. עיבוד פרק 1: הגדרות קישורים גלובליות ---
    link_matches = re.findall(r'>>([^:]+):\s*(https?://[^\s<]+)<<', chapter_1_text)
    for name, url in link_matches:
        LINKS_DICTIONARY[name.strip()] = url.strip()
    print(f"Loaded {len(LINKS_DICTIONARY)} global links from Chapter 1.")

    # --- 2. עיבוד פרק 2: שאלות ותשובות נפוצות ---
    qna_blocks = re.split(r'(?=שאלה:)', chapter_2_text)
    for block in qna_blocks:
        block_clean = block.strip()
        if block_clean and "תשובה:" in block_clean:
            CHUNKS_TEXTS.append(block_clean)

    # --- 3. עיבוד פרק 3: תיאור אתר מייצגים (דפי מייצגים) ---
    page_blocks = re.split(r'(?=דף מייצגים - \d+)', chapter_3_text)
    for block in page_blocks:
        block_clean = block.strip()
        if block_clean and ("נושא:" in block_clean or "הסבר והנחיות:" in block_clean):
            CHUNKS_TEXTS.append(block_clean)

    print(f"Total structured chunks extracted: {len(CHUNKS_TEXTS)}")

    # --- 4. וקטוריזציה מראש (Embedding) של כל המנות ---
    if CHUNKS_TEXTS:
        try:
            response = client.embeddings.create(
                input=CHUNKS_TEXTS,
                model="text-embedding-3-small"
            )
            CHUNKS_EMBEDDINGS = np.array([item.embedding for item in response.data])
            print("Successfully generated embeddings for all chunks. Backend is ready!")
        except Exception as e:
            print(f"❌ Error generating initial embeddings: {e}")

# הפעלת הפונקציה בזמן עליית השרת
load_and_parse_terminal_data()

def get_embedding(text):
    """הפיכת שאלת המשתמש לוקטור"""
    response = client.embeddings.create(
        input=[text],
        model="text-embedding-3-small"
    )
    return response.data[0].embedding

def inject_hyperlinks(text):
    """השתלת קישורים בצורה אוטומטית מטקסט בתוך סוגריים מרובעים"""
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
    chat_history = data.get('history', [])

    if not user_question:
        return jsonify({"response": "לא התקבלה שאלה תקינה."})

    if not CHUNKS_TEXTS or CHUNKS_EMBEDDINGS is None:
        return jsonify({"response": "מערכת הנתונים של הטרמינל אינה טעונה כראוי בשרת. ודא שהגדרת את משתנה הסביבה OPENAI_API_KEY ב-Fly.io וששם הקובץ הוא Terminal.txt."})

    # א. מרחק סמנטי
    user_vector = get_embedding(user_question)
    semantic_scores = np.dot(CHUNKS_EMBEDDINGS, user_vector)

    # ב. חיפוש מילולי מהיר (Fuzzy Match)
    fuzzy_scores = []
    for chunk in CHUNKS_TEXTS:
        score = fuzz.partial_ratio(user_question, chunk) / 100.0
        fuzzy_scores.append(score)

    # ג. שקלול היברידי (70% סמנטי, 30% מילולי)
    combined_scores = (semantic_scores * 0.7) + (np.array(fuzzy_scores) * 0.3)
    
    # שליפת 3 המנות הכי מתאימות
    top_indices = np.argsort(combined_scores)[-3:][::-1]
    retrieved_chunks = [CHUNKS_TEXTS[idx] for idx in top_indices]
    context = "\n\n---\n\n".join(retrieved_chunks)

    # ד. בניית ה-Prompt ל-OpenAI
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

    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({
        "role": "user",
        "content": f"מידע מהנהלים:\n{context}\n\nהשאלה הנוכחית של המשתמש: {user_question}"
    })

    # ה. פנייה ל-OpenAI לקבלת תשובה חכמה
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.2
        )
        raw_answer = response.choices[0].message.content
        final_answer = inject_hyperlinks(raw_answer)
        return jsonify({"response": final_answer})

    except Exception as e:
        print(f"❌ Error calling OpenAI Chat Completion: {e}")
        return jsonify({"response": "מצטער, נתקלתי בשגיאה בתקשורת עם שרת ה-AI. אנא נסה שוב."})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
