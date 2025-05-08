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
    'buy now', 'checkout', 'shop', 'shopping cart', 'shop now',
    'catalog', 'collections', 'online shop', 'zur kasse',
    'jetzt kaufen', 'zahlung', 'versand', 'bestellen'
]

# Banned words
banned_keywords = ['workshop', 'shoping']

# Class and icon pattern keywords
icon_class_patterns = [
    re.compile(r'(fa|icon)-(shopping-)?(cart|bag|basket|trolley)', re.I),
    re.compile(r'cart[-_]?icon', re.I),
    re.compile(r'basket[-_]?icon', re.I),
    re.compile(r'shop[-_]?icon', re.I),
    re.compile(r'warenkorb', re.I),
]

image_alt_src_patterns = [
    re.compile(r'(cart|bag|basket|trolley|shop|warenkorb)', re.I)
]


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

        # Step 4: Class pattern check
        for tag in soup.find_all(class_=True):
            class_list = " ".join(tag.get("class", []))
            for pattern in icon_class_patterns:
                if pattern.search(class_list):
                    return (url, "Online shop detected", f"Class: {pattern.pattern}", "None")

        # Step 5: Image alt/src pattern check
        for img in soup.find_all('img'):
            alt = img.get('alt', '').lower()
            src = img.get('src', '').lower()
            for pattern in image_alt_src_patterns:
                if pattern.search(alt) or pattern.search(src):
                    return (url, "Online shop detected", f"Image: {pattern.pattern}", "None")

        # Step 6: Product-related structure check
        product_indicators = ['price', 'product-item', 'add-to-cart', 'qty', 'product-grid', 'product-title']
        for div in soup.find_all(['div', 'span', 'section']):
            class_list = " ".join(div.get('class', [])).lower()
            if any(indicator in class_list for indicator in product_indicators):
                return (url, "Online shop detected", f"Product structure: {class_list}", "None")

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

            # Heuristic 2: URL path contains shop/store/products/catalog
            if any(x in parsed_href.path for x in ['/shop', '/store', '/products', '/catalog']):
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
