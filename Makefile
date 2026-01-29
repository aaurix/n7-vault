.PHONY: install push-scripts

install:
	python3 -m pip install -r requirements.txt

# Usage: make push-scripts MSG="describe change"
push-scripts:
	@if [ -z "$(MSG)" ]; then echo "ERROR: MSG is required. Example: make push-scripts MSG=\"update oi output\""; exit 1; fi
	git add scripts requirements.txt Makefile skills/market-ops || true
	git commit -m "$(MSG)" || true
	git push
