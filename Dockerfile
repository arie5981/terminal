FROM python:3.11-slim

WORKDIR /app

# התקנת הספריות הבסיסיות (כמו flask ו-openai)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# העתקת קבצי האפליקציה, תיקיית התבניות ותיקיית המידע של ה-Terminal
COPY app.py .
COPY templates/ ./templates/
COPY data/ ./data/

# הגדרת הפורט הנדרש על ידי Fly.io
ENV PORT=8080
EXPOSE 8080

# הרצה ישירה של השרת שכתבנו
CMD ["python", "app.py"]
