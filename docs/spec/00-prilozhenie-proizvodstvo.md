# Спецификация: приложение «НПК Производство»

**Статус:** черновик агента по поручению заказчика от 06.11.2026 («отдельное приложение по
прототипу на стеке ИС, весь функционал в одном»). Правит заказчик (CLAUDE.md §7).
**Источник требований:** прототип «Производство» (HTML-артефакт, редакция v9). Прототип —
иллюстрация, источник истины — этот документ.
**Отношение к ИС:** автономное приложение по правилам ИС (CLAUDE.md, инварианты И1–И7,
структура модуля). Ядро (`src/core`) скопировано из ИС без функциональных изменений, модули
построены так, чтобы позже переехать в ИС модулями (`sales` → `crm`, `production`,
`supply` → `procurement`, `timesheet` → `hr` и т. д.).

---

## 1. Состав модулей

| Модуль | Что делает | Экраны |
|---|---|---|
| `sales` | заявка на просчёт, калькуляция, предварительный план, этапы «Новые / Просчёт / Согласование КП» с визами | доска (левая часть), карточка заявки |
| `production` | участки, шаблоны изделий, производственный заказ, этапы «Запуск / Подготовка / Изготовление / ОТК / Отгружено» с визами, операции, связи, критический путь, ход выполнения, освоение, документы, журнал | доска (правая часть), карточка заказа, Гант всех заказов, «Мои визы», загрузка участков |
| `quality` | точки контроля участков, записи контроля операций, брак, причины, статистика | вкладка контроля в операции, экран «Качество» |
| `supply` | потребность в материалах, инструменте, оснастке и расходниках, заявки в закупку, статусы до выдачи в цех, поставщики | вкладки «Материалы», «Оснастка и расходники» заказа, экран «Закупки и склад» |
| `timesheet` | профили работников, разноска часов по заказам и операциям, табель месяца, проверки, согласование, пакеты в 1С | экран «Табель» |
| `equipment` | оборудование, наработка по дням, простои, ТО по моточасам, аварии и ремонты с трудозатратами | экран «Оборудование» |
| `energy` | ресурсы, тарифы, счётчики-дерево, получасовые интервалы, баланс, удельный расход | экран «Энергоучёт» |
| `analytics` | недельные отсечки, загрузка 10 недель, портфель и загрузка по месяцам, выработка сотрудников в часах и рублях, сквозная команда демо-данных | экраны «Отсечки», «Портфель», «Сотрудники» |

Ядро (`src/core`): `accounts`, `org`, `identity`, `documents`, `events`, `numbering`,
`notifications`, `audit`, `common`. Чистые функции графика — `src/core/common/scheduling.py`
(нужны `sales`, `production`, `analytics`; в ядре, потому что функциональный модуль не
может импортировать чужие внутренности).

Границы приложения (CLAUDE.md §1) в силе: бухгалтерия, зарплата, ЭДО — в 1С. Табель
отдаётся в 1С пакетами, расчёт оплаты не делается.

---

## 2. Общие понятия

### 2.1 Рабочие дни и график

- Рабочие дни — пн–пт, праздников нет (производственный календарь — вне объёма, как в ИС
  ADR 0031, решение 7).
- `core.common.scheduling`: `add_working_days`, `working_days_between`, `next_working_day`,
  `compute_schedule` (прямой и обратный проход, резерв, критичность), `find_cycle`.
- **Длительность операции** = `max(1, ceil(трудоёмкость / (8 × исполнителей)))` рабочих
  дней; для снабженческой операции (участок с признаком `is_supply`) трудоёмкость — это
  срок поставки в днях, длительность = `max(1, round(дни))`.
- **Плановое начало операции** выводится прямым проходом: не раньше начала заказа, не раньше
  окончания всех предшественников, не раньше ограничения «не ранее» (`not_before`). Начатая
  операция стоит по факту. В заказе в работе не начатая операция не планируется раньше
  сегодняшнего дня.
