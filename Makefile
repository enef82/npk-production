.PHONY: dev migrate mm test lint fix shell api api-diff seed

dev:
	docker compose up --build

migrate:
	docker compose exec web python manage.py migrate

mm:
	docker compose exec web python manage.py makemigrations

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy config src tests conftest.py
	uv run lint-imports
	$(MAKE) api-diff

fix:
	uv run ruff check --fix .
	uv run ruff format .

shell:
	docker compose exec web python manage.py shell_plus

# Экспорт OpenAPI + генерация TS-клиента. Без docker: export_openapi_schema строит
# схему из роутеров и в БД не ходит, orval читает openapi.json из корня репозитория.
api:
	uv run python manage.py export_openapi_schema --api config.api.api --output openapi.json --indent 2
	cd frontend && npx orval --config orval.config.ts

# Проверяет ровно один вопрос: даёт ли перегенерация тот же результат, что лежит
# на диске. НЕ сравнение с HEAD — иначе «сгенерировано верно, но ещё не закоммичено»
# краснеет наравне с «устарело», и мы возвращаемся к объяснённому красному.
# Приём: снимок текущих файлов → перегенерация → сравнение со снимком → восстановление.
# Состояние индекса и рабочего дерева на результат не влияет; в CI на чистом дереве
# поведение не меняется. Тот же смысл, что у tests/test_doc_references.py: написанное
# (TS-типы, openapi.json) не должно молча расходиться с существующим (роутеры).
api-diff:
	@set -e; \
	snapshot=$$(mktemp -d); \
	trap 'cp "$$snapshot/openapi.json" openapi.json; rm -rf frontend/lib/api; cp -r "$$snapshot/api" frontend/lib/api; rm -rf "$$snapshot"' EXIT; \
	cp openapi.json "$$snapshot/openapi.json"; \
	cp -r frontend/lib/api "$$snapshot/api"; \
	$(MAKE) --no-print-directory api >/dev/null; \
	status=0; \
	diff -u "$$snapshot/openapi.json" openapi.json || status=1; \
	diff -ru "$$snapshot/api" frontend/lib/api || status=1; \
	if [ $$status -ne 0 ]; then \
		echo ""; \
		echo ">>> openapi.json или TS-клиент устарели относительно роутеров. Запусти 'make api' и закоммить результат."; \
		exit 1; \
	fi

seed:
	docker compose exec web python manage.py seed
	docker compose exec web python manage.py seed_demo
