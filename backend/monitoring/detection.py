"""Logique de détection de fuite : comparaison du débit amont et aval d'une portion.

Décisions :
- écart de débit > seuil sur N mesures d'affilée       -> alerte AVERTISSEMENT
- + pression aval sous le minimum (confirmée)           -> alerte CRITIQUE (forte perte d'eau)
- retour à la normale                                   -> alerte RÉSOLUE
Chaque décision est enregistrée (Alerte) et notifiée (Notification : web, e-mail, WhatsApp).
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import Alerte, Mesure, Notification, Portion
from .notifications import notifier

DEBIT_MIN = 0.1  # L/min : en dessous, on considère qu'il n'y a pas d'écoulement


def ecart_pct(amont, aval):
    """Écart de débit en % du débit amont. Un aval > amont n'est pas une fuite."""
    if amont.debit <= DEBIT_MIN:
        return 0.0
    return max(0.0, (amont.debit - aval.debit) / amont.debit * 100)


def mesure_proche(noeud, horodatage):
    """Mesure du nœud la plus proche dans le temps (dans la tolérance), ou None."""
    tol = timedelta(seconds=settings.APPARIEMENT_TOLERANCE_SECONDS)
    candidates = noeud.mesures.filter(
        horodatage__gte=horodatage - tol, horodatage__lte=horodatage + tol
    )
    return min(candidates, key=lambda m: abs(m.horodatage - horodatage), default=None)


def paires_recentes(portion, n):
    """Les n dernières paires (mesure amont, mesure aval) appariées dans le temps."""
    paires = []
    for m_amont in portion.noeud_amont.mesures.order_by("-horodatage")[:n]:
        m_aval = mesure_proche(portion.noeud_aval, m_amont.horodatage)
        if m_aval is not None:
            paires.append((m_amont, m_aval))
    return paires


def evaluer_portion(portion):
    """Ouvre, met à jour ou résout l'alerte de fuite d'une portion."""
    n = portion.mesures_consecutives
    paires = paires_recentes(portion, n)
    if len(paires) < n:
        return  # pas assez de données pour décider

    ecarts = [ecart_pct(a, v) for a, v in paires]
    alerte = portion.alertes.filter(type=Alerte.Type.FUITE, statut=Alerte.Statut.OUVERTE).first()

    if all(e > portion.seuil_ecart_pct for e in ecarts):
        moyenne = sum(ecarts) / len(ecarts)
        derniere_aval = paires[0][1]
        confirmee = derniere_aval.pression < portion.pression_min_aval
        message = (
            f"Fuite probable sur « {portion.nom} » : écart de débit amont/aval "
            f"de {moyenne:.0f} %"
            + (f", pression aval basse ({derniere_aval.pression:.1f} bar)." if confirmee else ".")
        )
        if alerte is None:
            alerte = Alerte.objects.create(
                type=Alerte.Type.FUITE, portion=portion, message=message,
                ecart_pct=moyenne, confirmee_pression=confirmee,
            )
            notifier(alerte, Notification.Evenement.OUVERTE)
        else:
            etait_confirmee = alerte.confirmee_pression
            alerte.message, alerte.ecart_pct, alerte.confirmee_pression = message, moyenne, confirmee
            alerte.save(update_fields=["message", "ecart_pct", "confirmee_pression"])
            if confirmee and not etait_confirmee:  # escalade : fuite légère -> majeure
                notifier(alerte, Notification.Evenement.AGGRAVEE)
    elif alerte is not None and all(e <= portion.seuil_ecart_pct for e in ecarts):
        alerte.statut = Alerte.Statut.RESOLUE
        alerte.resolue_le = timezone.now()
        alerte.save(update_fields=["statut", "resolue_le"])
        notifier(alerte, Notification.Evenement.RESOLUE)


def evaluer_noeud(noeud, derniere_mesure):
    """Alerte d'anomalie propre au nœud (capteur défaillant, anomalie signalée)."""
    anormal = derniere_mesure.code_etat in (Mesure.CODE_ANOMALIE, Mesure.CODE_CAPTEUR)
    ouverte = noeud.alertes.filter(type=Alerte.Type.ANOMALIE, statut=Alerte.Statut.OUVERTE).first()
    if anormal and ouverte is None:
        alerte = Alerte.objects.create(
            type=Alerte.Type.ANOMALIE, noeud=noeud,
            message=f"Anomalie signalée par le nœud « {noeud.code} » (code {derniere_mesure.code_etat}).",
        )
        notifier(alerte, Notification.Evenement.OUVERTE)
    elif not anormal and ouverte is not None:
        ouverte.statut = Alerte.Statut.RESOLUE
        ouverte.resolue_le = timezone.now()
        ouverte.save(update_fields=["statut", "resolue_le"])
        notifier(ouverte, Notification.Evenement.RESOLUE)


def evaluer_apres_ingestion(noeud):
    """À appeler une fois les nouvelles mesures d'un nœud enregistrées."""
    derniere = noeud.mesures.order_by("-horodatage").first()
    if derniere is None:
        return
    evaluer_noeud(noeud, derniere)
    portions = Portion.objects.filter(noeud_amont=noeud) | Portion.objects.filter(noeud_aval=noeud)
    for portion in portions.distinct():
        evaluer_portion(portion)
