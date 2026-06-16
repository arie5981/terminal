from flask import Flask, render_template, request, jsonify
import os
import re

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    file_path = os.path.join(os.path.dirname(__file__), 'data', 'Terminal.txt')
    
    if not os.path.exists(file_path):
        return jsonify({"response": "❌ קובץ הנהלים לא נמצא בשרת."})

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

        # --- בדיקה ושיפור חילוץ פרק 2 ---
        # שימוש בביטוי רגולרי גמיש יותר שמתמודד עם רווחים: (?=^\s*שאלה:) או (?=שאלה:)
        qna_blocks = re.split(r'(?=שאלה:)', chapter_2_text)
        chunks_chapter_2 = []
        for block in qna_blocks:
            block_clean = block.strip()
            if block_clean and "תשובה:" in block_clean:
                chunks_chapter_2.append(block_clean)

        # --- בדיקה וחילוץ של פרק 3 ---
        # נבדוק כמה בלוקים של דפי מייצגים הוא מצליח למצוא בפרק 3
        page_blocks = re.split(r'(?=דף מייצגים - \d+)', chapter_3_text)
        chunks_chapter_3 = []
        for block in page_blocks:
            block_clean = block.strip()
            if block_clean and ("נושא:" in block_clean or "הסבר והנחיות:" in block_clean):
                chunks_chapter_3.append(block_clean)

        # 4. החזרת הנתונים המדויקים למסך
        return jsonify({
            "response": f"✅ <b>ניתוח מעמיק של מבנה הקובץ הצליח!</b><br><br>"
                        f"📋 <b>מצב פרק 2 (שאלות ותשובות):</b><br>"
                        f"• חולצו בהצלחה: {len(chunks_chapter_2)} שאלות ותשובות.<br><br>"
                        f"🖥️ <b>מצב פרק 3 (תיאור אתר המייצגים):</b><br>"
                        f"• האם פרק 3 נקרא? {'כן' if chapter_3_text.strip() else 'לא, הפרק ריק'}<br>"
                        f"• אורך הטקסט של פרק 3: {len(chapter_3_text)} תווים.<br>"
                        f"• מספר דפי המערכת שחולצו מפרק 3: {len(chunks_chapter_3)} דפים.<br><br>"
                        f"💡 תגיד לי כמה שאלות ודפים מופיעים לך עכשיו, ונוכל להתאים את ה-Regex בצורה מושלמת לפני שנחזיר את ה-Embeddings!"
        })

    except Exception as e:
        return jsonify({"response": f"❌ שגיאה בניתוח הפרקים: {e}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
