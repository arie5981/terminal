from flask import Flask, render_template, request, jsonify
import os
import re
import numpy as np
from google import genai
from google.genai import types
from rapidfuzz import fuzz
import markdown  # ספרייה להמרת Markdown ל-HTML תקני ויפה

app = Flask(__name__)

# שליפת מפתח ה-API של גוגל באותיות גדולות
gemini_api_key = os.environ.get("GEMINI_API_KEY")

# הגדרת לקוח בצורה בטוחה שלא תקריס את עליית השרת ב-Fly.io
client = None
if gemini_api_key:
    try:
        client = genai.Client(api_key=gemini_api_key)
    except Exception as e:
        print(f"🚨 כישלון באתחול הלקוח של גוגל: {e}")

# משתנים גלובליים
LINKS_DICTIONARY = {}  
CHUNKS_TEXTS = []      
CHUNKS_EMBEDDINGS = None 

def load_and_parse_terminal_data():
    """
    טעינה וניתוח של קובץ הנהלים Terminal.txt לפי סימני ===פרק X===
    """
    global LINKS_DICTIONARY, CHUNKS_TEXTS, CHUNKS_EMBEDDINGS
    
    # בדיקה 1: האם הלקוח או המפתח חסרים במערכת
    if not gemini_api_key or client is None:
        print("🚨 חסר מפתח API של Gemini (GEMINI_API_KEY) או שהלקוח לא אותחל.")
        CHUNKS_TEXTS = ["שגיאה: מפתח ה-API לא הוגדר כראוי ב-Fly.io תחת השם GEMINI_API_KEY (אותיות גדולות בלבד!)."]
        CHUNKS_EMBEDDINGS = np.zeros((1, 768)) 
        return

    # בדיקה 2: האם קובץ הטקסט קיים בנתיב המיועד
    file_path = os.path.join(os.path.dirname(__file__), 'data', 'Terminal.txt')
    if not os.path.exists(file_path):
        print(f"⚠️ הקובץ בכתובת {file_path} לא נמצא!")
        CHUNKS_TEXTS = [f"שגיאה: הקובץ Terminal.txt לא נמצא בנתיב השרת: {file_path}"]
        CHUNKS_EMBEDDINGS = np.zeros((1, 768))
        return

    # קריאת הקובץ
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        CHUNKS_TEXTS = [f"שגיאה בקריאת הקובץ: {e}"]
        CHUNKS_EMBEDDINGS = np.zeros((1, 768))
        return

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

    # --- 4. וקטוריזציה מראש באמצעות מודל גוגל ---
    if CHUNKS_TEXTS:
        try:
            response = client.models.embed_content(
                model="text-embedding-004",
                contents=CHUNKS_TEXTS
            )
            CHUNKS_EMBEDDINGS = np.array([item.values for item in response.embeddings])
        except Exception as e:
            print(f"❌ Error generating embeddings: {e}")
            CHUNKS_TEXTS = [f"שגיאה בתהליך יצירת ה-Embeddings מול גוגל: {e}"]
            CHUNKS_EMBEDDINGS = np.zeros((1, 768))

# הרצת פונקציית הטעינה
load_and_parse_terminal_data()

def get_embedding(text):
    """יצירת וקטור לשאילתת המשתמש"""
    if client is None:
        return [0] * 768
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

    # הדפסת הודעת שגיאה מובנית בצ'אט אם משהו נכשל בטעינה
    if CHUNKS_TEXTS and "שגיאה:" in CHUNKS_TEXTS[0]:
        return jsonify({"response": CHUNKS_TEXTS[0]})

    if not CHUNKS_TEXTS or CHUNKS_EMBEDDINGS is None or client is None:
        return jsonify({"response": "מערכת הנתונים של הטרמינל או לקוח ה-AI אינם טעונים כראוי."})

    # חישוב סמנטי וחישוב פאזי (Fuzzy Match)
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
        "3. נסח את הדברים בצורה שירותית, זורמת וחופשית - אל תעתיק משפטים יבשים מהקובץ מילה במילה, אלא תן חוויית מענה אנושית ואינטליגנטית.\n"
        "4. אם מופיע ביטוי בסוגריים מרובעים (כמו [אתר מייצגים בגביה] או כתובת אימייל), שמור על הסוגריים המרובעים בדיוק כפי שהם בתשובתך."
    )

    contents = []
    for msg in chat_history:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(
            types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])])
        )

    current_user_content = f"מידע מהנהלים:\n{context}\n\nהשאלה הנוכחית של המשתמש: {user_question}"
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=current_user_content)])
    )

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.5
            )
        )
        
        raw_answer = response.text
        html_answer = markdown.markdown(raw_answer, extensions=['nl2br'])
        final_answer = inject_hyperlinks(html_answer)
        return jsonify({"response": final_answer})

    except Exception as e:
        return jsonify({"response": f"מצטער, נתקלתי בשגיאה בתקשורת עם שרת ה-AI של גוגל: {e}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
