#!/bin/sh
set -e

echo ">> Migrations"
python manage.py migrate --noinput

# Données de démo (nœuds amont-01 / aval-01, portion, clés API) : seulement si la base est vide
if python manage.py shell -c "import sys; from monitoring.models import Noeud; sys.exit(0 if Noeud.objects.exists() else 1)"; then
  echo ">> Données de démo déjà présentes"
else
  echo ">> Création des données de démo"
  python manage.py seed_demo
fi

echo ">> Démarrage du serveur"
exec python manage.py runserver 0.0.0.0:8000
