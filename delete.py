import os
import shutil
from config import app, db
from models import Contact

uploads_dir = app.config['UPLOAD_FOLDER']

def delete_all_files_in_directory(directory):
    try:
        shutil.rmtree(directory)
        os.makedirs(directory)
    except Exception as e:
        print(f"Error: {e}")

with app.app_context():
    db.session.query(Contact).delete()
    db.session.commit()
    print("All database entries have been deleted.")
    
    delete_all_files_in_directory(uploads_dir)
    print("All files in the upload directory have been deleted.")
