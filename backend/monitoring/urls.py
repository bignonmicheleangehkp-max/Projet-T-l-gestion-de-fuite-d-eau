from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .notif_api import NotificationList
from . import views

router = DefaultRouter()
router.register("noeuds", views.NoeudViewSet, basename="noeud")
router.register("portions", views.PortionViewSet, basename="portion")
router.register("historique", views.MesureViewSet, basename="historique")
router.register("alertes", views.AlerteViewSet, basename="alerte")
router.register("constats", views.ConstatViewSet, basename="constat")

urlpatterns = [
    path("mesures/", views.IngestionView.as_view(), name="ingestion"),
    path("", include(router.urls)),
    path("notifications/", NotificationList.as_view()),
]
