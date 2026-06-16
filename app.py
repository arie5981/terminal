from flask import Flask, render_template, request, jsonify
import os
import re

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    # 1. הגדרת נתיב הקובץ (מניחים שהוא בתוך תיקיית data באותו הגובה של app.py)
    file_path = os.path.join(os.path.dirname(__file__), 'data', 'Terminal.txt')
    
    # 2. בדיקה פיזית אם הקובץ קיים בשרת
    if not os.path.exists(file_path):
        return jsonify({
            "response": f"❌ קובץ הנהלים לא נמצא בנתיב המבוקש!<br>הנתיב שנבדק: <br><code>{file_path}</code><br><br>אנא ודא שב-GitHub קיימת תיקייה בשם data ובתוכה הקובץ Terminal.txt"
        })

    # 3. ניסיון לקרוא את הקובץ ולפרק אותו לשאלות ותשובות
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        # פירוק פרק 2 כדי לחלץ שאלות ותשובות
        parts = re.split(r'===(פרק \d+)===', content)
        chapter_2_text = ""
        
        for i in range(1, len(parts), 2):
            header = parts[i]
            body = parts[i+1] if i+1 < len(parts) else ""
            if "פרק 2" in header:
                chapter_2_text = body

        # חילוץ בלוקים של שאלה/תשובה
        chunks = []
        qna_blocks = re.split(r'(?=שאלה:)', chapter_2_text)
        for block in qna_blocks:
            block_clean = block.strip()
            if block_clean and "תשובה:" in block_clean:
                chunks.append(block_clean)

        # 4. הצגת תוצאת הניתוח על המסך
        return jsonify({
            "response": f"✅ קובץ הנהלים נקרא בהצלחה!<br><br>"
                        f"📊 <b>נתוני הקובץ בשרת:</b><br>"
                        f"• גודל הקובץ: {len(content)} תווים.<br>"
                        f"• מספר השאלות והתשובות שחולצו מפרק 2: {len(chunks)} בלוקים.<br><br>"
                        f"💡 אם המספרים תקינים, הקובץ מוכן לעבור לשלב ה-Embeddings!"
        })

    except Exception as e:
        return jsonify({"response": f"❌ שגיאה בקריאת או ניתוח הקובץ: {e}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
