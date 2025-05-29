from django.db import models
from django.utils.translation import gettext_lazy as _


class Terminal(models.Model):

    class Meta:
        verbose_name = _('Web Terminal')
        permissions = [
            ('terminal_connect', 'Can Use Web Terminal'),
            ('terminal_file', 'Can Edit Files'),
        ]
