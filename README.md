# НПК Производство

Приложение управления производством: заявки и калькуляция, производственные заказы и
план-график, ОТК, снабжение и склад, табель, оборудование и ТО, энергоучёт, аналитика.
Автономное приложение на стеке и ядре корпоративной ИС (`enef82/IS_ERP`).

Спецификация — [docs/spec/00-prilozhenie-proizvodstvo.md](docs/spec/00-prilozhenie-proizvodstvo.md).
Правила разработки — [CLAUDE.md](CLAUDE.md).

## Запуск

```bash
cp .env.example .env
make dev
make migrate
make seed        # роли, администратор и демо-данные прототипа
```

Проверить: `curl http://localhost:8000/health/`