- Даты начала операций **хранятся** (`planned_start`) и пересчитываются сервисом
  `reschedule(order)` при любой правке графика — Гант читает их, а не считает на лету.
  Это отступление от ИС 8а (там даты выводились), принятое потому, что здесь операцию
  двигают мышью: перенос записывается как `not_before`, а `planned_start` — результат
  пересчёта (ADR 0001 приложения).
- Критический путь, резерв и признак нарушения связи — селектор, не хранится.

### 2.2 Деньги и количества

`Decimal` везде (И6). Деньги — `MoneyField` (18,4) ядра. Часы — `DecimalField(10,2)`.
Количества — `DecimalField(12,3)`. Проценты — `DecimalField(5,2)`.

### 2.3 Визы

«Виза» — статусный переход с отметкой «кто и когда» (`*_by`, `*_at`), а не маршрут
согласования (ИС ADR 0031, решение 2). Ставит ответственный за этап или операцию;
начальник производства может поставить визу за любого (замещение) — с отметкой, что за
кого.

---

## 3. Модули

### 3.1 `production`

#### Справочники

**`WorkCenter`** — участок: `code` (уник.), `short_name` (≤8), `name`, `hourly_rate`
(Money, ставка нормо-часа для калькуляции и выработки), `capacity` (исполнителей,
PositiveSmallInteger), `responsible` (FK Employee, null), `phase` (`WorkPhase`: `prep`
подготовка / `prod` изготовление / `qc` ОТК), `is_supply` (bool — «Снабжение»: трудоёмкость
это срок поставки, в часы и загрузку не входит), `order` (сортировка), `is_active`.
Демо-данные — 12 участков прототипа (КО, ТП, Снаб, Лист, Мех, Свар, Покр, СбОб, СбШк, ЭМ,
Прог, ОТК) со ставками и мощностями оттуда.

**`ProductTemplate`** — тип изделия: `code` (ШУ, НКУ, ВРУ, ШОТ, РЗА, МЕХ, ЛИСТ, ОБОР),
`name`, `is_active`. **`TemplateMaterial`**: `template`, `name`, `qty_per_unit`, `price`,
`order`. **`TemplateOperation`**: `template`, `seq`, `name`, `work_center`, `hours`,
`scales_with_qty` (bool — трудоёмкость × количество), `people` (≥1), `order`.
**`TemplateOperationDependency`**: `predecessor`, `successor` (обе одного шаблона —
триггер). Демо — 8 шаблонов прототипа целиком.

#### Производственный заказ

**`ProductionOrder`**: `number` (нумератор `production.order`, `ПЗ-{year}-{seq:04d}`),
`inquiry_id` (UUID, уник., null), `inquiry_number`, `customer_name` (копия из заявки),
`customer_id` (UUID Party, null), `object_name`, `product_name`, `template_id` (FK ProductTemplate, null),
`quantity`, `manager` (FK Employee), `planned_start` (дата запуска), `due_date`,
`stage` (`OrderStage`: `launch` / `prep` / `prod` / `qc` / `done`, FSM protected),
`contract_total` (Money — итог калькуляции с НДС на момент запуска, для портфеля),
`labor_cost_planned` (Money — копия), `shipped_at`.

**`OrderStageApproval`** (виза этапа): `order`, `stage`, `responsible` (FK Employee),
`approved_by` (FK Employee, null), `approved_at`, `comment`. Уникальность (`order`, `stage`).
Ответственные по умолчанию: launch, prod — начальник производства (руководитель участка
с ролью); prep — технолог; qc — инженер ОТК; done — менеджер заказа. Берутся из
`ProductionSettings` (singleton, FK на сотрудников, правится в админке).

Переходы этапов (`move_order_stage(order, to, comment)`), правила прототипа:
- только на соседний этап; вперёд — после визы текущего этапа (если её нет и пользователь —
  ответственный, сервис ставит визу и переводит в одной транзакции; иначе ошибка
  «нужна виза ответственного»);
- `prep → prod`: все операции фазы `prep` выполнены и **есть хотя бы один документ вида
  КД или Чертёж** (правило прототипа «подготовка не закрывается без КД»);
