from io import BytesIO
import logging
import os
import random
import time
from urllib.parse import urljoin
from openai import OpenAI
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import pdfplumber
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

client = OpenAI()


def fetch_website_content(url, max_retries=3):
    """Fetch website content with retry logic and improved browser configuration"""
    for attempt in range(max_retries):
        try:
            with sync_playwright() as p:
                # Configure browser with options to help avoid detection
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-accelerated-2d-canvas',
                        '--disable-gpu'
                    ]
                )
                
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                )
                
                # Add a random delay to mimic human behavior
                time.sleep(random.uniform(1, 3))
                
                page = context.new_page()
                # Set HTTP/1.1 as default for problematic sites
                page.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
                
                logger.info(f"Navigating to {url}...")
                response = page.goto(url, wait_until='networkidle', timeout=60000)
                
                if response is None or not response.ok:
                    logger.error(f"Failed to load page: {response.status if response else 'No response'}")
                    if attempt < max_retries - 1:
                        continue
                
                # Wait for the page to be fully loaded
                page.wait_for_load_state('networkidle')
                
                # Scroll down to load any lazy content
                page.evaluate("""
                    () => {
                        window.scrollTo(0, document.body.scrollHeight / 2);
                        return new Promise(resolve => setTimeout(resolve, 1000));
                    }
                """)
                
                raw_content = page.content()
                logger.info("Page content fetched successfully.")
                browser.close()
                return raw_content
                
        except Exception as e:
            logger.error(f"Attempt {attempt+1}/{max_retries} failed: {str(e)}")
            if attempt == max_retries - 1:
                logger.error("All attempts failed.")
                raise
            time.sleep(random.uniform(2, 5))  # Backoff before retry
    
    return None

def fetch_pdf_links_from_page(url):
    """Fetch PDF links from a webpage"""
    pdf_links = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )
            
            page = context.new_page()
            page.goto(url, wait_until='networkidle', timeout=60000)
            
            # Wait for the page to be fully loaded
            page.wait_for_load_state('networkidle')
            
            links = page.query_selector_all("a")
            
            for link in links:
                href = link.get_attribute("href")
                if href and href.endswith('.pdf'):
                    full_url = urljoin(url, href)
                    logger.info(f"Found PDF link: {full_url}")
                    pdf_links.append(full_url)
            
            browser.close()
    except Exception as e:
        logger.error(f"Error fetching PDF links: {str(e)}")
    
    return pdf_links

def extract_pdf_link_content(pdf_path):
    print(f"Extracting content from PDF link: {pdf_path}")

    response = requests.get(pdf_path)
    if response.status_code == 200:
        with pdfplumber.open(BytesIO(response.content)) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text()
        print("PDF content extracted successfully.")
        print('pugyo yah')
        return text
    else:
        print(f"Failed to fetch PDF. Status code: {response.status_code}")
        return None

def extract_pdf_content(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text()
        print("PDF content extracted successfully.")
        return text


def parse_content(raw_content):
    # Parses the raw content of the website using GPT-4
    print("Sending the content to GPT-4 for processing...")
    message = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"Extract relevant data from the following content. Focus on any fee-related tables or pricing information. Here is the content:\n\n{raw_content}"}
        ]

    try:
        # Use the ChatCompletion endpoint for GPT-4
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=message,
        )

        # print(response.choices[0].message.content)
        # print(response)
        # Extract parsed content from the response
        parsed_data = response.choices[0].message.content
        return parsed_data
    except Exception as e:
        print(f"Error while processing the content: {e}")
        return None

def display_parsed_data(parsed_data):
    """
    Function to display the parsed data in the terminal.
    """
    if parsed_data:
        print("\n--- Parsed Data from the Website ---")
        print(parsed_data)
    else:
        print("No parsed data found.")

def main():
    print("Enter 1 for website URL. \nEnter 2 for PDF link")
    choice = input("Enter your choice (1/2): ")
    if choice == '1':
        input_url = input("Enter the URL of the website: ")
        raw_content = fetch_website_content(input_url)


        # pdf_links = fetch_pdf_links_from_page(input_url)
        # print(pdf_links)




        # if pdf_links:
        #     print("PDF links found on the page")
        #     print(pdf_links,'linkssss pdf')
        # else:
        #     print("No PDF links found on the page.")
    elif choice == '2':
        is_url = input("Is the PDF link a URL? (yes/no): ").strip().lower()
        if is_url == 'yes':
            pdf_path = input("Enter the PDF link: ")
            raw_content = extract_pdf_link_content(pdf_path)
        else:
            pdf_path = input("Enter the path to the PDF file: ")
            raw_content = extract_pdf_content(pdf_path)
    else:
        print("Invalid choice. Please enter 1 or 2.")
        return None    
    print('pugyo ya')
    parsed_data = parse_content(raw_content)
    # print('HERE IS THE PARSED DATA ',parsed_data)

    display_parsed_data(parsed_data)

if __name__ == "__main__":
    main()

