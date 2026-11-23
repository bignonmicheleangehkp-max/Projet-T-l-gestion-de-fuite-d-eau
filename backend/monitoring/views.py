from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .detection import evaluer_apres_ingestion
from .models import Alerte, Constat, Mesure, Noeud, Portion
from .serializers import (
    AlerteSerializer, ConstatSerializer, MesureIngestionSerializer,
    MesureSerializer, NoeudSerializer, PortionSerializer,
)


class IngestionView(APIView):
    """POST /api/mesures/ : reçoit une mesure (objet JSON) ou un lot (liste JSON).

    Authentification : en-tête « X-API-Key » propre à chaque nœud.
    Un lot sert au rattrapage après coupure (données stockées sur la carte microSD) :
    les doublons (même nœud, même horodatage) sont ignorés.
    """

    authentication_classes = []
    parser_classes = [JSONParser]

    def post(self, request):
        cle = request.headers.get("X-API-Key", "")
        noeud = Noeud.objects.filter(api_key=cle).first() if cle else None
        if noeud is None:
            return Response({"detail": "Clé API invalide ou absente."}, status=status.HTTP_401_UNAUTHORIZED)

        donnees = request.data if isinstance(request.data, list) else [request.data]
        serializer = MesureIngestionSerializer(data=donnees, many=True)
        serializer.is_valid(raise_exception=True)

        for item in serializer.validated_data:
            if item.get("node_id") not in (None, noeud.code):
                return Response(
                    {"detail": f"Cette clé API appartient au nœud « {noeud.code} »."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        nouvelles = 0
        with transaction.atomic():
            for item in serializer.validated_data:
                _, cree = Mesure.objects.get_or_create(
                    noeud=noeud,
                    horodatage=item.get("ts") or timezone.now(),
                    defaults={
                        "debit": item["debit"],
                        "pression": item["pression"],
                        "code_etat": item["code_etat"],
                    },
                )
                nouvelles += cree
            evaluer_apres_ingestion(noeud)

        return Response(
            {"recues": len(donnees), "nouvelles": nouvelles, "doublons": len(donnees) - nouvelles},
            status=status.HTTP_201_CREATED,
        )


class NoeudViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Noeud.objects.all()
    serializer_class = NoeudSerializer


class PortionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Portion.objects.select_related("noeud_amont", "noeud_aval")
    serializer_class = PortionSerializer


class MesureViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/historique/?noeud=amont-01&depuis=2026-11-24T08:00:00Z&limite=200"""

    serializer_class = MesureSerializer

    def get_queryset(self):
        qs = Mesure.objects.select_related("noeud")
        p = self.request.query_params
        if p.get("noeud"):
            qs = qs.filter(noeud__code=p["noeud"])
        if p.get("depuis"):
            depuis = parse_datetime(p["depuis"])
            if depuis:
                qs = qs.filter(horodatage__gte=depuis)
        try:
            limite = min(int(p.get("limite", 200)), 2000)
        except ValueError:
            limite = 200
        return qs[:limite]


class AlerteViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/alertes/?statut=ouverte ; POST /api/alertes/<id>/resoudre/"""

    serializer_class = AlerteSerializer

    def get_queryset(self):
        qs = Alerte.objects.select_related("portion", "noeud")
        statut = self.request.query_params.get("statut")
        return qs.filter(statut=statut) if statut else qs

    @action(detail=True, methods=["post"])
    def resoudre(self, request, pk=None):
        alerte = self.get_object()
        if alerte.statut != Alerte.Statut.RESOLUE:
            alerte.statut = Alerte.Statut.RESOLUE
            alerte.resolue_le = timezone.now()
            alerte.save(update_fields=["statut", "resolue_le"])
        return Response(self.get_serializer(alerte).data)


class ConstatViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                     viewsets.GenericViewSet):
    """Dépôt et consultation des documents de constat des techniciens."""

    queryset = Constat.objects.all()
    serializer_class = ConstatSerializer
    parser_classes = [MultiPartParser, FormParser]
