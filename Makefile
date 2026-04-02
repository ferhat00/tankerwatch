.PHONY: install scrape app test

install:
	pip install -r requirements.txt
	playwright install chromium

scrape:
	python scripts/run_scraper.py --schedule

app:
	python scripts/run_app.py

test:
	pytest tests/ -v
