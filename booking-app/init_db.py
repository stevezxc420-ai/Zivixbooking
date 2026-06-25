"""Run this once to initialise the database."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from app import app, init_db

if __name__ == "__main__":
    init_db()
    print("Database initialised successfully.")
