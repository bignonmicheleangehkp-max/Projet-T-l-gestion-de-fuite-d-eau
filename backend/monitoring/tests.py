from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import Alerte, Constat, Mesure, Noeud, Portion


class BaseTest(APITestCase):
    def setUp(self):
        self.amont = Noeud.objects.create(code="amont-01", nom="Amont", role="amont", api_key="ka")
        self.aval = Noeud.objects.create(code="aval-01", nom="Aval", role="aval", api_key="kv")
        self.portion = Portion.objects.create(nom="P1", noeud_amont=self.amont, noeud_aval=self.aval)
        self.t0 = timezone.now().replace(microsecond=0)

    def envoyer(self, cle, debit, pression, i, code=0):
        return self.client.post(
            "/api/mesures/",
            {"ts": (self.t0 + timedelta(seconds=10 * i)).isoformat(), "debit": debit,
             "pression": pression, "code_etat": code},
            format="json", HTTP_X_API_KEY=cle,
        )

    def cycle(self, i, q_amont, q_aval, p_aval=3.0):
        self.envoyer("ka", q_amont, 3.5, i)
        self.envoyer("kv", q_aval, p_aval, i)


class IngestionTests(BaseTest):
    def test_cle_absente_ou_invalide(self):
        r = self.client.post("/api/mesures/", {"debit": 1, "pression": 1}, format="json")
        self.assertEqual(r.status_code, 401)
        r = self.envoyer("mauvaise", 1, 1, 0)
        self.assertEqual(r.status_code, 401)

    def test_mesure_enregistree(self):
        r = self.envoyer("ka", 10.0, 3.5, 0)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Mesure.objects.count(), 1)

    def test_node_id_doit_correspondre_a_la_cle(self):
        r = self.client.post("/api/mesures/", {"node_id": "aval-01", "debit": 1, "pression": 1},
                             format="json", HTTP_X_API_KEY="ka")
        self.assertEqual(r.status_code, 403)

    def test_valeurs_invalides(self):
        r = self.envoyer("ka", -5, 3, 0)
        self.assertEqual(r.status_code, 400)

    def test_lot_et_doublons_ignores(self):
        lot = [{"ts": (self.t0 + timedelta(seconds=10 * i)).isoformat(), "debit": 10, "pression": 3}
               for i in range(3)]
        r = self.client.post("/api/mesures/", lot, format="json", HTTP_X_API_KEY="ka")
        self.assertEqual(r.json(), {"recues": 3, "nouvelles": 3, "doublons": 0})
        r = self.client.post("/api/mesures/", lot, format="json", HTTP_X_API_KEY="ka")
        self.assertEqual(r.json(), {"recues": 3, "nouvelles": 0, "doublons": 3})
        self.assertEqual(Mesure.objects.count(), 3)


class DetectionTests(BaseTest):
    def test_fonctionnement_normal_sans_alerte(self):
        for i in range(5):
            self.cycle(i, 10.0, 9.8)
        self.assertEqual(Alerte.objects.count(), 0)

    def test_fuite_apres_mesures_consecutives(self):
        self.cycle(0, 10.0, 9.9)
        self.cycle(1, 10.0, 6.0)
        self.cycle(2, 10.0, 6.0)
        self.assertEqual(Alerte.objects.count(), 0, "pas d'alerte avant 3 mesures anormales")
        self.cycle(3, 10.0, 6.0)
        self.assertEqual(Alerte.objects.filter(type="fuite", statut="ouverte").count(), 1)

    def test_pas_de_doublon_d_alerte(self):
        for i in range(6):
            self.cycle(i, 10.0, 6.0)
        self.assertEqual(Alerte.objects.filter(type="fuite").count(), 1)

    def test_confirmation_par_pression(self):
        for i in range(3):
            self.cycle(i, 10.0, 6.0, p_aval=0.5)
        self.assertTrue(Alerte.objects.get(type="fuite").confirmee_pression)

    def test_resolution_automatique(self):
        for i in range(3):
            self.cycle(i, 10.0, 6.0)
        for i in range(3, 6):
            self.cycle(i, 10.0, 9.9)
        self.assertEqual(Alerte.objects.get(type="fuite").statut, "resolue")

    def test_aval_superieur_a_amont_n_est_pas_une_fuite(self):
        for i in range(4):
            self.cycle(i, 10.0, 12.0)
        self.assertEqual(Alerte.objects.count(), 0)

    def test_rattrapage_apres_coupure_declenche_la_detection(self):
        lot_a = [{"ts": (self.t0 + timedelta(seconds=10 * i)).isoformat(), "debit": 10, "pression": 3}
                 for i in range(3)]
        lot_v = [{"ts": (self.t0 + timedelta(seconds=10 * i)).isoformat(), "debit": 5, "pression": 3}
                 for i in range(3)]
        self.client.post("/api/mesures/", lot_a, format="json", HTTP_X_API_KEY="ka")
        self.client.post("/api/mesures/", lot_v, format="json", HTTP_X_API_KEY="kv")
        self.assertEqual(Alerte.objects.filter(type="fuite").count(), 1)

    def test_alerte_anomalie_noeud(self):
        self.envoyer("ka", 10, 3, 0, code=2)
        self.assertEqual(Alerte.objects.filter(type="anomalie", statut="ouverte").count(), 1)
        self.envoyer("ka", 10, 3, 1, code=0)
        self.assertEqual(Alerte.objects.get(type="anomalie").statut, "resolue")


class LectureTests(BaseTest):
    def test_endpoints_de_lecture(self):
        for i in range(3):
            self.cycle(i, 10.0, 6.0)
        noeuds = self.client.get("/api/noeuds/").json()
        self.assertEqual(len(noeuds), 2)
        self.assertTrue(noeuds[0]["en_ligne"])
        self.assertNotIn("api_key", noeuds[0])
        portions = self.client.get("/api/portions/").json()
        self.assertEqual(portions[0]["ecart_actuel_pct"], 40.0)
        self.assertTrue(portions[0]["fuite_en_cours"])
        self.assertEqual(len(self.client.get("/api/historique/?noeud=amont-01").json()), 3)
        self.assertEqual(len(self.client.get("/api/alertes/?statut=ouverte").json()), 1)

    def test_resoudre_alerte(self):
        for i in range(3):
            self.cycle(i, 10.0, 6.0)
        a = Alerte.objects.get()
        r = self.client.post(f"/api/alertes/{a.id}/resoudre/")
        self.assertEqual(r.json()["statut"], "resolue")

    @override_settings(NOEUD_TIMEOUT_SECONDS=-1)
    def test_noeud_hors_ligne(self):
        self.envoyer("ka", 10, 3, 0)
        noeuds = {n["code"]: n for n in self.client.get("/api/noeuds/").json()}
        self.assertFalse(noeuds["amont-01"]["en_ligne"])
        self.assertFalse(noeuds["aval-01"]["en_ligne"])

    def test_depot_constat(self):
        import tempfile
        with override_settings(MEDIA_ROOT=tempfile.mkdtemp()):
            f = SimpleUploadedFile("constat.pdf", b"%PDF-1.4 test", content_type="application/pdf")
            r = self.client.post("/api/constats/", {"titre": "Visite du 24/11", "fichier": f,
                                                    "portion": self.portion.id}, format="multipart")
            self.assertEqual(r.status_code, 201)
            self.assertEqual(Constat.objects.count(), 1)
