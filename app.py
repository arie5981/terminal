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
        return jsonify({"response": "❌ הקובץ לא נמצא"})

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # --- מנגנון חיתוך גמיש וחסין ---
        # מחפש את המילה פרק ואחריה מספר, ללא קשר למיקום שלה בשורה
        parts = re.split(r'(פרק \d+)', content)
        
        chapter_1_text = ""
        chapter_2_text = ""
        chapter_3_text = ""
        
        # רצים על פני החלקים שנחתכו ומחברים את התוכן לפרק המתאים
        for i in range(1, len(parts), 2):
            header = parts[i]  # ישיל את "פרק 1", "פרק 2" וכו'
            body = parts[i+1] if i+1 < len(parts) else "" # גוף הטקסט שאחרי הכותרת
            
            if "פרק 1" in header:
                chapter_1_text = body
            elif "פרק 2" in header:
                chapter_2_text = body
            elif "פרק 3" in header:
                chapter_3_text = body

        # ספירת מנות (Chunks) בתוך פרק 2 ופרק 3 לבדיקה
        qna_chunks = [b.strip() for b in re.split(r'(?=שאלה:)', chapter_2_text) if b.strip() and "תשובה:" in b]
        page_chunks = [b.strip() for b in re.split(r'(?=דף מייצגים - )', chapter_3_text) if b.strip()]

        return jsonify({
            "response": (
                f"📊 **תוצאות חיתוך גמיש חדש:**<br>"
                f"• אורך פרק 1: {len(chapter_1_text)} תווים.<br>"
                f"• אורך פרק 2: {len(chapter_2_text)} תווים (נמצאו {len(qna_chunks)} שאלות ותשובות).<br>"
                f"• אורך פרק 3: {len(chapter_3_text)} תווים (נמצאו {len(page_chunks)} דפי מייצגים).<br><br>"
                f"אם המספרים כאן גדולים מ-0, פיצחנו את החיתוך ואפשר להעלות את הקוד המלא!"
            )
        })

    except Exception as e:
        return jsonify({"response": f"❌ שגיאה: {str(e)}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
