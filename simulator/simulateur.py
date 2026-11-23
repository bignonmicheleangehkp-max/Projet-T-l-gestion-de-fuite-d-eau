#!/usr/bin/env python3
"""Simulateur de la carte ESP32 (4 capteurs, un seul envoi par relevé) + panneau de contrôle.

Au lancement tout est NORMAL. Ouvrez le panneau de contrôle dans le navigateur :
    http://localhost:8001
Vous y déclenchez à la main : fuite légère, fuite majeure, coupure réseau, capteur
défaillant, réparation, ou vous passez en mode ALÉATOIRE (fuites et coupures au hasard).

Usage :
    python3 simulateur.py                   # démarre normal, panneau sur le port 8001
    python3 simulateur.py --aleatoire       # démarre directement en mode aléatoire
    python3 simulateur.py --intervalle 1 --seed 42
    python3 simulateur.py --port-controle 8010
Ctrl+C pour arrêter.
"""
import argparse
import json
import math
import os
import random
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import requests
except ImportError:
    sys.exit("Installez requests :  pip install requests")

CLE = os.environ.get("CLE_CARTE", os.environ.get("CLE_AMONT", "demo-cle-amont-01"))
TAILLE_LOT = 100


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def log(msg):
    print(f"\n*** {msg} ***", flush=True)


class Reseau:
    """État de la simulation, partagé entre la boucle d'envoi et le panneau web."""

    def __init__(self, a):
        self.a = a
        self.lock = threading.RLock()
        self.mode = "aleatoire" if a.aleatoire else "manuel"
        self.fuite = None            # None | "legere" | "majeure"
        self.fuite_restant = None    # None = jusqu'à réparation manuelle
        self.coupure = False
        self.coupure_restant = None  # None = jusqu'à reprise manuelle
        self.capteur = False         # capteur défaillant (code_etat = 2)
        self.t = 0
        self.dernier = None
        self.envoyes = 0
        self.attente = 0

    # ---------- commandes du panneau ----------
    def commande(self, action):
        with self.lock:
            if action == "normal":
                self.fuite = None
                self.coupure = False
                self.capteur = False
                log("RÉPARATION : retour à la normale")
            elif action == "fuite_legere":
                self.fuite, self.fuite_restant = "legere", None
                log("FUITE LÉGÈRE déclenchée")
            elif action == "fuite_majeure":
                self.fuite, self.fuite_restant = "majeure", None
                log("FUITE MAJEURE déclenchée")
            elif action == "coupure_on":
                self.coupure, self.coupure_restant = True, None
                log("COUPURE RÉSEAU : les relevés sont stockés (microSD)")
            elif action == "coupure_off":
                self.coupure = False
                log("RÉSEAU RÉTABLI : envoi du lot stocké")
            elif action == "capteur_on":
                self.capteur = True
                log("CAPTEUR DÉFAILLANT (code_etat = 2)")
            elif action == "capteur_off":
                self.capteur = False
                log("Capteur réparé")
            elif action == "mode_aleatoire":
                self.mode = "aleatoire"
                log("MODE ALÉATOIRE activé")
            elif action == "mode_manuel":
                self.mode = "manuel"
                log("MODE MANUEL activé")
            else:
                return False
            return True

    def etat(self):
        with self.lock:
            return {
                "mode": self.mode, "fuite": self.fuite, "coupure": self.coupure,
                "capteur": self.capteur, "dernier": self.dernier,
                "envoyes": self.envoyes, "attente": self.attente,
            }

    # ---------- un tick de simulation ----------
    def avancer(self):
        a = self.a
        with self.lock:
            self.t += 1
            # fuite
            if self.fuite is None:
                if self.mode == "aleatoire" and random.random() < a.proba_fuite:
                    self.fuite = random.choice(["legere", "legere", "majeure"])
                    self.fuite_restant = random.randint(15, 45)
                    log(f"Fuite {self.fuite.upper()} aléatoire (~{self.fuite_restant} relevés)")
            elif self.fuite_restant is not None:  # fuite aléatoire : évolue toute seule
                self.fuite_restant -= 1
                if self.fuite == "legere" and random.random() < 0.04:
                    self.fuite = "majeure"
                    log("La fuite s'AGGRAVE : fuite MAJEURE")
                if self.fuite_restant <= 0:
                    self.fuite = None
                    log("Réparation : retour à la normale")
            # coupure
            if self.coupure:
                if self.coupure_restant is not None:
                    self.coupure_restant -= 1
                    if self.coupure_restant <= 0:
                        self.coupure = False
                        log("Réseau de retour : envoi du lot stocké")
            elif self.mode == "aleatoire" and random.random() < a.proba_coupure:
                self.coupure, self.coupure_restant = True, random.randint(8, 25)
                log(f"COUPURE RÉSEAU aléatoire (~{self.coupure_restant} relevés)")

            # lecture des 4 capteurs
            d1 = 4.2 + 0.25 * math.sin(self.t / 25) + random.gauss(0, 0.07)
            p1 = 3.1 + 0.05 * math.sin(self.t / 40) + random.gauss(0, 0.04)
            if self.fuite == "legere":
                d2, p2 = d1 * random.uniform(0.82, 0.88), p1 * random.uniform(0.93, 0.97)
            elif self.fuite == "majeure":
                d2, p2 = d1 * random.uniform(0.60, 0.70), random.uniform(0.5, 0.9)
            else:
                d2, p2 = d1 * random.uniform(0.98, 1.0), p1 * random.uniform(0.93, 0.97)
            d1, d2, p1, p2 = max(d1, 0), max(d2, 0), max(p1, 0), max(p2, 0)
            code = 2 if self.capteur else 0
            releve = {
                "ts": iso(datetime.now(timezone.utc)),
                "debit1": round(d1, 2), "debit2": round(d2, 2),
                "pression1": round(p1, 2), "pression2": round(p2, 2),
                "code_etat": code,
            }
            self.dernier = dict(releve)
            ecart = (d1 - d2) / d1 * 100 if d1 > 0.1 else 0
            etat = {None: "normal", "legere": "FUITE LÉGÈRE", "majeure": "FUITE MAJEURE"}[self.fuite]
            if self.capteur:
                etat += " + capteur HS"
            return releve, ecart, etat, self.coupure


