from flask import Flask, render_template, request, jsonify
import os
import re
import numpy as np
from google import genai
from google.genai import types
from rapidfuzz import fuzz
import markdown  # ספרייה להמרת Markdown ל-HTML תקני ויפה

app = Flask(__name__)

# שליפת מפתח ה-API של גוגל (המערכת שולפת אוטומטית את GEMINI_API_KEY מתוך הסביבה)
gemini_api_key = os.environ.get("Gemini_API_Key")
client = genai.Client()

# משתנים גלובליים
LINKS_DICTIONARY = {}  
CHUNKS_TEXTS = []      
CHUNKS_EMBEDDINGS = None 

def load_and_parse_terminal_data():
    """
    טעינה וניתוח של קובץ הנהלים Terminal.txt לפי סימני ===פרק X===
    """
    global LINKS_DICTIONARY, CHUNKS_TEXTS, CHUNKS_EMBEDDINGS
    
    if not gemini_api_key:
        print("🚨 חסר מפתח API של Gemini (GEMINI_API_KEY).")
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

    # --- 4. וקטוריזציה מראש באמצעות מודל גוגל ---
    if CHUNKS_TEXTS:
        try:
            # שימוש במודל האמבדינגס העדכני של גוגל
            response = client.models.embed_content(
                model="text-embedding-004",
                contents=CHUNKS_TEXTS
            )
            # גוגל מחזירה רשימה של אובייקטי embedding המכילים ערכי values
            CHUNKS_EMBEDDINGS = np.array([item.values for item in response.embeddings])
            print("Successfully generated Gemini embeddings. System is live!")
        except Exception as e:
            print(f"❌ Error generating embeddings: {e}")

load_and_parse_terminal_data()

def get_embedding(text):
    """יצירת וקטור לשאילתת המשתמש"""
    response = client.models.embed_content(
        model="text-embedding-004",
        contents=[text]
    )
    return response.embeddings[0].values

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

    # שליפת וקטור והרצת החיפוש הסמנטי והפזי
    user_vector = get_embedding(user_question)
    semantic_scores = np.dot(CHUNKS_EMBEDDINGS, user_vector)

    fuzzy_scores = []
    for chunk in CHUNKS_TEXTS:
        score = fuzz.partial_ratio(user_question, chunk) / 100.0
        fuzzy_scores.append(score)

    combined_scores = (semantic_scores * 0.7) + (np.array(fuzzy_scores) * 0.3)
    
    top_indices = np.argsort(combined_scores)[-6:][::-1]
    retrieved_chunks = [CHUNKS_TEXTS[idx] for idx in top_indices]
    context = "\n\n---\n\n".join(retrieved_chunks)

    # הגדרת ה-System Prompt המקיף כהנחיית מערכת ייעודית של גוגל
    system_instruction = (
        "אתה עוזר דיגיטלי מקצועי, שירותי וידידותי ביותר של אתר מייצגים בגביה של הביטוח הלאומי.\n"
        "תפקידך לספק תשובות מלאות, עשירות, מקיפות ונעימות מאוד לעין, בדיוק ברמה של צ'אטבוט מתקדמים.\n\n"
        "הנחיות עיצוב ומבנה (Markdown תקני):\n"
        "1. השתמש בהדגשות (כוכביות כפולות, למשל **טקסט מודגש**) עבור כותרות משנה, שלבים קריטיים, או שמות של תפריטים ומסלולים במערכת.\n"
        "2. חלק את התשובה לפסקאות קטנות וברורות. השתמש ברשימות ממוספרות (1, 2, 3) או בנקודות (בוליטים) בצורה מרווחת ומסודרת.\n"
        "3. התחל את התשובה בפתיח קצר ונעים (למשל: 'על פי נהלי התמיכה וההנחיות, הנה הדרכים לביצוע...'), וסיים בסיום שירותי.\n\n"
        "הנחיות תוכן וניסוח:\n"
        "1. הבס את תשובתך אך ורק על העובדות והנהלים המופיעים תחת 'מידע מהנהלים' המצורף מטה.\n"
        "2. חבר את המידע בצורה חכמה! אם השאלה נוגעת לחובות, ומופיע מידע על מספר שיטות (למשל: גם הרשאה לחיוב, גם הסדר בפריסה וגם הפקת שוברים), הצג את כל האפשרויות הללו למשתמש בצורה מאורגנת ומסווגת.\n"
        "3. Nסח את הדברים בצורה שירותית, זורמת וחופשית - אל תעתיק משפטים יבשים מהקובץ מילה במילה, אלא תן חוויית מענה אנושית ואינטליגנטית.\n"
        "4. אם מופיע ביטוי בסוגריים מרובעים (כמו [אתר מייצגים בגביה] או כתובת אימייל), שמור על הסוגריים המרובעים בדיוק כפי שהם בתשובתך."
    )

    # בניית מערך התוכן (contents) כולל היסטוריית השיחה בהתאמה למבנה של גוגל
    contents = []
    
    for msg in chat_history:
        # התאמת התפקידים: OpenAI משתמש ב-assistant, גוגל ב-model
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(
            types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])])
        )

    # הוספת השאילתה הנוכחית יחד עם הקשר הנהלים שנשלף מה-RAG
    current_user_content = f"מידע מהנהלים:\n{context}\n\nהשאלה הנוכחית של המשתמש: {user_question}"
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=current_user_content)])
    )

    try:
        # קריאה ל-Gemini 3.5 Flash עם הגדרות קונפיגורציה
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.5
            )
        )
        
        raw_answer = response.text
        
        # המרה תקנית ומקצועית של Markdown ל-HTML
        html_answer = markdown.markdown(raw_answer, extensions=['nl2br'])
        
        # השתלת הקישורים על גבי ה-HTML הסופי
        final_answer = inject_hyperlinks(html_answer)
        return jsonify({"response": final_answer})

    except Exception as e:
        print(f"❌ Error calling Gemini API: {e}")
        return jsonify({"response": "מצטער, נתקלתי בשגיאה בתקשורת עם שרת ה-AI. אנא נסה שוב."})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
