import { useEffect, useRef, useState } from "react";

// Adresse du backend Django (modifiable via frontend/.env : VITE_API_URL=...)
export const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const REFRESH_MS = 2000;

async function get(path) {
  const r = await fetch(`${API}/api/${path}`);
  if (!r.ok) throw new Error(`${path} : HTTP ${r.status}`);
  return r.json();
}

const VIDE = { noeuds: [], portions: [], alertes: [], notifications: [], historique: [] };

/** Interroge l'API toutes les 2 s. En cas d'échec on garde les dernières données. */
export function useDonnees() {
  const [data, setData] = useState(VIDE);
  const [etat, setEtat] = useState({ connecte: false, maj: null, erreur: null });
  const actif = useRef(true);

  useEffect(() => {
    actif.current = true;
    async function charger() {
      try {
        const [noeuds, portions, alertes, notifications, historique] = await Promise.all([
          get("noeuds/"),
          get("portions/"),
          get("alertes/"),
          get("notifications/"),
          get("historique/?limite=240"),
        ]);
        if (!actif.current) return;
        setData({ noeuds, portions, alertes, notifications, historique });
        setEtat({ connecte: true, maj: new Date(), erreur: null });
      } catch (e) {
        if (!actif.current) return;
        setEtat((s) => ({ ...s, connecte: false, erreur: String(e.message || e) }));
      }
    }
    charger();
    const id = setInterval(charger, REFRESH_MS);
    return () => {
      actif.current = false;
      clearInterval(id);
    };
  }, []);

  return { data, etat };
}