- `prod → qc`: все операции, кроме фазы `qc`, выполнены;
- `qc → done`: все операции выполнены; ставится `shipped_at`;
- назад — на один этап, причина обязательна, виза целевого этапа снимается;
- из заказа в заявку вернуться нельзя.
Событие `production.order_stage_changed` (v1: `from_stage`, `to_stage`).

Кроме ручного перехода есть **выведенный этап** (`derived_stage` в селекторе): по
состоянию операций, как `deriveStage` прототипа, — подсказка на доске «можно переводить».

#### Операции

**`Operation`**: `order`, `seq`, `name`, `work_center`, `hours` (н-ч; для снабжения — дни),
`people` (1…capacity участка), `responsible` (FK Employee), `not_before` (дата, null),
`planned_start` (дата, null — выводится), `status` (`OperationStatus`: `wait` ожидает /
`work` в работе / `check` на визе / `done` выполнено; FSM protected), `progress`
(0–100, шаг 10), `started_at/by`, `approved_at/by` (виза), `approved_for` (если поставил
начальник за ответственного).
**`OperationDependency`**: `predecessor`, `successor`, без задержки (в прототипе её нет);
ограничения — как в ИС 8а: не сама с собой, уникальная пара, один заказ (триггер), без
циклов (сервис).
**`OperationEarning`** (освоение): `operation`, `date`, `hours` (может быть отрицательным
при откате прогресса). Сумма по операции = `hours × progress/100`. Пишется сервисом при
каждом изменении прогресса (`earnOp` прототипа): Δ = `hours × (новый − старый)/100`.
Снабженческие операции не осваивают часов.

Правила (прототип `opDialog`, `opVisa`, `autoStart`):
- статус `wait → work` — вручную или **автостарт**: при визе предшественника все
  операции, у которых закрыты предшественники и наступила плановая дата, переходят
  в `work` с записью в журнал «система»;
- `work`: прогресс 0…100; при 100 → `check` («передано на визу»);
- виза (`approve_operation`) — только ответственный (или начальник производства за него),
  все предшественники `done`, **есть запись контроля, если у участка есть точка
  контроля** (`quality.facade.has_inspection(operation_id)`); ставит прогресс 100,
  дописывает освоение, `done`;
- откат статуса до `wait` обнуляет прогресс и сторнирует освоение;
- правка `people` (≤ мощности участка), `not_before` — только у `wait`; затем `reschedule`;
- перенос на Ганте: операции — `not_before := новая дата`, если раньше нельзя из-за
  предшественника — ошибка с названием мешающей операции; всего заказа — сдвиг
  `planned_start` заказа и всех `not_before` не начатых операций на Δ рабочих дней.

#### Документы

Через `core.documents`: `DocumentLink(entity_type="production.order" | "production.operation")`.
Вид документа (`DocumentType` ядра): КД, Чертёж, ТЗ / опросный лист, Спецификация,
Техпроцесс, УП ЧПУ, Прочее — засеиваются миграцией. Утверждение документа в производство
(`DocumentRelease`: `document_id`, `order`, `operation` null, `approved_by`, `approved_at`).
Аннулирование документа — `core.documents` (если нет — флаг `is_annulled` в
`DocumentRelease` не заводится; аннулированный — это снятый `DocumentLink`).

#### Журнал

**`OrderJournalEntry`** — хранимая лента (в отличие от ИС 8а), потому что прототип пишет
в журнал события других модулей (закупка, контроль) и системные записи: `order`,
`operation` (null), `stage` (null), `kind` (`JournalKind`: `stage` / `visa` / `status` /
`plan` / `comment` / `qc` / `proc` / `doc`), `author` (FK Employee, null — «система»),
`text`, `created_at`. Пишут сервисы `production` в той же транзакции; `quality` и `supply`
пишут через `production.facade.add_journal_entry(...)` — синхронный вызов фасада в своей
транзакции (И4 соблюдён: одна транзакция БД). Комментарий пользователя — `kind=comment`.

#### Фасад `production.facade`

