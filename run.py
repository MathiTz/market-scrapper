"""Entry point: run the Flask web app from the project root."""

from web.app import app

if __name__ == "__main__":
    from config import HOST, PORT, DEBUG
    app.run(debug=DEBUG, host=HOST, port=PORT)
