# utils/google_drive.py

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

# Укажи путь к файлу с ключами
KEYS_FILE = "./credentials.json"





# Подключаемся к API Google Drive
def get_drive_service():
    creds = Credentials.from_service_account_file(KEYS_FILE, scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=creds)