```python
list_work_centers() -> list[WorkCenterBrief]          # id, code, short_name, name, rate, capacity, phase, is_supply, responsible_id
get_work_center(id) -> WorkCenterBrief | None
get_template(code_or_id) -> TemplateBrief | None      # материалы и операции со связями (индексы)
create_order_from_inquiry(data: LaunchData, *, actor_id) -> UUID   # вызывает sales при запуске
get_orders_brief(ids) -> dict[UUID, OrderBrief]        # number, product, customer, stage, manager_id, due, planned_finish
list_active_orders() -> list[OrderBrief]               # stage != done
get_operations_brief(ids) -> dict[UUID, OperationBrief]  # order_id, seq, name, wc, status, responsible_id, planned_start/finish, hours, people
list_order_operations(order_id) -> list[OperationBrief]
list_planned_operations(work_center_id, day) -> list[OperationBrief]   # для «заполнить по плану» в табеле
list_earnings(date_from, date_to) -> list[EarningRow]  # operation_id, order_id, work_center_id, date, hours
add_journal_entry(order_id, kind, text, *, operation_id=None, author_employee_id=None) -> None
order_has_kd(order_id) -> bool
seed_demo() -> None
```

### 3.2 `sales`

**`Inquiry`** — заявка: `number` (нумератор `sales.inquiry`, `З-{seq:04d}`),
`customer_id` (UUID `Party` ядра; выбирается или создаётся через
`core.identity.services.create_party`), `customer_name` (копия для отображения),
`object_name`, `template_id` (UUID шаблона изделия `production`, null), `product_name`,
`quantity`, `due_date`, `manager` (FK Employee), `stage` (`InquiryStage`: `new` / `calc` /
`approval` / `launched` / `lost`), `planned_start` (предварительный старт для плана),
`overhead_pct` (25), `margin_pct` (20), `vat_pct` (22), `order_id` (UUID, null — после
запуска), `lost_reason` (FK справочника `LossReason`, null) и `lost_comment`.
**`InquiryStageApproval`** — как у заказа, этапы `new`, `calc`, `approval`;
ответственные: new и approval — менеджер, calc — экономист из `SalesSettings`.

**Калькуляция**: **`CalcMaterial`** (`inquiry`, `name`, `quantity`, `price`, `order`),
**`CalcOperation`** (`inquiry`, `seq`, `name`, `work_center_id` UUID, `hours`, `people`,
`not_before`, `planned_start`), **`CalcOperationDependency`**. «Заполнить из шаблона» —
по `production.facade.get_template`, количество × `quantity`, трудоёмкость × `quantity`
если `scales_with_qty`.

Итоги (`sales/calculations.py`, чистые функции, как `calcTotals` прототипа):
материалы = Σ кол × цена; труд = Σ часы × ставка участка (снабжение 0); часы = Σ часы
(без снабжения); накладные = труд × overhead%; себестоимость = мат + труд + накладные;
цена = себестоимость × (1 + margin%); НДС = цена × vat%; итог = цена + НДС;
прибыль = цена − себестоимость. Округление — только при выводе, хранится 4 знака.

Этапы (правила прототипа `checkMove`): по порядку, назад на один с причиной;
`calc → approval` — есть калькуляция (материалы или операции) и **есть план** (у всех
операций есть `planned_start`); вперёд — после визы текущего этапа.
**Запуск** (`approval → launched`): действие начальника производства «Запуск в работу»
с датой запуска и сроком; `sales.services.launch_inquiry` в одной транзакции вызывает
`production.facade.create_order_from_inquiry` (копия операций со связями, материалов —
в потребность `supply` через событие), ставит `order_id`, `stage=launched`, публикует
`sales.inquiry_launched`. Предупреждение, если нет КД (не блокирует).
Проигрыш — `lost` с причиной.

Предварительный план заявки и «Не укладываемся на N дн.» — селектор по
`core.common.scheduling` (как `health()` прототипа).

Вероятности этапов для портфеля (`SalesSettings`: `prob_new`, `prob_calc`,
`prob_approval`, по умолчанию 10/30/60 %).

**Фасад:** `get_inquiries_brief`, `list_open_inquiries()` (для портфеля и загрузки:
итог, этап, вероятность, операции плана с датами и часами, участками), `seed_demo()`.

### 3.3 `quality`

