.PHONY: demo test lint eval sft chat dashboard dashboard-host docker-build docker-run evolve evolve-daemon evolve-daemon-stop
TOKEN ?=

demo:            ## offline tri-strata demo -> examples/demo_outputs/
	python3 scripts/run_demo.py

test:            ## unit + integration tests
	python3 -m pytest tests/ -q

lint:            ## static checks (pip install -r requirements-dev.txt)
	python3 -m ruff check .

eval:            ## compliance gate over curated investor cases
	python3 training/eval/eval_suite.py

sft:             ## generate SFT conversations for local fine-tuning
	python3 training/generate_sft_data.py --n 400 --out training/sft_data/train.jsonl

chat:            ## interactive CLI (LLM if key set, else offline pipeline)
	python3 -m invest_agent.cli

dashboard:       ## streamlit UI on localhost (pip install streamlit)
	streamlit run dashboard/app.py

dashboard-host:  ## streamlit UI on all interfaces (requires TOKEN=<secret>)
	@test -n "$(TOKEN)" || { echo "error: TOKEN is required, e.g. make dashboard-host TOKEN='s3cret'"; exit 1; }
	ATLAS_ACCESS_TOKEN='$(TOKEN)' streamlit run dashboard/app.py \
		--server.address 0.0.0.0 --server.port 8501 --server.headless true

docker-build:    ## build the non-root runtime image
	docker build -t atlas-multiasset-advisor .

docker-run:      ## run the image (requires TOKEN=<secret>)
	@test -n "$(TOKEN)" || { echo "error: TOKEN is required, e.g. make docker-run TOKEN='s3cret'"; exit 1; }
	docker run --rm -p 127.0.0.1:8501:8501 \
		-e ATLAS_ACCESS_TOKEN='$(TOKEN)' atlas-multiasset-advisor

evolve:          ## one factor-learning cycle (foreground)
	python3 scripts/evolution_daemon.py --once

evolve-daemon:   ## start the autonomous learning daemon (background, 6h cycle)
	mkdir -p data && nohup python3 scripts/evolution_daemon.py --interval-hours 6 \
		>> data/evolution_daemon.log 2>&1 & echo "daemon pid $$!"

evolve-daemon-stop:  ## stop the autonomous learning daemon
	-pkill -f "evolution_daemon.py"
