import os
import random
import hashlib
import urllib.request
import sqlalchemy
import pymysql
from flask import (
    Flask,
    flash,
    render_template,
    send_from_directory,
    request,
    redirect,
    url_for,
    send_file,
    abort)
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from RandomWordGenerator import RandomWord
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from google.cloud import storage

app = Flask(__name__)

# -------------------- environment variables --------------------

load_dotenv()

UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER')

GOOGLE_APPLICATION_CREDENTIALS = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

CLOUD_STORAGE_BUCKET = os.getenv('CLOUD_STORAGE_BUCKET')

CLOUD_SQL_USERNAME = os.getenv('CLOUD_SQL_USERNAME')
CLOUD_SQL_PASSWORD = os.getenv('CLOUD_SQL_PASSWORD')
CLOUD_SQL_DATABASE_NAME = os.getenv('CLOUD_SQL_DATABASE_NAME')
CLOUD_SQL_CONNECTION_NAME = os.getenv('CLOUD_SQL_CONNECTION_NAME')
CLOUD_SQL_PORT = os.getenv('CLOUD_SQL_PORT')

SQL_PUBLIC_IP_ADDRESS = os.getenv('SQL_PUBLIC_IP_ADDRESS')
SQL_INSTANCE_NAME = os.getenv('SQL_INSTANCE_NAME')

PROJECT_ID = os.getenv('PROJECT_ID')

DB_CONNECT_P = sqlalchemy.engine.url.URL.create(
    drivername="mysql+pymysql",
    username=CLOUD_SQL_USERNAME,
    password=CLOUD_SQL_PASSWORD,
    database=CLOUD_SQL_DATABASE_NAME,
    query={
        "unix_socket": "{}/{}".format(
            '/cloudsql',
            CLOUD_SQL_CONNECTION_NAME)
    })

DB_CONNECT_D = f"mysql+mysqldb://{CLOUD_SQL_USERNAME}:{CLOUD_SQL_PASSWORD}@{SQL_PUBLIC_IP_ADDRESS}:{CLOUD_SQL_PORT}/{CLOUD_SQL_DATABASE_NAME}?unix_socket=/cloudsql/{PROJECT_ID}:{SQL_INSTANCE_NAME}"

# -------------------- database -------------------

app.config["SECRET_KEY"] = os.urandom(256)
app.config["SQLALCHEMY_DATABASE_URI"] = DB_CONNECT_D
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True

db = SQLAlchemy(app)

# -------------------- defined variables --------------------

common_ext = '.redfile'

delete_time = 10 # minutes after upload

# -------------------- db model --------------------

class FileData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_full_name = db.Column(db.String(100), nullable=False)
    file_name = db.Column(db.String(100), nullable=False)
    file_id = db.Column(db.String(6), unique=True, nullable=False)
    file_extension = db.Column(db.String(10), nullable=False)
    file_content_type = db.Column(db.String(50), nullable=False)
    file_encoded_name = db.Column(db.String(100), nullable=False)
    file_delete_time = db.Column(db.DateTime, nullable=False)
    file_erase = db.Column(db.Boolean(), default=False)
    file_key = db.Column(db.String(100), nullable=True)

# -------------------- service functions --------------------

def file_id_generate():
    rw = RandomWord(max_word_size = 6,
        constant_word_size=True,
        include_digits=True,
        special_chars=r"@_!#$%^&*()<>?/\|}{~:",
        include_special_chars=False
    )

    final_id = rw.generate()

    while FileData.query.filter_by(file_id=final_id).first():
        final_id = rw.generate()

    return final_id.lower()

def gcloud_upload(item_bytes, item_content_type, item_enc_name):
    
    # # Create a Cloud Storage client.
    gcs = storage.Client()

    # # Get the bucket that the file will be uploaded to.
    bucket = gcs.get_bucket(CLOUD_STORAGE_BUCKET)

    # # Create a new blob and upload the file's content.
    blob = bucket.blob(item_enc_name + common_ext)

    blob.upload_from_string(
        item_bytes,
        content_type = item_content_type
    )

def gcloud_download(item_name):
    storage_client = storage.Client()

    bucket = storage_client.bucket(CLOUD_STORAGE_BUCKET)

    blob = bucket.blob(item_name)

    return blob.generate_signed_url(expiration=datetime.utcnow() + timedelta(minutes=1))

