import os
import json
import base64
import firebase_admin
from firebase_admin import credentials, db

def get_database():
    encoded_key = os.environ.get("FIREBASE_SERVICE_KEY_B64")
    decoded_json = base64.b64decode(encoded_key).decode("utf-8")

    # Gerçek satır sonlarını sil, sadece kaçışlı olanları bırak
    # İlk olarak \r ve \n karakterlerini escape'li hale çeviriyoruz
    cleaned = decoded_json.replace('\r', '\\r').replace('\n', '\\n')

    # Ardından JSON olarak yükle
    service_account_info = json.loads(cleaned)

    if not firebase_admin._apps:
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://cine-select-default-rtdb.europe-west1.firebasedatabase.app'
        })

    return db
