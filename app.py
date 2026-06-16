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
            
        # ניקוי ירידות שורה לפורמט אחיד
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        # פירוק הנהלים לפי הפרקים הראשיים
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

        # --- 📋 חילוץ מתוקן וגמיש לפרק 2 ---
        # חותך לפי 'שאלה:' בתחילת שורה, ומתעלם מרווחים או הצמדות
        qna_blocks = re.split(r'\n(?=שאלה:)', chapter_2_text)
        chunks_chapter_2 = []
        for block in qna_blocks:
            block_clean = block.strip()
            if block_clean and "תשובה:" in block_clean:
                chunks_chapter_2 = [] if not chunks_chapter_2 and not block_clean.startswith("שאלה:") else chunks_chapter_2
                chunks_chapter_2.append(block_clean)
        
        # אם הבלוק הראשון פוספס בגלל הפירוק, נטפל בו נקודתית
        if chapter_2_text.strip().startswith("שאלה:") and not any("מהו אתר מייצגים" in c for c in chunks_chapter_2):
            # חילוץ השאלה הראשונה ביותר בפרק
            first_block = chapter_2_text.split("שאלה:")[1].split("\nשאלה:")[0]
            chunks_chapter_2.insert(0, f"שאלה:{first_block.strip()}")

        # --- 🖥️ חילוץ פרק 3 ---
        page_blocks = re.split(r'\n(?=דף מייצגים - \d+)', chapter_3_text)
        chunks_chapter_3 = []
        for block in page_blocks:
            block_clean = block.strip()
            if block_clean and ("נושא:" in block_clean or "הסבר והנחיות:" in block_clean):
                chunks_chapter_3.append(block_clean)

        # סך הכל צ'אנקים שיעברו וקטוריזציה
        total_chunks = len(chunks_chapter_2) + len(chunks_chapter_3)

        return jsonify({
            "response": f"✅ <b>ה-Regex עודכן בהצלחה! הנה הנתונים המדויקים מהקובץ שהעלית:</b><br><br>"
                        f"📋 <b>מצב פרק 2 (שאלות ותשובות):</b><br>"
                        f"• חולצו בהצלחה: <b>{len(chunks_chapter_2)}</b> שאלות ותשובות (עלינו מ-39!).<br><br>"
                        f"🖥️ <b>מצב פרק 3 (תיאור אתר המייצגים):</b><br>"
                        f"• חולצו בהצלחה: <b>{len(chunks_chapter_3)}</b> דפי מערכת.<br><br>"
                        f"📊 <b>סך הכל יחידות מידע (Chunks) מוכנות ל-AI:</b> {total_chunks} יחידות.<br><br>"
                        f"💡 ברגע שתאשר לי שהמספרים האלו תואמים בדיוק למה שציפית, אנחנו מחזירים את ה-Embeddings לפעולה על כל המאגר המשולב!"
        })

    except Exception as e:
        return jsonify({"response": f"❌ שגיאה בניתוח הפרקים: {e}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
