# Обе операции связи калькуляции принадлежат одной заявке
# (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.2). CheckConstraint видит только
# собственную строку, а `inquiry_id` живёт в строках операций — поэтому BEFORE-триггер,
# как у связей операций заказа в `production`.
# `ERRCODE = '23000'` — Django поднимает тот же `IntegrityError`, что и на ограничениях.

from django.db import migrations

FUNCTION = """
CREATE OR REPLACE FUNCTION sales_calc_dependency_same_inquiry() RETURNS TRIGGER AS $$
DECLARE
    pred_inquiry uuid;
    succ_inquiry uuid;
BEGIN
    SELECT inquiry_id INTO pred_inquiry FROM sales_calcoperation WHERE id = NEW.predecessor_id;
    SELECT inquiry_id INTO succ_inquiry FROM sales_calcoperation WHERE id = NEW.successor_id;
    IF pred_inquiry IS DISTINCT FROM succ_inquiry THEN
        RAISE EXCEPTION 'Связать можно только операции одной заявки.'
            USING ERRCODE = '23000';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

TRIGGER = """
CREATE TRIGGER sales_calc_dependency_same_inquiry_trg
    BEFORE INSERT OR UPDATE ON sales_calcoperationdependency
    FOR EACH ROW
    EXECUTE FUNCTION sales_calc_dependency_same_inquiry();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=FUNCTION + TRIGGER,
            reverse_sql=(
                "DROP TRIGGER IF EXISTS sales_calc_dependency_same_inquiry_trg"
                " ON sales_calcoperationdependency;"
                " DROP FUNCTION IF EXISTS sales_calc_dependency_same_inquiry();"
            ),
        ),
    ]
