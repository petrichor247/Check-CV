from flask import Flask, request, render_template, session, redirect, url_for, jsonify, send_file, make_response
import cohere
import os
from PyPDF2 import PdfReader
from werkzeug.utils import secure_filename
import pandas as pd
from io import BytesIO

#from config import app, db
#from models import Contact
#from second import second

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os
from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__)
#app.register_blueprint(second, url_prefix="")
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
        
        '''
        # Map assessment to a numerical score
        score_mapping = {
            'excellent': 10,
            'good': 8,
            'average': 6,
            'below average': 4,
            'poor': 2
        }
        score = score_mapping.get(assessment, "Unable to determine score")
        
        scores.append(score)

    '''
    return answer

'''
def CV_improvement(text):
    response = co.chat(
        model='command',
        #message=f"Suggest top 3 improvements in {text}", 
        message = "tell me why ain't nothing but a heartache", 
        temperature=0.5, 
        #prompt_truncation='AUTO'
    )   
    mistakes = response.text.strip().split('\n')
    return mistakes

def CV_score(text):
    response = co.chat(
        model='command',
        #message=f"Analyse {text} and give it an integer score",
        message = "tell me why ain't nothing but a mistake",  
        temperature=0.8, 
        #prompt_truncation='AUTO'
    )   
    return response

def CV_summary(text):
    response = co.chat(
        model='command',
        message=f"Summarise {text} in a short paragraph",  
        temperature=0.3, 
    )   
    summary = response.text.strip().split('\n')
    return summary
'''

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
    
@app.route('/download_xls')
def download_xls():
    try:
        contacts = Contact.query.all()
        data = {
            'name': [contact.name for contact in contacts],
            'email': [contact.email for contact in contacts],
            'resume_file': [f"http://127.0.0.1:5000/download_resume/{contact.resume_file.split('/')[-1]}" for contact in contacts], #change url
            'improvements': [contact.improvements for contact in contacts],
            'cvscore': [contact.cvscore for contact in contacts]
        }
        df = pd.DataFrame(data)
        output = BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        df.to_excel(writer, sheet_name='Contacts', index=False)
        
        writer.close()

        output.seek(0)
        return send_file(output, download_name='contacts.xlsx', as_attachment=True)
    except Exception as e:
        return str(e)

'''
@app.route('/download_csv')
def download_csv():
    try:
        contacts = Contact.query.all()
        csv_data = "Email,Name,Resume File,Improvements\n"
        for contact in contacts:
            csv_data += f"{contact.email},{contact.name},{contact.resume_file},{contact.improvements}\n"

        response = make_response(csv_data)
        response.headers["Content-Disposition"] = "attachment; filename=entries.csv"
        response.headers["Content-Type"] = "text/csv"
        return response
    except Exception as e:
        print(f"Error: {e}")
        return f"An error occurred: {e}"



@app.route('/download-entries')
def download_entries():
    try:
        contacts = Contact.query.all()
        data = [contact.to_json() for contact in contacts]

        # Convert data to DataFrame
        df = pd.DataFrame(data)

        # Convert DataFrame to CSV
        csv_buffer = BytesIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)

        return send_file(csv_buffer, as_attachment=True, download_name="contacts.csv", mimetype='text/csv')
    
    except Exception as e:
        print(f"Error: {e}")
        return f"An error occurred: {e}"
'''   
if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    with app.app_context():
        #db.drop_all()
        db.create_all()

    app.run(debug=True) 
