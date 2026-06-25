"""Entry point: initialise DB then run the Flask app."""
import os
from app import app, init_db

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
