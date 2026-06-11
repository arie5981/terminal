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
    
    # 1. בדיקה האם הקובץ פיזית קיים בנתיב
    if not os.path.exists(file_path):
        return jsonify({
            "response": f"❌ בדיקה נכשלה: הקובץ לא נמצא בנתיב המצופה: {file_path}. ודא ששם התיקייה הוא data ושם הקובץ הוא Terminal.txt"
        })

    try:
        # 2. ניסיון קריאת הקובץ
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        file_size = len(content)
        
        # 3. ניסיון פירוק ראשוני לפרקים
        chapters = re.split(r'(?=^פרק \d+)', content, flags=re.MULTILINE)
        
        chapter_1_len = 0
        chapter_2_len = 0
        chapter_3_len = 0
        
        for ch in chapters:
            ch_clean = ch.strip()
            if ch_clean.startswith("פרק 1"):
                chapter_1_len = len(ch_clean)
            elif ch_clean.startswith("פרק 2"):
                chapter_2_len = len(ch_clean)
            elif ch_clean.startswith("פרק 3"):
                chapter_3_len = len(ch_clean)

        # 4. החזרת הדוח למסך
        return jsonify({
            "response": (
                f"✅ קריאת הקובץ הצליחה!<br>"
                f"• גודל הקובץ הכולל: {file_size} תווים.<br>"
                f"• מספר הבלוקים שזוהו בפירוק ראשוני: {len(chapters)}<br>"
                f"• אורך טקסט פרק 1 שזוהה: {chapter_1_len} תווים.<br>"
                f"• אורך טקסט פרק 2 שזוהה: {chapter_2_len} תווים.<br>"
                f"• אורך טקסט פרק 3 שזוהה: {chapter_3_len} תווים.<br><br>"
                f"אם אחד הפרקים מציג 0 תווים, סימן שהביטוי הרגולרי לא זיהה את כותרת הפרק בקובץ הטקסט שלך."
            )
        })

    except Exception as e:
        return jsonify({
            "response": f"❌ שגיאה בזמן קריאת הקובץ או הפירוק שלו: {str(e)}"
        })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
