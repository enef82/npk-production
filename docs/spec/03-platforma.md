# Спецификация: платформенные подсистемы

**Приложения:** `core.documents`, `core.approvals`, `core.numbering`, `core.notifications`, `core.audit`
**Реализуется:** шаги 7 и 8 Фазы 0
**Термины:** `docs/spec/glossary.md`, раздел 4

---

## 1. Назначение и границы

Пять подсистем, которыми пользуются все девять модулей. Их ценность в том, что каждый
следующий модуль переиспользует их вместо того, чтобы городить своё: при команде
из полутора человек это экономит месяцы.

**Общее правило:** ни одна из этих подсистем не знает ни одного функционального модуля
по имени. Связь с прикладными сущностями — через строковые идентификаторы типа
и UUID объекта, без `ForeignKey`, без `GenericForeignKey`, без `contenttypes`.

`GenericForeignKey` запрещён сознательно: он тянет `contenttypes`, ломает типизацию,
делает невозможными нормальные `JOIN` в отчётах и создаёт зависимость от порядка
миграций. Строковая пара «тип сущности + UUID» решает ту же задачу и остаётся
читаемой в SQL.

---

## 2. Документы и файлы · `core.documents`

### 2.1 Модели

```python
class Document(TimeStampedModel, UUIDPrimaryKeyModel):
    original_name = models.CharField("Имя файла", max_length=255)
    file          = models.FileField("Файл", upload_to=...)      # S3 через django-storages
    size_bytes    = models.BigIntegerField("Размер")
    mime_type     = models.CharField("MIME-тип", max_length=128)
    checksum      = models.CharField("SHA-256", max_length=64, db_index=True)
    doc_type      = models.ForeignKey("documents.DocumentType", on_delete=models.PROTECT)
    version       = models.PositiveSmallIntegerField("Версия", default=1)
    supersedes    = models.ForeignKey("self", null=True, blank=True,
                                      on_delete=models.PROTECT, related_name="superseded_by")
    uploaded_by   = models.UUIDField("Кто загрузил")     # actor_id, без FK на User
```

```python
class DocumentLink(models.Model):
    """Привязка документа к произвольной сущности. Без contenttypes."""
    document    = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="links")
    entity_type = models.CharField(max_length=64, db_index=True)   # "contracts.contract"
    entity_id   = models.UUIDField(db_index=True)
    role        = models.CharField(max_length=32, blank=True)      # скан, оригинал, приложение

    class Meta:
        constraints = [UniqueConstraint(fields=["document", "entity_type", "entity_id", "role"],
                                        name="core_documents_link_uniq")]
        indexes = [models.Index(fields=["entity_type", "entity_id"])]
```

`DocumentType` — справочник: наименование, допустимые MIME-типы, максимальный размер,
требуется ли согласование, срок хранения.

`DocumentTemplate` — DOCX-шаблон: файл, описание ожидаемого контекста, к какому типу
документа относится.

### 2.2 Хранилище

Приватный бакет, публичного доступа нет. Выдача файла — только по временной подписанной
ссылке с ограниченным сроком (по умолчанию 15 минут, настройка `DOCUMENTS_URL_TTL`).

Локально MinIO, в облаке Yandex Object Storage, on-premise MinIO. Один и тот же код
через `django-storages`, различаются только настройки.

### 2.3 Версионирование

Новая версия не затирает предыдущую: создаётся новый `Document` с `version + 1`
и ссылкой `supersedes` на предыдущий. Старые версии остаются доступными и не удаляются.
Селектор `get_current_version(entity_type, entity_id, role)` возвращает последнюю.

### 2.4 Генерация

`docxtpl` рендерит DOCX из `DocumentTemplate`, конвертация в PDF — за одним интерфейсом
`render_to_pdf(html_or_docx) -> bytes`, чтобы движок (WeasyPrint или headless LibreOffice)
можно было заменить в одном месте.

### 2.5 Что не делает

Электронную подпись, ЭДО, распознавание, предпросмотр в браузере, полнотекстовый поиск
по содержимому. Всё это либо внешние сервисы, либо более поздние фазы.

### 2.6 Права доступа: целевая модель

`core.documents` не знает сущностей функциональных модулей (§1), поэтому не может сам
решить «виден ли этот скан пользователю» — договор загрузил менеджер, а увидеть скан
должны юрист на согласовании, финансист при оплате, снабженец при закупке по этому
договору. Правило «доступ у загрузившего или у администратора» — это не бизнес-правило,
а нижняя граница видимости на уровне самого `core.documents`.

