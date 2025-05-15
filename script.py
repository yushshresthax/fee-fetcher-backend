
#look into what can be done for the websites with login wall protcted or paywall. 
# Integrate both the part? Maybe the validation and the data extraction can be done in the same tine?
from io import BytesIO
import logging
import os
import random
import re
import time
from urllib.parse import urljoin
from openai import OpenAI
import playwright
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from dotenv import load_dotenv
import pdfplumber
import requests
import googleapiclient.discovery
import urllib.parse


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

client = OpenAI()



def generate_search_query(message):
    message = [
        {"role": "system", "content": "You are a specialist in logistics and transport industry research."},
        {"role": "user", "content": message}
    ]
    
    response = client.chat.completions.create(model="gpt-4o", messages=message)
    search_query = response.choices[0].message.content.strip()
    search_query = ' '.join(search_query.splitlines())  # Remove newlines
    search_query = search_query.replace("\n", " ")  # Replace any newlines with spaces
    search_query = search_query.replace('"', '')  # Remove quotation marks (optional)

    return search_query

    return search_query

def fetch_links_from_search_api(query):
    print("===================================")
    print(f"Fetching links for query: {query}")
    print("===================================")

    # Only encode the query once here, no need to do it in generate_search_query    
    service = googleapiclient.discovery.build("customsearch", "v1", developerKey="AIzaSyCjQHxsjmaclTYE6363M2CchgmrY9ObAHE")
    res = service.cse().list(q=query, cx="2684caba0321448bd").execute()
    # Collect and return the links from the response
    links = [item['link'] for item in res.get('items', [])]
    return links


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

def is_login_required(page_content):
    login_indicators = [
        "please log in",
        "login required",
        "access denied",
        "sign in",
        "register to access",
        "paywall",
        "subscription required"
    ]
    content_lower = page_content.lower()
    return any(phrase in content_lower for phrase in login_indicators)


def validate_link_content_with_gpt4(url):
    if url.lower().endswith(".pdf"):
        print("===================================")
        print(f"Processing PDF link: {url}")
        print("===================================")
        try:
            pdf_content = extract_pdf_link_content(url)
        except requests.RequestException as e:
            print("========ERROR=================")
            logger.error(f"Error fetching PDF {url}: {e}")
            print(f"Skipped {url} because it is unreachable or returned an error.")

            return False

        if pdf_content:
            pdf_content = pdf_content[:15000]  

            prompt = f"Please analyze the following PDF content and check if it contains relevant logistic and shipment surcharge data like prices, dates, or surcharges (fuel, toll, etc.):\n\n{pdf_content}\n\nDoes this pdf contain surcharge-related information (such as prices, dates, or fees)? Respond with simple 'yes' or 'no'"
            response = client.chat.completions.create(
                model="gpt-4o",  # Use GPT-4
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ]
            )
            validation_result = response.choices[0].message.content.strip().lower() 
            validation_result = re.sub(r'[^a-z\s]', '', validation_result)


            print(f"Validation result: {validation_result}")
            if validation_result == 'yes':
                return True
            else:
                print(f"Skipped {url} because PDF content could not be extracted.")
                return False
    else:

        # Handle non-PDF links (web pages)
        print("===================================")
        print(f"Processing web link: {url}")
        print("===================================")


        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
            except PlaywrightTimeoutError:
                logger.error(f"Timeout loading page: {url}")
                print(f"Skipped {url} because it timed out or is unreachable.")

                browser.close()
                return False            
            except Exception as e:
                logger.error(f"Error loading page {url}: {e}")
                print(f"Skipped {url} because it is unreachable or returned an error.")

                browser.close()
                return False

            try:
                content = page.inner_text("body")
            except Exception as e:
                logger.error(f"Error extracting text from page {url}: {e}")
                print(f"Skipped {url} because content could not be extracted.")

                browser.close()
                return False

            content = content[:15000] 

            if is_login_required(content):
                logger.info(f"Login required detected, skipping: {url}")
                browser.close()
                return False


            browser.close()
            print("===================================")

            # Send the content to GPT-4 for validation
            prompt = f"""
            Analyze the following page content and determine if it's an official carrier surcharge page containing ACTUAL NUMERIC DATA.

            A valid page MUST have ALL of these elements:
            1. Published by an official logistics/shipping carrier (not a news site or blog)
            2. Contains SPECIFIC NUMERIC surcharge rates or percentages (not just general descriptions)
            3. Includes effective dates or time periods for the surcharges
            4. Focuses on transport-related surcharges (fuel, CO2, toll, etc.)
            5. Is publicly accessible (no login wall detected)

            Example of valid content: "Current fuel surcharge: 12.5% effective from April 1, 2025"
            
            Page content:
            {content}
            
            Based ONLY on the criteria above, is this a valid carrier surcharge page with actual data? Answer with ONLY 'yes' or 'no'.
            """
            response = client.chat.completions.create(
                model="gpt-4o",  # Use GPT-4
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ]
            )

            # Extract GPT-4's response
            validation_result = response.choices[0].message.content.strip().lower()
            validation_result = re.sub(r'[^a-z\s]', '', validation_result)

            print(f"Validation result: {validation_result}")
            # If GPT-4 says 'yes', the link contains relevant data
            if validation_result == 'yes':
                return True
            else:
                return False

