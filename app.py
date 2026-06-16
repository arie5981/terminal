from flask import Flask, render_template, request, jsonify
import os
import re
import numpy as np
from google import genai
from google.genai import types
from rapidfuzz import fuzz
import markdown

app = Flask(__name__)

# שליפת מפתח ה-API של גוגל
gemini_api_key = os.environ.get("GEMINI_API_KEY")

# אתחול הלקוח של גוגל
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
    """ טעינה וניתוח של קובץ הנהלים """
    global LINKS_DICTIONARY, CHUNKS_TEXTS, CHUNKS_EMBEDDINGS
    
    # אם כבר טענו בעבר, אין צורך לטעון שוב
    if CHUNKS_TEXTS and CHUNKS_EMBEDDINGS is not None:
        return True

    if not gemini_api_key or client is None:
        return False

    file_path = os.path.join(os.path.dirname(__file__), 'data', 'Terminal.txt')
    if not os.path.exists(file_path):
        return False

    try:
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

        # חילוץ קישורים
        link_matches = re.findall(r'>>([^:]+):\s*([^\s<<]+)<<', chapter_1_text)
        for name, url in link_matches:
            LINKS_DICTIONARY[name.strip()] = url.strip()

        # חילוץ פרק 2 (שאלות ותשובות) - מנגנון חסין
        local_chunks = []
        qna_blocks = re.split(r'(?=שאלה:)', chapter_2_text)
        for block in qna_blocks:
            block_clean = block.strip()
            if block_clean and "תשובה:" in block_clean:
                local_chunks.append(block_clean)

        # חילוץ פרק 3 (דפים)
        page_blocks = re.split(r'(?=דף מייצגים - \d+)', chapter_3_text)
        for block in page_blocks:
            block_clean = block.strip()
            if block_clean and ("נושא:" in block_clean or "הסבר והנחיות:" in block_clean):
                local_chunks.append(block_clean)

        # יצירת ה-Embeddings מול גוגל
        if local_chunks:
            response = client.models.embed_content(
                model="text-embedding-004",
                contents=local_chunks
            )
            CHUNKS_EMBEDDINGS = np.array([item.values for item in response.embeddings])
            CHUNKS_TEXTS = local_chunks
            return True
    except Exception as e:
        print(f"❌ שגיאה בטעינה בזמן אמת: {e}")
    
    return False

# ניסיון טעינה ראשון בעת עליית השרת
load_and_parse_terminal_data()

def get_embedding(text):
    if client is None:
        return [0] * 768
    response = client.models.embed_content(
        model="text-embedding-004",
        contents=[text]
    )
    return response.embeddings[0].values

def inject_hyperlinks(text):
    for name, url in LINKS_DICTIONARY.items():
        placeholder = f"[{name}]"
        if placeholder in text:
            href_target = f"mailto:{url}" if "@" in url and not url.startswith("http") else url
            hyperlink = f'<a href="{href_target}" style="color: #007bff; text-decoration: underline; font-weight: bold;" target="_blank">{name}</a>'
            text = text.replace(placeholder, hyperlink)
    return text

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    try:
        # הגנה אקטיבית: אם הנתונים לא נטענו באתחול, ננסה לטעון אותם שוב עכשיו בזמן אמת!
        if not CHUNKS_TEXTS or CHUNKS_EMBEDDINGS is None:
            success = load_and_parse_terminal_data()
            if not success:
                return jsonify({"response": "מערכת הנתונים או לקוח ה-AI עדיין אינם טעונים כראוי בשרת. אנא ודא שמפתח ה-API מוגדר ב-Fly."})

        data = request.json or {}
        user_question = data.get('question', '').strip()
        chat_history = data.get('history', [])

        if not user_question:
            return jsonify({"response": "לא התקבלה שאלה תקינה."})

        # חישוב סמנטי ופאזי
        user_vector = get_embedding(user_question)
        semantic_scores = np.dot(CHUNKS_EMBEDDINGS, user_vector)

        fuzzy_scores = [fuzz.partial_ratio(user_question, chunk) / 100.0 for chunk in CHUNKS_TEXTS]
        combined_scores = (semantic_scores * 0.7) + (np.array(fuzzy_scores) * 0.3)
        
        top_indices = np.argsort(combined_scores)[-6:][::-1]
        retrieved_chunks = [CHUNKS_TEXTS[idx] for idx in top_indices]
        context = "\n\n---\n\n".join(retrieved_chunks)

        system_instruction = (
            "אתה עוזר דיגיטלי מקצועי ושירותי של אתר מייצגים בגביה של הביטוח הלאומי.\n"
            "תפקידך לספק תשובות מלאות ומקיפות על בסיס הנתונים בלבד.\n"
            "השתמש ב-Markdown (הדגשות, רשימות) כדי לעצב את התשובה בצורה יפה.\n"
            "אם מופיע ביטוי בסוגריים מרובעים (כמו [אתר מייצגים בגביה]), שמור עליו בדיוק כך בתשובתך."
        )

        contents = []
        for msg in chat_history:
            role = "model" if msg["role"] == "assistant" else "user"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))

        current_user_content = f"מידע מהנהלים:\n{context}\n\nהשאלה: {user_question}"
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=current_user_content)]))

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system_instruction, temperature=0.5)
        )
        
        html_answer = markdown.markdown(response.text, extensions=['nl2br'])
        final_answer = inject_hyperlinks(html_answer)
        return jsonify({"response": final_answer})

    except Exception as e:
        return jsonify({"response": f"שגיאה כללית בקוד השרת: {e}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
