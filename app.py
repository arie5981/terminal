from flask import Flask, render_template, request, jsonify
import os
import re
from google import genai

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json or {}
    user_question = data.get('question', '').strip()

    # === שלב 1: קריאת ה-API KEY והדפסתו ===
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if gemini_api_key:
        api_key_status = f"✅ נמצא (מתחיל ב-{gemini_api_key[:4]} ומסתיים ב-{gemini_api_key[-4:]})"
    else:
        api_key_status = "❌ לא נמצא! מפתח ה-API ריק."

    # === שלב 2: פנייה ל-gemini-2.5-flash לקבלת תשובת "שלום עולם" ===
    gemini_response_status = ""
    if gemini_api_key:
        try:
            client = genai.Client(api_key=gemini_api_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents="תגיד בדיוק את המילים הבאות: שלום עולם! הקישור לג'ימיני עובד.",
            )
            gemini_response_status = f"✅ תגובת המודל: \"{response.text.strip()}\""
        except Exception as api_error:
            gemini_response_status = f"❌ שגיאה בפנייה ל-Gemini: {api_error}"
    else:
        gemini_response_status = "❌ לא בוצעה פנייה כי המפתח חסר."

    # === שלב 3: קריאת המסמך וניתוח הנתונים ===
    file_path = os.path.join(os.path.dirname(__file__), 'data', 'Terminal.txt')
    
    if not os.path.exists(file_path):
        return jsonify({
            "response": f"🚧 <b>בדיקת שלבים טורית:</b><br>"
                        f"1️⃣ מפתח API: {api_key_status}<br>"
                        f"2️⃣ פנייה למודל: {gemini_response_status}<br>"
                        f"3️⃣ קובץ נהלים: ❌ קובץ הנהלים Terminal.txt לא נמצא בשרת."
        })

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        content = content.replace('\r\n', '\n').replace('\r', '\n')
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

        # חילוץ פרק 2
        qna_blocks = re.split(r'\n(?=שאלה:)', chapter_2_text)
        chunks_chapter_2 = []
        for block in qna_blocks:
            block_clean = block.strip()
            if block_clean and "תשובה:" in block_clean:
                chunks_chapter_2 = [] if not chunks_chapter_2 and not block_clean.startswith("שאלה:") else chunks_chapter_2
                chunks_chapter_2.append(block_clean)
        
        if chapter_2_text.strip().startswith("שאלה:") and not any("מהו אתר מייצגים" in c for c in chunks_chapter_2):
            first_block = chapter_2_text.split("שאלה:")[1].split("\nשאלה:")[0]
            chunks_chapter_2.insert(0, f"שאלה:{first_block.strip()}")

        # חילוץ פרק 3
        page_blocks = re.split(r'\n(?=דף מייצגים - \d+)', chapter_3_text)
        chunks_chapter_3 = []
        for block in page_blocks:
            block_clean = block.strip()
            if block_clean and ("נושא:" in block_clean or "הסבר והנחיות:" in block_clean):
                chunks_chapter_3.append(block_clean)

        # איחוד כל 136 היחידות לרשימה אחת
        all_chunks = chunks_chapter_2 + chunks_chapter_3
        total_chunks = len(all_chunks)

        # === שלב 4: מנוע שליפת המידע הרלוונטי (Information Retrieval) ===
        retrieval_status = ""
        retrieved_results_html = ""
        
        if user_question:
            # פירוק מילות השאלה של המשתמש לצורך חיפוש התאמות
            search_words = [w.lower() for w in user_question.split() if len(w) > 1]
            scored_chunks = []
            
            for chunk in all_chunks:
                # ספירה פשוטה ויציבה כמה ממילות השאלה מופיעות בצ'אנק הנוכחי
                score = sum(1 for word in search_words if word in chunk.lower())
                if score > 0:
                    scored_chunks.append((score, chunk))
            
            # מיון התוצאות מהציון הגבוה לנמוך ושליפת ה-3 הכי טובים
            scored_chunks.sort(key=lambda x: x[0], reverse=True)
            top_3_results = scored_chunks[:3]
            
            if top_3_results:
                retrieval_status = f"✅ נמצאו {len(scored_chunks)} יחידות מידע מתאימות. מציג את 3 המובילות:"
                for idx, (score, text) in enumerate(top_3_results, 1):
                    # חיתוך קל של הטקסט כדי שלא יציף את כל המסך, תוך הצגת תחילתו
                    short_text = text[:150] + "..." if len(text) > 150 else text
                    short_text_escaped = short_text.replace('\n', '<br>')
                    retrieved_results_html += f"📌 <b>תוצאה {idx} (ציון התאמה: {score}):</b><br><code>{short_text_escaped}</code><br><br>"
            else:
                retrieval_status = "ℹ️ לא נמצאה התאמה ישירה בין מילות השאלה לנהלים. מציג צ'אנק ברירת מחדל מהמאגר."
                retrieved_results_html = f"📌 <b>ברירת מחדל:</b><br><code>{all_chunks[0][:150]}...</code><br>"
        else:
            retrieval_status = "💡 שלח שאלה ספציפית בצ'אט (למשל: 'איפוס סיסמה' או 'כרטיס חכם') כדי לראות את השליפה בפעולה."

        # החזרת כל ארבעת השלבים בטור לדף הדפדפן
        return jsonify({
            "response": f"🚧 <b>בדיקת שלבים טורית - שלב 4 נוסף בהצלחה!</b><br><br>"
                        f"🔑 <b>1. בדיקת מפתח סביבה:</b><br>• {api_key_status}<br><br>"
                        f"🤖 <b>2. בדיקת קריאה לג'ימיני (Flash):</b><br>• {gemini_response_status}<br><br>"
                        f"📋 <b>3. ניתוח מסמך הנהלים (Terminal.txt):</b><br>"
                        f"• חולצו בהצלחה מפרק 2: <b>{len(chunks_chapter_2)}</b> שאלות ותשובות.<br>"
                        f"• חולצו בהצלחה מפרק 3: <b>{len(chunks_chapter_3)}</b> דפי מערכת.<br>"
                        f"📊 <b>סך הכל יחידות מידע מוכנות בזיכרון:</b> {total_chunks} יחידות.<br><br>"
                        f"🔍 <b>4. שלב שליפת המידע (Retrieval) עבור: \"{user_question}\":</b><br>"
                        f"• סטטוס: {retrieval_status}<br><br>"
                        f"{retrieved_results_html}"
        })

    except Exception as e:
        return jsonify({"response": f"❌ שגיאה במהלך הרצת השלבים: {e}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
