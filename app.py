from flask import Flask, render_template, request, jsonify
import os
import re
from google import genai
from rapidfuzz import fuzz

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
            "response": f"🚧 <b>בדיקת שלבים טורית:</b><br>1️⃣ API: {api_key_status}<br>3️⃣ קובץ: ❌ לא נמצא."
        })

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        parts = re.split(r'===(פרק \d+)===', content)
        
        chapter_2_text = ""
        chapter_3_text = ""
        for i in range(1, len(parts), 2):
            if "פרק 2" in parts[i]: chapter_2_text = parts[i+1]
            elif "פרק 3" in parts[i]: chapter_3_text = parts[i+1]

        qna_blocks = re.split(r'\n(?=שאלה:)', chapter_2_text)
        chunks_chapter_2 = [b.strip() for b in qna_blocks if b.strip() and "תשובה:" in b]
        
        page_blocks = re.split(r'\n(?=דף מייצגים - \d+)', chapter_3_text)
        chunks_chapter_3 = [b.strip() for b in page_blocks if b.strip() and ("נושא:" in b or "הסבר והנחיות:" in b)]

        all_chunks = chunks_chapter_2 + chunks_chapter_3
        total_chunks = len(all_chunks)

        # === שלב 5 המאבחן: הדפסת המודלים הנתמכים ישירות מגוגל ===
        available_models_list = []
        try:
            # קריאה לפונקציה שגוגל ביקשה שנריץ: ListModels
            for m in client.models.list():
                # נסנן רק מודלים שמסוגלים לעשות Embedding (מכילים את המילה embed)
                if 'embed' in m.name.lower() or 'embedding' in m.name.lower():
                    available_models_list.append(f"• <code>{m.name}</code> (שיטות נתמכות: {m.supported_methods})")
            
            models_display = "<br>".join(available_models_list) if available_models_list else "• לא נמצאו מודלי Embedding ברשימה."
            retrieval_status = "📊 <b>סריקת המודלים של גוגל הצליחה! הנה מה שבאמת פתוח בחשבון שלך:</b>"
        except Exception as list_err:
            models_display = f"❌ נכשל בשליפת רשימת המודלים: {list_err}"
            retrieval_status = "⚠️ שגיאה בסריקת המודלים."

        # מציג בינתיים את התוצאות הפאזיות שעובדות מעולה כגיבוי
        retrieved_results_html = "<h3>🤖 תוצאות חיפוש פאזי (זמני לאבחון):</h3>"
        fuzzy_scored_chunks = []
        for chunk in all_chunks:
            f_score = fuzz.partial_ratio(user_question, chunk) / 100.0
            fuzzy_scored_chunks.append((f_score, chunk))
        fuzzy_scored_chunks.sort(key=lambda x: x[0], reverse=True)
        
        for idx, (score, chunk_text) in enumerate(fuzzy_scored_chunks[:2], 1):
            retrieved_results_html += f"📌 <b>תוצאה {idx} (פאזי: {score:.2f}):</b><br><code>{chunk_text[:120]}...</code><br><br>"

        return jsonify({
            "response": f"🚧 <b>בדיקת שלבים טורית - שלב אבחון המודלים באוויר!</b><br><br>"
                        f"🔑 <b>1. בדיקת מפתח סביבה:</b><br>• {api_key_status}<br><br>"
                        f"🤖 <b>2. בדיקת קריאה לג'ימיני (Flash):</b><br>• {gemini_response_status}<br><br>"
                        f"📋 <b>3. ניתוח מסמך הנהלים (Terminal.txt):</b><br>"
                        f"• חולצו בהצלחה: <b>{total_chunks}</b> יחידות מידע.<br><br>"
                        f"🔍 <b>5. סטטוס מודלים סמנטיים בגוגל:</b><br>{retrieval_status}<br>{models_display}<br><br>"
                        f"{retrieved_results_html}"
        })

    except Exception as e:
        return jsonify({"response": f"❌ שגיאה כללית: {e}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