**Целевая модель:** права на документ выводятся из прав на сущность, к которой он привязан.
«Кто может видеть договор — может видеть его сканы» реализуется через фасад
владеющего модуля: `core.documents` спрашивает «есть ли у пользователя доступ к
`contracts.contract` с таким `entity_id`», не зная, что такое договор. Практически —
владеющий модуль публикует в своём `facade.py` предикат наподобие
`has_access(user, entity_id) -> bool`, а вызывающий код (обычно API-эндпоинт самого
владеющего модуля, не `core.documents`) делает эту проверку сам и только потом идёт
в `documents.facade` за ссылкой или списком.

Внедрять это сейчас преждевременно: единственный потребитель `core.documents.rules.
can_download` на момент реализации — сам модуль documents, ни один функциональный модуль
ещё не подключён. Реализуется по факту первого реального потребителя (например, `contracts`
в Фазе 2), а не заранее — иначе предикат в Фазе 2 будут расширять костылями поверх
заглушки вместо того, чтобы заменить её на модель выше.

---

## 3. Согласования и делегирование · `core.approvals`

Самая сложная из пяти подсистем. Ею пользуются договоры, заявки на платёж, заявки
на закупку, табель, отпуска — то есть почти каждый модуль.

### 3.1 Маршрут

```python
class ApprovalRoute(models.Model):
    code        = models.CharField(max_length=64, unique=True)
    name        = models.CharField(max_length=255)
    entity_type = models.CharField(max_length=64)          # к чему применяется
    condition   = models.JSONField(default=dict, blank=True)  # когда применяется
    is_active   = models.BooleanField(default=True)


class ApprovalRouteStep(models.Model):
    route        = models.ForeignKey(ApprovalRoute, on_delete=models.CASCADE, related_name="steps")
    order        = models.PositiveSmallIntegerField()
    name         = models.CharField(max_length=128)
    mode         = models.CharField(max_length=16, choices=StepMode)   # последовательно / параллельно
    approver_kind = models.CharField(max_length=16, choices=ApproverKind)
    approver_role = models.CharField(max_length=64, blank=True)        # код группы
    approver_employee = models.UUIDField(null=True, blank=True)
    is_required  = models.BooleanField(default=True)
    sla_hours    = models.PositiveSmallIntegerField(null=True, blank=True)
```

`condition` — простое сравнение по полям объекта, передаваемым при запуске
(например, сумма договора больше порога). Полноценный язык правил не нужен: набор
условий «поле — оператор — значение», проверяемый в коде. Никакого `eval`.

### 3.2 Экземпляр согласования

```python
class ApprovalRequest(TimeStampedModel, UUIDPrimaryKeyModel):
    route       = models.ForeignKey(ApprovalRoute, on_delete=models.PROTECT)
    entity_type = models.CharField(max_length=64, db_index=True)
    entity_id   = models.UUIDField(db_index=True)
    status      = FSMField(default=ApprovalStatus.DRAFT)
    started_by  = models.UUIDField()
    started_at  = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)


class ApprovalStep(TimeStampedModel, UUIDPrimaryKeyModel):
    request      = models.ForeignKey(ApprovalRequest, on_delete=models.CASCADE, related_name="steps")
    order        = models.PositiveSmallIntegerField()
    name         = models.CharField(max_length=128)
    assignee     = models.UUIDField(db_index=True)          # Employee
    decided_by   = models.UUIDField(null=True, blank=True)  # кто РЕАЛЬНО решил
    delegation   = models.ForeignKey("approvals.Delegation", null=True, blank=True,
                                     on_delete=models.SET_NULL)
    decision     = models.CharField(max_length=16, choices=Decision, blank=True)
    comment      = models.TextField(blank=True)
    decided_at   = models.DateTimeField(null=True, blank=True)
    due_at       = models.DateTimeField(null=True, blank=True)
```

Различение `assignee` и `decided_by` обязательно: когда согласование авторизует платёж,
вопрос «кто на самом деле подписал» имеет юридическое значение. Если решение принято
по делегированию, `delegation` заполнен и связь прослеживается.

### 3.3 Статусы

```
DRAFT ──► IN_PROGRESS ──┬──► APPROVED
                        ├──► REJECTED
                        ├──► RETURNED ──► IN_PROGRESS   (пройденные шаги сбрасываются)
                        └──► WITHDRAWN
```

Возврат на доработку сбрасывает решения всех пройденных шагов: изменённый документ
согласуется заново с начала.

### 3.4 Делегирование полномочий

Механизм замещения. Основной сценарий — не увольнение, а **отпуск**: три-четыре недели
в год у каждого руководителя, и всё это время поток согласований стоит.

