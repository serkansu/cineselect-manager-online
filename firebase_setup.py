import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("serviceAccountKey.json")

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

def test_connection():
    print("✅ Firebase bağlantısı kuruluyor...")
    test_ref = db.collection("test").document("connection")
    test_ref.set({"status": "connected"})
    print("🎉 Bağlantı başarılı ve Firestore'a veri yazıldı.")

if __name__ == "__main__":
    test_connection()
