# ------------------------------------------------------------------------------
# Makefile for Python Project
#
.DEFAULT_GOAL := deploy

.PHONY: help clean install dev-install lint format check test docs-install docs-serve docs-build install-all uninstall reinstall app-install app-start app-stop deploy

help:
	@echo "Usage: make <command>"
	@echo ""
	@echo "Available commands:"
	@echo "  install       Install the project in editable mode for regular use."
	@echo "  dev-install   Install the project with all development dependencies."
	@echo "  docs-install  Install dependencies for building documentation."
	@echo "  docs-serve    Serve the documentation site locally for development."
	@echo "  docs-build    Build the documentation site."
	@echo "  install-all   Install the project with ALL dependencies (dev, docs)."
	@echo "  app-install   Install local full-stack development dependencies."
	@echo "  app-start     Start backend, visual, and goview development services."
	@echo "  app-stop      Stop backend, visual, and goview development services."
	@echo "  deploy        Run the interactive deployment wizard."
	@echo "  clean         Stop local services and remove build artifacts, cache files, and logs."
	@echo "  lint          Check code style and potential errors (report only, do not modify)."
	@echo "  format        Automatically format and repair code."
	@echo "  check         Combine commands: format first, then check to make sure the codebase is clean."
	@echo "  test          Perform one-click tests."
	@echo "  uninstall     Stop local services and uninstall the project."
	@echo "  reinstall     Stop local services, clean, and reinstall the project."
	@echo "  help          Show this help message."

install:
	@echo "--> Installing project in editable mode..."
	pip install -e .
	omc ./script/modelica_install/install.mos 
	@echo "--> Installation complete."

dev-install:
	@echo "--> Installing project with development dependencies..."
	pip install -e ".[dev]"
	omc ./script/modelica_install/install.mos 
	@echo "--> Development installation complete."

docs-install:
	@echo "--> Installing documentation dependencies..."
	pip install -e ".[docs]"
	@echo "--> Documentation dependencies installed."

docs-serve:
	@echo "--> Starting local documentation server..."
	mkdocs serve

docs-build:
	@echo "--> Building documentation..."
	mkdocs build

install-all:
	@echo "--> Installing project with ALL dependencies..."
	pip install -e ".[dev,docs]"
	omc ./script/modelica_install/install.mos
	@echo "--> Full installation complete."

app-install:
	@echo "--> Installing local full-stack development dependencies..."
	bash ./script/dev/linux/install_all_deps.sh

app-start:
	@echo "--> Starting local full-stack development services..."
	bash ./script/dev/linux/start_all.sh

app-stop:
	@echo "--> Stopping local full-stack development services..."
	bash ./script/dev/linux/stop_all.sh

deploy:
	@echo "--> Running the interactive deployment wizard..."
	bash ./script/dev/linux/deploy.sh

uninstall:
	@echo "--> Stopping local full-stack development services before uninstall..."
	-bash ./script/dev/linux/stop_all.sh
	@echo "--> Uninstalling project..."
	pip uninstall tricys -y
	@echo "--> Uninstallation complete."

reinstall: uninstall clean install
	@echo "--> Re-installation complete."

clean:
	@echo "--> Stopping local full-stack development services before cleanup..."
	-bash ./script/dev/linux/stop_all.sh
	@echo "--> Cleaning up project..."
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf tricys/*.egg-info/
	rm -f .coverage
	rm -rf temp/
	rm -rf log/
	rm -rf results/
	rm -rf data/
	rm -rf test/test_*/
	@echo "--> Cleanup complete."

lint:
	@echo "--> Checking code with Ruff..."
	ruff check .

format:
	@echo "--> Formatting code with Black..."
	black .
	@echo "--> Sorting imports and fixing code with Ruff..."
	ruff check . --fix
	@echo "--> Code formatting complete."

check: format lint
	@echo "--> All checks passed!"

test:
	@echo "--> Pytest Project..."
	pytest -v test/.