def gcloud_delete(blob_name):
    storage_client = storage.Client()

    bucket = storage_client.bucket(CLOUD_STORAGE_BUCKET)
    blob = bucket.blob(blob_name)
    
    blob.delete()

def check_delete():
    true_erase_file = FileData.query.filter_by(file_erase=True).first()
    over_time_file = FileData.query.filter(FileData.file_delete_time < datetime.utcnow()).first()

    if true_erase_file or over_time_file:
        if true_erase_file:
            f = true_erase_file
        else:
            f = over_time_file

        try:
            gcloud_delete(f.file_encoded_name + common_ext)
        except:
            db.session.delete(f)

        db.session.delete(f)
        db.session.commit()

def file_encrypt(item, item_encoded_name):

    # -------------- key processing -----------------

    key = Fernet.generate_key()
  
    fernet = Fernet(key)
  
    # -------------- encryption -----------------

    original = item.read()
    
    encrypted = fernet.encrypt(original)

    # ---------------- db operations ----------------

    f = FileData.query.filter_by(file_encoded_name = item_encoded_name).first()
    f.file_key = key
    db.session.commit()

    return encrypted

def file_decrypt(item_id):
    
    f = FileData.query.filter_by(file_id = item_id).first()
    key = f.file_key
    file_encoded_name = f.file_encoded_name
    file_content_type = f.file_content_type
        
    # using the key
    fernet = Fernet(key)
    
    # reading the encrypted file
    with urllib.request.urlopen(gcloud_download(f.file_encoded_name + common_ext)) as item:
        encrypted = item.read()
    
    # decrypting the file
    decrypted = fernet.decrypt(encrypted)

    gcloud_upload(decrypted, file_content_type, file_encoded_name)

    f.file_erase = True
    db.session.commit()


# -------------------- application requests --------------------

@app.route('/', methods=['GET', 'POST'])
def index():
    check_delete()
    if request.method == 'GET':
        return render_template("index.html")
    else:
        f = request.files.get('file')
        if f:

            file_full_name = secure_filename(f.filename)
            file_name = os.path.splitext(file_full_name)[0]
            file_id = file_id_generate()
            file_extension = os.path.splitext(file_full_name)[1]
            file_content_type = f.content_type
            file_encoded_name = hashlib.sha224(str(file_full_name + datetime.now().strftime("%d%m%Y%H%M%S")).encode()).hexdigest()
            file_delete_time = datetime.utcnow() + timedelta(minutes=delete_time)

            new_file = FileData(
                file_full_name=file_full_name, 
                file_id=file_id, 
                file_extension=file_extension, 
                file_content_type=file_content_type, 
                file_name=file_name, 
                file_encoded_name=file_encoded_name,
                file_delete_time=file_delete_time
            )
            
            db.session.add(new_file)
            db.session.commit()

            encrypted_bytes = file_encrypt(f, file_encoded_name)

            if len(encrypted_bytes) > 10 ** 8:
                return "errFileTooLarge"

            gcloud_upload(encrypted_bytes, f.content_type, file_encoded_name)

            f.close()
        
            return file_id
        else:
            return 'errNoFile'

@app.route('/u/<file_id>')
def uploaded(file_id):
    return render_template("access.html", file_id=file_id, access=False)

@app.route('/<file_id>')
def access(file_id=None):
    if file_id == None or file_id == 'favicon.ico':
        return render_template("index.html")
    else:
        f = FileData.query.filter_by(file_id=file_id).first()
        if f:
            return render_template("access.html", file_full_name=f.file_full_name, file_id=file_id, access=True)
        else:
            abort(404)
        
@app.route('/<file_id>/download')
def download_file(file_id):
    f = FileData.query.filter_by(file_id=file_id).first()
    if f:
        file_decrypt(f.file_id)
        try:
            return send_file(urllib.request.urlopen(gcloud_download(f.file_encoded_name + common_ext)), attachment_filename=f.file_full_name)
        finally:
            check_delete()
    else:
        abort(404)

# -------------------- miscellaneous pages --------------------

@app.route('/m/about')
def about():
    return render_template("about.html")

# -------------------- error handler --------------------

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# -----------------------------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)