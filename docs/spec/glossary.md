# Словарь терминов проекта

Единственный источник правды по именованию. Имена в коде — английские, интерфейс — русский.
**Если термина здесь нет — не выдумывай синоним, спроси и добавь сюда.**

Расхождения в именовании — самый дешёвый в предотвращении и самый дорогой в исправлении
класс проблем. Через год `Contractor`, `Counterparty`, `Vendor` и `Supplier` в разных модулях
означают одно и то же, и никто уже не помнит, какой из них настоящий.

---

## 1. Запрещённые синонимы

Слева — то, что модель порождает по умолчанию. Справа — единственно допустимое.

| Никогда | Только так | Почему |
|---|---|---|
| `Contractor`, `Counterparty`, `Supplier`, `Customer`, `Client` как отдельные модели | `Party` + профиль модуля | инвариант И5: одна идентичность, много профилей |
| `Nomenclature`, `Product`, `Material`, `Goods`, `Article` | `Item` + профиль модуля | то же |
| `OrgUnit`, `Division`, `Subdivision`, `Unit` | `Department` | |
| `Proposal`, `CommercialOffer`, `Offer` | `Quote` | |
| `TimeSheet` как первичный ввод | `WorkAllocation` — ввод, `TimesheetEntry` — производная | инвариант И7 |
| `Order` без уточнения | `PurchaseOrder` или `ProductionOrder` | «заказ» в системе два разных |
| `Document` для договора или счёта | `Document` — только файл; договор это `Contract` | |
| `Status` как свободная строка | `<Entity>Status(models.TextChoices)` | |

---

## 2. Ядро идентичности · `core.identity`

| Русский | Код | Примечание |
|---|---|---|
| Контрагент | `Party` | 7 полей, не расширять |
| Контактное лицо | `Contact` | |
| Номенклатура, позиция | `Item` | 6 полей, не расширять |
| Единица измерения | `UnitOfMeasure` | сокращение в коде `uom` |
| Профиль контрагента | `PartyProfile` (абстрактный) | |
| Профиль номенклатуры | `ItemProfile` (абстрактный) | |
| Схемо-свободные атрибуты | `attributes` (JSONB) | |
| Схема атрибутов | `AttributeSchema` | JSON Schema на категорию |
| Кандидат | `<X>Candidate` | до промоушена в ядро |
| Промоушен в ядро | `promote_to_party()` | |
| Поиск дубликатов | `find_duplicates()` | |

## 3. Организация и доступ · `core.org`, `core.accounts`

| Русский | Код |
|---|---|
| Юридическое лицо | `LegalEntity` |
| Подразделение | `Department` |
| ЦФО, центр финансовой ответственности | `CostCenter` |
| Должность | `Position` |
| Разряд, категория | `Grade` |
| Штатное расписание | `StaffingTable` |
| Штатная единица | `StaffUnit` |
| Сотрудник | `Employee` |
| Пользователь | `User` |
| Роль | `Role` |
| Технический директор (роль) | `TECHNICAL_DIRECTOR` |
| Коммерческий директор (роль) | `COMMERCIAL_DIRECTOR` |

## 4. Платформа · `core.*`

| Русский | Код |
|---|---|
| Документ, файл | `Document` |
| Привязка документа | `DocumentLink` |
| Шаблон документа | `DocumentTemplate` |
| Согласование (экземпляр) | `ApprovalRequest` |
| Маршрут согласования | `ApprovalRoute` |
| Шаг согласования | `ApprovalStep` |
| Нумератор | `Numerator` |
| Доменное событие | `DomainEvent` |
| Строка outbox | `OutboxEvent` |
| Обработанное событие | `ProcessedEvent` |
| Уведомление | `Notification` |

## 5. Коммерческий блок · `crm`

| Русский | Код |
|---|---|
| Лид | `Lead` |
| Источник лида | `LeadSource` |
| Сделка | `Deal` |
| Воронка | `Pipeline` |
| Стадия воронки | `PipelineStage` |
| Коммерческое предложение, КП | `Quote` |
| Позиция КП | `QuoteLine` |
| Версия КП | `QuoteVersion` |
| Активность (звонок, встреча, письмо) | `Activity` |
| Отрасль | `Industry` |
| Сегмент | `Segment` |
| Профиль заказчика | `CustomerProfile` |
| Коммерческая карточка позиции | `SalesItem` |

## 6. Договоры · `contracts`

| Русский | Код |
|---|---|
| Договор | `Contract` |
| Приложение к договору | `Annex` |
| Спецификация | `Specification` |
| Строка спецификации | `SpecificationLine` |
| Этап | `Stage` |
| График платежей | `PaymentSchedule` |
| Плановый платёж | `ScheduledPayment` |
| Счёт | `Invoice` |
| Акт выполненных работ | `Act` |
| УПД | `UniversalTransferDocument` |
| Дебиторская задолженность | `receivables` (селектор, не модель) |

## 7. Закупки и логистика · `procurement`