**`InspectionPoint`** — точка контроля участка: `work_center_id` (UUID, уник.), `name`
(«Контроль допусков (размеры, шероховатость)» и т. п.), `is_final` (финальный контроль),
`is_active`. **`DefectType`**: `inspection_point`, `name`. **`DefectCause`** —
справочник причин (Оператор, Оборудование, Материал / комплектующие, КД / УП ЧПУ,
Технология, Прочее). Демо — 9 точек прототипа (QCP) с видами дефектов.

**`InspectionRecord`**: `operation_id`, `order_id`, `work_center_id` (UUID, копия для
отчётов), `date`, `inspector` (FK Employee), `checked` (>0), `rework` (≥0), `scrap` (≥0),
`defect_type` (FK, null), `cause` (FK, null), `comment`. Ограничения: `rework + scrap ≤
checked`; при `rework + scrap > 0` обязательны вид дефекта и причина (CheckConstraint).
Записывать — после запуска заказа (этап ≥ prep) или для входного контроля снабжения;
право — инженер ОТК, мастер, ответственный за операцию. Пишет запись журнала заказа через
`production.facade.add_journal_entry(kind="qc")`. При `scrap > 0` ответ API содержит
предупреждение «нужно повторное изготовление».

Отчёты (селекторы): по участку и неделе — проверено, брак, %, доработка/списание;
Парето по причинам и видам дефектов; динамика 12 недель; доля брака по вине оператора
(для выработки сотрудника).

**Фасад:** `has_inspection(operation_id) -> bool`, `requires_inspection(work_center_id)
-> bool`, `get_qc_by_operation(ids) -> dict[UUID, QcAgg]`, `list_qc_by_week(from, to)`,
`seed_demo()`.

### 3.4 `supply`

**`Supplier`** — справочник поставщиков (имя; позже — профиль поверх `Party`).
**`PurchaseLine`** — строка потребности: `order_id` (UUID, null — заявка «на склад / ТО»),
`operation_id` (UUID, null), `kind` (`mat` материал / `tool` оснастка, инструмент,
расходники), `category` (`LineCategory`: Материал, Инструмент, Оснастка, Расходники),
`name`, `quantity`, `unit`, `price`, `need_date`, `status` (`LineStatus`: `draft`
черновик / `sent` передано в закупку / `ordered` заказано / `received` принято на склад /
`reserved` резерв со склада / `issued` передано в производство; FSM), `requisition_no`
(ЗЗ-{year}-{seq:04d}, присваивается при передаче в закупку, одна заявка на пачку строк),
`supplier` (FK, null), `po_number` (ЗП-…), `eta`, `received_at`, `received_qty`,
`storage_place`, `issued_at`, `issued_to` (FK Employee), `created_by`.
**`PurchaseLineEvent`** — история строки (кто, когда, что) — нужна на экране; хранится
отдельно, т. к. pghistory не даёт текста действия.

Переходы и роли (прототип `prAction`): `draft → sent` (кто угодно из производства/ПМ —
формирует номер заявки на группу строк); `sent → ordered` — снабженец, обязательны
поставщик и срок поставки, номер заказа поставщику; `ordered → received` — склад
(начальник склада или начальник производства), фактическое количество и место;
`sent → reserved` — склад, «есть на складе»; `received/reserved → issued` — склад, кому
выдано. Каждое действие пишет журнал заказа через `production.facade.add_journal_entry`.

Генерация потребности: обработчик `production.order_launched` создаёт черновики строк
материалов (из материалов калькуляции, `need_date` = окончание снабженческой операции)
и оснастки/расходников по `ToolTemplate` участков операций (`ToolTemplate`:
`work_center_id`, `category`, `name`, `quantity`, `unit`, `price`; расходники × ceil(qty/5)),
`need_date` = старт операции − 2 рабочих дня. Идемпотентно по `order_id`.

Опоздание строки (селектор, `prLate`): если не выполнена — дней между `need_date` и
`max(eta, сегодня)`.

**Фасад:** `list_lines_by_operation(ids)`, `get_order_supply_status(order_id)`, `seed_demo()`.

### 3.5 `timesheet`

