import os
import requests
import pandas as pd
import bs4
from flask import Flask, render_template, request, send_file
from werkzeug.utils import secure_filename
from io import BytesIO
import concurrent.futures

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'csv'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

shop_keywords = [
    'add to cart', 'cart', 'web shop', 'store', 'basket',
    'warenkorb', 'buy now', 'checkout', 'shop', 'shopping cart', 'shop now'
]

banned_keywords = ['workshop', 'shoping']

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def analyze_url(url):
    try:
        response = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        soup = bs4.BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text().lower()

        for banned in banned_keywords:
            if banned in text:
                return (url, "No shop found", "None", banned)

        found_keywords = [word for word in shop_keywords if word in text]
        if found_keywords:
            return (url, "Online shop detected", ", ".join(found_keywords), "None")

        for a_tag in soup.find_all('a'):
            link_text = a_tag.get_text().lower()
            href = a_tag.get('href', '').lower()
            for word in shop_keywords:
                if word in link_text or word in href:
                    return (url, "Online shop detected", word, "None")

        return (url, "No shop found", "None", "None")

    except Exception as e:
        return (url, f"Error: {str(e)}", "N/A", "N/A")

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(path)

            if filename.endswith('.csv'):
                df = pd.read_csv(path)
            else:
                df = pd.read_excel(path)

            with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
                results = list(executor.map(analyze_url, df['URL']))

            result_df = pd.DataFrame(results, columns=['URL', 'Status', 'Found Keywords', 'Banned Keywords'])

            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                result_df.to_excel(writer, index=False, sheet_name='Results')
            output.seek(0)

            return send_file(
                output,
                download_name='shop_results.xlsx',
                as_attachment=True,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
