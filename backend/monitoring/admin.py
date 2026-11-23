from django.contrib import admin

from .models import Alerte, Constat, Mesure, Noeud, Portion


@admin.register(Noeud)
class NoeudAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "role", "api_key")


@admin.register(Portion)
class PortionAdmin(admin.ModelAdmin):
    list_display = ("nom", "noeud_amont", "noeud_aval", "seuil_ecart_pct", "mesures_consecutives")


@admin.register(Mesure)
class MesureAdmin(admin.ModelAdmin):
    list_display = ("noeud", "horodatage", "debit", "pression", "code_etat")
    list_filter = ("noeud",)


@admin.register(Alerte)
class AlerteAdmin(admin.ModelAdmin):
    list_display = ("cree_le", "type", "statut", "message")
    list_filter = ("type", "statut")


admin.site.register(Constat)
