import secrets

from django.db import models


def generer_cle():
    return secrets.token_urlsafe(24)


class Noeud(models.Model):
    """Point de mesure (un ESP32 ou, ici, le script qui le simule)."""

    class Role(models.TextChoices):
        AMONT = "amont", "Amont"
        AVAL = "aval", "Aval"
        AUTRE = "autre", "Autre"

    code = models.CharField(max_length=50, unique=True, help_text="Ex. amont-01")
    nom = models.CharField(max_length=100)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.AUTRE)
    api_key = models.CharField(max_length=64, unique=True, default=generer_cle)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class Portion(models.Model):
    """Tronçon de conduite délimité par un nœud amont et un nœud aval."""

    nom = models.CharField(max_length=100)
    noeud_amont = models.ForeignKey(Noeud, on_delete=models.PROTECT, related_name="portions_amont")
    noeud_aval = models.ForeignKey(Noeud, on_delete=models.PROTECT, related_name="portions_aval")
    seuil_ecart_pct = models.FloatField(
        default=10.0, help_text="Écart de débit amont/aval (en % du débit amont) jugé anormal"
    )
    pression_min_aval = models.FloatField(
        default=1.0, help_text="Pression aval (bar) en dessous de laquelle la fuite est confirmée"
    )
    mesures_consecutives = models.PositiveSmallIntegerField(
        default=3, help_text="Nombre de mesures consécutives anormales avant d'alerter"
    )

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Mesure(models.Model):
    """Mesure envoyée par un nœud.

    code_etat : 0 = normal, 1 = anomalie signalée par le nœud,
                2 = capteur défaillant, 3 = reprise après coupure d'alimentation.
    """

    CODE_OK = 0
    CODE_ANOMALIE = 1
    CODE_CAPTEUR = 2
    CODE_REPRISE = 3

    noeud = models.ForeignKey(Noeud, on_delete=models.CASCADE, related_name="mesures")
    horodatage = models.DateTimeField(db_index=True)
    debit = models.FloatField(help_text="L/min")
    pression = models.FloatField(help_text="bar")
    code_etat = models.PositiveSmallIntegerField(default=CODE_OK)
    recu_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-horodatage"]
        constraints = [
            # Évite les doublons quand l'ESP32 renvoie les données de sa carte microSD.
            models.UniqueConstraint(fields=["noeud", "horodatage"], name="mesure_unique_noeud_ts"),
        ]
        indexes = [models.Index(fields=["noeud", "-horodatage"])]

    def __str__(self):
        return f"{self.noeud.code} @ {self.horodatage:%Y-%m-%d %H:%M:%S}"


class Alerte(models.Model):
    class Type(models.TextChoices):
        FUITE = "fuite", "Fuite probable"
        ANOMALIE = "anomalie", "Anomalie du nœud"

    class Statut(models.TextChoices):
        OUVERTE = "ouverte", "Ouverte"
        RESOLUE = "resolue", "Résolue"

    type = models.CharField(max_length=10, choices=Type.choices)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.OUVERTE)
    portion = models.ForeignKey(Portion, null=True, blank=True, on_delete=models.CASCADE, related_name="alertes")
    noeud = models.ForeignKey(Noeud, null=True, blank=True, on_delete=models.CASCADE, related_name="alertes")
    message = models.CharField(max_length=300)
    ecart_pct = models.FloatField(null=True, blank=True)
    confirmee_pression = models.BooleanField(default=False)
    cree_le = models.DateTimeField(auto_now_add=True)
    resolue_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-cree_le"]

    def __str__(self):
        return f"[{self.statut}] {self.message}"


class Constat(models.Model):
    """Document de constat déposé par un technicien (archive, sans lien avec l'ESP32)."""

    titre = models.CharField(max_length=150)
    fichier = models.FileField(upload_to="constats/%Y/%m/")
    portion = models.ForeignKey(Portion, null=True, blank=True, on_delete=models.SET_NULL, related_name="constats")
    depose_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-depose_le"]

    def __str__(self):
        return self.titre


class Notification(models.Model):
    """Trace de chaque décision notifiée (web / e-mail / WhatsApp)."""

    class Canal(models.TextChoices):
        WEB = "web", "Tableau de bord"
        EMAIL = "email", "E-mail"
        WHATSAPP = "whatsapp", "WhatsApp"

    class Evenement(models.TextChoices):
        OUVERTE = "ouverte", "Alerte ouverte"
        AGGRAVEE = "aggravee", "Alerte aggravée"
        RESOLUE = "resolue", "Alerte résolue"

    class Niveau(models.TextChoices):
        INFO = "info", "Information"
        AVERTISSEMENT = "avertissement", "Avertissement"
        CRITIQUE = "critique", "Critique"

    class Statut(models.TextChoices):
        ENVOYEE = "envoyee", "Envoyée"
        SIMULEE = "simulee", "Simulée (non configurée)"
        ECHEC = "echec", "Échec"

    alerte = models.ForeignKey("Alerte", on_delete=models.CASCADE, related_name="notifications")
    canal = models.CharField(max_length=10, choices=Canal.choices)
    evenement = models.CharField(max_length=10, choices=Evenement.choices)
    niveau = models.CharField(max_length=15, choices=Niveau.choices)
    message = models.TextField()
    statut = models.CharField(max_length=10, choices=Statut.choices)
    detail = models.CharField(max_length=255, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le", "-id"]

    def __str__(self):
        return f"[{self.niveau}/{self.canal}] {self.message[:60]}"
