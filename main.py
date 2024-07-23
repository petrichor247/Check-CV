
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
        #new_contact = Contact(name=name, email=email, resume_file=relative_path, improvements=improvements, cvscore=cvscore)
        #db.session.add(new_contact)
        #db.session.commit()

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
        word_length = len(word) + 1  # Plus one for the space
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
        # Construct the full file path
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
'''
from flask import Flask, request, render_template, session, redirect, url_for, jsonify, send_file, make_response
import cohere
import os
from PyPDF2 import PdfReader
from werkzeug.utils import secure_filename
import pandas as pd
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build

from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

app.secret_key = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///database.db'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_PATH'] = 16 * 1024 * 1024 

db = SQLAlchemy(app)

class Contact(db.Model):
    email = db.Column("Email", db.String(100), primary_key = True)
    name = db.Column("Name", db.String(100))
    resume_file = db.Column(db.String(200))  # Path to the resume file
    improvements = db.Column(db.Text)  
    cvscore = db.Column(db.String(30))   
    
    def __init__ (self, name, email, resume_file, improvements, cvscore):
        self.name = name
        self.email = email
        self.resume_file = resume_file
        self.improvements = improvements
        self.cvscore = cvscore

    def to_json(self):
        return {
            "email": self.email,
            "name": self.name,
            "resume_file": self.resume_file,
            "improvements": self.improvements,
            "cvscore": self.cvscore
        }

cohere_api_key = os.getenv('COHERE_API_KEY')
if not cohere_api_key:
    raise ValueError("No COHERE_API_KEY found in environment variables")
co = cohere.Client(cohere_api_key)

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

        # Save to database
        relative_path = os.path.relpath(file_path, start=os.path.dirname(__file__))
        new_contact = Contact(name=name, email=email, resume_file=relative_path, improvements = improvements, cvscore = cvscore)
        db.session.add(new_contact)
        db.session.commit()

        return render_template('share.html', name=name, email=email, resume_file = relative_path)
    
    except Exception as e:
        print(f"Error: {e}")
        return f"An error occurred: {e}"
    

def chunk_text(text, max_tokens):
    words = text.split()
    chunks = []
    chunk = []
    chunk_length = 0
    for word in words:
        word_length = len(word) + 1  # Plus one for the space
        if chunk_length + word_length > max_tokens:
            chunks.append(''.join(chunk))
            chunk = []
            chunk_length = 0
        chunk.append(word)
        chunk_length += word_length
    if chunk:
        chunks.append(''.join(chunk))
    return chunks

def CV_improvement(text):
    max_tokens = 3000  # Define max token limit based on Cohere API model

    # Split text into chunks
    chunks = chunk_text(text, max_tokens)
    
    improvements = []
    for chunk in chunks:
        response = co.generate(
            model='command',
            prompt=f"Suggest the most important improvement in the following section of the resume, and just give one point :\n\n{chunk}",
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
        
        # Extract the assessment from the response
        assessment = response.generations[0].text.strip().lower()
        answer = assessment.split()[0]
        
        return answer

@app.route('/entries')
def show_entries():
    try:
        contacts = Contact.query.all()  # Query all entries in the Contact table
        entries = [contact.to_json() for contact in contacts]  # Convert each entry to JSON format
        return render_template('entries.html', entries=entries)  # Render entries in the template
    except Exception as e:
        print(f"Error: {e}")
        return f"An error occurred: {e}"
    
@app.route('/download_resume/<path:resume_path>')
def download_resume(resume_path):
    try:
        # Construct the full file path
        full_path = os.path.join(os.path.dirname(__file__), resume_path)
        return send_file(full_path, as_attachment=True)
    except Exception as e:
        print(f"Error: {e}")
        return f"An error occurred: {e}"

# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SERVICE_ACCOUNT_FILE = 'credentials.json'  # Replace with your service account file path
SPREADSHEET_ID = "19Wp1ZXqUw1rmpptbrzGc1g5BT3oRcm64SoE8Jjlkaus"  # Replace with your spreadsheet ID
RANGE_NAME = 'Sheet1'  # Replace with the range of your data

def upload_to_google_sheet():
    try:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('sheets', 'v4', credentials=credentials)
        
        contacts = Contact.query.all()
        data = [
            ['Name', 'Email', 'Resume File', 'Improvements', 'CV Score']
        ]
        for contact in contacts:
            data.append([
                contact.name, contact.email, contact.resume_file, contact.improvements, contact.cvscore
            ])
        
        body = {
            'values': data
        }
        result = service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME,
            valueInputOption='RAW', body=body).execute()
        print('{0} cells updated.'.format(result.get('updatedCells')))
    except Exception as e:
        print(f"Error: {e}")

@app.route('/download_xls')
def download_xls():
    try:
        upload_to_google_sheet()
        return redirect(f'https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}')
    except Exception as e:
        return str(e)

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    with app.app_context():
        db.create_all()

    app.run(debug=True)
'''
