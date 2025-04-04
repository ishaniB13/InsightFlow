import os
import sys
import re
import json
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger   
import sqlite3
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import tempfile
import openai
import subprocess
import base64
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import subprocess
import firebase_admin
from firebase_admin import credentials, db
import gzip
from datetime import datetime
import requests
from fuzzywuzzy import fuzz
import math
from translate import Translator
from io import BytesIO
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone

app = Flask(__name__)
app.secret_key = '<Please insert your key>'  # For flash message
DB_NAME = 'users.db'
PHP_SCRIPT_PATH = "./send_email.php"
scheduler = BackgroundScheduler()
logging.basicConfig(level=logging.INFO)

# Directly define API keys here
SPRINGER_API_KEY = "<Please insert your Springer API key>"  # Your Springer API Key
OPENAI_API_KEY = "<Please insert your OpenAI API key>"  # Your OpenAI API Key

# Set the OpenAI API key
openai.api_key = OPENAI_API_KEY

# Firebase Initialization
FIREBASE_DB_URL = os.getenv("FIREBASE_DB_URL")
FIREBASE_KEY_PATH = "firebase_key.json"

if not firebase_admin._apps:  # Prevent reinitialization error
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

# Database initialization with the new 'newsletter_frequency' column
def init_db():
    """Create the database if it doesn't exist.
    """
    
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            surname TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            profession TEXT NOT NULL,
            research_interest TEXT DEFAULT '',
            user_level TEXT DEFAULT '',
            summary_preference TEXT DEFAULT '',
            translate_summary BOOL DEFAULT '',
            language_preference TEXT DEFAULT 'en',
            newsletter_frequency TEXT DEFAULT ''
        )''')
        conn.commit()
        

# Insert new user into the database
def  insert_user(name, surname, email, profession, research_interest, 
                 summary_preference, user_level, translate_summary, language_preference, newsletter_frequency):
    """Insert a new user into the database.

    Args:
        name (str): First Name of the user
        surname (str): Last Name of the user
        email (str): Email of the user
        profession (str): Profession of the user
        research_interest (str): The research interest of the user
        summary_preference (str): Additional summary preferences
        user_level (str): The level of knowledge of the user wrt the research interest
        translate_summary (str): yes or no based on whether the user wants the summary translated
        language_preference (str): language key which shows the user's preferred language
        newsletter_frequency (str): Newsletter frequency sleceted by the user
    """
    
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''INSERT INTO users (name, surname, email, profession, research_interest, user_level, summary_preference, translate_summary, language_preference, newsletter_frequency)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (name, surname, email, profession, research_interest, user_level, summary_preference, translate_summary, language_preference,  newsletter_frequency))
        conn.commit()
    # Sync with Firebase
    ref = db.reference('users')
    ref.child(email).set({
        "name": name,
        "surname": surname,
        "email": email,
        "profession": profession,
        "research_interest": research_interest,
        "user_level": user_level,
        "summary_preference": summary_preference,
        "translate_summary": translate_summary,
        "language_preference": language_preference,
        "newsletter_frequency": newsletter_frequency
    })

# Fetch user by email
def get_user_by_email(email):
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row  # Enables dictionary-like access to rows
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        return dict(row) if row else None


def fetch_papers_from_springer(interest):
    """
    Fetch paper metadata from the Springer API for a specific topic of interest.
    Prioritizes searching in the title, then the abstract. Filters for the newest publications.
    Logs relevancy scores for better insight.
    
    Args:
        interest (str): The topic of interest to search for in the Springer API.
        
    Returns:
        list: A list of dictionaries containing the top 5 most relevant and recent papers.
    """

    # all_data = []
    url = f'https://api.springer.com/metadata/json?q={interest}&api_key={SPRINGER_API_KEY}&p=10'

    response = requests.get(url)
    response.raise_for_status()  # Raise an error for non-200 responses
    data = response.json()
    # all_data.append(data)
        
    
    """ ResearchGate API (Alternative or additional source) """ 
    # url = "https://www.researchgate.net/publicliterature.PublicLiterature.search.html"
    # response = requests.get(url, params={"search": interest})
    # response.raise_for_status()
    # data = response.json()
    # all_data.append(data)
    


    papers = []
    # for data in all_data:
    for record in data.get('records', []):
        title = record.get('title', 'No Title')
        abstract = record.get('abstract', 'No Abstract Available')
        published_date = record.get('publicationDate', 'No Date')
        link = record.get('url', [{}])[0].get('value', 'No Link Available')
        authors = [author['creator'] for author in record.get('creators', [])]
        journal = record.get('publicationName', 'Unknown Journal')
        volume = record.get('volume', 'Unknown Volume')
        starting_page = record.get('startingPage', '')
        ending_page = record.get('endingPage', '')
        doi = record.get('doi', 'No DOI Available')
        

        
        # Calculate relevancy score with priority on title
        title_score = fuzz.partial_ratio(interest.lower(), title.lower())
        abstract_score = fuzz.partial_ratio(interest.lower(), abstract.lower())
        relevancy_score = title_score * 0.8 + abstract_score * 0.2  # Heavily weight the title

        # Log scores
        print(f"Paper Title: {title}")
        print(f"Relevancy Score: {relevancy_score:.2f} (Title Score: {title_score}, Abstract Score: {abstract_score})\n")

        papers.append({
            'title': title,
            'published_date': published_date,
            'abstract': abstract,
            'link': link,
            'relevancy_score': relevancy_score,
            'authors': authors,
            'journal': journal,
            'volume': volume,
            'starting_page': starting_page,
            'ending_page': ending_page,
            'doi': doi
        })

    # Filter for recent papers within the last year
    filtered_papers = [
        paper for paper in papers
        if paper['published_date'] != 'No Date' and
            (datetime.now() - datetime.strptime(paper['published_date'], "%Y-%m-%d")).days <= 365
    ]

    # Sort by relevancy score first, then by publication date
    filtered_papers.sort(key=lambda x: (x['relevancy_score'], x['published_date']), reverse=True)

    return filtered_papers[:5]  # Return top 5 most relevant and recent papers


# Generate summary using OpenAI
def generate_summary(papers, summary_preference, user_level, profession):
    """
    Generate a summary for the given papers using OpenAI GPT.
    Each paper contains 'title', 'abstract' (or part of the content).
    
    Args:
        papers (list): A list of dictionaries containing paper metadata.
        summary_preference (str): The user's preference for the summary.
        user_level (str): The user's level of knowledge.
        profession (str): The user's profession.
        
    Returns:
        list: A list of dictionaries containing the paper title and the generated summary.
    """
    
    summaries = []
    
    for paper in papers:
        title = paper.get('title', 'Untitled Research')
        content = paper.get('abstract', 'No abstract available.')
        publishing_date = paper.get('published_date', 'Unknown')
        link = paper.get('link', 'No link available')
        authors = paper.get('authors', 'Unknown')
        journal = paper.get('journal', 'Unknown Journal')
        volume = paper.get('volume', 'Unknown Volume')
        starting_page = paper.get('starting_page', '')
        ending_page = paper.get('ending_page', '')
        doi = paper.get('doi', 'No DOI available')
        
        # Check if content is missing or empty
        if not content.strip():
            print(f"Warning: No abstract available for {title}")
            summaries.append({'title': title, 'summary': "No abstract available."})
            continue  # Skip this paper
        
        # Create the prompt for each paper
        prompt = (
            f"Provide a summary suitable for a {profession} audience with {user_level} level. "
            f"The paper's title is: {title}.\n\n"
            f"The paper's abstract is as follows:\n{content[:3000]}...\n"  # Limit to the first 1500 characters
            f"Summarize with key findings and relevance and {summary_preference}."
        )
        
        try:
            # Call OpenAI's API using the chat model endpoint
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",  # Use the GPT-3.5 turbo model for summaries
                messages=[{"role": "system", "content": "You are a helpful assistant."},
                          {"role": "user", "content": prompt}],
                max_tokens=500  # Adjust as per the desired summary length
            )
            
            summary = response['choices'][0]['message']['content'].strip()  # Fetch the summary
            
            summaries.append({
                'title': title,
                'summary': summary,
                'publishing_date': publishing_date,  
                'link': link,
                'authors': authors,
                'journal': journal,
                'volume': volume,
                'starting_page': starting_page,
                'ending_page': ending_page,
                'doi': doi
            })
            print(f"Summary generated successfully for: {title}")
        
        except Exception as e:
            print(f"Error generating summary for {title}: {e}")
            summaries.append({'title': title, 'summary': "Summary generation failed."})
    
    return summaries
    
def sanitize_text(text):
    """Function to sanitize the text by replacing problematic or special characters.

    Args:
        text (str): The text to sanitize

    Returns:
        text (str): Sanitized text
    """
    
    # Replace curly quotes with straight quotes
    text = text.replace('“', '"').replace('”', '"')
    text = text.replace('‘', "'").replace('’', "'")
    text = text.replace('“', '"').replace('”', '"')
    text = text.replace('‘', "'").replace('’', "'")
    # Replace curly quotes with straight quotes
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("‘", "'").replace("’", "'")

    # Replace dashes and spaces with ASCII equivalents
    text = text.replace("–", "-")  # En dash
    text = text.replace("—", "-")  # Em dash
    text = text.replace(" ", " ")  # Thin space
    text = text.replace(" ", " ")  # Non-breaking space

    
    # Replace other common problematic characters
    text = text.replace('–', '-')  # En dash to hyphen
    text = text.replace('—', '-')  # Em dash to hyphen
    text = text.replace('—', '-')  # Em dash to hyphen

    # Remove any other non-ASCII characters except special characters from european languages
    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789äöüßÄÖÜẞáéíóúÁÉÍÓÚñÑçÇàèìòùÀÈÌÒÙâêîôûÂÊÎÔÛãõÃÕ- \n*<>/.:,;$%&()[]{}!?")
    text = ''.join(char if char in allowed_chars else ' ' for char in text)

    return text


def send_email_using_php(recipient_email, recipient_name, research_interest, translate_summary, language_preference, summary):
    """Function to send an email using a PHP script.

    Args:
        recipient_email (str): The recipient's email address
        recipient_name (str): The recipient's name
        research_interest (str): The research interest
        translate_summary (str): yes or no based on whether the user wants the summary translated
        language_preference (str): language key which shows the user's preferred language
        summary (str): The summary to send in the email
    """
    
    # Path to PHP script
    php_script = './send_email.php'
    
    subject = f"Recent Research on {research_interest}"
    
    # Validate summary content
    if not summary or summary == "Summary generation failed.":
        print("Error: Summary is empty or generation failed.")
        return

    # Generate and compress PDFs, then encode in base64
    pdf_base64_list = generate_split_pdfs_base64(research_interest, translate_summary, language_preference, summary)
    if not pdf_base64_list:
        print("Error: PDF generation or compression failed.")
        return

    print(f"Number of PDFs generated: {len(pdf_base64_list)}")

    
    # Use temporary files to store base64 strings
    with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt') as temp_file:
            # Write the base64 PDFs to the temporary file
            json.dump(pdf_base64_list, temp_file)
            temp_file_path = temp_file.name
    
    # Prepare command with a single temporary file
    command = [
            "php",
            php_script,
            recipient_email,
            recipient_name,
            subject,
            temp_file_path  # Pass the path to the temporary file
        ]

    try:
        # Run the PHP script to send the email
        subprocess.run(command, check=True)
        print(f"Email sent successfully to {recipient_email}")
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while sending email: {e}")
        
    finally:
        # Optionally, delete the temporary file after use
        os.remove(temp_file_path)


class PDF(FPDF):
    # Page footer
    def footer(self):
        # Position at 1.5 cm from bottom
        self.set_y(-15)
        # Arial italic 8
        self.set_font('Arial', 'I', 8)
        # Page number
        self.cell(0, 10, 'Page ' + str(self.page_no()) + '/{nb}', 0, 0, 'C')
        
    def calculate_num_lines(pdf, title, font_name="Arial", font_size=12, line_height=10):
        pdf.set_font(font_name, "", font_size)
        # Get the width of the page minus the margins
        effective_page_width = pdf.w - pdf.l_margin - pdf.r_margin
        # Use multi_cell to determine the number of lines
        num_lines = pdf.multi_cell(effective_page_width, line_height, title, border=0, align='L', split_only=True)
        return len(num_lines)


def generate_pdf_from_chunk(research_interest, translate_summary, language_preference, chunk, titles=None, titles_processed=0):
    """Generate a PDF from a chunk of text. Include a table of contents if titles are provided.

    Args:
        research_interest (str): The research interest
        translate_summary (str): yes or no based on whether the user wants the summary translated
        language_preference (str): language key which shows the user's preferred language
        chunk (str): The chunk of text to include in the PDF
        titles (list, optional): A list of titles. Defaults to None.
        titles_processed (int, optional): The number titles processed until when the function is called. Defaults to 0.

    Returns:
        pdf_output: generated PDF in bytes
        titles_processed: number of titles processed until the end of the chunk
    """
    
    pdf = PDF()
    pdf.alias_nb_pages()  # Add total page count to the footer
    pdf.add_page()
    
    if translate_summary == "yes":
        translator = Translator(to_lang = language_preference, from_lang="en")


    # Add Title of the PDF
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Recent Research on {research_interest}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(10)
    
    # print(f"{titles=}\n")
    print(f"Number of titles found on the topic = {len(titles)}")
    # Generate contents page if titles are provided
    if titles_processed==0 and titles:
        pdf.set_font("Arial", "B", 14)
        pdf.cell(75)    # Move 75 units to the right
        pdf.cell(0, 10, "Table of Contents", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        pdf.ln(5)
        pdf.set_font("Arial", "", 12)
        for i, title in enumerate(titles, start=1):
            num_lines = PDF.calculate_num_lines(pdf, title)
            num_lines = math.ceil(num_lines)
            pdf.cell(10, num_lines*10, f"{i}.", ln=0, border=1, align="C")
            pdf.multi_cell(0, 10, f"{title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, border=1)
        pdf.add_page()      # Add a page break after the contents page
        
        if translate_summary == "yes":
            # # add the font from a .ttf file
            # pdf.add_font("DejaVu", "", "./fonts/DejaVuSans.ttf")
            # pdf.add_font("DejaVu", "B", "./fonts/DejaVuSans-Bold.ttf")
            pdf.set_font("Arial", "B", 12)
            pdf.cell(75)    # Move 75 units to the right
            toc_tr = {
                "de": "Inhaltsverzeichnis",
                "fr": "Table des matières",
                "es": "Tabla de contenido",
                "pt": "Índice"
            }
            toc_text = toc_tr.get(language_preference, "Table of Contents")
            pdf.cell(0, 10, toc_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
            pdf.ln(5)
            
            pdf.set_font("Arial", "", 12)
            for i, title in enumerate(titles, start=1):
                title = translator.translate(title)
                num_lines = PDF.calculate_num_lines(pdf, title)
                num_lines = math.ceil(num_lines)
                pdf.cell(10, num_lines*10, f"{i}.", ln=0, border=1, align="C")
                pdf.multi_cell(0, 10, f"{title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, border=1)
            pdf.add_page()      # Add a page break after the translated contents page
            
    if translate_summary == "yes":
        
        english_titles_processed = titles_processed
        
        # Translate chunk content before adding to PDF
        translated_chunk = ""
        for i in range(0, len(chunk), 500):
            translated_chunk += translator.translate(chunk[i:i+500])
            
        # Sanitize translated chunk content before adding to PDF
        sanitized_chunk_tr = sanitize_text(translated_chunk)
        sanitized_chunk = sanitize_text(chunk)
                
        pdf.set_font("Arial", "", size=12)
        
        # Split the chunk into lines and handle bold lines specifically
        for line in sanitized_chunk_tr.split('\n'):
            if line.__contains__('--------------------------------------------------'):
                titles_processed += 1
                if titles_processed < len(titles):
                    pdf.add_page()
                continue
            if line.startswith("$$$$"):  # If the line starts with citation marker
                pdf.set_font("Arial", "I", 10)  # Set font to italic for citations
                pdf.set_text_color(128, 128, 128)  # Set color to gray for citations
                line = line.lstrip("$$$$")  # Remove the citation markers   
            elif line.startswith("**") or line.startswith("*"):  # If the line starts with bold marker (e.g., **Title: )
                pdf.set_font("Arial", "B", size=12)  # Set font to bold
                pdf.set_text_color(0, 0, 255)  # Set color to blue for titles
                line = line.lstrip("**")  # Remove the bold markers
            elif line.startswith("<b>") or line.endswith("</b>"):
                pdf.set_font("Arial", "B",size=12)  # Set font to bold
                line = line.lstrip("<b>").rstrip("</b>")
            else:
                pdf.set_font("Arial", "", size=12)  # Set font to regular for non-bold text
                pdf.set_text_color(0, 0, 0)  # Set color to black for regular text
            
            pdf.multi_cell(0, 10, line)  # Add the line to the PDF
            pdf.ln(1)  # Add a small gap between lines
            
        pdf.add_page()  # Add a page break after the translated chunk
        
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "English Version", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        pdf.ln(5)
        
        
        
        for line in sanitized_chunk.split('\n'):
            if line.__contains__('--------------------------------------------------'):
                english_titles_processed += 1
                if english_titles_processed < len(titles):
                    pdf.add_page()
                continue
            if line.startswith("$$$$"):  # If the line starts with citation marker
                pdf.set_font("Arial", "I", 10)  # Set font to italic for citations
                pdf.set_text_color(128, 128, 128)  # Set color to gray for citations
                line = line.lstrip("$$$$")  # Remove the citation markers
            elif line.startswith("**") or line.startswith("*"):  # If the line starts with bold marker (e.g., **Title: )
                pdf.set_font("Arial", "B", 12)  # Set font to bold
                pdf.set_text_color(0, 0, 255)  # Set color to blue for titles
                line = line.lstrip("**")  # Remove the bold markers
            elif line.startswith("<b>") or line.endswith("</b>"):
                pdf.set_font("Arial", "B", 12)  # Set font to bold
                line = line.lstrip("<b>").rstrip("</b>")
            else:
                pdf.set_font("Arial", "", 12)  # Set font to regular for non-bold text
                pdf.set_text_color(0, 0, 0)  # Set color to black for regular text
            
            pdf.multi_cell(0, 10, line)  # Add the line to the PDF
            pdf.ln(1)  # Add a small gap between lines    
    else:
        sanitized_chunk = sanitize_text(chunk)
        for line in sanitized_chunk.split('\n'):
            if '--------------------------------------------------' in line:
                titles_processed += 1
                if titles_processed < len(titles):
                    pdf.add_page()
                continue
            if line.startswith("$$$$"):  # If the line starts with citation marker
                pdf.set_font("Arial", "I", 10)  # Set font to italic for citations
                pdf.set_text_color(128, 128, 128)  # Set color to gray for citations
                line = line.lstrip("$$$$")  # Remove the citation markers
            elif line.startswith("**") or line.startswith("*"):  # If the line starts with bold marker (e.g., **Title: )
                pdf.set_font("Arial", "B", 12)  # Set font to bold
                pdf.set_text_color(0, 0, 255)  # Set color to blue for titles
                line = line.lstrip("**")  # Remove the bold markers
            elif line.startswith("<b>") or line.endswith("</b>"):
                pdf.set_font("Arial", "B", 12)  # Set font to bold
                line = line.lstrip("<b>").rstrip("</b>")
            else:
                pdf.set_font("Arial", "", 12)  # Set font to regular for non-bold text
                pdf.set_text_color(0, 0, 0)  # Set color to black for regular text
                
            pdf.multi_cell(0, 10, line)  # Add the line to the PDF
            pdf.ln(1)  # Add a small gap between lines

            
        
    # Convert the PDF to bytes in memory
    pdf_output = pdf.output(dest='S')  # This is already a bytearray        
    return pdf_output, titles_processed



def compress_pdf(pdf_data):
    """Compress the PDF using gzip."""
    with BytesIO() as compressed_pdf:
        with gzip.GzipFile(fileobj=compressed_pdf, mode='wb') as f:
            f.write(pdf_data)
        return compressed_pdf.getvalue()

def update_user(email, user_level, research_interest, summary_preference, 
                translate_summary, language_preference, newsletter_frequency):
    """Function to update user preferences in the database if the user edits their profile.

    Args:
        email (str): email address of the user
        user_level (str): The user's level of knowledge
        research_interest (str): The user's research interest
        summary_preference (str): Additional summary preferences
        translate_summary (str): yes or no based on whether the user wants the summary translated
        language_preference (str): language key which shows the user's preferred language
        newsletter_frequency (str): Newsletter frequency sleceted by the user
    """
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET user_level = ?, research_interest = ?, summary_preference = ?, translate_summary = ?, language_preference = ?,  newsletter_frequency = ?
            WHERE email = ?
        ''', (user_level, research_interest, summary_preference, translate_summary, language_preference, newsletter_frequency, email))
        conn.commit()
        print(f"User with email {email} updated successfully.")



