from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Alerte, Mesure, Noeud, Portion


class ReleveTests(TestCase):
    def setUp(self):
        self.amont = Noeud.objects.create(code="amont-t", nom="A", role="amont", api_key="cle-a")
        self.aval = Noeud.objects.create(code="aval-t", nom="B", role="aval", api_key="cle-b")
        self.portion = Portion.objects.create(nom="P", noeud_amont=self.amont, noeud_aval=self.aval)
        self.client = APIClient()

    def post(self, data, cle="cle-a"):
        return self.client.post("/api/releves/", data, format="json", HTTP_X_API_KEY=cle)

    def test_cle_invalide(self):
        r = self.post({"debit1": 1, "debit2": 1, "pression1": 1, "pression2": 1}, cle="x")
        self.assertEqual(r.status_code, 401)

    def test_un_releve_cree_deux_mesures(self):
        r = self.post({"debit1": 4, "debit2": 3.9, "pression1": 3, "pression2": 2.9})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Mesure.objects.count(), 2)

    def test_doublons_ignores(self):
        ts = timezone.now().isoformat()
        corps = {"ts": ts, "debit1": 4, "debit2": 4, "pression1": 3, "pression2": 3}
        self.post(corps)
        r = self.post(corps)
        self.assertEqual(r.json()["doublons"], 1)
        self.assertEqual(Mesure.objects.count(), 2)

    def test_fuite_detectee_sur_lot(self):
        base = timezone.now() - timedelta(minutes=1)
        lot = [{"ts": (base + timedelta(seconds=i)).isoformat(),
                "debit1": 4.0, "debit2": 2.5, "pression1": 3.0, "pression2": 0.6}
               for i in range(4)]
        r = self.post(lot)
        self.assertEqual(r.status_code, 201)
        self.assertTrue(Alerte.objects.filter(type="fuite", statut="ouverte").exists())

    def test_valeur_invalide(self):
        r = self.post({"debit1": -1, "debit2": 1, "pression1": 1, "pression2": 1})
        self.assertEqual(r.status_code, 400)