**`WorkerProfile`** (расширение `Employee` 1:1, PK = FK на `Employee`): `personnel_no`
(табельный, уник.), `work_center_id` (UUID, null), `hourly_rate` (Money).
**`TimeCode`** — справочник кодов (Я, РВ, С, К, ВП, ОТ, Б, ДО, ПР, НН) с признаками
`is_work`, `is_allocatable`, `cost_multiplier` (С — 1,5; РВ — 2; прочие 1).
**`WorkAllocation`** — разноска (первичный ввод, И7): `employee` (FK), `date`,
`time_code`, `target` (`AllocationTarget`: `order` / `overhead` накладные / `repair`
ремонт и ТО / `training` обучение / `idle` простой), `order_id`, `operation_id` (UUID,
null), `hours` (>0, ≤24 в сумме за день — проверка), `source` (`manual` / `plan` / `repair`),
`source_ref` (номер ремонта и т. п.).
**`TimesheetPeriod`** — табель подразделения (`core.org.Department`) за месяц:
`department`, `month` (первое число), `status` (`draft` / `on_review` / `approved` /
`sent` / `closed` / `reopened`), `version`, журнал переходов `TimesheetPeriodEvent`.
Правка разноски — только в `draft`/`reopened`. **Свод табеля — производная** разноски
(И7): селектор, хранимого `TimesheetEntry` нет.

Проверки (`tsChecks`): не закрытые рабочие дни, > 24 ч в день, часы сверх нормы без «С»/
«РВ», > 50 % на накладные у рабочего. Блокирующие проверки не дают отправить на
согласование.
Согласование — экономист (роль `экономист-сметчик`); перед ним — визы менеджеров по своим
заказам (часы по заказам каждого менеджера, `mgrHours`) — хранятся в `TimesheetPeriodEvent`.
**Пакеты в 1С** (`buildPackages`): JSON `timesheet` (табельный, дата, код, часы) и
`cost_allocation` (табельный, аналитика — номер заказа / OVH-<код> / REP-<код> / TRN /
IDLE, часы, доля); статус `sent`, версия +1 при переоткрытии. Обмен — файлом
(скачать), как в ИС ADR 0002; транспорт в 1С вне объёма.

«Заполнить по плану» (`autoFillDay`): для работника с участком — операции участка на день
(`production.facade.list_planned_operations`), 8 ч делятся поровну, остаток — накладные.

Обработчик `equipment.repair_closed`: часы работников ремонта → разноска `target=repair`
на дату ремонта (вытесняя накладные/простой того же дня, как `repToTimesheet`), если
период открыт; иначе — уведомление начальнику производства.

**Фасад:** `get_worker_profiles()`, `list_allocations(from, to)` (для выработки),
`worked_hours_by_work_center(from, to)`, `actual_by_order(ids)` (часы и стоимость),
`seed_demo()`.

### 3.6 `equipment`

**`Equipment`**: `inventory_no` (уник.), `name`, `work_center_id` (UUID, null),
`control_system`, `connection` (способ подключения), `status` (`run` / `idle` / `to` /
`repair` — текущее состояние, ставит сервис), `operating_hours_initial`.
**`RuntimeLog`** — сутки: `equipment`, `date` (уник. пара), `run`, `setup`, `idle`,
`down` (часы), `idle_reason` (FK `IdleReason`), `down_reason` (FK `DownReason`), `source`
(`manual` / `scada`). Сумма ≤ 24. Наработка (моточасы) = начальная + Σ `run`.
**`MaintenanceType`**: `equipment`, `code` (ТО-1, ТО-2), `interval_hours`, `scope`.
**`MaintenanceRecord`**: `maintenance_type`, `date`, `at_hours`, `performed_by`.
Следующее ТО **выводится**: `(last.at_hours или 0) + interval`, остаток, прогноз даты по
средней наработке за 20 дней, цвет (просрочено / < 10 % / норма).
**`Repair`** — авария, плановый ремонт или ТО: `number` (`АР-{seq:04d}`), `equipment`,
`kind` (`fail` / `repair` / `maintenance`), `started_at`, `finished_at`, `category`
(`FailureCategory` справочник: Механика, Гидравлика, Электрика, Электроника / ЧПУ,
Пневматика, Износ оснастки), `alarm_code`, `description`, `fix`, `parts`, `status`
(`open` / `work` / `done`), `RepairWorker` (`employee`, `hours`). Простой =
`finished − started`; трудозатраты = Σ часов; стоимость = Σ часы × ставка работника
(через `timesheet.facade`). Закрытие (`done`) публикует `equipment.repair_closed`
(v1: `equipment_id`, `date`, `workers: [{employee_id, hours}]`, `number`) и для
`kind=maintenance` создаёт `MaintenanceRecord`.

