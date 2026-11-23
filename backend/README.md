# Backend : télégestion et détection de fuites d'eau

API Django REST + PostgreSQL. Reçoit les mesures des nœuds (ESP32 ou script simulateur), détecte les fuites par comparaison débit amont/aval et expose les données au frontend React.

## Lancer (depuis la racine du dépôt)

```bash
cp .env.example .env                    # puis éditer si besoin
docker compose up -d db                 # PostgreSQL en conteneur

cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo              # crée amont-01, aval-01 et la portion de démo
python manage.py createsuperuser        # optionnel : interface /admin/
python manage.py runserver              # http://localhost:8000
```

Tests : `python manage.py test` (la base de test est créée automatiquement).
Sans Docker : `DB_ENGINE=sqlite python manage.py test`.

## API

| Méthode | URL | Rôle |
|---|---|---|
| POST | `/api/mesures/` | Ingestion d'une mesure ou d'un lot (en-tête `X-API-Key` du nœud) |
| GET | `/api/noeuds/` | Nœuds, dernière mesure, en ligne ou non |
| GET | `/api/portions/` | Portions, écart de débit actuel, fuite en cours |
| GET | `/api/historique/?noeud=amont-01&depuis=<ISO>&limite=200` | Historique des mesures |
| GET | `/api/alertes/?statut=ouverte` | Alertes |
| POST | `/api/alertes/<id>/resoudre/` | Résolution manuelle |
| GET/POST | `/api/constats/` | Documents de constat des techniciens (multipart) |

### Format envoyé par un nœud

```json
POST /api/mesures/
X-API-Key: demo-cle-amont-01

{ "ts": "2026-11-24T09:00:00Z", "debit": 12.0, "pression": 3.4, "code_etat": 0 }
```

- `ts` est optionnel (par défaut : heure de réception). Une liste JSON envoie un lot ; les doublons (même nœud, même `ts`) sont ignorés, ce qui permet le rattrapage depuis la carte microSD.
- `code_etat` : 0 normal, 1 anomalie signalée par le nœud, 2 capteur défaillant, 3 reprise après coupure.

## Règle de détection

Pour chaque portion, le backend apparie les mesures amont et aval (tolérance de 30 s). Si l'écart de débit dépasse `seuil_ecart_pct` (10 % par défaut) sur `mesures_consecutives` mesures d'affilée (3 par défaut), une alerte « fuite » est ouverte. Elle est marquée « confirmée par la pression » si la pression aval est sous `pression_min_aval`. Elle se résout automatiquement quand l'écart redevient normal sur le même nombre de mesures. Les seuils se règlent par portion dans `/admin/`.

## Limites connues (volontaires pour la démo)

- Lecture de l'API sans authentification.
- Les notifications (WhatsApp, SMS) ne sont pas encore envoyées : les alertes sont visibles via l'API et le tableau de bord.
