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
import googleapiclient.discovery
import urllib.parse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

client = OpenAI()

def get_user_input():
    query = input("Enter your search query: ")
    return query

def generate_search_query(prompt):
    message = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": f"Generate a relevant optimal search query which is simple in a single string which will help the search engine to fetch information for the following prompt: {prompt} "}
    ]
    
    response = client.chat.completions.create(model="gpt-4", messages=message)
    search_query = response.choices[0].message.content.strip()
    search_query = ' '.join(search_query.splitlines())  # Remove newlines
    search_query = search_query.replace("\n", " ")  # Replace any newlines with spaces
    search_query = search_query.replace('"', '')  # Remove quotation marks (optional)


    return search_query

def fetch_links_from_search_api(query):
    query = urllib.parse.quote(query)

    service = googleapiclient.discovery.build("customsearch", "v1", developerKey="AIzaSyCjQHxsjmaclTYE6363M2CchgmrY9ObAHE")
    res = service.cse().list(q=query, cx="YOUR_CX").execute()
    links = [item['link'] for item in res.get('items', [])]
    return links

def validate_link_content(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        content = page.content()
        browser.close()

        # Keywords to look for in the page content
        keywords = ["price", "fee", "cost", "charges"]
        if any(keyword in content.lower() for keyword in keywords):
            return True
        return False
    
def display_valid_links(links):
    if links:
        print("Valid Links:")
        for link in links:
            print(link)
    else:
        print("No valid links found.")

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
    # print(f"Extracting content from PDF link: {pdf_path}")

    response = requests.get(pdf_path)
    if response.status_code == 200:
        with pdfplumber.open(BytesIO(response.content)) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text()
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
            {"role": "user", "content": f"Extract relevant data from the following content. Focus on any fee-related tables or pricing information. Also please mention the title each link/pdf that you process. Here is the content:\n\n{raw_content}"}
            # {"role": "user", "content": f"Summarize the data found in just 50 words. Also please write the title of each content found. Here is the content:\n\n{raw_content}"}
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
        print("\n--- Parsed Data ---")
        print(parsed_data)
    else:
        print("No parsed data found.")

def main():
    # user_query = get_user_input()

    user_query = "Find me the best websites for transport and logistics surcharge data, including fuel indices"

    search_query = generate_search_query(user_query)
    print(search_query)
    print(f"Generated search query: {search_query}")
    print("++++++++++++++++++++++++++++++++++++++===============")

    links = fetch_links_from_search_api(search_query)
    print(f"Fetched {len(links)} links.")
    print(links)


    # valid_links = []
    # for link in links:
    #     if validate_link_content(link):
    #         valid_links.append(link)

    # # Step 5: Display valid links
    # display_valid_links(valid_links)

# ======================================================================================

    # pdf_processed = False
    # print("Enter 1 for website URL. \nEnter 2 for PDF link")
    # choice = input("Enter your choice (1/2): ")
    # count = 0
    # if choice == '1':
    #     input_url = input("Enter the URL of the website: ")
    #     pdf_links = fetch_pdf_links_from_page(input_url)

    #     if pdf_links:
    #         print("PDF links found on the page")
    #         pdf_content_list = []
            
    #         print(len(pdf_links),'number of pdf links')
    #         for pdf_link in pdf_links:
    #             count += 1
    #             print(f"run {count}")
    #             print(f"Extracting content from PDF link: {pdf_link}")

    #             pdf_content = extract_pdf_link_content(pdf_link)

    #             if pdf_content:
    #                 parsed_pdf_data = parse_content(pdf_content)
    #                 pdf_content_list.append(parsed_pdf_data)

    #         if pdf_content_list:
    #             print("\nAggregated Parsed Data from All PDFs:")
    #             for data in pdf_content_list:
    #                 display_parsed_data(data)
    #             pdf_processed = True  

    #         else:
    #             print("No parsed data found in the PDFs.")
             
    #     else:
    #         print("No PDF links found on the page.")
    #         raw_content = fetch_website_content(input_url)



    # elif choice == '2':
    #     is_url = input("Is the PDF link a URL? (yes/no): ").strip().lower()
    #     if is_url == 'yes':
    #         pdf_path = input("Enter the PDF link: ")
    #         raw_content = extract_pdf_link_content(pdf_path)
    #     else:
    #         pdf_path = input("Enter the path to the PDF file: ")
    #         raw_content = extract_pdf_content(pdf_path)
    # else:
    #     print("Invalid choice. Please enter 1 or 2.")
    #     return None   

    # if not pdf_processed:
    #     parsed_data = parse_content(raw_content)
    #     display_parsed_data(parsed_data)

if __name__ == "__main__":
    main()

