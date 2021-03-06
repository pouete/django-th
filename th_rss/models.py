# coding: utf-8
from django.db import models
from django_th.models.services import Services


class Rss(Services):
    """
        Model for RSS Service
    """
    url = models.URLField(max_length=255)
    trigger = models.ForeignKey('TriggerService')

    class Meta:
        app_label = 'django_th'
        db_table = 'django_th_rss'

    def __str__(self):
        return "%s" % (self.url)

    def show(self):
        return "Services RSS %s %s" % (self.url, self.trigger)
