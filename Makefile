.PHONY: install run test demo agent
install:
	python -m pip install -e '.[dev]'
run:
	uvicorn app.api:create_app --factory --reload --port 8000
test:
	python -m pytest -q
demo:
	python -m app.seed_demo
agent:
	python -m app.agent
