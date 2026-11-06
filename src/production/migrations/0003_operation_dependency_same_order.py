# Обе операции связи принадлежат одному заказу (`docs/spec/00-prilozhenie-proizvodstvo.md`
# §3.1). CheckConstraint видит только собственную строку, а `order_id` живёт в строках
# `production_operation` — поэтому BEFORE-триггер, как в ИС 8а.
# `ERRCODE = '23000'` — Django поднимает тот же `IntegrityError`, что и на ограничениях.

from django.db import migrations

FUNCTION = """
CREATE OR REPLACE FUNCTION production_dependency_same_order() RETURNS TRIGGER AS $$
DECLARE
    pred_order uuid;
    succ_order uuid;
BEGIN
    SELECT order_id INTO pred_order FROM production_operation WHERE id = NEW.predecessor_id;
    SELECT order_id INTO succ_order FROM production_operation WHERE id = NEW.successor_id;
    IF pred_order IS DISTINCT FROM succ_order THEN
        RAISE EXCEPTION 'Связать можно только операции одного заказа.'
            USING ERRCODE = '23000';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

TRIGGER = """
CREATE TRIGGER production_dependency_same_order_trg
    BEFORE INSERT OR UPDATE ON production_operationdependency
    FOR EACH ROW
    EXECUTE FUNCTION production_dependency_same_order();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0002_template_dependency_same_template"),
    ]

    operations = [
        migrations.RunSQL(
            sql=FUNCTION + TRIGGER,
            reverse_sql=(
                "DROP TRIGGER IF EXISTS production_dependency_same_order_trg"
                " ON production_operationdependency;"
                " DROP FUNCTION IF EXISTS production_dependency_same_order();"
            ),
        ),
    ]
