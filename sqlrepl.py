import sqlite3

db = sqlite3.connect('mail.db')
cursor = db.cursor()

print("db: The database", "cursor: The db cursor", sep='\n')
