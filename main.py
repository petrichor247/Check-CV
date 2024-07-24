
from flask import Flask, request, render_template, session, redirect, url_for, send_file
import cohere
import os
from PyPDF2 import PdfReader
from werkzeug.utils import secure_filename
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

app.secret_key = os.getenv('SECRET_KEY')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_PATH'] = 16 * 1024 * 1024 

cohere_api_key = os.getenv('COHERE_API_KEY')
if not cohere_api_key:
    raise ValueError("No COHERE_API_KEY found in environment variables")
co = cohere.Client(cohere_api_key)

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
         "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)

sheet_id = "19Wp1ZXqUw1rmpptbrzGc1g5BT3oRcm64SoE8Jjlkaus"
sheet = client.open_by_key(sheet_id).sheet1

@app.route('/')
def upload_file():
    return render_template('index.html')

@app.route('/share', methods=['POST'])
def share():
    try:
        if 'file' not in request.files:
            return 'No file part'
        file = request.files['file']
        if file.filename == '':
            return 'No selected file'
        
        name = request.form['name']
        email = request.form['email']

        session['name'] = name
        session['email'] = email
        session['filename'] = file.filename

        file_name = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_name)
        file.save(file_path)
        session['filepath'] = file_path

        pdfreader = PdfReader(file)
        content = ''
        for page in pdfreader.pages:
            raw_text = page.extract_text()
            if raw_text:
                content += raw_text
        
        session['content'] = content

        improvements = "\n".join(CV_improvement(content))
        cvscore = CV_score(content)

        resume_url = url_for('download_resume', resume_path=file_name, _external=True)

        # Save to database
        relative_path = os.path.relpath(file_path, start=os.path.dirname(__file__))

        # Add entry to Google Sheets
        #sheet.append_row(["Name", "Email", "Resume URL", "Improvements", "CV Score"])  # Add headings
        sheet.append_row([name, email, resume_url, improvements, cvscore])

        return render_template('share.html', name=name, email=email, resume_file=resume_url)
    
    except Exception as e:
        print(f"Error: {e}")
        return f"An error occurred: {e}"

def chunk_text(text, max_tokens):
    words = text.split()
    chunks = []
    chunk = []
    chunk_length = 0
    for word in words:
        word_length = len(word) + 1  
        if chunk_length + word_length > max_tokens:
            chunks.append(' '.join(chunk))
            chunk = []
            chunk_length = 0
        chunk.append(word)
        chunk_length += word_length
    if chunk:
        chunks.append(' '.join(chunk))
    return chunks

def CV_improvement(text):
    max_tokens = 3000  # Define max token limit based on Cohere API model

    # Split text into chunks
    chunks = chunk_text(text, max_tokens)
    
    improvements = []
    for chunk in chunks:
        response = co.generate(
            model='command',
            prompt=f"Suggest the most important improvement in the following section of the resume, and just give one point:\n\n{chunk}",
            max_tokens=100,  # Define a suitable response token limit
            temperature=0.8
        )
        improvements.append(response.generations[0].text.strip())
    
    return improvements

@app.route('/analyse', methods=['POST', 'GET'])
def analyse_file():
    try:
        name = session.get('name')
        email = session.get('email')
        filename = session.get('filename')
        content = session.get('content')

        if not content:
            return 'No content to analyze'

        mistakes = CV_improvement(content)
        score = CV_score(content)

        return render_template('result.html', name=name, email=email, filename=filename, mistakes=mistakes, cvscore=score)
    
    except Exception as e:
        print(f"Error: {e}")
        return f"An error occurred: {e}"

def CV_score(text):
    max_tokens = 1000
    chunks = chunk_text(text, max_tokens)
    
    scores = []
    for chunk in chunks:
        response = co.generate(
            model='command',
            prompt=f"Please analyze the following resume content and provide an assessment of its quality. Respond with a one-word assessment like 'Excellent', 'Good', 'Average', 'Below average', or 'Poor'. Don't give a reason:\n\n{chunk}",
            max_tokens=50,
            temperature=0.3
        )
        
        assessment = response.generations[0].text.strip().lower()
        answer = assessment.split()[0]

    return answer

@app.route('/entries')
def show_entries():
    try:
        records = sheet.get_all_records()
        entries = [{"name": record["name"], "email": record["email"], "resume_file": record["resume_file"], "improvements": record["improvements"], "cvscore": record["cvscore"]} for record in records]
        return render_template('entries.html', entries=entries)
    except Exception as e:
        print(f"Error: {e}")
        return f"An error occurred: {e}"

@app.route('/download_resume/<path:resume_path>')
def download_resume(resume_path):
    try:
        full_path = os.path.join(app.config['UPLOAD_FOLDER'], resume_path)
        return send_file(full_path, as_attachment=True)
    except Exception as e:
        print(f"Error: {e}")
        return f"An error occurred: {e}"

@app.route('/download_xls')
def download_xls():
    try:
        return redirect(f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit", code=302)
    except Exception as e:
        return str(e)

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    app.run(debug=True)
