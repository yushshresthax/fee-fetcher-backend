import os
from openai import OpenAI
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# Set up OpenAI API key from environment variable
client = OpenAI(
    # This is the default and can be omitted
    api_key=os.environ.get("OPENAI_API_KEY"),
)

def fetch_website_content(url):
    # Fetches the content of a website using Playwright
    with sync_playwright() as p:
        # Launch a headless browser
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print(f"Navigating to {url}...")
        page.goto(url)

        raw_content = page.content()
        print("Page content fetched successfully.")
        # Close the browser
        browser.close()
    return raw_content

def parse_content(raw_content):
    # Parses the raw content of the website using GPT-4
    print("Sending the content to GPT-4 for processing...")


    try:
        # Use the ChatCompletion endpoint for GPT-4
        completion = client.chat.completions.create(
        model="gpt-4o",
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"Extract relevant data from the following HTML content. Focus on any fee-related tables or pricing information. Here is the content:\n\n{raw_content}"}
        ]
        )
        # print(completion.choices[0].message.content)

        # Extract parsed content from the response
        parsed_data = response['choices'][0]['message']['content']
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
    input_url = input("Enter the URL of the website: ")
    # Fetch the website content
    raw_content = fetch_website_content(input_url)

    # Parse the content with GPT-4
    parsed_data = parse_content(raw_content)

    # Display the parsed data
    display_parsed_data(parsed_data)

if __name__ == "__main__":
    main()
