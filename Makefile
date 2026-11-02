.PHONY: test lint demo deploy
test:   ; python -m pytest -q
lint:   ; ruff check src tests
demo:   ; python scripts/demo_local.py
deploy: ; cd terraform && terraform init && terraform apply
