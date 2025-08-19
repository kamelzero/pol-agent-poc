.PHONY: up db-init bridges norms agents ui setup setup-system setup-venv install test bluesky-install bluesky-git-clone bluesky-run bluesky-bridge

# One-shot bootstrap: installs system deps (sudo), Python 3.11, Docker, venv, and project deps
setup:
	$(MAKE) setup-system
	$(MAKE) setup-venv
	@echo "\nSetup complete. Activate venv with: source .venv/bin/activate"
	@echo "Then run: make check"

# Installs system-level dependencies for Ubuntu 22.04
setup-system:
	@echo "[setup-system] Installing system dependencies (requires sudo)"
	@command -v sudo >/dev/null 2>&1 || { echo "sudo is required. Run as root or install sudo."; exit 1; }
	@sudo apt-get update -y
	@sudo apt-get install -y software-properties-common curl make git ca-certificates gnupg lsb-release
	@# Python 3.11 (Ubuntu 22.04 default is 3.10)
	@sudo add-apt-repository -y ppa:deadsnakes/ppa
	@sudo apt-get update -y
	@sudo apt-get install -y python3.11 python3.11-venv python3.11-dev
	@# Docker Engine and Compose plugin (official Docker repo)
	@sudo install -m 0755 -d /etc/apt/keyrings
	@curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
	@sudo chmod a+r /etc/apt/keyrings/docker.gpg
	@echo "deb [arch=$$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $$(. /etc/os-release && echo $$VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
	@sudo apt-get update -y
	@sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
	@sudo usermod -aG docker $$(id -un) || true
	@docker --version || true
	@docker compose version || true
	@echo "If Docker group was just added, open a new shell or run: newgrp docker"

# Creates virtualenv and installs Python dependencies
setup-venv:
	@echo "[setup-venv] Creating Python 3.11 virtualenv and installing deps"
	python3.11 -m venv .venv
	. .venv/bin/activate && python -m pip install -U pip setuptools wheel
	. .venv/bin/activate && pip install -r requirements.txt

# Convenience targets
install:
	. .venv/bin/activate && pip install -r requirements.txt

test:
	. .venv/bin/activate && python -m pytest -q

up:
	docker compose up -d

db-init:
	# Run DDL inside the db container (no local psql needed)
	docker compose exec -T db psql -U postgres -d pol -v ON_ERROR_STOP=1 -f - < ops/sql/ddl.sql

check:
	. .venv/bin/activate && ruff check . --exclude external/ --exclude .venv/ && black --check . --extend-exclude 'external/|\.venv/' && python -m pytest -q --ignore=external/

bridges:
	PYTHONPATH=packages python packages/bridges/ais_bridge.py &
	PYTHONPATH=packages python packages/bridges/adsb_bridge.py &
	PYTHONPATH=packages python packages/bridges/ground_bridge.py &

norms:
	PYTHONPATH=packages python packages/normalizers/ais_normalizer.py &
	PYTHONPATH=packages python packages/normalizers/adsb_normalizer.py &
	PYTHONPATH=packages python packages/normalizers/ground_normalizer.py &

agents:
	PYTHONPATH=packages python packages/agents/maritime_agent.py &
	PYTHONPATH=packages python packages/agents/air_agent.py &
	PYTHONPATH=packages python packages/agents/ground_agent.py &
	PYTHONPATH=packages python packages/agents/fusion_agent.py &
	PYTHONPATH=packages python packages/agents/explainer_agent.py &

status:
	docker compose ps agent-maritime agent-air agent-ground agent-fusion agent-explainer
	docker compose exec -T db psql -U postgres -d pol -c "SELECT domain, count(*) FROM anomalies_domain WHERE ts > now() - interval '5 minutes' GROUP BY 1;"

tail-agents:
	docker compose logs --tail=50 agent-maritime agent-air agent-ground agent-fusion agent-explainer

ui:
	PYTHONPATH=packages streamlit run packages/ui/app.py

# --- BlueSky (Air Traffic Simulator) ---
# Install from PyPI into the venv
bluesky-install:
	. .venv/bin/activate && pip install "bluesky-simulator"

# Clone upstream and install editable (alternative to PyPI install)
bluesky-git-clone:
	mkdir -p external && cd external && test -d bluesky || git clone https://github.com/TUDelft-CNS-ATM/bluesky.git
	. .venv/bin/activate && pip install -e external/bluesky

# Run BlueSky (pass extra args via BS_ARGS, e.g., BS_ARGS="--nogui")
bluesky-run:
	. .venv/bin/activate && python -m bluesky $(BS_ARGS)

# Run our BlueSky→Kafka bridge
bluesky-bridge:
	. .venv/bin/activate && PYTHONPATH=packages BLUESKY_SCN=$(BLUESKY_SCN) BLUESKY_PUBLISH_HZ=$${BLUESKY_PUBLISH_HZ:-1.0} BLUESKY_DT_MULT=$${BLUESKY_DT_MULT:-1.0} python packages/bridges/bluesky_bridge.py