def display_valid_links(links):
    valid_links = []
    invalid_links = []
    
    # Validate each link and sort into valid and invalid categories
    for link in links:
        if validate_link_content_with_gpt4(link):
            print(link, "True")  # For debugging, prints each link and its validation result

            valid_links.append(link)
        else:
            invalid_links.append(link)

    # Display valid links
    if valid_links:
        print("Valid Links:")
        for link in valid_links:
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


def parse_content(raw_content,source):
    print(source)
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
        parsed_data_with_source = f"This data was extracted from: {source}\n\n{parsed_data}"

        return parsed_data_with_source
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
    print("Do you want to manually enter a link or use the prompt to extract a link?, Enter: \n 1 for manual link \n2 for automated extraction")
    primary_choice = input("Enter your choice (1 or 2): ")
    if primary_choice == '1':
        print("Enter 1 for website URL. \nEnter 2 for PDF link")
        choice = input("Enter your choice (1/2): ")
        if choice == '1':
            input_url = input("Enter the URL of the website: ")
            raw_content = fetch_website_content(input_url)
            display_link = input_url

            if raw_content:
                parsed_data = parse_content(raw_content, display_link)
                display_parsed_data(parsed_data)
            else:
                print(f"Failed to fetch or parse content from: {input_url}")
            pdf_links = fetch_pdf_links_from_page(input_url)
            if pdf_links:
                print(f"Found {len(pdf_links)} PDF links on the page. Processing PDFs...")
                for pdf_link in pdf_links:
                    pdf_content = extract_pdf_link_content(pdf_link)
                    if pdf_content:
                        parsed_pdf_data = parse_content(pdf_content, pdf_link)
                        display_parsed_data(parsed_pdf_data)
                    else:
                        print(f"Failed to extract content from PDF link: {pdf_link}")
            else:
                print("No PDF links found on the page.")


        elif choice == '2':
            is_url = input("Is the PDF link a URL? (yes/no): ").strip().lower()
            if is_url == 'yes':
                pdf_path = input("Enter the PDF link: ")
                raw_content = extract_pdf_link_content(pdf_path)
                display_link = pdf_path
                parsed_data = parse_content(raw_content,display_link)

            else:
                pdf_path = input("Enter the path to the PDF file: ")
                raw_content = extract_pdf_content(pdf_path)
                display_link = pdf_path
                parsed_data = parse_content(raw_content,display_link)


        else:
            print("Invalid choice. Please enter 1 or 2.")
            return None    
        # print('HERE IS THE PARSED DATA ',parsed_data)

        display_parsed_data(parsed_data)

    elif primary_choice == '2':
        user_query = f"""
            Generate a precise search query to find official carrier surcharge pages similar to this example: 
            https://www.bring.se/tjanster/internationell-logistik/internationell-vagtransport/fuel-surcharge

            The query should:
            1. Target major logistics carriers' official websites (like DHL, Maersk, DSV, DB Schenker, FedEx, UPS, etc.)
            2. Focus on specific surcharge types (fuel surcharge, bunker adjustment factor, CO2 fee, toll surcharge)
            3. Include technical terms that appear on surcharge pages (index, adjustment factor, calculator, percentage)
            4. Exclude general news, articles, or third-party aggregators
            5. Return a single search string without quotes or explanations
            """
        search_query = generate_search_query(user_query)
        print(f"Generated search query: {search_query}")


        links = fetch_links_from_search_api(search_query)
        print(f"Fetched {len(links)} links.")

        if not links:
            print("No links found.")
            return
        

        valid_links = []
        for link in links:
            print(f"Validating link: {link}")
            if validate_link_content_with_gpt4(link):
                valid_links.append(link)

        if not valid_links:
            print("No valid links found.")
            return

        print(f"Valid links: {valid_links}")
        
        for link in valid_links:
            print(f"\nProcessing content from: {link}")
            raw_content = None

            if link.lower().endswith(".pdf"):
                raw_content = extract_pdf_link_content(link)
            else:
                raw_content = fetch_website_content(link)

            if raw_content:
                parsed_data = parse_content(raw_content)
                display_parsed_data(parsed_data)
            else:
                print(f"Failed to extract content from: {link}")        
    else:
        print("Enter a valid answer")

 

if __name__ == "__main__":
    main()