Недельная сводка (`machWeek`): работа, наладка, простой, отказ, коэффициент загрузки
`run / (дней × 8)`; Парето простоев по причинам.

**Фасад:** `list_equipment()`, `get_runtime(from, to)`, `seed_demo()`.

### 3.7 `energy`

**`EnergyResource`** (электроэнергия кВт·ч, газ м³, сжатый воздух м³, азот м³,
тепло Гкал, вода м³) с `tariff` (Money за единицу, история — `TariffPeriod`).
**`Meter`**: `code` (уник.), `name`, `resource`, `parent` (FK self, дерево), `kind`
(`input` ввод / `node` узел / `shop` цех / `equipment` / прочие), `equipment_id` (UUID,
null), `source` (`scada` / `manual`). **`MeterInterval`** — получасовой интервал:
`meter`, `start` (TIMESTAMPTZ, кратно 30 мин, уник. пара), `value` (Decimal), `source`.
Ручной ввод — показания (`MeterReading`: `meter`, `taken_at`, `value`), расход между
показаниями. Приём от SCADA — эндпоинт `POST /api/v1/energy/intervals` (JSON по формату
предложения «SCADA и энергоучёт»: `schema_version`, `source_id`, `message_id`, массив
интервалов; идемпотентно по `message_id`).
Отчёты: расход и стоимость по дням/месяцам и ресурсам; профиль суток (48 точек);
баланс узла «ввод − Σ дочерних» = потери; удельный расход оборудования кВт·ч на машино-час
(`equipment.facade.get_runtime`); заказы на участке в день пика (`ordersOnWc`).

### 3.8 `analytics`

**`WeeklyCutoff`** — закрытая неделя: `week_start` (понедельник, уник.), `closed_by`,
`closed_at`, `comment`; **`WeeklyCutoffRow`**: `cutoff`, `work_center_id`, `planned_hours`,
`earned_hours`, `worked_hours`, `checked`, `defects`. Снимок неизменяем; переоткрытие —
удаление снимка с причиной в истории (кто закрывает — начальник производства; вопрос
плана интеграции №5 решён так для приложения).
Живая неделя (`liveWeekRow`): план — н-ч операций заказов в работе, распределённые по
рабочим дням операции; освоено — `production.facade.list_earnings`; отработано —
`timesheet.facade.worked_hours_by_work_center`; качество — `quality.facade`.
Выработка участка = освоено / отработано; выполнение плана = освоено / план.

**Загрузка 10 недель** (`renderLoad`): остаток часов `hours × (1 − progress)` не
выполненных операций, распределённый по дням операции, заказы — «твёрдо», заявки —
«предварительно» (из `sales.facade.list_open_inquiries`); мощность = исполнители × 40 ч.

**Портфель по месяцам** (`portfolioData`): выручка по месяцу окончания — факт
(отгружено), твёрдо (заказы), воронка (заявки × вероятность этапа); загрузка в часах
по месяцам против мощности `исполнители × 8 × рабочих дней месяца`.

**Выработка сотрудников** (`empStats`): за период — отработано, на заказах, накладные,
ремонт, простой, обучение, сверхурочные, отсутствия (дни); **освоено н-ч** = освоение
операций, распределённое по сотрудникам пропорционально их часам на операции за период;
**в рублях** = освоено × ставка участка операции; стоимость часов = часы × ставка ×
коэффициент кода; отдача = рубли / стоимость; брак сотрудника — по долям тех же операций,
отдельно «по вине оператора». Помесячная разбивка за 6 месяцев.