```python
class Delegation(TimeStampedModel, UUIDPrimaryKeyModel):
    from_employee = models.UUIDField(db_index=True)
    to_employee   = models.UUIDField(db_index=True)
    scope         = models.CharField(max_length=16, choices=DelegationScope)
    scope_value   = models.CharField(max_length=64, blank=True)   # код роли или UUID подразделения
    valid_from    = models.DateField()
    valid_to      = models.DateField()                            # ОБЯЗАТЕЛЬНО
    reason        = models.CharField(max_length=16, choices=DelegationReason)
    created_by    = models.UUIDField()
    revoked_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            CheckConstraint(condition=Q(valid_to__gte=F("valid_from")),
                            name="core_approvals_delegation_dates"),
            CheckConstraint(~Q(from_employee=F("to_employee")),
                            name="core_approvals_delegation_not_self"),
        ]
```

`scope`: все полномочия / конкретная роль / конкретное подразделение.
`reason`: отпуск / болезнь / командировка / вакансия.

**Четыре правила, без которых механизм становится дырой:**

1. **Срок обязателен**, открытого конца не бывает. Делегирование, которое никто
   не отменил, — постоянный второй комплект прав, о котором все забыли.
   Регламентная задача ежедневно докладывает об истекающих в ближайшую неделю
   и об истёкших.
2. **Цепочки запрещены.** А передал Б, Б передал В — В прав А не получает.
   Проверяется при создании.
3. **Передать можно только своё.** Полученное по делегированию дальше не передаётся.
4. **Создаёт только сам делегирующий или администратор.** Получатель — никогда.

Предикаты прав становятся делегирование-осведомлёнными **сразу**, при первой
реализации, а не переписываются потом:

```python
def effective_employee_ids(user, at: date | None = None) -> set[UUID]:
    """Свой Employee плюс те, чьи полномочия делегированы пользователю на дату."""
```

Каждое использование делегирования пишется в аудит: кто, за кого, по какому
делегированию, когда.

### 3.5 Сервисы

```python
def start_approval(entity_type: str, entity_id: UUID, context: dict, *, actor_id: UUID) -> ApprovalRequest
def approve_step(step_id: UUID, comment: str, *, actor_id: UUID) -> None
def reject_step(step_id: UUID, comment: str, *, actor_id: UUID) -> None
def return_for_revision(request_id: UUID, comment: str, *, actor_id: UUID) -> None
def withdraw(request_id: UUID, *, actor_id: UUID) -> None
def create_delegation(...) -> Delegation
def revoke_delegation(delegation_id: UUID, *, actor_id: UUID) -> None
```

### 3.6 События

`approvals.request.started`, `approvals.request.approved`, `approvals.request.rejected`,
`approvals.request.returned`, `approvals.step.overdue`, `approvals.delegation.created`,
`approvals.delegation.expiring`.

Модуль-инициатор подписывается на завершающие события и меняет статус своего объекта.
Обратных вызовов из `approvals` в модули нет.

---

## 4. Нумерация · `core.numbering`

```python
class Numerator(models.Model):
    code        = models.CharField(max_length=64, unique=True)
    template    = models.CharField(max_length=128)   # "ДГ-{year}-{seq:05d}"
    reset_period = models.CharField(max_length=16, choices=ResetPeriod)  # никогда/год/месяц
    legal_entity = models.ForeignKey("core_org.LegalEntity", null=True, blank=True,
                                     on_delete=models.CASCADE)


class NumeratorCounter(models.Model):
    numerator = models.ForeignKey(Numerator, on_delete=models.CASCADE, related_name="counters")
    period_key = models.CharField(max_length=16)   # "2026" или "2026-08"
    last_value = models.BigIntegerField(default=0)

    class Meta:
        constraints = [UniqueConstraint(fields=["numerator", "period_key"],
                                        name="core_numbering_counter_uniq")]
```

Выдача номера — `SELECT ... FOR UPDATE` по строке счётчика внутри транзакции вызывающего
сервиса. Последовательность PostgreSQL не подходит: она не откатывается при отмене
транзакции, а в нумерации договоров дырки объяснять бухгалтерии придётся дорого.

Плата за это — сериализация на строке счётчика. При реальных объёмах (десятки документов
в день) несущественно.

```python
def next_number(numerator_code: str, *, at: date | None = None) -> str
```

Вызывается **внутри** транзакции создания документа. Если транзакция откатится, номер
не будет израсходован.

---

## 5. Уведомления · `core.notifications`

```python
class NotificationTemplate(models.Model):
    code    = models.CharField(max_length=64, unique=True)
    subject = models.CharField(max_length=255)
    body    = models.TextField()          # Django-шаблон
    channel = models.CharField(max_length=16, choices=Channel)   # email / in_app


class Notification(TimeStampedModel, UUIDPrimaryKeyModel):
    recipient  = models.UUIDField(db_index=True)     # Employee
    template   = models.ForeignKey(NotificationTemplate, on_delete=models.PROTECT)
    context    = models.JSONField(default=dict)
    entity_type = models.CharField(max_length=64, blank=True)
    entity_id  = models.UUIDField(null=True, blank=True)
    is_read    = models.BooleanField(default=False)
    sent_at    = models.DateTimeField(null=True, blank=True)
    digest_key = models.CharField(max_length=64, blank=True, db_index=True)
```

