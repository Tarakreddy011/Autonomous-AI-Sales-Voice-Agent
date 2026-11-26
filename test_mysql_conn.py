import os
from pathlib import Path
from dotenv import load_dotenv
import mysql.connector

# Load .env explicitly
env_path = Path('C:/Users/hp/Desktop/Automated_caller_System/.env')
load_dotenv(dotenv_path=env_path)

keys = ['MYSQL_HOST','MYSQL_PORT','MYSQL_USER','MYSQL_PASSWORD','MYSQL_DATABASE']
for k in keys:
    v = os.getenv(k)
    print(f"{k}:", 'SET' if v is not None and v!='' else 'UNSET or EMPTY')

# Attempt connection
try:
    conn = mysql.connector.connect(
        host=os.getenv('MYSQL_HOST'),
        port=int(os.getenv('MYSQL_PORT') or 0),
        user=os.getenv('MYSQL_USER'),
        password=os.getenv('MYSQL_PASSWORD'),
        database=os.getenv('MYSQL_DATABASE'))
    print('Connection SUCCESS')
    conn.close()
except Exception as e:
    print('Connection FAILED:', e)