**Команда `manage.py seed_demo`** — вызывает `seed_demo()` фасадов по порядку:
production → sales → quality → supply → timesheet → equipment → energy → analytics.
Данные — копия демо-набора прототипа (заказчики, 25 заявок/заказов, 19 сотрудников,
10 станков, 20 счётчиков) с детерминированным генератором.

---

## 4. Роли и права

Роли — Django `Group` (`core.accounts.groups`), права — `Meta.permissions` модулей,
карта `SEED_GROUP_PERMISSIONS`.

| Роль | Права |
|---|---|
| администратор | всё (суперпользователь) |
| менеджер проекта | `sales.manage_inquiries` (свои заявки и заказы — объектный предикат `is_order_manager`) |
| экономист-сметчик | `sales.manage_calculation`, `timesheet.approve_period` |
| конструктор, технолог | `production.manage_documents` |
| снабженец | `supply.order_lines` |
| начальник производства | `production.manage_orders`, `production.plan_operations`, `production.approve_any`, `production.manage_reference`, `sales.launch_inquiry`, `supply.store_lines`, `analytics.close_cutoff`, `equipment.manage_equipment`, `timesheet.edit_any` |
| начальник склада | `supply.store_lines` |
| мастер участка | `quality.record_inspection`, `equipment.log_runtime`, `timesheet.edit_department` |
| инженер ОТК | `quality.record_inspection`, `quality.manage_reference` |
| энергетик | `energy.manage_meters` |
| наблюдатель | только чтение |

Чтение всех экранов — любой аутентифицированный. Объектные предикаты: ответственный за
операцию (`is_operation_responsible`), за этап (`is_stage_responsible`), менеджер заказа.
Фронт получает `abilities` от сервера.

---

## 5. События

| Событие | Когда | Подписчики |
|---|---|---|
| `sales.inquiry_launched` v1 | заявка запущена в производство | — (журнал) |
| `production.order_launched` v1 (`inquiry_id`, `planned_start`) | создан заказ | `supply` — потребность |
| `production.order_stage_changed` v1 | смена этапа | — |
| `production.operation_approved` v1 (`order_id`, `work_center_id`) | виза операции | — |
| `equipment.repair_closed` v1 | закрыт ремонт | `timesheet` — часы ремонта |

Каталог — `docs/events.md`.

---

## 6. Экраны (Next.js)

Меню: **Доска** · **План-график** (Гант всех заказов) · **Мои визы** · **Загрузка** ·
**Отсечки** · **Качество** · **Портфель** · **Закупки и склад** · **Табель** ·
**Оборудование** · **Энергоучёт** · **Сотрудники**.

- **Доска**: 8 колонок, карточки с номером, заказчиком, изделием, сроком, здоровьем
  («В графике», «Срыв на N дн.»), прогрессом, ответственным этапа; перетаскивание между
  колонками вызывает переход (с диалогом визы / причины возврата / запуска); KPI сверху
  (в работе, срыв, мои визы, портфель).
- **Карточка** (боковая панель): вкладки Основное, Калькуляция (только заявка или
  чтение у заказа), План (таблица операций со связями, перестановкой, «не ранее»,
  исполнителями), Состояние (ход, прогресс, визы), Документы, Материалы, Оснастка и
  расходники, Журнал.
- **Карточка операции** (модальное окно): всё из `opDialog`.
- **Гант**: шкала рабочих дней, полосы операций по заказам, критический путь, нарушения
  связей, сегодня; drag полосы операции — перенос, drag полосы заказа — сдвиг заказа.

Внешний вид — по образцу ИС (shadcn/ui, DataTable, EntityCard), русский интерфейс.

---

## 7. Открытые вопросы

1. Причина проигрыша — в прототипе её нет; заведена справочником `LossReason`
   (CLAUDE.md §5: по причинам строится отчёт). Состав справочника — заказчику.
2. Контрагент — `Party` ядра вместо строки прототипа (И5, дедупликация по ИНН).
3. Праздники в графике — вне объёма до производственного календаря.
