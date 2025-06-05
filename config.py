import os

MY_OPENAI_KEY = os.getenv("MY_OPENAI_KEY")


#ROOM 5 CONFIG
'''
DB_CONFIG = {
    "host": "localhost",       
    "port": "5432",            
    "dbname": "room5",
    "user": "postgres",
    "password": "burnout96"
}
'''

#R2M OFFICE CONFIG



DB_CONFIG = {
    "host": "localhost",
    "dbname": "r2m_office",
    "user": "postgres",
    "password": "burnout96",
    "port": 5432  # default PostgreSQL port
}