| Русский | Код |
|---|---|
| Поставщик (профиль) | `VendorProfile` |
| Кандидат в поставщики | `VendorCandidate` |
| Закупочная карточка позиции | `PurchaseItem` |
| Категория закупки | `PurchaseCategory` |
| Потребность | `Requirement` |
| Заявка на закупку | `PurchaseRequisition` |
| Запрос предложений, RFQ | `RequestForQuotation` |
| Предложение поставщика | `VendorQuote` |
| Заказ поставщику | `PurchaseOrder` |
| Приёмка | `GoodsReceipt` |
| Рекламация | `Claim` |
| История цен | `SupplierPriceHistory` |
| Снимок рынка по категории | `CategoryMarketSnapshot` |
| Аналог, взаимозаменяемость | `ItemAlternative` |
| Склад | `Warehouse` |
| Остаток | `StockBalance` |
| Резерв | `Reservation` |

## 8. Кадры: труд и рабочее время · `hr`

| Русский | Код |
|---|---|
| Производственный календарь | `ProductionCalendar` |
| День календаря | `CalendarDay` |
| Вид рабочего времени | `TimeType` |
| **Разноска (первичный ввод)** | **`WorkAllocation`** |
| Объект отнесения затрат | `CostObject` |
| Период табеля | `TimesheetPeriod` |
| Строка табеля (производная) | `TimesheetEntry` |
| Плановая ставка по должности | `PositionRate` |
| Ставка себестоимости сотрудника | `EmployeeCostRate` |
| Пакет обмена с 1С | `ExchangePackage` |

## 9. Кадры: персонал · `hr`

| Русский | Код |
|---|---|
| Допуск, квалификация | `Competency` |
| Вид допуска | `CompetencyKind` |
| Аттестация | `Certification` |
| Отсутствие | `Absence` |
| Командировка | `BusinessTrip` |
| Кадровое событие | `PersonnelEvent` |
| Обучение | `Training` |

## 10. Финансы · `finance`

| Русский | Код | Примечание |
|---|---|---|
| БДДС | `CashFlowBudget` | |
| БДР | `IncomeExpenseBudget` | |
| Статья ДДС | `CashFlowItem` | классификатор движения денег |
| Статья затрат | `ExpenseItem` | классификатор расходов |
| Учётный профиль номенклатуры | `AccountingItemProfile` | ОКПД2, НДС, статья затрат |
| Платёжный календарь | `PaymentCalendar` | |
| Заявка на платёж | `PaymentRequest` | |
| Реестр на оплату | `PaymentRegistry` | |
| Лимит | `Limit` | |
| Банковская выписка | `BankStatement` | |
| Финансовый профиль контрагента | `CounterpartyProfile` | |
| Себестоимость | `cost_amount` | поле, не модель |
| Маржа | `margin` | вычисляется, не хранится |

> Не путать `ExpenseItem` (статья затрат — аналитика) и `AccountingItemProfile`
> (учётные атрибуты позиции номенклатуры). Первое — классификатор, второе — профиль.

## 11. Проекты · `projects`

| Русский | Код |
|---|---|
| Проект | `Project` |
| ИСР, WBS | `WbsNode` |
| Веха | `Milestone` |
| Задача | `Task` |
| Риск | `Risk` |
| Запрос на изменение | `ChangeRequest` |
| Освоенный объём | `earned_value` |
| Процент готовности | `completion_percent` |

## 12. Производство и ОТК · `production`

| Русский | Код |
|---|---|
| Производственный заказ | `ProductionOrder` |
| Маршрутная карта | `Routing` |
| Операция | `Operation` |
| Рабочий центр | `WorkCenter` |
| Сменное задание | `ShiftTask` |
| Технологический профиль позиции | `TechItem` |
| План контроля | `InspectionPlan` |
| Результат контроля | `InspectionResult` |
| Несоответствие | `Nonconformity` |
| Корректирующее действие | `CorrectiveAction` |
| Паспорт изделия | `ProductPassport` |
| Прослеживаемость | `traceability` |

## 13. Маркетинг и OSINT · `intelligence`

| Русский | Код |
|---|---|
| Источник | `Source` |
| Находка | `Finding` |
| Конкурент | `Competitor` |
| Снимок рынка | `MarketSnapshot` |
| Дайджест | `Digest` |

---

## 14. Конвенции именования

**Модели** — единственное число, CamelCase: `Party`, `PurchaseOrder`, `WorkAllocation`.

**Таблицы** — автоматически из метки приложения: `core_identity_party`, `procurement_purchaseorder`.
Вручную `db_table` не задаём.

**Статусы** — `TextChoices` с именем `<Entity>Status`: `ContractStatus`, `PeriodStatus`.
Строковых литералов статуса в коде быть не должно.

**Сервисы** — функции, глагол в инфинитиве: `create_party`, `approve_requisition`,
`rebuild_entries`. Не `PartyService.create()`.

**Селекторы** — `get_*` (одна запись или None), `list_*` (набор), `count_*`, `exists_*`.

