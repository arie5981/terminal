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

    user_vector = get_embedding(user_question)
    semantic_scores = np.dot(CHUNKS_EMBEDDINGS, user_vector)

    fuzzy_scores = []
    for chunk in CHUNKS_TEXTS:
        score = fuzz.partial_ratio(user_question, chunk) / 100.0
        fuzzy_scores.append(score)

    combined_scores = (semantic_scores * 0.7) + (np.array(fuzzy_scores) * 0.3)
    
    top_indices = np.argsort(combined_scores)[-4:][::-1]
    retrieved_chunks = [CHUNKS_TEXTS[idx] for idx in top_indices]
    context = "\n\n---\n\n".join(retrieved_chunks)

# 🧠 הנחיות מבנה ועיצוב גנריות לחלוטין - מתאימות לכל שאלה ומחקות את ג'ימיני
    messages = [
        {
            "role": "system", 
            "content": (
                "אתה עוזר דיגיטלי מקצועי, שירותי, ואינטליגנטי ביותר של אתר מייצגים בגביה של הביטוח הלאומי.\n"
                "תפקידך להנדס את המידע הגולמי מהנהלים ולנסח תשובה עשירה, מרווחת, ואסתטית מאוד לעין.\n\n"
                "🧱 חוקי מבנה וארכיטקטורה (חובה לכל שאלה):\n"
                "1. חוק ה-2 עד 4: חלוק את התשובה למינימום 2 ומקסימום 4 חלקים או שלבים מרכזיים בלבד. אל תפצל את המידע ליותר מדי תתי-נושאים.\n"
                "2. כותרות מודגשות: כל חלק מרכזי חייב להתחיל בכותרת ברורה ומודגשת (למשל: '**חלק 1: [שם החלק]**' או '**שלב 1: [שם השלב]**').\n"
                "3. תתי-סעיפים (בוליטים): מתחת לכל כותרת ראשית, פרט את המידע וההנחיות בשורות קצרות, מרווחות וברורות באמצעות נקודות (•).\n"
                "4. דגשים מיוחדים: אם יש תנאי חובה, אזהרה או שלב קריטי, הצג אותו בשורה נפרדת ומודגשת (למשל: '**שים לב:**' או '**שלב קריטי:**').\n"
                "5. מסגרת שירותית: פתח תמיד בפתיח קצר, חיובי וממוקד בשאלת המשתמש, וסיים במשפט סיום שירותי.\n\n"
                "🔗 חוקי קישורים וסוגריים מרובעים (קריטי לכל מונח):\n"
                "- עליך לסרוק את תשובתך ולוודא שכל שם של טופס, אתר, מערכת או כתובת מייל שמופיעים בה, עטופים בדיוק בסוגריים מרובעים כפי שהם מופיעים בנהלים (לדוגמה: [אתר שירות אישי], [טופס הוספת משתמשים \"בל 68\"], [addmy@nioi.gov.il]). אל תשמיט את הסוגריים המרובעים האלו, הם קריטיים להפעלת הקישורים באתר!\n\n"
                "📋 תבנית המבנה הוויזואלי הנדרש ממך (דוגמה מופשטת):\n"
                "[פתיח לבבי וממוקד בשאלה]\n\n"
                "**שלב 1: [שם שלב ראשון מקיף]**\n"
                "• [פרט מידע א']\n"
                "• [פרט מידע ב']\n\n"
                "**שלב 2: [שם שלב שני מקיף]**\n"
                "• [פרט מידע ג']\n"
                "• [פרט מידע ד']\n"
                "**שים לב:** [הערה או אזהרה חשובה במידה וקיימת]\n\n"
                "**סיום התהליך / זמני טיפול:**\n"
                "[תיאור סיום התהליך כפי שמופיע בנהלים]\n\n"
                "[משפט סיום שירותי]"
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
            temperature=0.4  # הגדלה קלה ל-0.4 כדי לתת לו חופש עיצובי עשיר יותר, אך עדיין מדויק
        )
        raw_answer = response.choices[0].message.content
        
        # המרה תקנית של Markdown ל-HTML (מטפל בכותרות, הדגשות, ובוליטים)
        html_answer = markdown.markdown(raw_answer, extensions=['nl2br'])
        
        # השתלת הקישורים על גבי ה-HTML הסופי על בסיס הסוגריים המרובעים
        final_answer = inject_hyperlinks(html_answer)
        return jsonify({"response": final_answer})

    except Exception as e:
        print(f"❌ Error calling OpenAI Chat Completion: {e}")
        return jsonify({"response": "מצטער, נתקלתי בשגיאה בתקשורת עם שרת ה-AI. אנא נסה שוב."})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