**Дайджест вместо потока.** Однотипные уведомления группируются по `digest_key`
и отправляются одним письмом по расписанию. Без этого руководитель подразделения
получит двадцать писем за утро и через неделю заведёт фильтр в почте — после чего
подсистема уведомлений перестанет существовать функционально.

Настройки на пользователя: какие типы событий, каким каналом, немедленно или в дайджесте.

Отправка асинхронная, через Celery. `core.notifications` лежит выше `core.events`
в слоевом контракте, поэтому подписывается на события, а не вызывается из них напрямую.

---

## 6. Аудит · `core.audit`

`django-pghistory` — триггеры на уровне БД. Принципиальное отличие от библиотек,
работающих через сигналы Django: триггеры ловят `bulk_update`, `QuerySet.update()`,
изменения из админки и вообще любую запись, включая ту, что сделана в обход ORM.
Обойти аудит из Python невозможно.

Под аудитом: все модели `core.identity`, `core.org`, `core.accounts`, `core.approvals`,
плюс модели прикладных модулей, помеченные миксином.

### Актор

`actor_id` пробрасывается в контекст pghistory:

```python
with pghistory.context(actor_id=str(actor_id)):
    ...
```

Отсюда требование ко всем сервисам, меняющим состояние, принимать `actor_id: UUID`.
Это относится и к уже написанным сервисам `core.identity` — см. спецификацию ядра §5.1.
Причина, почему UUID, а не `User`: слоевой контракт, `identity` ниже `accounts`.

Просмотр истории объекта — в админке через инлайн, в API — отдельным эндпоинтом
`/api/v1/audit/{entity_type}/{entity_id}`.

---

## 7. Обязательные тесты

**Документы**

- файл загружается в хранилище и читается обратно
- ссылка временная и протухает по истечении TTL
- прямой публичный доступ к бакету закрыт
- нельзя скачать файл без прав
- документ привязывается к произвольной сущности без `contenttypes`
- новая версия не затирает предыдущую, `supersedes` заполнен
- файл недопустимого типа и превышающий размер отклоняются
- контрольная сумма совпадает после загрузки
- генерация DOCX из шаблона подставляет контекст
- `core.documents` не импортирует ни один функциональный модуль

**Согласования**

- последовательный маршрут проходит по шагам
- параллельный маршрут требует всех согласующих
- возврат на доработку сбрасывает пройденные шаги
- отклонение завершает согласование
- условие маршрута выбирает нужный маршрут по сумме
- согласование публикует события
- решение по делегированию заполняет `decided_by` и `delegation`

**Делегирование**

- делегирование даёт права на период и не даёт вне периода
- цепочка делегирований запрещена
- нельзя передать полученное по делегированию
- получатель не может создать делегирование себе
- нельзя делегировать самому себе (`CheckConstraint`)
- отозванное делегирование прав не даёт
- истёкшее делегирование попадает в отчёт

**Нумерация**

- **конкурентная выдача не даёт дублей** — 50 параллельных транзакций, 50 уникальных
  номеров. Ключевой тест, должен реально запускать параллельные транзакции
- откат транзакции не расходует номер
- счётчик сбрасывается в новом периоде
- нумераторы разных юрлиц независимы

**Уведомления**

- однотипные уведомления группируются в дайджест
- настройки пользователя учитываются
- уведомление не отправляется дважды

**Аудит**

- `pghistory` ловит `bulk_update`
- `pghistory` ловит изменение из админки
- актор доезжает до записи истории
- история не теряется при откате внешней транзакции

---

## 8. Открытые вопросы

1. **Срок хранения документов и удаление.** Хранить вечно проще всего, но объём растёт.
   Нужна ли политика архивации, и через сколько лет?
2. **Кто по умолчанию согласует, если у роли в подразделении никого нет.** Эскалация
   на уровень выше или блокировка запуска маршрута?
3. **SLA на шаг согласования** — только уведомление или автоматическая эскалация
   по истечении срока?
4. **Массовое делегирование на период отпусков.** Если в июле уезжает половина
   руководителей, заводить делегирования по одному неудобно. Нужен ли групповой ввод?
5. **Согласование в мобильном виде.** Руководитель в командировке — самый частый
   источник задержек. Отдельный упрощённый экран или хватит адаптивной вёрстки?
6. **Хранить ли документы прошлых версий в том же бакете** или переносить в холодное
   хранилище по истечении срока.
