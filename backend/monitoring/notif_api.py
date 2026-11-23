"""Endpoint de lecture des notifications pour le frontend.

GET /api/notifications/                 -> 50 dernières
GET /api/notifications/?canal=web       -> filtrer par canal
GET /api/notifications/?apres_id=12     -> seulement les nouvelles (polling)
"""
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "alerte", "canal", "evenement", "niveau",
                  "message", "statut", "detail", "cree_le"]


class NotificationList(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        qs = Notification.objects.all()
        if canal := request.query_params.get("canal"):
            qs = qs.filter(canal=canal)
        if apres := request.query_params.get("apres_id"):
            qs = qs.filter(id__gt=int(apres))
        return Response(NotificationSerializer(qs[:50], many=True).data)