# Global variable to ensure the scheduler starts only once
scheduler_started = False

def fetch_users_with_frequency():
    """Utility to fetch users with a newsletter frequency
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.execute('''SELECT name, surname, email, user_level, profession, 
                                 research_interest, summary_preference, translate_summary, language_preference, newsletter_frequency 
                                 FROM users 
                                 WHERE newsletter_frequency IS NOT NULL''')
        return cursor.fetchall()

def get_interval_from_frequency(frequency):
    """
    Utility to convert newsletter frequency to time intervals
    """
    frequency_map = {
        "biweekly": 20160,  # 14 days in minutes
        "monthly": 43200,   # 30 days in minutes
        "two": 2,   
        "one": 1440        # For testing
    }
    return frequency_map.get(frequency.lower())

def get_language_code(language):
    """Get the language code for the user's preferred language.

    Args:
        language (String): the user's preferred language    

    Returns:
        string: language code for the user's preferred language
    """
    language_map = {
        "english": "en",
        "deutsch": "de",
        "español": "es",
        "français": "fr",
        "português": "pt"
    }
    return language_map.get(language.lower(), "en") # Default to English if not found

# Function to run the PHP script for sending emails
def run_php_script(recipient_email, recipient_name, subject, summary_preference):
    """
    Run the PHP script to send the newsletter email.
    """
    args = ["php", PHP_SCRIPT_PATH, recipient_email, recipient_name, subject, summary_preference]
    result = subprocess.run(args, text=True, capture_output=True)

    if result.returncode == 0:
        logging.info(f"[{datetime.now()}] Email sent successfully to {recipient_email}.")
    else:
        logging.error(f"[{datetime.now()}] Error sending email to {recipient_email}: {result.stderr}")


def schedule_user_jobs():
    """ Function to dynamically schedule jobs

    """
    global scheduler_started

    # Fetch all users with newsletter frequency
    users = fetch_users_with_frequency()

    if not users:
        logging.info(f"[{datetime.now()}] No users to schedule.")
        return

    for user in users:
        name = f"{user[0]} {user[1]}"
        email = user[2]
        profession = user[4]
        user_level = user[3]
        research_interest = user[5]
        summary_preference = user[6]            
        frequency = user[9]
        translate_summary = user[7]
        language_preference = user[8]

        # Determine interval
        interval_minutes = get_interval_from_frequency(frequency)
        if interval_minutes is None:
            logging.warning(f"Invalid frequency '{frequency}' for {email}. Skipping.")
            continue

        # Schedule the job
        job_id = f"newsletter_{email}"
        scheduler.add_job(
            func=process_user_newsletter,
            args=[email, name, user_level, profession, research_interest, translate_summary, language_preference, summary_preference],
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=job_id,
            replace_existing=True
        )


    if not scheduler_started:
        scheduler.start()
        logging.info("Scheduler started globally.")
        scheduler_started = True

def process_user_newsletter(email, name, user_level, profession, research_interest, translate_summary, language_preference, summary_preference):
    """
    Processes the user's newsletter by fetching papers, generating summaries,
    creating PDFs, and sending them via email.
    """
    
    print(f"Processing newsletter for {name} ({email})...")

    # Fetch papers related to the user's research interest
    papers = fetch_papers_from_springer(research_interest)
    print(f"Fetched {len(papers)} papers for {research_interest}.")

    # Generate summaries for the fetched papers
    summary = generate_summary(papers, summary_preference, user_level, profession)
    print(f"Generated summaries for {len(summary) if isinstance(summary, list) else 'N/A'} papers.")

    # Sanitize the summary to ensure all items are dictionaries
    sanitized_summary = sanitize_summary_items(summary)

    # Validate sanitized summaries
    if not sanitized_summary:
        print(f"No valid summaries generated for {email}. Skipping newsletter.")
        return

    # Generate and compress PDFs, then encode in base64
    pdf_base64_list = generate_split_pdfs_base64(research_interest, translate_summary, language_preference, sanitized_summary)
    if not pdf_base64_list:
        print(f"PDF generation failed for {email}. Skipping newsletter.")
        return

    print(f"Generated {len(pdf_base64_list)} PDF(s) for {email}. Sending email...")

    # Send the email with the generated PDF(s)
    send_email_using_php(email, name, research_interest, translate_summary, language_preference, summary)
    print(f"Newsletter sent to {email} successfully.")
        

def generate_split_pdfs_base64(research_interest, translate_summary, language_preference, summary, max_size_kb=7):
    """A function to generate and split PDFs based on the summary content.

    Args:
        research_interest (str): The research interest
        translate_summary (str): yes or no based on whether the user wants the summary translated
        language_preference (str): language key which shows the user's preferred language
        summary (str): The summary content to split into PDFs
        max_size_kb (int, optional): The maximum size. Defaults to 7.

    Returns:
        base64_pdfs: list of base64 encoded PDFs
    """
        
    pdf_chunks = []
    chunk_content = ""
    titles = []  # Collect titles for the contents page

    def format_bold(text):
        """Function to replace **text** with bold formatting.
        """
        return re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)

    # Ensure summary is a list of dictionaries
    if isinstance(summary, str):
        print("Warning: 'summary' is a string. Converting to a single-item list.")
        summary = [{"summary": summary}]  # Wrap the string in a dictionary
    elif not isinstance(summary, list):
        print(f"Error: Expected summary to be a list, but got {type(summary)}")
        return None

    # Split the summary into manageable chunks
    for item in summary:
        if not isinstance(item, dict):
            print(f"Error: Expected each summary item to be a dictionary, got {type(item)}")
            continue

        # Append summary details to chunk_content
        title = sanitize_text(item.get("title", "Untitled Research"))
        titles.append(title)  # Collect title for contents page
        chunk_content += f"**Title: {title}\n"

        publishing_date = sanitize_text(item.get("publishing_date", "Unknown"))
        chunk_content += f"**Publishing Date: {publishing_date}\n"
        
        authors = item.get("authors", "Unknown")
        chunk_content += f"**Authors: {', '.join(authors)}\n"

        summary_content = sanitize_text(item.get("summary", "No summary available"))
        chunk_content += format_bold(summary_content) + "\n"

        link = sanitize_text(item.get("link", "No link available"))
        chunk_content += f"**Link to Know More: {link}\n"
        
        # Add citation details at the end of each paper's summary
        authors = ', '.join(item.get("authors", ["Unknown"]))
        title = item.get("title", "Untitled Research")
        journal = item.get("journal", "Unknown Journal")
        volume = item.get("volume", "Unknown Volume")
        starting_page = item.get("starting_page", "")
        ending_page = item.get("ending_page", "")
        pages = f"{starting_page}-{ending_page}" if starting_page and ending_page else ""
        year = item.get("publication_date", "Unknown Year").split('-')[0]
        doi = item.get("doi", "No DOI available")

        citation = f"$$$${authors}. {title}. {journal} {volume}, {pages} ({year}). https://doi.org/{doi}\n{'-' * 50}\n"
        chunk_content += citation

        # Check chunk size
        if len(chunk_content.encode('utf-8')) > (max_size_kb * 1024):
            pdf_chunks.append(chunk_content)
            chunk_content = ""  # Reset for the next chunk

    # Append the last chunk if it's non-empty
    if chunk_content:
        pdf_chunks.append(chunk_content)    

    base64_pdfs = []
    
    # Generate PDFs for each chunk
    for i, chunk in enumerate(pdf_chunks):
        print(f"Generating PDF for chunk {i + 1} of size: {len(chunk.encode('utf-8'))} bytes")
        
        if i == 0:
            titles_processed = 0

        pdf_data, titles_processed = generate_pdf_from_chunk(research_interest, translate_summary, language_preference, chunk, titles, titles_processed)
        if not pdf_data:
            print(f"Error: Failed to generate PDF for chunk {i + 1}")
            continue

        print(f"Generated raw PDF for chunk {i + 1} of size: {len(pdf_data)} bytes")

        if len(pdf_data) > (max_size_kb * 1024):
            pdf_data = compress_pdf(pdf_data)
            print(f"Compressed PDF for chunk {i + 1} to size: {len(pdf_data)} bytes")

        if pdf_data:
            pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')
            base64_pdfs.append(pdf_base64)

    return base64_pdfs
    
def sanitize_summary_items(summary):
    """
    Ensures that each item in the summary is a dictionary.
    If an item is a string, it is converted into a dictionary with default values.
    Invalid items are skipped with a warning.
    """
    sanitized_summary = []

    if isinstance(summary, list):
        for item in summary:
            if isinstance(item, dict):
                # Item is already a dictionary, ensure required keys exist
                sanitized_summary.append({
                    "title": item.get("title", "Untitled Research"),
                    "summary": item.get("summary", "No summary available"),
                    "publishing_date": item.get("publishing_date", "Unknown"),
                    "link": item.get("link", "N/A"),
                })
            elif isinstance(item, str):
                # Convert string to a dictionary
                sanitized_summary.append({
                    "title": "Untitled Research",
                    "summary": item,
                    "publishing_date": "Unknown",
                    "link": "N/A",
                })
                print(f"Warning: Converted string to dictionary: {item}")
            else:
                # Skip invalid items
                print(f"Warning: Skipping invalid summary item: {item} (type: {type(item)})")
    elif isinstance(summary, str):
        # Handle case where the summary is a single string
        print(f"Warning: 'summary' is a string. Converting to a single-item list.")
        sanitized_summary.append({
            "title": "Untitled Research",
            "summary": summary,
            "publishing_date": "Unknown",
            "link": "N/A",
        })
    else:
        print(f"Error: Expected summary to be a list or string, got {type(summary)}")

    return sanitized_summary

def get_user_by_email(email):
    """
    Retrieve a user from the database by email.
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.execute("SELECT * FROM users WHERE email = ?", (email,))
        return cursor.fetchone()

