"""POST /api/releves/ : un envoi = les 4 valeurs de la carte ESP32.

Corps JSON (objet, ou liste d'objets pour le rattrapage après coupure) :
    {"ts": "2026-11-23T20:00:00.000Z",      # optionnel (heure de réception sinon)
     "debit1": 4.2, "debit2": 4.1,          # débitmètre amont / aval (L/min)
     "pression1": 3.1, "pression2": 2.9,    # capteur amont / aval (bar)
     "code_etat": 0}                        # optionnel

Authentification : en-tête X-API-Key (clé d'un des nœuds de la portion, ex. amont-01).
Chaque relevé crée deux Mesure (amont + aval) avec le MÊME horodatage, puis la
détection existante (detection.py) est appelée : rien d'autre ne change.
Les doublons (même nœud, même horodatage) sont ignorés.
"""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .detection import evaluer_apres_ingestion
from .models import Mesure, Noeud, Portion


class ReleveSerializer(serializers.Serializer):
    ts = serializers.DateTimeField(required=False)
    debit1 = serializers.FloatField(min_value=0)
    debit2 = serializers.FloatField(min_value=0)
    pression1 = serializers.FloatField(min_value=0)
    pression2 = serializers.FloatField(min_value=0)
    code_etat = serializers.IntegerField(required=False, default=0, min_value=0, max_value=255)


class ReleveView(APIView):
    authentication_classes = []
    parser_classes = [JSONParser]

    def post(self, request):
        cle = request.headers.get("X-API-Key", "")
        noeud = Noeud.objects.filter(api_key=cle).first() if cle else None
        if noeud is None:
            return Response({"detail": "Clé API invalide ou absente."}, status=status.HTTP_401_UNAUTHORIZED)

        portion = (
            Portion.objects.filter(Q(noeud_amont=noeud) | Q(noeud_aval=noeud))
            .select_related("noeud_amont", "noeud_aval")
            .first()
        )
        if portion is None:
            return Response({"detail": "Ce nœud n'appartient à aucune portion."},
                            status=status.HTTP_400_BAD_REQUEST)

        donnees = request.data if isinstance(request.data, list) else [request.data]
        serializer = ReleveSerializer(data=donnees, many=True)
        serializer.is_valid(raise_exception=True)

        nouveaux = 0
        with transaction.atomic():
            for item in serializer.validated_data:
                ts = item.get("ts") or timezone.now()
                _, c1 = Mesure.objects.get_or_create(
                    noeud=portion.noeud_amont, horodatage=ts,
                    defaults={"debit": item["debit1"], "pression": item["pression1"],
                              "code_etat": item["code_etat"]},
                )
                _, c2 = Mesure.objects.get_or_create(
                    noeud=portion.noeud_aval, horodatage=ts,
                    defaults={"debit": item["debit2"], "pression": item["pression2"],
                              "code_etat": item["code_etat"]},
                )
                nouveaux += int(c1 or c2)
            evaluer_apres_ingestion(portion.noeud_amont)
            evaluer_apres_ingestion(portion.noeud_aval)

        return Response(
            {"recus": len(donnees), "nouveaux": nouveaux, "doublons": len(donnees) - nouveaux},
            status=status.HTTP_201_CREATED,
        )
