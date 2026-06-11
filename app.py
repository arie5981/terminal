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
        return jsonify({"response": "❌ הקובץ לא נמצא בתיקיית data"})

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # נירמול הקובץ: הופך את כל סוגי ירידות השורה ל-\n רגיל כדי למנוע בעיות של Windows
        content = content.replace('\r\n', '\n')

        # חיתוך חסין במיוחד: מוצא את המילה פרק ומספר, ומתעלם מכל המקפים והרווחים שמסביב
        parts = re.split(r'\n*-+\n*(פרק \d+)[^\n]*\n*-+\n*', content)
        
        chapter_1_text = ""
        chapter_2_text = ""
        chapter_3_text = ""
        
        for i in range(1, len(parts), 2):
            header = parts[i]      # תופס "פרק 1", "פרק 2", "פרק 3"
            body = parts[i+1] if i+1 < len(parts) else "" # הטקסט ששייך לפרק
            
            if "פרק 1" in header:
                chapter_1_text = body
            elif "פרק 2" in header:
                chapter_2_text = body
            elif "פרק 3" in header:
                chapter_3_text = body

        # ספירת מנות (Chunks) בתוך פרק 2 ופרק 3
        qna_chunks = [b.strip() for b in re.split(r'(?=שאלה:)', chapter_2_text) if b.strip() and "תשובה:" in b]
        page_chunks = [b.strip() for b in re.split(r'(?=דף מייצגים - \d+)', chapter_3_text) if b.strip() and "נושא:" in b]

        return jsonify({
            "response": (
                f"📊 **תוצאות חיתוך מנורמל של שלושת הפרקים:**<br>"
                f"• **פרק 1:** {len(chapter_1_text)} תווים.<br>"
                f"• **פרק 2:** {len(chapter_2_text)} תווים (נמצאו {len(qna_chunks)} שאלות ותשובות).<br>"
                f"• **פרק 3:** {len(chapter_3_text)} תווים (נמצאו {len(page_chunks)} דפי מייצגים).<br><br>"
                f"ברגע שהמספרים כאן יקפצו מעל 0, אנחנו מוכנים להעלות את הקוד המלא והסופי!"
            )
        })

    except Exception as e:
        return jsonify({"response": f"❌ שגיאה: {str(e)}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
