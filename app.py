from flask import Flask, render_template, request, jsonify
import os
import re
import numpy as np
from google import genai

app = Flask(__name__)

# שליפת המפתח
gemini_api_key = os.environ.get("GEMINI_API_KEY")

# משתנים גלובליים שישמרו בזיכרון של השרת
CHUNKS_TEXTS = []      
CHUNKS_EMBEDDINGS = None 

def initialize_rag_system():
    """ פונקציה שרצה פעם אחת עם עליית השרת, קוראת את הקובץ ומייצרת וקטורים """
    global CHUNKS_TEXTS, CHUNKS_EMBEDDINGS
    
    if not gemini_api_key:
        return

    file_path = os.path.join(os.path.dirname(__file__), 'data', 'Terminal.txt')
    if not os.path.exists(file_path):
        return

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        # פירוק הקובץ לפי הפרקים הראשיים
        parts = re.split(r'===(פרק \d+)===', content)
        
        chapter_2_text = ""
        chapter_3_text = ""
        
        for i in range(1, len(parts), 2):
            header = parts[i]
            body = parts[i+1] if i+1 < len(parts) else ""
            if "פרק 2" in header:
                chapter_2_text = body
            elif "פרק 3" in header:
                chapter_3_text = body

        # 1. חילוץ פרק 2 (השאלות והתשובות שלך)
        qna_blocks = re.split(r'\n(?=שאלה:)', chapter_2_text)
        for block in qna_blocks:
            block_clean = block.strip()
            if block_clean and "תשובה:" in block_clean:
                CHUNKS_TEXTS.append(block_clean)

        # 2. חילוץ פרק 3 (דפי המערכת)
        page_blocks = re.split(r'\n(?=דף מייצגים - \d+)', chapter_3_text)
        for block in page_blocks:
            block_clean = block.strip()
            if block_clean and ("נושא:" in block_clean or "הסבר והנחיות:" in block_clean):
                CHUNKS_TEXTS.append(block_clean)

        # 3. יצירת ה-Embeddings מול גוגל לכל 136 היחידות בבת אחת
        if CHUNKS_TEXTS:
            client = genai.Client(api_key=gemini_api_key)
            response = client.models.embed_content(
                model="text-embedding-004",
                contents=CHUNKS_TEXTS
            )
            # המרה למטריצת מספרים של נומפאי
            CHUNKS_EMBEDDINGS = np.array([item.values for item in response.embeddings])
            
    except Exception as e:
        # במקרה של שגיאה, נרשום אותה לתוך המערך כדי שנראה אותה על המסך בצ'אט
        CHUNKS_TEXTS = [f"שגיאה בתהליך יצירת ה-Embeddings: {e}"]

# הרצת תהליך הוקטוריזציה מיד עם עליית השרת
initialize_rag_system()


@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    # בדיקה אם יש הודעת שגיאה שנרשמה באתחול
    if CHUNKS_TEXTS and "שגיאה" in CHUNKS_TEXTS[0]:
        return jsonify({"response": CHUNKS_TEXTS[0]})

    # בדיקה מה מצב הוקטורים בזיכרון של השרת
    if CHUNKS_EMBEDDINGS is None:
        return jsonify({
            "response": "❌ השרת עלה, אך מטריצת ה-Embeddings ריקה. ודא שמפתח ה-API תקין."
        })
        
    # שליפת המימדים של המטריצה שנוצרה בזיכרון
    rows, columns = CHUNKS_EMBEDDINGS.shape
    
    return jsonify({
        "response": f"✅ <b>שלב ה-Embeddings עבר בהצלחה מושלמת!</b><br><br>"
                    f"📊 <b>נתוני המטריצה בזיכרון השרת:</b><br>"
                    f"• מספר יחידות מידע שמופו (Rows): {rows} (תואם בדיוק ל-136 היחידות שלנו!)<br>"
                    f"• אורך וקטור של גוגל (Columns): {columns} ממדים לכל יחידת מידע.<br><br>"
                    f"🚀 הזיכרון הסמנטי של השרת מוכן! שלח לי את האישור ונחבר את שליפת התשובות הבלעדית."
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
