import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re

# Set headers to mimic a browser request for Amazon
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36'
}

# Function to extract and standardize quantity from the product name or other relevant tags
def extract_quantity(text):
    match = re.search(r'(\d+\s?g|\d+\s?kg|\d+\s?ml|\d+\.\d+\s?kg|\d+\.\d+\s?l|\d+\s?pcs|\d+\s?pack)', text.lower())
    if match:
        quantity = match.group()
        try:
            if 'kg' in quantity:
                return float(quantity.replace('kg', '')) * 1000  # Convert kg to grams
            elif 'g' in quantity:
                return float(quantity.replace('g', ''))
            elif 'l' in quantity:
                return float(quantity.replace('l', '')) * 1000  # Convert liters to milliliters
            elif 'ml' in quantity:
                return float(quantity.replace('ml', ''))
        except ValueError:
            print(f"Warning: Unable to convert quantity '{quantity}' to a float. Check the format.")
    return 'N/A'

# Function to calculate similarity score based on keyword matches
def calculate_similarity_score(product_name, search_query):
    product_name = product_name.lower()
    search_keywords = search_query.lower().split()
    score = 0
    
    for keyword in search_keywords:
        if keyword in product_name:
            score += 1  # Increase score for each matching keyword
    return score

# Function to search for a product on Amazon
def search_amazon(search_query, num_pages=1):
    base_url = 'https://www.amazon.in/s'
    params = {'k': search_query}
    products = []

    for page in range(1, num_pages + 1):
        params['page'] = page
        for attempt in range(5):  # Try up to 5 times
            try:
                response = requests.get(base_url, headers=headers, params=params)
                response.raise_for_status()  # Raises an error for bad responses
                break  # Exit the retry loop on success
            except requests.exceptions.HTTPError as e:
                if response.status_code == 503:
                    print(f"Service unavailable. Retrying... (Attempt {attempt + 1})")
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    print(f"HTTP error occurred: {e}")
                    return products
            except requests.exceptions.RequestException as e:
                print(f"Request failed: {e}")
                return products

        soup = BeautifulSoup(response.content, 'html.parser')

        for product in soup.find_all('div', {'data-component-type': 's-search-result'}):
            title = product.find('span', {'class': 'a-size-base-plus a-color-base a-text-normal'})
            price_whole = product.find('span', {'class': 'a-price-whole'})
            price_fraction = product.find('span', {'class': 'a-price-fraction'})
            product_link = product.find('a', {'class': 'a-link-normal s-no-outline'})
            asin = product.get('data-asin')

            if title and price_whole:
                title_text = title.get_text(strip=True)
                price_text = price_whole.get_text(strip=True)
                if price_fraction:
                    price_text += '.' + price_fraction.get_text(strip=True)

                try:
                    price = float(price_text.replace('₹', '').replace(',', ''))
                except ValueError:
                    price = None

                quantity = extract_quantity(title_text)
                score = calculate_similarity_score(title_text, search_query)

                if score > 0 and asin.startswith("B07"):  # Only add products that match the query and have valid ASIN
                    products.append({
                        'Product Name': title_text,
                        'Price': price,
                        'Quantity': quantity,
                        'More Info': "https://www.amazon.in" + product_link['href'] if product_link else 'N/A',
                        'ASIN': asin,
                        'Score': score
                    })

        time.sleep(2)  # General delay between pages

    # Sort products by score in descending order
    products.sort(key=lambda x: x['Score'], reverse=True)
    print(f"Amazon Products Found: {len(products)}")
    return products

# Function to search for a product on Grace Online
def search_grace(search_query, num_pages=5):
    base_url = 'https://www.graceonline.in/ct/fruit-vegetables'
    all_html_text = []

    for page in range(1, num_pages + 1):
        params = {'q': search_query, 'page': page}
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        html_text = response.text
        all_html_text.append(html_text)

        soup = BeautifulSoup(html_text, 'lxml')
        if not soup.find_all('div', class_='item-contents'):
            break

        time.sleep(1)

    return all_html_text

# Parsing function for Grace Online products
def parse_grace_products(all_html_text, search_query):
    product_data = []

    for html_text in all_html_text:
        soup = BeautifulSoup(html_text, 'lxml')
        products = soup.find_all('div', class_='item-contents')

        for product in products:
            product_name = product.find('span', class_='item-name')
            item_quantity = product.find('div', class_='item-default item-quantity')
            price_container = product.find('div', class_='item-price')
            product_link = product.find('a')
            brand_name = product.find('span', class_='item-brand')  # Assuming there's a brand element

            product_name = product_name.text.strip() if product_name else 'N/A'
            item_quantity_text = item_quantity.text.strip() if item_quantity else 'N/A'

            quantity = extract_quantity(product_name + ' ' + item_quantity_text)
            score = calculate_similarity_score(product_name, search_query)

            if price_container:
                price_spans = price_container.find_all('span')
                if price_spans:
                    product_price = price_spans[0].get_text(strip=True).replace("mrp :", "").strip()
                else:
                    product_price = 'Price Not Available'
            else:
                product_price = 'Price Not Available'

            try:
                product_price = float(product_price.replace('₹', '').replace(',', ''))
            except ValueError:
                product_price = float('inf')

            # Filter products based on the brand and score
            if score > 0 and brand_name and "grace fresh" in brand_name.text.lower():
                link = product_link['href'] if product_link else 'N/A'
                product_data.append({
                    'Product Name': product_name,
                    'Price': product_price,
                    'Quantity': quantity,
                    'More Info': link,
                    'Score': score
                })

    # Sort products by score in descending order
    product_data.sort(key=lambda x: x['Score'], reverse=True)
    print(f"Grace Products Found: {len(product_data)}")
    return product_data

# Function to compare products using exact matching and save to Excel
def compare_and_save_to_excel(amazon_data, grace_data, filename='product_comparison.xlsx'):
    amazon_df = pd.DataFrame(amazon_data)
    grace_df = pd.DataFrame(grace_data)

    matched_products = []

    for _, amazon_row in amazon_df.iterrows():
        for _, grace_row in grace_df.iterrows():
            # Add only exact matches to the results
            matched_products.append({
                'Product Name_Amazon': amazon_row['Product Name'],
                'Price_Amazon': amazon_row['Price'],
                'Quantity_Amazon': amazon_row['Quantity'],
                'More_Info_Amazon': amazon_row['More Info'],
                'ASIN': amazon_row['ASIN'],
                'Product Name_Grace': grace_row['Product Name'],
                'Price_Grace': grace_row['Price'],
                'Quantity_Grace': grace_row['Quantity'],
                'More_Info_Grace': grace_row['More Info']
            })

    if matched_products:
        comparison_df = pd.DataFrame(matched_products)
        comparison_df.to_excel(filename, index=False)
        print(f"Comparison data saved to {filename}")
    else:
        print("No matching products found.")

# Main function
def main(search_query):
    amazon_data = search_amazon(search_query)
    grace_html_text = search_grace(search_query)
    grace_data = parse_grace_products(grace_html_text, search_query)

    compare_and_save_to_excel(amazon_data, grace_data)

if _name_ == '_main_':
    search_query = input("Enter the fruit or vegetable you want to search for: ")
    main(search_query)