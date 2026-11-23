"""Tests des décisions et notifications (à placer dans backend/monitoring/)."""
from datetime import datetime, timedelta, timezone

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Alerte, Notification

AUTH_AMONT = "demo-cle-amont-01"
AUTH_AVAL = "demo-cle-aval-01"


@override_settings(NOTIF_EMAIL_DESTINATAIRES=["responsable@exemple.com"])
class NotificationTests(TestCase):
    def setUp(self):
        call_command("seed_demo", verbosity=0)
        self.client = APIClient()
        self.debut = datetime.now(timezone.utc) - timedelta(minutes=10)
        self.i = 0

    def envoyer(self, d1, p1, d2, p2):
        """Envoie une paire de mesures (amont + aval) au même instant."""
        ts = (self.debut + timedelta(seconds=10 * self.i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.i += 1
        for node, auth, d, p in (("amont-01", AUTH_AMONT, d1, p1), ("aval-01", AUTH_AVAL, d2, p2)):
            r = self.client.post("/api/mesures/",
                                 {"node_id": node, "ts": ts, "debit": d, "pression": p, "code_etat": 0},
                                 format="json", HTTP_X_API_KEY=auth)
            self.assertLess(r.status_code, 300, r.content)

    def normal(self, n=3):
        for _ in range(n):
            self.envoyer(4.2, 3.1, 4.15, 2.9)

    def test_normal_aucune_notification(self):
        self.normal(5)
        self.assertEqual(Notification.objects.count(), 0)

    def test_fuite_legere_donne_avertissement(self):
        self.normal()
        for _ in range(3):
            self.envoyer(4.2, 3.1, 3.5, 2.9)          # ~17 % d'écart, pression OK
        n = Notification.objects.filter(canal="web").first()
        self.assertEqual(n.niveau, "avertissement")
        self.assertEqual(n.evenement, "ouverte")

    def test_fuite_majeure_donne_critique(self):
        self.normal()
        for _ in range(3):
            self.envoyer(4.2, 3.1, 2.7, 0.7)          # ~35 % d'écart, pression < 1 bar
        self.assertTrue(Alerte.objects.get(type="fuite").confirmee_pression)
        self.assertEqual(Notification.objects.filter(canal="web").first().niveau, "critique")

    def test_escalade_puis_resolution(self):
        self.normal()
        for _ in range(3):
            self.envoyer(4.2, 3.1, 3.5, 2.9)
        for _ in range(3):
            self.envoyer(4.2, 3.1, 2.7, 0.7)
        self.normal(3)
        evenements = list(Notification.objects.filter(canal="web")
                          .order_by("id").values_list("evenement", flat=True))
        self.assertEqual(evenements, ["ouverte", "aggravee", "resolue"])
        self.assertEqual(Alerte.objects.get(type="fuite").statut, "resolue")

    def test_email_envoye_et_whatsapp_simule(self):
        self.normal()
        for _ in range(3):
            self.envoyer(4.2, 3.1, 2.7, 0.7)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("CRITIQUE", mail.outbox[0].subject)
        self.assertEqual(Notification.objects.get(canal="whatsapp").statut, "simulee")

    def test_endpoint_notifications(self):
        self.normal()
        for _ in range(3):
            self.envoyer(4.2, 3.1, 2.7, 0.7)
        r = self.client.get("/api/notifications/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 3)   # web + email + whatsapp