# ---------- panneau de contrôle web ----------
PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Simulateur ESP32 – contrôle</title>
<style>
:root{--bg:#0b1220;--card:#121b2e;--line:#243049;--txt:#e6ecf5;--mut:#8a97b0;
--ok:#2ecc8f;--warn:#f5a524;--bad:#ff6b6b;--blue:#38bdf8;--viol:#a78bfa}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);
font:16px system-ui,sans-serif;padding:24px;max-width:900px;margin-inline:auto}
h1{font-size:22px;margin:0 0 4px}.sub{color:var(--mut);margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:16px}
.card h2{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);margin:0 0 12px}
.row{display:flex;gap:10px;flex-wrap:wrap}
button{flex:1;min-width:170px;padding:14px;border-radius:10px;border:2px solid var(--line);
background:#0f1727;color:var(--txt);font-size:16px;font-weight:600;cursor:pointer}
button:hover{border-color:var(--mut)}
button.on{border-color:var(--c);box-shadow:0 0 0 3px color-mix(in srgb,var(--c) 25%,transparent)}
.ok{--c:var(--ok)}.warn{--c:var(--warn)}.bad{--c:var(--bad)}.blue{--c:var(--blue)}.viol{--c:var(--viol)}
.big{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.val{background:#0f1727;border:1px solid var(--line);border-radius:10px;padding:12px}
.val small{color:var(--mut);display:block}.val b{font:600 24px ui-monospace,monospace}
.badge{display:inline-block;padding:4px 10px;border-radius:99px;border:1px solid var(--line);
margin-right:8px;font-size:14px}
@media(max-width:700px){.big{grid-template-columns:repeat(2,1fr)}}
</style></head><body>
<h1>Simulateur ESP32 – panneau de contrôle</h1>
<div class="sub">Pilotez les événements envoyés au backend. Le tableau de bord réagit en direct.</div>

<div class="card"><h2>État actuel</h2>
<div id="badges" style="margin-bottom:12px"></div>
<div class="big">
<div class="val"><small>Débitmètre 1 (amont)</small><b id="d1">–</b></div>
<div class="val"><small>Débitmètre 2 (aval)</small><b id="d2">–</b></div>
<div class="val"><small>Pression 1 (amont)</small><b id="p1">–</b></div>
<div class="val"><small>Pression 2 (aval)</small><b id="p2">–</b></div></div>
<div class="sub" style="margin:12px 0 0">Relevés envoyés : <b id="env">0</b> · en attente (microSD) : <b id="att">0</b></div>
</div>

<div class="card"><h2>Fuites</h2><div class="row">
<button class="ok" data-a="normal" data-k="normal">✅ Tout normal / Réparer</button>
<button class="warn" data-a="fuite_legere" data-k="legere">💧 Fuite légère</button>
<button class="bad" data-a="fuite_majeure" data-k="majeure">🚨 Fuite majeure</button></div></div>

<div class="card"><h2>Réseau et capteurs</h2><div class="row">
<button class="blue" data-a="coupure_on" data-k="coupure_on">📡 Couper le réseau</button>
<button class="blue" data-a="coupure_off" data-k="coupure_off">🔌 Rétablir (envoi du lot)</button>
<button class="viol" data-a="capteur_on" data-k="capteur_on">🛠 Capteur défaillant</button>
<button class="viol" data-a="capteur_off" data-k="capteur_off">✔ Capteur réparé</button></div></div>

<div class="card"><h2>Mode</h2><div class="row">
<button class="ok" data-a="mode_manuel" data-k="manuel">🎛 Manuel (je décide)</button>
<button class="warn" data-a="mode_aleatoire" data-k="aleatoire">🎲 Aléatoire (au hasard)</button></div></div>

<script>
const $=id=>document.getElementById(id);
async function cmd(a){await fetch('/cmd/'+a,{method:'POST'});refresh();}
document.querySelectorAll('button').forEach(b=>b.onclick=()=>cmd(b.dataset.a));
function on(k,v){document.querySelectorAll('[data-k="'+k+'"]').forEach(b=>b.classList.toggle('on',v));}
async function refresh(){
 try{const s=await (await fetch('/state')).json();
  const f=s.fuite;
  on('normal',!f&&!s.coupure&&!s.capteur);on('legere',f==='legere');on('majeure',f==='majeure');
  on('coupure_on',s.coupure);on('coupure_off',!s.coupure);
  on('capteur_on',s.capteur);on('capteur_off',!s.capteur);
  on('manuel',s.mode==='manuel');on('aleatoire',s.mode==='aleatoire');
  $('badges').innerHTML=
   '<span class="badge">Mode : <b>'+(s.mode==='aleatoire'?'aléatoire':'manuel')+'</b></span>'+
   '<span class="badge">Réseau : <b>'+(f?(f==='legere'?'fuite légère':'fuite majeure'):'normal')+'</b></span>'+
   '<span class="badge">Liaison : <b>'+(s.coupure?'COUPÉE':'ok')+'</b></span>'+
   (s.capteur?'<span class="badge">Capteur HS</span>':'');
  if(s.dernier){$('d1').textContent=s.dernier.debit1;$('d2').textContent=s.dernier.debit2;
   $('p1').textContent=s.dernier.pression1;$('p2').textContent=s.dernier.pression2;}
  $('env').textContent=s.envoyes;$('att').textContent=s.attente;
 }catch(e){}
}
setInterval(refresh,1000);refresh();
</script></body></html>"""


def lancer_panneau(net, port):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _rep(self, code, body, ctype="application/json"):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/state":
                self._rep(200, json.dumps(net.etat()))
            elif self.path in ("/", "/index.html"):
                self._rep(200, PAGE, "text/html")
            else:
                self._rep(404, "{}")

        def do_POST(self):
            if self.path.startswith("/cmd/") and net.commande(self.path[5:]):
                self._rep(200, json.dumps(net.etat()))
            else:
                self._rep(400, '{"detail":"commande inconnue"}')

    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    except OSError as e:
        print(f"! Panneau de contrôle indisponible (port {port} : {e}). Utilisez --port-controle.")
        return
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"Panneau de contrôle : http://localhost:{port}")


def envoyer(url, releves):
    payload = releves[0] if len(releves) == 1 else releves
    try:
        r = requests.post(f"{url}/api/releves/", json=payload, timeout=5, headers={"X-API-Key": CLE})
    except requests.RequestException as e:
        print(f"   ! serveur injoignable ({e.__class__.__name__}) : relevés conservés")
        return False
    if r.status_code >= 400:
        print(f"   ! HTTP {r.status_code} -> {r.text[:200]}")
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--intervalle", type=float, default=1.0, help="secondes entre deux relevés")
    ap.add_argument("--port-controle", type=int, default=8001, help="port du panneau de contrôle")
    ap.add_argument("--aleatoire", action="store_true", help="démarre en mode aléatoire")
    ap.add_argument("--proba-fuite", type=float, default=0.012)
    ap.add_argument("--proba-coupure", type=float, default=0.008)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    net = Reseau(args)
    lancer_panneau(net, args.port_controle)
    print(f"Simulateur ESP32 -> {args.url}/api/releves/  (mode {net.mode}, Ctrl+C pour arrêter)")
    tampon = []  # simule la microSD

    try:
        while True:
            releve, ecart, etat, coupure = net.avancer()
            tampon.append(releve)
            tag = ""
            if coupure:
                tag = f"stocké (microSD, {len(tampon)} en attente)"
            else:
                while tampon:
                    lot = tampon[:TAILLE_LOT]
                    if not envoyer(args.url, lot):
                        tag = f"ECHEC ({len(tampon)} en attente)"
                        break
                    with net.lock:
                        net.envoyes += len(lot)
                    del tampon[:len(lot)]
                    tag = "envoyé" if len(lot) == 1 else f"lot de {len(lot)} envoyé"
            with net.lock:
                net.attente = len(tampon)
            r = releve
            print(f"[{datetime.now():%H:%M:%S}] D1={r['debit1']:.2f} D2={r['debit2']:.2f} "
                  f"(écart {ecart:4.1f} %) P1={r['pression1']:.2f} P2={r['pression2']:.2f} "
                  f"| {etat:22} | {tag}", flush=True)
            time.sleep(args.intervalle)
    except KeyboardInterrupt:
        print(f"\nArrêt. {net.envoyes} relevés envoyés, {len(tampon)} encore en attente.")


if __name__ == "__main__":
    main()