"""Models owned by widgets, gathered where Django can find them.

**Widgets are not Django apps and this is how one keeps a table anyway.** Each
inhouse widget is a package under `widgets.inhouse`, so a model declared in
`widgets/inhouse/<name>/models.py` has a module path that `widgets` is a prefix
of - and `apps.get_containing_app_config` resolves an app label by longest
matching prefix. The model therefore belongs to the `widgets` app, and its
migrations land in `widgets/migrations/`, which has stood empty and ready since
the app was created.

What Django will not do is *import* those modules. Only `<app>/models.py` is
imported at startup, so a widget's models are invisible until they are named
here. That is the whole job of this file.

Keep it to imports. A model defined here rather than in the widget that owns it
is a model the widget cannot be removed without finding.
"""

from widgets.inhouse.alerts.models import AlertRule  # noqa: F401
