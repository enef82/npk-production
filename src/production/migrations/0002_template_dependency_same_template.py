# Обе операции связи шаблона принадлежат одному шаблону
# (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.1). CheckConstraint видит только
# собственную строку, а `template_id` живёт в строках операций — поэтому BEFORE-триггер
# по прецеденту ИС `production.migrations.0002_operation_dependency_same_order`.
# `ERRCODE = '23000'` — Django поднимает тот же `IntegrityError`, что и на ограничениях.

from django.db import migrations

FUNCTION = """
CREATE OR REPLACE FUNCTION production_template_dependency_same_template() RETURNS TRIGGER AS $$
DECLARE
    pred_template uuid;
    succ_template uuid;
BEGIN
    SELECT template_id INTO pred_template FROM production_templateoperation
        WHERE id = NEW.predecessor_id;
    SELECT template_id INTO succ_template FROM production_templateoperation
        WHERE id = NEW.successor_id;
    IF pred_template IS DISTINCT FROM succ_template THEN
        RAISE EXCEPTION 'Связать можно только операции одного шаблона.'
            USING ERRCODE = '23000';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

TRIGGER = """
CREATE TRIGGER production_template_dependency_same_template_trg
    BEFORE INSERT OR UPDATE ON production_templateoperationdependency
    FOR EACH ROW
    EXECUTE FUNCTION production_template_dependency_same_template();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=FUNCTION + TRIGGER,
            reverse_sql=(
                "DROP TRIGGER IF EXISTS production_template_dependency_same_template_trg"
                " ON production_templateoperationdependency;"
                " DROP FUNCTION IF EXISTS production_template_dependency_same_template();"
            ),
        ),
    ]
