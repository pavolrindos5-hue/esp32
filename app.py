import os
import zipfile
import io
import threading
from flask import Flask, request, jsonify
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

app = Flask(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'credentials.json'
PHOTOS_FOLDER_ID = 'SEM_ZAPISTE_ID_PRIECINKA_S_FOTKAMI'

def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def background_zip_process(phone_number):
    print(f"Spúšťam tvorbu ZIP archívu na pozadí pre číslo: {phone_number}")
    try:
        service = get_drive_service()
        
        query = f"'{PHOTOS_FOLDER_ID}' in parents and trashed = false"
        results = service.files().list(
            q=query, pageSize=50, orderBy="createdTime desc", fields="files(id, name, mimeType)").execute()
        items = results.get('files', [])

        if not items:
            print("Žiadne fotky na spracovanie.")
            return

        memory_zip = io.BytesIO()
        with zipfile.ZipFile(memory_zip, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for item in items:
                file_id = item['id']
                file_name = item['name']
                if file_name.endswith('.json'):
                    continue

                request_file = service.files().get_media(fileId=file_id)
                file_stream = io.BytesIO()
                downloader = MediaIoBaseDownload(file_stream, request_file)
                
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                
                file_stream.seek(0)
                zip_file.writestr(file_name, file_stream.read())

        memory_zip.seek(0)

        file_metadata = {
            'name': 'mamine_nove_fotky.zip',
            'parents': [PHOTOS_FOLDER_ID]
        }
        media = MediaIoBaseUpload(memory_zip, mimetype='application/zip', resumable=True)
        uploaded_file = service.files().create(
            body=file_metadata, media_body=media, fields='id').execute()
        
        file_id = uploaded_file.get('id')
        service.permissions().create(
            fileId=file_id,
            body={'role': 'reader', 'type': 'anyone'}
        ).execute()

        file_info = service.files().get(fileId=file_id, fields='webViewLink').execute()
        download_link = file_info.get('webViewLink')
        print(f"Hotovo! ZIP odkaz: {download_link}")

    except Exception as e:
        print(f"Chyba v procese na pozadí: {str(e)}")

@app.route('/generate-zip', methods=['POST'])
def generate_zip():
    data = request.get_json()
    phone = data.get('phone', 'Neznáme')
    print(f"Prijatá požiadavka od: {phone}")

    # Spustenie na pozadí, aby server okamžite odpovedal ESP32
    thread = threading.Thread(target=background_zip_process, args=(phone,))
    thread.start()

    return jsonify({"status": "Prijaté, fotky sa pripravujú..."}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