**Фасады** — короткое имя операции без префикса модуля: `procurement.get_vendor_summary()`,
а не `procurement.get_procurement_vendor_summary()`.

**Предикаты прав** (`rules.py`) — `is_*` только для принадлежности к роли, существующей
как Django `Group`: `is_procurement_officer`, `is_sales_manager`. Полномочие — право
на конкретное действие, не роль — называется `can_*` по имени проверяемого права:
`can_manage_costing_reference`, `can_force_create_party`. Путать шаблоны нельзя: имя
предиката обязано говорить, что он проверяет, а не создавать видимость роли, которой
в системе нет (прецедент — `is_data_administrator` в `procurement.rules`, проверявший
`core_identity.force_create_party`; переименован в `can_force_create_party`, см.
спецификация CRM ИС (IS_ERP, 10-crm) §6).

**События** — `<модуль>.<сущность>_<действие в прошедшем времени>` (`docs/events.md` —
публичный контракт, здесь только повтор формата, а не второй источник правды):
`contracts.contract_signed`, `hr.timesheet_period_approved`, `procurement.vendor_approved`.

**Профили** — `<Роль>Profile` для контрагента, `<Роль>Item` для номенклатуры:
`VendorProfile`, `CustomerProfile`, `PurchaseItem`, `SalesItem`, `TechItem`.

**Схемы API** — `<Entity>In`, `<Entity>Out`, `<Entity>ListItem`, `<Entity>Filter`.

**DTO между модулями** — `<Entity>DTO` или `<Entity>SummaryDTO`.

**Поля:**

| Тип | Шаблон | Пример |
|---|---|---|
| Булево | `is_*`, `has_*`, `needs_*` | `is_approved`, `has_vat` |
| Момент времени | `*_at` | `created_at`, `approved_at`, `sent_at` |
| Дата | `*_date`, `valid_from`, `valid_to` | `issue_date`, `valid_until` |
| Деньги | `*_amount`, `*_price` | `cost_amount`, `unit_price` |
| Ставка за единицу | `*_rate` | `cost_rate`, `vat_rate` |
| Количество | `*_qty` | `ordered_qty`, `received_qty` |
| Часы | `hours` | |
| Доля, процент | `*_share` (0..1), `*_percent` (0..100) | `cost_share`, `completion_percent` |
| Ссылка на сущность другого модуля | `*_id` (UUID без FK) | `project_id`, `contract_id`, `entity_id` |
| Актор совершённого действия | `*_by` (UUID без FK) | `created_by`, `uploaded_by`, `started_by`, `decided_by`, `rejected_by` |
| Назначенное лицо в роли | имя роли, без суффикса (UUID без FK) | `assignee`, `approver` |

Три разных смысла, три разных шаблона — путать их означает терять информацию:

- **`*_id`** — ссылка на сущность: что произошло, к чему это относится
  (`project_id`, `contract_id`, `entity_id` из пары `entity_type`/`entity_id`).
- **`*_by`** — актор совершённого действия: кто это сделал, факт свершившийся
  и неизменный (`ApprovalStep.decided_by`, `Document.uploaded_by`,
  `Delegation.created_by`).
- **Имя роли без суффикса** — назначенное лицо: кем именно кто-то *приходится*
  структуре, до и независимо от того, произошло ли действие
  (`ApprovalRouteStep.assignee`/`ApprovalStep.assignee` — назначенный
  согласующий, который ещё может ничего не решить или делегировать своё право
  другому; сравните с `ApprovalStep.decided_by` — кто решил *фактически*,
  возможно, не тот же человек, если решение принято по делегированию).

Все три — «голый» `UUIDField` без `ForeignKey`, если сущность, актор или назначенное
лицо находятся в другом модуле (см. §1 и `docs/spec/03-platforma.md` §1 про запрет
FK/GFK между этими подсистемами и функциональными модулями). Не `*_by_id`, не
`actor_id`, не `assignee_id` — суффикс `_id` в этих трёх шаблонах не добавляется:
он зарезервирован за первым, за ссылкой на сущность.

**`aggregate_id` (`core.events.OutboxEvent`) — отдельное понятие, не трогать
и не унифицировать с `*_id` выше.** Термин из DDD: идентификатор агрегата, о
котором рассказывает событие. У него нет парного поля типа (`aggregate_type`),
потому что `event_type` самого `OutboxEvent` уже кодирует, о какой сущности идёт
речь (`"approvals.approval_started"` однозначно про `ApprovalRequest`) — заводить
второе поле было бы дублированием. Это осознанное отличие от пары
`entity_type`/`entity_id`, а не непоследовательность, которую надо когда-нибудь
«причесать».

**Русские названия** — `verbose_name` у каждого поля и модели, `verbose_name_plural`
у каждой модели. Без этого админка нечитаема.

---

## 15. Как пополнять

Новый термин добавляется в словарь **до** того, как появится в коде. Если во время
работы обнаружился термин, которого здесь нет, — остановись, предложи имя, дождись
подтверждения, впиши сюда, и только потом пиши код.
