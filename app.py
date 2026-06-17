from flask import Flask, render_template, request, jsonify
import os
import re
import numpy as np
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

        # === שלב 5: מנוע RAG משולב באמצעות השם המלא המדויק של גוגל ===
        retrieval_status = ""
        retrieved_results_html = ""
        
        if user_question and gemini_api_key:
            # 1. סינון פאזי מוקדם ל-30 מועמדים (מהיר וקל)
            fuzzy_scored_chunks = []
            for idx, chunk in enumerate(all_chunks):
                f_score = fuzz.partial_ratio(user_question, chunk) / 100.0
                fuzzy_scored_chunks.append((f_score, idx, chunk))
            
            fuzzy_scored_chunks.sort(key=lambda x: x[0], reverse=True)
            candidate_chunks_info = fuzzy_scored_chunks[:30]
            
            candidate_texts = [item[2] for item in candidate_chunks_info]
            candidate_fuzzy_scores = [item[0] for item in candidate_chunks_info]

            # 2. פנייה לסמנטי עם השם המפורש והמלא
            is_semantic_valid = False
            try:
                # שימוש בנתיב המלא כפי שגוגל דורשת בתיעוד הרשמי של google-genai
                emb_response = client.models.embed_content(
                    model="models/text-embedding-004",
                    contents=[user_question] + candidate_texts
                )
                
                embeddings = [item.values for item in emb_response.embeddings]
                user_vector = np.array(embeddings[0])
                chunks_vectors = np.array(embeddings[1:])
                
                semantic_scores = np.dot(chunks_vectors, user_vector)
                is_semantic_valid = True
                retrieval_status = "✅ החיפוש המשולב פועל כהלכה מול ה-API הרשמי של גוגל!"
            except Exception as emb_err:
                semantic_scores = np.zeros(len(candidate_texts))
                retrieval_status = f"⚠️ סמנטי הושבת (מנגנון הגנה פאזי פעיל): {emb_err}"

            # 3. שילוב ציונים (70% סמנטי + 30% פאזי)
            if is_semantic_valid:
                combined_candidate_scores = (semantic_scores * 0.7) + (np.array(candidate_fuzzy_scores) * 0.3)
            else:
                combined_candidate_scores = np.array(candidate_fuzzy_scores)
            
            top_candidate_indices = np.argsort(combined_candidate_scores)[-3:][::-1]
            
            for idx, pos in enumerate(top_candidate_indices, 1):
                chunk_text = candidate_texts[pos]
                short_text = chunk_text[:150] + "..." if len(chunk_text) > 150 else chunk_text
                short_text_escaped = short_text.replace('\n', '<br>')
                
                sem_display = f"{semantic_scores[pos]:.2f}" if is_semantic_valid else "לא זמין"
                retrieved_results_html += (
                    f"📌 <b>תוצאה {idx}:</b><br>"
                    f"• ציון סמנטי: {sem_display} | ציון פאזי: {candidate_fuzzy_scores[pos]:.2f}<br>"
                    f"• ציון משולב סופי: {combined_candidate_scores[pos]:.2f}<br>"
                    f"<code>{short_text_escaped}</code><br><br>"
                )
        else:
            retrieval_status = "💡 שלח שאלה בצ'אט כדי להפעיל את החיפוש."

        return jsonify({
            "response": f"🚧 <b>בדיקת שלבים טורית - שלב 5 הרשמי באוויר!</b><br><br>"
                        f"🔑 <b>1. בדיקת מפתח סביבה:</b><br>• {api_key_status}<br><br>"
                        f"🤖 <b>2. בדיקת קריאה לג'ימיני (Flash):</b><br>• {gemini_response_status}<br><br>"
                        f"📋 <b>3. ניתוח מסמך הנהלים (Terminal.txt):</b><br>"
                        f"• חולצו בהצלחה: <b>{total_chunks}</b> יחידות מידע.<br><br>"
                        f"🧠 <b>5. מנוע RAG משולב (גוגל הרשמי):</b><br>"
                        f"• סטטוס: {retrieval_status}<br><br>"
                        f"{retrieved_results_html}"
        })

    except Exception as e:
        return jsonify({"response": f"❌ שגיאה כללית במהלך הרצת השלבים: {e}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
