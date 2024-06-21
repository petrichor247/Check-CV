from flask import Flask, request, render_template
import cohere
from PyPDF2 import PdfReader

app = Flask(__name__)

co = cohere.Client('yWBoy3c975BKgHTCkQUyUD10V0ZIzIw9Gjkex3fi')

@app.route('/')
def upload_file():
    return render_template('index.html')

@app.route('/analyse', methods=['POST'])
def analyse_file():
    try:
        if 'file' not in request.files:
            return 'No file part'
        file = request.files['file']
        if file.filename == '':
            return 'No selected file'
        
        name = request.form['name']
        email = request.form['email']

        pdfreader = PdfReader(file)
        content = ''
        for i, page in enumerate(pdfreader.pages):
            raw_text = page.extract_text()
            if raw_text:
                content += raw_text

        mistakes = analyse_CV(content)
        return render_template('result.html', name=name, email=email, filename=file.filename, mistakes=mistakes)
    except Exception as e:
        print(f"Error: {e}")
        return f"An error occurred: {e}"

def analyse_CV(text):
    response = co.chat(
        model='command',
        message=f"Find 3 mistakes in {text}",  
        temperature=0.3, 
    )   
    mistakes = response.text.strip().split('\n')
    return mistakes

if __name__ == '__main__':
    app.run(debug=True)













