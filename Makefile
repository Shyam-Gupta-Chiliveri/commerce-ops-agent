.PHONY: test demo

export PYTHONPATH := src

test:
	pytest -q

demo:
	python -m opsagent demo
