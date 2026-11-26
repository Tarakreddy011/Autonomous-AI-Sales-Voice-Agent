import os, mysql.connector
from dotenv import load_dotenv
load_dotenv()
conn = mysql.connector.connect(
    host=os.getenv('MYSQL_HOST'),
    port=int(os.getenv('MYSQL_PORT')),
    user=os.getenv('MYSQL_USER'),
    password=os.getenv('MYSQL_PASSWORD'),
    database=os.getenv('MYSQL_DATABASE')
)
cur = conn.cursor()
cur.execute('SHOW CREATE TABLE call_summaries')
for row in cur.fetchall():
    print(row[1])
cur.close()
conn.close()
