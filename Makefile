.PHONY: install dev run check docker-build docker-run clean

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -r requirements.txt

dev:
	.venv/bin/uvicorn app:app --reload --port 8000

run:
	.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000

check:
	.venv/bin/python -m py_compile app.py pipeline.py generate_video.py dreamina_batch.py doubao_review.py
	node --check web/app.js

docker-build:
	docker build -t short-video-ai-studio .

docker-run:
	docker run --rm -p 8000:8000 --env-file .env -v "$$(pwd)/data:/app/data" -v "$$(pwd)/uploads:/app/uploads" -v "$$(pwd)/output:/app/output" short-video-ai-studio

clean:
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	find . -name "*.pyc" -delete
