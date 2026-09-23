"""Entry point: run the local Flask API from scraping/ (mirrors api/ for local development)."""

from local_api.app import app

if __name__ == "__main__":
    from config import HOST, PORT, DEBUG
    app.run(debug=DEBUG, host=HOST, port=PORT)
