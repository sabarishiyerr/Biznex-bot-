import os
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

GOOGLE_SHEETS_CRED_PATH = os.getenv("GOOGLE_SHEETS_CRED_PATH")
GOOGLE_SHEETS_DOC_NAME = os.getenv("GOOGLE_SHEETS_DOC_NAME")

print("Cred path:", GOOGLE_SHEETS_CRED_PATH)
print("Doc name:", GOOGLE_SHEETS_DOC_NAME)

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds = Credentials.from_service_account_file(
    GOOGLE_SHEETS_CRED_PATH,
    scopes=scopes,
)

gc = gspread.authorize(creds)

print("Trying to open sheet...")
sh = gc.open(GOOGLE_SHEETS_DOC_NAME)
print("Opened spreadsheet successfully!")

print("Worksheets found:")
for ws in sh.worksheets():
    print(" -", ws.title)
