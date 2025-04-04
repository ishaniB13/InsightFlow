from datetime import datetime, timedelta, timezone
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from subprocess import run
import firebase_admin
from firebase_admin import credentials, db
import os
from app import generate_summary, fetch_papers_from_springer, send_email_using_php
import os
import re
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger   
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import base64
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import firebase_admin
from firebase_admin import credentials, db
import gzip
from datetime import datetime
import math
from translate import Translator
from io import BytesIO
from fuzzywuzzy import fuzz
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone


# Path to PHP script for sending emails
PHP_SCRIPT_PATH = "./send_email.php"

# Initialize logging
logging.basicConfig(level=logging.INFO)

# Firebase setup
firebase_key_content = os.getenv("FIREBASE_KEY")
firebase_db_url = os.getenv("FIREBASE_DB_URL")

if not firebase_key_content or not firebase_db_url:
    raise ValueError("Firebase key content or database URL is missing.")

firebase_key_path = "firebase_key.json"
with open(firebase_key_path, "w") as key_file:
    key_file.write(firebase_key_content)

if not firebase_admin._apps:
    cred = credentials.Certificate(firebase_key_path)
    firebase_admin.initialize_app(cred, {"databaseURL": firebase_db_url})

# Scheduler setup
scheduler = BackgroundScheduler()
scheduler_started = False


# Fetch users with a newsletter frequency
def fetch_users_with_frequency():
    ref = db.reference("users")  # Firebase path to the "users" node
    firebase_data = ref.get()

    if not firebase_data:
        logging.info("No user data found in Firebase.")
        return []

    users_with_frequency = []
    for user_id, user_info in firebase_data.items():
        if user_info.get("newsletter_frequency"):
            users_with_frequency.append({
                "name": user_info.get("name", ""),
                "surname": user_info.get("surname", ""),
                "email": user_info.get("email", ""),
                "profession": user_info.get("profession", ""),
                "research_interest": user_info.get("research_interest", ""),
                "user_level": user_info.get("user_level", ""),
                "summary_preference": user_info.get("summary_preference", ""),
                "translate_summary": user_info.get("translate_summary", ""),
                "language_preference": user_info.get("language_preference", ""),
                "newsletter_frequency": user_info.get("newsletter_frequency", ""),
                "last_sent": user_info.get("last_sent", "")  # Track last sent date
            })
    return users_with_frequency


def calculate_next_interval(frequency):
    frequency_map = {
        "biweekly": timedelta(weeks=2),
        "monthly": timedelta(weeks=4),
        "two": timedelta(minutes=2),  # For testing (remove in production)
        "one": timedelta(days=1),      # Daily
        "weekly": timedelta(weeks=1),  # Weekly
        "hourly": timedelta(hours=1)   # Hourly frequency
    }

    interval = frequency_map.get(frequency.lower())
    if not interval:
        logging.warning(f"Invalid frequency: {frequency}")
        return None
    return interval


# Run PHP script for sending emails
def run_php_script(recipient_email, recipient_name, subject, summary_preference):
    try:
        args = ["php", PHP_SCRIPT_PATH, recipient_email, recipient_name, subject, summary_preference]
        result = run(args, text=True, capture_output=True)

        if result.returncode == 0:
            logging.info(f"[{datetime.now()}] Email sent successfully to {recipient_email}.")
        else:
            logging.error(f"[{datetime.now()}] Error sending email to {recipient_email}: {result.stderr}")
    except Exception as e:
        logging.error(f"[{datetime.now()}] Exception while sending email: {str(e)}")


# Process and send newsletters
def process_user_newsletter(email, name, user_level, profession, research_interest, translate_summary, language_preference, summary_preference):
    """
    Processes the user's newsletter by fetching papers, generating summaries,
    creating PDFs, and sending them via email.
    """
    
    # try:
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
        
    # except Exception as e:
    #     print(f"Error processing newsletter for {email}: {e}")

