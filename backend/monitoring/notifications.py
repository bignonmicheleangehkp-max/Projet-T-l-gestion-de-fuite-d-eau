"""Notifications : enregistre chaque décision et la diffuse (web, e-mail, WhatsApp).

Canal « web » : simple enregistrement en base, lu par le frontend.
Canal « email » : Django send_mail (console par défaut, SMTP si configuré).
Canal « whatsapp » : Twilio si les clés sont dans le .env, sinon statut « simulée ».
"""
import base64
import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.mail import send_mail

from .models import Alerte, Notification

log = logging.getLogger(__name__)


def niveau_alerte(alerte):
    """Fuite avec chute de pression confirmée = critique (grosse perte d'eau)."""
    if alerte.type == Alerte.Type.FUITE and alerte.confirmee_pression:
        return Notification.Niveau.CRITIQUE
    return Notification.Niveau.AVERTISSEMENT


def _texte(alerte, evenement, niveau):
    if evenement == Notification.Evenement.RESOLUE:
        return f"✅ RÉSOLU – {alerte.message}"
    if niveau == Notification.Niveau.CRITIQUE:
        prefixe = "🚨 CRITIQUE – forte perte d'eau" + (
            " (aggravation)" if evenement == Notification.Evenement.AGGRAVEE else "")
    else:
        prefixe = "⚠️ AVERTISSEMENT"
    return f"{prefixe} – {alerte.message}"


def _envoyer_email(texte, niveau):
    dest = settings.NOTIF_EMAIL_DESTINATAIRES
    if not dest:
        return Notification.Statut.SIMULEE, "aucun destinataire e-mail configuré"
    send_mail(f"[Fuites eau] {niveau.upper()}", texte,
              settings.DEFAULT_FROM_EMAIL, dest, fail_silently=False)
    return Notification.Statut.ENVOYEE, ", ".join(dest)


def _envoyer_whatsapp(texte):
    dest = settings.NOTIF_WHATSAPP_DESTINATAIRES
    sid, token, expediteur = (settings.TWILIO_ACCOUNT_SID,
                              settings.TWILIO_AUTH_TOKEN, settings.TWILIO_WHATSAPP_FROM)
    if not (dest and sid and token and expediteur):
        return Notification.Statut.SIMULEE, "clés Twilio / destinataires absents : message non envoyé"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    for numero in dest:
        data = urllib.parse.urlencode({
            "From": f"whatsapp:{expediteur}", "To": f"whatsapp:{numero}", "Body": texte,
        }).encode()
        req = urllib.request.Request(url, data=data, headers={"Authorization": f"Basic {auth}"})
        urllib.request.urlopen(req, timeout=10).read()
    return Notification.Statut.ENVOYEE, ", ".join(dest)


def notifier(alerte, evenement):
    """Crée les notifications (une par canal) pour un événement d'alerte."""
    niveau = (Notification.Niveau.INFO if evenement == Notification.Evenement.RESOLUE
              else niveau_alerte(alerte))
    texte = _texte(alerte, evenement, niveau)

    envois = [
        (Notification.Canal.WEB, lambda: (Notification.Statut.ENVOYEE, "")),
        (Notification.Canal.EMAIL, lambda: _envoyer_email(texte, niveau)),
        (Notification.Canal.WHATSAPP, lambda: _envoyer_whatsapp(texte)),
    ]
    for canal, envoi in envois:
        try:
            statut, detail = envoi()
        except Exception as exc:  # un canal en panne ne doit jamais bloquer l'ingestion
            log.exception("Échec notification %s", canal)
            statut, detail = Notification.Statut.ECHEC, str(exc)[:250]
        Notification.objects.create(
            alerte=alerte, canal=canal, evenement=evenement, niveau=niveau,
            message=texte, statut=statut, detail=detail,
        )
