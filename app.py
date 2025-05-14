import os
import requests
import pandas as pd
import bs4
from flask import Flask, render_template, request, send_file
from werkzeug.utils import secure_filename
from io import BytesIO
import concurrent.futures
import re
# from urllib.parse import urlparse
from urllib.parse import urlparse, urljoin

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'csv'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Shop keywords (English + German)
shop_keywords = [
    'add to cart', 'cart', 'web shop', 'store', 'basket', 'warenkorb',
    'buy now', 'checkout', 'shop', 'shopping cart', 'shop now','online shop', 'zur kasse',
    'jetzt kaufen', 'zahlung', 'versand', 'bestellen'
]
shop_keywords.extend([
    'acheter', 'commander',  # French
    'comprar', 'carrito', 'tienda',    # Spanish
    'winkelwagen', 'bestellen',        # Dutch
])


# Banned words
banned_keywords = ['workshop', 'shoping']

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def analyze_url(url):
    try:
        response = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        soup = bs4.BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text().lower()

        # Step 1: Banned keyword check
        for banned in banned_keywords:
            if banned in text:
                return (url, "No shop found", "None", banned)

        # Step 2: Keyword scan in full page text
        found_keywords = [word for word in shop_keywords if word in text]
        if found_keywords:
            return (url, "Online shop detected", ", ".join(found_keywords), "None")

        # Step 3: Link text and href check
        for a_tag in soup.find_all('a'):
            link_text = a_tag.get_text().lower()
            href = a_tag.get('href', '').lower()
            for word in shop_keywords:
                if word in link_text or word in href:
                    return (url, "Online shop detected", word, "None")


        # Step 7: Subdomain or link to likely shop section
        parsed_url = urlparse(url)
        base_domain = parsed_url.netloc.replace('www.', '')

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href'].lower()

            # Normalize relative and full URLs
            full_href = urljoin(url, href)
            parsed_href = urlparse(full_href)

            # Heuristic 1: subdomain contains 'shop'
            if 'shop.' in parsed_href.netloc and base_domain in parsed_href.netloc:
                return (url, "Online shop detected", f"Subdomain: {parsed_href.netloc}", "None")

            # Heuristic 2: URL path contains shop/store
            if any(x in parsed_href.path for x in ['/shop', '/store']):
                return (url, "Online shop detected", f"Link path: {parsed_href.path}", "None")


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
