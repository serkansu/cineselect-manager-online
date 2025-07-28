import os
import json
import base64
import firebase_admin
from firebase_admin import credentials, db

def get_database():
    # Ortam değişkeninden base64 stringi al
    encoded_key = os.environ.get("FIREBASE_SERVICE_KEY_B64")
    decoded_json = base64.b64decode(encoded_key).decode("utf-8")

    # Parse etmeden önce PEM satır sonlarını düzelt
    decoded_json = decoded_json.replace('\\n', '\n')

    service_account_info = json.loads(decoded_json)

    # Firebase'e bağlan
    cred = credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://cine-select-default-rtdb.europe-west1.firebasedatabase.app'
    })

    return db
