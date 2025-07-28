import os
import json
import base64
import firebase_admin
from firebase_admin import credentials, db

def get_database():
    # Base64 ortam değişkenini al ve decode et
    encoded_key = os.environ.get("FIREBASE_SERVICE_KEY_B64")
    decoded_json = base64.b64decode(encoded_key).decode("utf-8")
    decoded_json = decoded_json.replace('\\n', '\n')
    service_account_info = json.loads(decoded_json)

    # Sadece ilk kez çalıştırıldığında initialize et
    if not firebase_admin._apps:
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://cine-select-default-rtdb.europe-west1.firebasedatabase.app'
        })

    return db
