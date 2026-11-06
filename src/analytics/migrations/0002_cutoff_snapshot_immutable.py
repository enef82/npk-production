# Снимок отсечки неизменяем (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.8): по закрытой
# неделе считается производительность, и правка задним числом — подлог отчёта, а не
# исправление. Переоткрытие — удаление снимка сервисом с причиной в журнале, поэтому
# запрещён только UPDATE; INSERT и DELETE остаются. Ограничение в БД, а не только в
# сервисе: админка, shell и будущий код не обойдут его (CLAUDE.md §5).
# `ERRCODE = '23000'` — Django поднимает `IntegrityError`, как на прочих ограничениях.

from django.db import migrations

FUNCTION = """
CREATE OR REPLACE FUNCTION analytics_cutoff_snapshot_immutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Снимок закрытой недели не изменяется — переоткройте отсечку.'
        USING ERRCODE = '23000';
END;
$$ LANGUAGE plpgsql;
"""

TRIGGERS = """
CREATE TRIGGER analytics_cutoff_immutable_trg
    BEFORE UPDATE ON analytics_weeklycutoff
    FOR EACH ROW EXECUTE FUNCTION analytics_cutoff_snapshot_immutable();
CREATE TRIGGER analytics_cutoff_row_immutable_trg
    BEFORE UPDATE ON analytics_weeklycutoffrow
    FOR EACH ROW EXECUTE FUNCTION analytics_cutoff_snapshot_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=FUNCTION + TRIGGERS,
            reverse_sql=(
                "DROP TRIGGER IF EXISTS analytics_cutoff_immutable_trg ON analytics_weeklycutoff;"
                " DROP TRIGGER IF EXISTS analytics_cutoff_row_immutable_trg"
                " ON analytics_weeklycutoffrow;"
                " DROP FUNCTION IF EXISTS analytics_cutoff_snapshot_immutable();"
            ),
        ),
    ]
