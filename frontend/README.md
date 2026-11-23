# Frontend – Télégestion des fuites d'eau

Tableau de bord React (Vite + Recharts). Il interroge l'API Django toutes les 2 s.

    npm install
    npm run dev        # http://localhost:5173

Backend attendu sur http://localhost:8000 (modifiable : copier `.env.example` en `.env`).

Écran : bandeau d'état (normal / avertissement / critique), 4 capteurs, synoptique animé,
courbes débit et pression, cloche de notifications (web, e-mail, WhatsApp), historique des alertes.
