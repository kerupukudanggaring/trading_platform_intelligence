#!/usr/bin/env python
"""Script untuk insert test data ke intelligence_score."""

import psycopg2
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
)
cur = conn.cursor()

# Insert test data dengan skor bullish yang jelas
test_timestamp = datetime.now(timezone.utc).replace(minute=5, second=0, microsecond=0)

insert_query = """
    INSERT INTO intelligence_score 
    (timestamp, score, label, technical_score, retail_score, institutional_score, details)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (timestamp) DO UPDATE SET
        score = EXCLUDED.score,
        label = EXCLUDED.label,
        technical_score = EXCLUDED.technical_score,
        retail_score = EXCLUDED.retail_score,
        institutional_score = EXCLUDED.institutional_score,
        details = EXCLUDED.details;
"""

cur.execute(insert_query, (
    test_timestamp,
    25,  # Score bullish
    "strong_bullish",
    15,  # Technical score
    -10, # Retail score
    20,  # Institutional score
    None  # Details (opsional)
))

conn.commit()
print("✅ Test data inserted successfully!")
print(f"Timestamp: {test_timestamp}")
print(f"Score: 25 (strong_bullish)")
print(f"Technical: +15, Ritel: -10, Institusi: +20")
print("\nRefresh browser untuk melihat score breakdown di frontend!")

cur.close()
conn.close()
