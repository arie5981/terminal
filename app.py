from flask import Flask, render_template, request, jsonify
import os
import re
import numpy as np
from google import genai
from rapidfuzz import fuzz
from sentence_transformers import SentenceTransformer, util

app = Flask(__name__)

# טעינת מודל סמנטי קל ואיכותי שרץ מקומית על השרת (תומך רב-לשוני ומצוין לעברית)
# המודל נטען פעם אחת בלבד עם עליית השרת
try:
    semantic_model = SentenceTransformer('sentence-transformers/LabSE')
except Exception as e:
    print(f"Error loading local semantic model: {e}")
    semantic_model = None

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

        # === שלב 5 הסופי: מנוע RAG משולב מקומי (חסין שגיאות רשת) ===
        retrieval_status = ""
        retrieved_results_html = ""
        
        if user_question:
            # 1. חלק פאזי מקומי
            fuzzy_scores = []
            for chunk in all_chunks:
                f_score = fuzz.partial_ratio(user_question, chunk) / 100.0
                fuzzy_scores.append(f_score)

            # 2. חלק סמנטי מקומי (רץ על השרת שלך - ללא פנייה לגוגל!)
            is_semantic_valid = False
            if semantic_model:
                try:
                    # יצירת וקטורים מקומית
                    user_embedding = semantic_model.encode(user_question, convert_to_tensor=True)
                    chunks_embeddings = semantic_model.encode(all_chunks, convert_to_tensor=True)
                    
                    # חישוב מרחק קוסינוס סמנטי
                    semantic_scores_tensor = util.cos_sim(user_embedding, chunks_embeddings)[0]
                    semantic_scores = semantic_scores_tensor.cpu().numpy()
                    is_semantic_valid = True
                    retrieval_status = "✅ החיפוש המשולב (סמנטי מקומי + פאזי) פועל ב-100% יציבות ללא תלות ברשת!"
                except Exception as local_emb_err:
                    semantic_scores = np.zeros(len(all_chunks))
                    retrieval_status = f"⚠️ חישוב סמנטי מקומי נכשל: {local_emb_err}"
            else:
                semantic_scores = np.zeros(len(all_chunks))
                retrieval_status = "⚠️ המודל הסמנטי המקומי לא נטען באתחול השרת."

            # 3. שילוב הציונים (70% סמנטי מקומי + 30% פאזי)
            if is_semantic_valid:
                combined_scores = (semantic_scores * 0.7) + (np.array(fuzzy_scores) * 0.3)
            else:
                combined_scores = np.array(fuzzy_scores)

            # שליפת 3 המקומות הראשונים
            top_indices = np.argsort(combined_scores)[-3:][::-1]
            
            for idx, position in enumerate(top_indices, 1):
                chunk_text = all_chunks[position]
                short_text = chunk_text[:150] + "..." if len(chunk_text) > 150 else chunk_text
                short_text_escaped = short_text.replace('\n', '<br>')
                
                sem_display = f"{semantic_scores[position]:.2f}" if is_semantic_valid else "לא זמין"
                retrieved_results_html += (
                    f"📌 <b>תוצאה {idx}:</b><br>"
                    f"• ציון סמנטי מקומי: {sem_display} | ציון פאזי: {fuzzy_scores[position]:.2f}<br>"
                    f"• ציון משולב סופי: {combined_scores[position]:.2f}<br>"
                    f"<code>{short_text_escaped}</code><br><br>"
                )
        else:
            retrieval_status = "💡 שלח שאלה כדי לראות את האלגוריתם המשולב בפעולה."

        return jsonify({
            "response": f"🚧 <b>בדיקת שלבים טורית - שלב 5 (ארכיטקטורה מקומית חסינה) באוויר!</b><br><br>"
                        f"🔑 <b>1. בדיקת מפתח סביבה:</b><br>• {api_key_status}<br><br>"
                        f"🤖 <b>2. בדיקת קריאה לג'ימיני (Flash):</b><br>• {gemini_response_status}<br><br>"
                        f"📋 <b>3. ניתוח מסמך הנהלים (Terminal.txt):</b><br>"
                        f"• חולצו בהצלחה: <b>{total_chunks}</b> יחידות מידע.<br><br>"
                        f"🧠 <b>5. מנוע RAG משולב (סמנטי מקומי מנותק רשת + פאזי):</b><br>"
                        f"• סטטוס: {retrieval_status}<br><br>"
                        f"{retrieved_results_html}"
        })

    except Exception as e:
        return jsonify({"response": f"❌ שגיאה כללית במהלך הרצת השלבים: {e}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
