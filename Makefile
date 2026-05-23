build:
	docker compose build

up:
	docker compose up

up-d:
	docker compose up -d

down:
	docker compose down

shell:
	docker compose run --rm opencode /bin/sh

attach:
	opencode attach http://localhost:$${PORT:-4300}
