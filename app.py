from flask import Flask, render_template
import os

app = Flask(__name__)

@app.route('/')
def home():
    # מציג את קובץ ה-index.html מתוך תיקיית templates
    return render_template('index.html')

if __name__ == '__main__':
    # קריטי עבור Fly.io - הקשבה לפורט 8080
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
