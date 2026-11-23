from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from .detection import ecart_pct, paires_recentes
from .models import Alerte, Constat, Mesure, Noeud, Portion


class MesureIngestionSerializer(serializers.Serializer):
    """Format envoyé par l'ESP32 (ou le script qui le simule)."""

    node_id = serializers.CharField(required=False)
    ts = serializers.DateTimeField(required=False)
    debit = serializers.FloatField(min_value=0)
    pression = serializers.FloatField(min_value=0)
    code_etat = serializers.IntegerField(required=False, default=0, min_value=0, max_value=255)


class MesureSerializer(serializers.ModelSerializer):
    noeud = serializers.CharField(source="noeud.code")

    class Meta:
        model = Mesure
        fields = ["id", "noeud", "horodatage", "debit", "pression", "code_etat"]


class NoeudSerializer(serializers.ModelSerializer):
    derniere_mesure = serializers.SerializerMethodField()
    en_ligne = serializers.SerializerMethodField()

    class Meta:
        model = Noeud
        fields = ["id", "code", "nom", "role", "latitude", "longitude", "derniere_mesure", "en_ligne"]

    def _derniere(self, obj):
        return obj.mesures.order_by("-horodatage").first()

    def get_derniere_mesure(self, obj):
        m = self._derniere(obj)
        return MesureSerializer(m).data if m else None

    def get_en_ligne(self, obj):
        m = self._derniere(obj)
        if m is None:
            return False
        limite = timezone.now() - timedelta(seconds=settings.NOEUD_TIMEOUT_SECONDS)
        return m.recu_le >= limite


class PortionSerializer(serializers.ModelSerializer):
    noeud_amont = serializers.CharField(source="noeud_amont.code")
    noeud_aval = serializers.CharField(source="noeud_aval.code")
    ecart_actuel_pct = serializers.SerializerMethodField()
    fuite_en_cours = serializers.SerializerMethodField()

    class Meta:
        model = Portion
        fields = [
            "id", "nom", "noeud_amont", "noeud_aval", "seuil_ecart_pct",
            "pression_min_aval", "ecart_actuel_pct", "fuite_en_cours",
        ]

    def get_ecart_actuel_pct(self, obj):
        paires = paires_recentes(obj, 1)
        if not paires:
            return None
        return round(ecart_pct(*paires[0]), 1)

    def get_fuite_en_cours(self, obj):
        return obj.alertes.filter(type=Alerte.Type.FUITE, statut=Alerte.Statut.OUVERTE).exists()


class AlerteSerializer(serializers.ModelSerializer):
    portion_nom = serializers.CharField(source="portion.nom", default=None, read_only=True)
    noeud_code = serializers.CharField(source="noeud.code", default=None, read_only=True)

    class Meta:
        model = Alerte
        fields = [
            "id", "type", "statut", "message", "ecart_pct", "confirmee_pression",
            "portion", "portion_nom", "noeud", "noeud_code", "cree_le", "resolue_le",
        ]


class ConstatSerializer(serializers.ModelSerializer):
    class Meta:
        model = Constat
        fields = ["id", "titre", "fichier", "portion", "depose_le"]
        read_only_fields = ["depose_le"]
