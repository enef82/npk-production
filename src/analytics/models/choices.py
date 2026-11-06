from django.db import models


class WeekStatus(models.TextChoices):
    """Состояние недели на экране отсечек — выводится, не хранится."""

    CURRENT = "current", "Текущая"
    OPEN = "open", "Открыта"
    CLOSED = "closed", "Отсечка закрыта"


class EmployeePeriod(models.TextChoices):
    """Период выработки сотрудников (`empPeriod` прототипа)."""

    FOUR_WEEKS = "4w", "4 недели"
    CURRENT_MONTH = "m0", "Текущий месяц"
    PREVIOUS_MONTH = "m1", "Прошлый месяц"


class PortfolioKind(models.TextChoices):
    """Слой портфеля: факт отгрузки, твёрдые заказы, воронка заявок."""

    FACT = "fact", "Отгружено (факт)"
    FIRM = "firm", "Заказы в работе"
    PIPE = "pipe", "Воронка (взвешенно)"
