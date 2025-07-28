import os
import json
import firebase_admin
from firebase_admin import credentials, db

def get_database():
    # Ortam değişkeninden JSON stringini al ve parse et
    firebase_key_json = os.environ.get("FIREBASE_SERVICE_KEY")
    service_account_info = json.loads(firebase_key_json)

    # Firebase'e bağlan
    cred = credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://cine-select-default-rtdb.europe-west1.firebasedatabase.app/'
    })

    return db
