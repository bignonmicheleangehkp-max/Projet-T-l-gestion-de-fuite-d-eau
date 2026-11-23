#!/usr/bin/env python3
"""Simulateur de nœuds ESP32 (amont-01 / aval-01) pour la démo.

Scénario : normal -> fuite -> réparation -> coupure réseau + rattrapage.

Usage :
    python3 simulateur.py                  # scénario complet
    python3 simulateur.py --intervalle 1   # plus rapide
    python3 simulateur.py --url http://localhost:8000

Les clés API sont celles créées par `python manage.py seed_demo`.
Adaptez CLE_AMONT / CLE_AVAL (ou variables d'environnement du même nom).
"""
import argparse
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone

try:
    import requests
except ImportError:
    sys.exit("Installez requests :  pip install requests")

# >>> À REMPLACER par les clés affichées/définies dans seed_demo.py <<<
CLE_AMONT = os.environ.get("CLE_AMONT", "demo-cle-amont-01")
CLE_AVAL = os.environ.get("CLE_AVAL", "demo-cle-aval-01")

NOEUDS = {"amont-01": CLE_AMONT, "aval-01": CLE_AVAL}

# (nom de phase, nombre de mesures)
SCENARIO = [
    ("NORMAL", 8),
    ("FUITE LEGERE", 8),     # débit aval < débit amont, pression OK
    ("FUITE MAJEURE", 8),    # débit ET pression aval en chute -> critique
    ("REPARATION", 8),
    ("COUPURE RESEAU", 10),   # mesures stockées localement (microSD)
    ("RATTRAPAGE", 1),        # envoi du lot avec horodatages d'origine
    ("NORMAL", 4),
]


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mesures(phase):
    """4 capteurs simulés, regroupés par carte (nœud) :
       amont-01 = débitmètre 1 + capteur de pression 1
       aval-01  = débitmètre 2 + capteur de pression 2
    Retourne {noeud: (debit, pression, code_etat)}.
    code_etat reste 0 : la carte mesure seulement, c'est le BACKEND qui décide."""
    d1 = random.uniform(4.0, 4.4)          # débitmètre amont
    p1 = random.uniform(3.0, 3.2)          # pression amont
    if phase == "FUITE LEGERE":            # débit2 < débit1, pression normale
        d2, p2, code = d1 * random.uniform(0.82, 0.88), p1 * random.uniform(0.93, 0.97), 0
    elif phase == "FUITE MAJEURE":         # débit2 << débit1 ET pression2 basse
        d2, p2, code = d1 * random.uniform(0.60, 0.70), random.uniform(0.5, 0.9), 0  # < 1.0 bar (seuil backend)
    else:                                  # normal : petites variations
        d2, p2, code = d1 * random.uniform(0.98, 1.0), p1 * random.uniform(0.93, 0.97), 0
    return {"amont-01": (d1, p1, 0), "aval-01": (d2, p2, code)}


def point(node, ts, d, p, code):
    return {"node_id": node, "ts": iso(ts), "debit": round(d, 2),
            "pression": round(p, 2), "code_etat": code}


def envoyer(url, node, payload):
    """payload : dict (une mesure) ou list (lot)."""
    try:
        r = requests.post(f"{url}/api/mesures/", json=payload, timeout=5,
                          headers={"X-API-Key": NOEUDS[node]})
    except requests.RequestException as e:
        print(f"   ! {node} : serveur injoignable ({e.__class__.__name__})")
        return False
    if r.status_code >= 400:
        print(f"   ! {node} : HTTP {r.status_code} -> {r.text[:200]}")
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--intervalle", type=float, default=2.0,
                    help="secondes réelles entre deux mesures")
    args = ap.parse_args()

    tampon = {n: [] for n in NOEUDS}   # simule la microSD
    coupure = False

    for phase, n in SCENARIO:
        print(f"\n=== PHASE : {phase} ===")
        if phase == "RATTRAPAGE":
            for node, lot in tampon.items():
                ok = envoyer(args.url, node, lot)
                print(f"   {node} : lot de {len(lot)} mesures "
                      f"{'envoyé' if ok else 'ECHEC'}")
                lot.clear()
            coupure = False
            continue
        coupure = phase == "COUPURE RESEAU"
        for i in range(n):
            maintenant = datetime.now(timezone.utc)
            vals = mesures(phase)
            (d1, p1, _), (d2, p2, _) = vals["amont-01"], vals["aval-01"]
            ecart = (d1 - d2) / d1 * 100
            print(f"   [{i+1}/{n}] débitmètre1={d1:.2f} débitmètre2={d2:.2f} "
                  f"(écart {ecart:4.1f} %) | pression1={p1:.2f} pression2={p2:.2f}")
            for node, (d, p, code) in vals.items():
                m = point(node, maintenant, d, p, code)
                if coupure:
                    tampon[node].append(m)
                    tag = "stockée (microSD)"
                else:
                    ok = envoyer(args.url, node, m)
                    tag = "envoyée" if ok else "ECHEC"
                print(f"        {node:9} -> {tag}")
            time.sleep(args.intervalle)

    print("\nScénario terminé. Consultez /api/alertes/ ou le frontend.")


if __name__ == "__main__":
    main()