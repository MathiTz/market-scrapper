#!/usr/bin/env fish
# Convenience script to set up, diagnose, scrape, and run the market scraper app.

# Ensure we're in the project root
set -l script_dir (dirname (status --current-filename))
cd $script_dir

# Activate venv if it exists, else create it
if test -d venv
    source venv/bin/activate.fish
else
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate.fish
end

# Install/update all dependencies (includes Scrapling)
echo "Installing dependencies..."
pip install -r requirements.txt

# Ensure .env exists
if not test -f .env
    cp .env.example .env
end

# Upgrade SQLAlchemy to a version compatible with Python 3.14
pip install --upgrade SQLAlchemy

# Ensure Scrapling is installed (primary scraper engine)
pip install scrapling

# Set up chromedriver (downloads if missing - used as fallback)
echo "Setting up chromedriver..."
python setup_chromedriver.py

# Run diagnostics to see if sites are reachable and products are extractable
echo "Running diagnostics..."
python analyze_diagnostics.py

# Initialize DB and seed
echo "Initializing database..."
python -m models.database
python -m seed

# Ask if user wants to scrape offers now
read -P "Run scraper to collect offers now? (y/n): " run_scrape
if test "$run_scrape" = "y" -o "$run_scrape" = "Y"
    echo "Scraping offers from all sites..."
    python -c "from services.scraper_service import run_all_offers; results = run_all_offers(); print(f'Scraped: {results}')"
end

# Run the app
echo "Starting web app at http://localhost:5050 ..."
python run.py
