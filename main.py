from flask import Flask, request, render_template, session, redirect, url_for
import cohere
from PyPDF2 import PdfReader
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv('SECRET_KEY')

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

        pdfreader = PdfReader(file)
        content = ''
        for page in pdfreader.pages:
            raw_text = page.extract_text()
            if raw_text:
                content += raw_text
        
        session['content'] = content

        return render_template('share.html', name=name, email=email)
    except Exception as e:
        print(f"Error: {e}")
        return f"An error occurred: {e}"
    

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
        summary = CV_summary(content)

        return render_template('result.html', name=name, email=email, filename=filename, mistakes=mistakes, score=score, summary=summary)
    except Exception as e:
        print(f"Error: {e}")
        return f"An error occurred: {e}"

def CV_improvement(text):
    response = co.chat(
        model='command',
        message=f"Suggest a few improvements in {text}",  
        temperature=0.3, 
    )   
    mistakes = response.text.strip().split('\n')
    return mistakes

def CV_score(text):
    response = co.chat(
        model='command',
        message=f"Give this {text} a score out of 10 in the format of score/10",  
        temperature=0.3, 
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

if __name__ == '__main__':
    app.run(debug=True)
