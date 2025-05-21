from bs4 import BeautifulSoup
import requests
import re

def extract_hidden_fields(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    hidden_inputs = soup.find_all('input', {'type': 'hidden'})
    
    date_time_lines = []

    for input_tag in hidden_inputs:
        if 'name' in input_tag.attrs and 'value' in input_tag.attrs:
            input_name = input_tag['name']
            input_value = input_tag['value']
            if re.search(r'\bdate\b|\btime\b', input_name, re.IGNORECASE):
                line = str(input_tag.parent)
                date_time_lines.append(line)
   
    return hidden_inputs

def write_to_file(lines, file_path):
    with open(file_path, 'w', encoding='utf-8') as file:
        for line in lines:
            file.write(f"{line}\n")

def get_html_from_url(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        print(f"Failed to fetch HTML from {url}. Status code: {response.status_code}")
        return None

# Example usage with a URL
url = "https://trackmaxx.ch/registration/?race=solazh24&special=vip24late"
html_content = get_html_from_url(url)

if html_content:
    result = extract_hidden_fields(html_content)

    for line in result:
        print(line)
    write_to_file(result,"out.txt")
