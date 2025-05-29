from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class TerminalConfig(AppConfig):
    name = 'apps.terminal'
    verbose_name = _('terminal')

    def ready(self):
        super().ready()
