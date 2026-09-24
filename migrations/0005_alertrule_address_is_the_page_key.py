"""Store a rule's page under the key the engine actually publishes it under."""

from django.db import migrations

from utils.helpers import bundle_from_addresses


def to_page_key(apps, schema_editor):
    """Replace a joined address list with the bundle hash of those addresses.

    Rules made on a multi-address page were stored under the space-joined
    addresses, which is not a key the live pass writes - so `payload_for` read
    `lvp:<ADDR ADDR>`, found nothing, and the rule never fired. At three
    addresses the value also overflowed the column and the rule could not be
    saved at all.

    Single-address rules already hold the right value and are left alone: the
    engine keys those by the address itself.
    """
    AlertRule = apps.get_model("widgets", "AlertRule")
    for rule in AlertRule.objects.exclude(address="").iterator():
        if " " not in rule.address:
            continue
        rule.address = bundle_from_addresses(rule.address)
        rule.save(update_fields=["address"])


def to_addresses(apps, schema_editor):
    """Nothing to reverse to.

    The joined list a rule came from is not recoverable from its hash here -
    the mapping lives in Redis, which a migration must not depend on being up.
    Reversing leaves the page keys in place, which the old code reads as a
    bundle it has no rule for: no rule fires, and none fired before either.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("widgets", "0004_alertrule_asset_unit_alertrule_threshold_unit_and_more"),
    ]

    operations = [
        migrations.RunPython(to_page_key, to_addresses),
    ]
