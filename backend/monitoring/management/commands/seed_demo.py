from django.core.management.base import BaseCommand

from monitoring.models import Noeud, Portion

# Clés fixes pour la démo uniquement : le script simulateur les utilise telles quelles.
CLE_AMONT = "demo-cle-amont-01"
CLE_AVAL = "demo-cle-aval-01"


class Command(BaseCommand):
    help = "Crée les nœuds et la portion de démonstration (idempotent)."

    def handle(self, *args, **options):
        amont, _ = Noeud.objects.update_or_create(
            code="amont-01",
            defaults={"nom": "Nœud amont (sortie réservoir)", "role": Noeud.Role.AMONT,
                      "api_key": CLE_AMONT, "latitude": 6.4483, "longitude": 2.3553},
        )
        aval, _ = Noeud.objects.update_or_create(
            code="aval-01",
            defaults={"nom": "Nœud aval (entrée village)", "role": Noeud.Role.AVAL,
                      "api_key": CLE_AVAL, "latitude": 6.4561, "longitude": 2.3702},
        )
        Portion.objects.update_or_create(
            nom="Conduite principale",
            defaults={"noeud_amont": amont, "noeud_aval": aval, "seuil_ecart_pct": 10.0,
                      "pression_min_aval": 1.0, "mesures_consecutives": 3},
        )
        self.stdout.write(self.style.SUCCESS("Données de démo prêtes."))
        self.stdout.write(f"  amont-01 → clé API : {CLE_AMONT}")
        self.stdout.write(f"  aval-01  → clé API : {CLE_AVAL}")