# Home route - Redirect to Register
@app.route('/')
def home():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """
        Register a new user. If the user already exists, redirect to login.
    
    """
    if request.method == 'POST':
        name = request.form['name']
        surname = request.form['surname']
        email = request.form['email']
        profession = request.form['profession']
        
        user = get_user_by_email(email)
        if user:
            flash("You are already registered. Please login.", "info")
            return redirect(url_for('login'))
        
        # Insert new user with blank questionnaire fields
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute('''
                INSERT INTO users (name, surname, email, profession, research_interest, user_level, summary_preference, translate_summary, language_preference, newsletter_frequency) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (name, surname, email, profession, "", "", "", "FALSE", "en", ""))

        
        flash("Registration successful! Please complete the questionnaire.", "success")
        return redirect(url_for('questionnaire', email=email))
    
    return render_template('register.html')

@app.route('/questionnaire/<email>', methods=['GET', 'POST'])
def questionnaire(email):
    """This function is used to record the user's preferences and generate a summary based on the user's research interest.

    Args:
        email (str): email address of the user

    """
    user = get_user_by_email(email)
    if not user:
        return "No user found. Please register.", 400

    if request.method == 'POST':
        # Extract user inputs from the form
        user_level = request.form.get('user_level', '').strip()
        research_interest = request.form.get('research_interest', '').strip()
        summary_preference = request.form.get('summary_preference', '').strip()
        translate_summary = request.form.get('translate_summary', '').strip()
        language_preference = request.form.get('language_preference', '').strip()
        newsletter_frequency = request.form.get('newsletter_frequency', '').strip()

        # Update user preferences in SQLite
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute('''UPDATE users 
                                SET research_interest = ?, user_level = ?, summary_preference = ?, translate_summary = ?, 
                                    language_preference = ?, newsletter_frequency = ?
                                WHERE email = ?''',
                            (research_interest, user_level, summary_preference, translate_summary, language_preference, newsletter_frequency, email))
            conn.commit()

        # Fetch research papers and generate summary
        papers = fetch_papers_from_springer(research_interest)
        summary = (generate_summary(papers, summary_preference, user_level, user[4]) 
                    if papers else "No papers found for the given research interest.")
        

        # Send an email with updated details
        send_email_using_php(email, user[1], research_interest, translate_summary, language_preference, summary)

        # Update Firebase with user data
        sanitized_email = sanitize_email(email)
        try:
            ref = db.reference(f'users/{sanitized_email}')
            ref.update({
                "name": user[1],
                "surname": user[2],
                "email": email,
                "profession": user[4],
                "research_interest": research_interest,
                "user_level": user_level,
                "summary_preference": summary_preference,
                "translate_summary": translate_summary,
                "language_preference": language_preference,
                "newsletter_frequency": newsletter_frequency,
                "last_sent": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            app.logger.warning(f"Firebase update failed: {str(e)}")

        # Refresh scheduler
        schedule_user_jobs()

        flash("Your preferences were updated, and an email was sent.", "success")
        return redirect(url_for('home'))

    return render_template('questionnaire.html', user=user)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login route to authenticate the user.
    """
    if request.method == 'POST':
        email = request.form['email']
        user = get_user_by_email(email)
        if user:
            return redirect(url_for('profile', email=email))
        else:
            flash("No user found with this email. Please register.", "danger")
            return redirect(url_for('register'))
    
    
    return render_template('login.html')

@app.route('/profile/<email>')
def profile(email):
    """ User profile route to display the user's profile."""
    user = get_user_by_email(email)
    if not user:
        flash("User not found. Please register.", "danger")
        return redirect(url_for('register'))
    
    # Start the scheduler after rendering profile
    return render_template('profile.html', user=user)


# Function to sanitize email for Firebase path
def sanitize_email(email):
    # Replace special characters with underscores
    sanitized_email = re.sub(r'[.#$[\]/]', '_', email)
    sanitized_email = sanitized_email.replace('.', ',')
    return sanitized_email

@app.route('/update_profile', methods=['POST'])
def update_profile():
    updated_data = request.json

    # Extract data from the request
    email = updated_data.get("email")
    name = updated_data.get("name")
    surname = updated_data.get("surname")
    profession = updated_data.get("profession")
    research_interest = updated_data.get("research_interest")
    user_level = updated_data.get("user_level")
    summary_preference = updated_data.get("summary_preference")
    translate_summary = updated_data.get("translate_summary")
    language_preference = updated_data.get("language_preference")
    newsletter_frequency = updated_data.get("newsletter_frequency")

    # Update the SQLite database
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''UPDATE users 
                         SET name = ?, surname = ?, profession = ?,  
                             research_interest = ?, user_level = ?, summary_preference = ?,
                             translate_summary = ?, language_preference = ?, newsletter_frequency = ?
                         WHERE email = ?''',
                     (name, surname, profession, research_interest, user_level, summary_preference, 
                      translate_summary, language_preference, newsletter_frequency, email))
        conn.commit()

    # Sanitize the email for Firebase path
    sanitized_email = sanitize_email(email)

    # Update Firebase database
    try:
        ref = db.reference(f'users/{sanitized_email}')
        ref.update({
            "name": name,
            "surname": surname,
            "email": email,
            "profession": profession,
            "research_interest": research_interest,
            "user_level": user_level,
            "summary_preference": summary_preference,
            "translate_summary": translate_summary,
            "language_preference": language_preference,
            "newsletter_frequency": newsletter_frequency
        })
        firebase_update_status = "Firebase updated successfully."
    except Exception as e:
        firebase_update_status = f"Failed to update Firebase: {str(e)}"

    # Refresh the scheduler after updating the profile
    schedule_user_jobs()

    return jsonify({
        "success": True,
        "message": "Your profile has been successfully updated! You will now receive newsletters based on your updated preferences.",
        "firebase_update_status": firebase_update_status
    })
    
if __name__ == '__main__':
    init_db() # Schedule the newsletters based on the user settings
    app.run(debug=True)