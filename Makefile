.PHONY: up db-init bridges norms agents ui

up:
	docker compose up -d
db-init:
	# Run DDL inside the db container (no local psql needed)
	docker compose exec -T db psql -U postgres -d pol -v ON_ERROR_STOP=1 -f - < ops/sql/ddl.sql

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

ui:
	PYTHONPATH=packages streamlit run packages/ui/app.py
