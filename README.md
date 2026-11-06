# IS_ERP

Корпоративная информационная система инжиниринговой компании. Правила разработки — в [CLAUDE.md](CLAUDE.md).

## Запуск

```bash
cp .env.example .env
make dev
make migrate
```

Проверить: `curl http://localhost:8000/health/`