def generate_split_pdfs_base64(research_interest, translate_summary, language_preference, summary, max_size_kb=7):
        
    # try:
    pdf_chunks = []
    chunk_content = ""
    titles = []  # Collect titles for the contents page

    # Function to replace **text** with bold formatting (adjust based on your PDF library)
    def format_bold(text):
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

        summary_content = sanitize_text(item.get("summary", "No summary available"))
        chunk_content += format_bold(summary_content) + "\n"

        link = sanitize_text(item.get("link", "No link available"))
        chunk_content += f"**Link to Know More: {link}\n{'-' * 50}\n\n"

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
            # try:
            pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')
            base64_pdfs.append(pdf_base64)
            # except Exception as e:
            #     print(f"Error encoding PDF for chunk {i + 1} to base64: {e}")

    return base64_pdfs

    # except Exception as e:
    #     print(f"Error generating PDFs: {e}")
    #     return None

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
    """Generate a PDF from a single chunk of text with an optional contents page."""
    
    # try:
    pdf = PDF()
    pdf.alias_nb_pages()  # Add total page count to the footer
    pdf.add_page()

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
        
        english_titles_processed = titles_processed
        
        # Translate chunk content before adding to PDF
        translator = Translator(to_lang = language_preference, from_lang="en")
        translated_chunk = ""
        for i in range(0, len(chunk), 500):
            translated_chunk += translator.translate(chunk[i:i+500])
            
        
        # Sanitize translated chunk content before adding to PDF
        sanitized_chunk_tr = sanitize_text(translated_chunk)
        sanitized_chunk = sanitize_text(chunk)

        # Add the sanitized chunk content with proper formatting for bold
        # add the font from a .ttf file
        pdf.add_font("DejaVu", "", "./fonts/DejaVuSans.ttf")
        pdf.add_font("DejaVu", "B", "./fonts/DejaVuSans-Bold.ttf")
                
        pdf.set_font("DejaVu", "", size=12)
        
        # Split the chunk into lines and handle bold lines specifically
        for line in sanitized_chunk_tr.split('\n'):
            if line.__contains__('--------------------------------------------------'):
                titles_processed += 1
                if titles_processed < len(titles)-1:
                    pdf.add_page()
                continue              
            if line.startswith("**") or line.startswith("*"):  # If the line starts with bold marker (e.g., **Title: )
                pdf.set_font("DejaVu", "B", size=12)  # Set font to bold
                line = line.lstrip("**")  # Remove the bold markers
            elif line.startswith("<b>") or line.endswith("</b>"):
                pdf.set_font("DejaVu", "B",size=12)  # Set font to bold
                line = line.lstrip("<b>").rstrip("</b>")
            else:
                pdf.set_font("DejaVu", "", size=12)  # Set font to regular for non-bold text
            pdf.multi_cell(0, 10, line)  # Add the line to the PDF
            pdf.ln(1)  # Add a small gap between lines
            
        pdf.add_page()  # Add a page break after the translated chunk
        
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "English Version", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        pdf.ln(5)
        
        
        
        for line in sanitized_chunk.split('\n'):
            if line.__contains__('--------------------------------------------------'):
                english_titles_processed += 1
                if english_titles_processed < len(titles)-1:
                    pdf.add_page()
                continue
            if line.startswith("**") or line.startswith("*"):  # If the line starts with bold marker (e.g., **Title: )
                pdf.set_font("Arial", "B", 12)  # Set font to bold
                line = line.lstrip("**")  # Remove the bold markers
            elif line.startswith("<b>") or line.endswith("</b>"):
                pdf.set_font("Arial", "B", 12)  # Set font to bold
                line = line.lstrip("<b>").rstrip("</b>")
            else:
                pdf.set_font("Arial", "", 12)  # Set font to regular for non-bold text
            pdf.multi_cell(0, 10, line)  # Add the line to the PDF
            pdf.ln(1)  # Add a small gap between lines    
    else:
        sanitized_chunk = sanitize_text(chunk)
        for line in sanitized_chunk.split('\n'):
            if '--------------------------------------------------' in line:
                titles_processed += 1
                if titles_processed < len(titles)-1:
                    pdf.add_page()
                continue
            if line.startswith("**") or line.startswith("*"):  # If the line starts with bold marker (e.g., **Title: )
                pdf.set_font("Arial", "B", 12)  # Set font to bold
                pdf.set_text_color(0, 0, 255)  # Set color to blue for titles
                line = line.lstrip("**")  # Remove the bold markers
            elif line.startswith("<b>") or line.endswith("</b>"):
                pdf.set_font("Arial", "B", 12)  # Set font to bold
                line = line.lstrip("<b>").rstrip("</b>")
            else:
                pdf.set_font("Arial", "", 12)  # Set font to regular for non-bold text
                pdf.set_text_color(0, 0, 0)  # Set color to black for regular text
                
            # Check if the line contains a link
            if "Link to Know More:" in line:
                link = line.split(":", 1)[1].strip()
                pdf.set_text_color(0, 0, 255)  # Set color to black for regular text
                pdf.set_font("Arial", "B", 12)  # Regular font for the text
                pdf.multi_cell(0, 10, "Link to Know More:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_text_color(0, 0, 255)  # Set color to blue for hyperlink
                pdf.set_font("Arial", "U", 12)  # Underline the hyperlink
                pdf.cell(0, 10, link, link=link, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_text_color(0, 0, 0)  # Reset color to black for regular text
                pdf.set_font("Arial", "", 12)  # Reset font to regular
                pdf.ln(1)  # Add a small gap after the link
                continue  # Skip the rest of the processing for this line
                
            pdf.multi_cell(0, 10, line)  # Add the line to the PDF
            pdf.ln(1)  # Add a small gap between lines

            
        
    # Convert the PDF to bytes in memory
    pdf_output = pdf.output(dest='S')  # This is already a bytearray        
    return pdf_output, titles_processed

    # except Exception as e:
    #     print(f"Error generating PDF from chunk: {e}")
    #     return None


def compress_pdf(pdf_data):
    """Compress the PDF using gzip."""
    # try:
    with BytesIO() as compressed_pdf:
        with gzip.GzipFile(fileobj=compressed_pdf, mode='wb') as f:
            f.write(pdf_data)
        return compressed_pdf.getvalue()
    # except Exception as e:
    #     print(f"Error compressing PDF: {e}")
    #     return None

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

def sanitize_text(text):
    
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
    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789äöüßÄÖÜẞáéíóúÁÉÍÓÚñÑçÇàèìòùÀÈÌÒÙâêîôûÂÊÎÔÛãõÃÕ- \n*<>/.:")
    text = ''.join(char if char in allowed_chars else ' ' for char in text)

    return text



# Schedule the user jobs dynamically using IntervalTrigger
def schedule_user_jobs(manually_triggered=False):
    global scheduler_started

    users = fetch_users_with_frequency()
    if not users:
        logging.info("No users to schedule.")
        return

    for user in users:
        try:
            name = f"{user['name']} {user['surname']}"
            email = user['email']
            profession = user['profession']
            research_interest = user['research_interest']
            user_level = user['user_level']
            summary_preference = user['summary_preference']
            translate_summary = user['translate_summary']
            language_preference = user['language_preference']
            frequency = user['newsletter_frequency']

            logging.info(f"Scheduling for user: {email}, Frequency: {frequency}")

            # Calculate the interval based on user's preference
            interval = calculate_next_interval(frequency)
            if not interval:
                logging.warning(f"Invalid interval for user: {email}, Frequency: {frequency}")
                continue

            # Fetch last_sent from Firebase
            sanitized_email = email.replace(".", "_")
            ref = db.reference(f"users/{sanitized_email}")
            user_data = ref.get()

            if not user_data or 'last_sent' not in user_data:
                logging.info(f"No last_sent found for {email}, sending first email.")
                process_user_newsletter(
                    email, name, user_level, profession, research_interest, translate_summary, language_preference, summary_preference
                )
                last_sent = datetime.now(timezone.utc)
                ref.update({"last_sent": last_sent.isoformat()})
            else:
                last_sent = datetime.fromisoformat(user_data['last_sent'])

            # Calculate next run time
            next_run = last_sent + interval

            # Handle missed runs
            now_utc = datetime.now(timezone.utc)
            if next_run <= now_utc:
                logging.warning(f"Missed run detected for {email}. Executing now.")
                process_user_newsletter(
                    email, name, user_level, profession, research_interest, translate_summary, language_preference, summary_preference
                )
                last_sent = now_utc
                ref.update({"last_sent": last_sent.isoformat()})
                next_run = last_sent + interval  # Reschedule the next run

            logging.info(f"Next run for {email}: {next_run}")

            # Remove existing job if it exists to prevent duplicates
            job_id = f"newsletter_{email}"
            existing_job = scheduler.get_job(job_id)
            if existing_job:
                logging.info(f"Removing existing job for {email}")
                scheduler.remove_job(job_id)

            # Schedule the job with correct interval
            scheduler.add_job(
                func=process_user_newsletter,
                args=[email, name, user_level, profession, research_interest, translate_summary, language_preference, summary_preference],
                trigger=IntervalTrigger(seconds=interval.total_seconds(), start_date=next_run, timezone=timezone.utc),
                id=job_id,
                replace_existing=True,
                max_instances=1
            )
            logging.info(f"Scheduled job for {email} with interval {interval}. Next run at {next_run}.")

        except Exception as e:
            logging.error(f"Error scheduling job for {email}: {e}")

    # Start the scheduler if not already started
    if not scheduler_started:
        scheduler.start()
        logging.info("Scheduler started.")
        scheduler_started = True

    # Log all scheduled jobs
    jobs = scheduler.get_jobs()
    if jobs:
        logging.info(f"Current scheduled jobs: {[job.id for job in jobs]}")
    else:
        logging.info("No jobs scheduled.")



# Main execution
if __name__ == "__main__":
    logging.info("Starting scheduler...")
    schedule_user_jobs(manually_triggered=True)

    # Keep script running for background jobs
    while True:
        pass  # Ensure the scheduler continues running
