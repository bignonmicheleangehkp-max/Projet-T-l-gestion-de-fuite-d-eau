import { useEffect, useMemo, useRef, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useDonnees, API } from "./api.js";
import Synoptique from "./Synoptique.jsx";

/* ---------- utilitaires ---------- */
const heure = (iso) => (iso ? new Date(iso).toLocaleTimeString("fr-FR") : "—");
const dateHeure = (iso) =>
  iso
    ? new Date(iso).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "—";
const nb = (v, d = 2) => (v == null ? "—" : Number(v).toFixed(d));

const gravite = (a) => (a.type === "fuite" && a.confirmee_pression ? "critique" : "avertissement");

function etatGlobal(alertes) {
  const ouvertes = alertes.filter((a) => a.statut === "ouverte");
  if (ouvertes.some((a) => gravite(a) === "critique")) return { niveau: "crit", ouvertes };
  if (ouvertes.length) return { niveau: "warn", ouvertes };
  return { niveau: "ok", ouvertes };
}

/** Regroupe les notifications (une ligne par canal) en un événement par alerte. */
function grouperNotifications(notifs) {
  const m = new Map();
  for (const n of notifs) {
    const cle = `${n.alerte}-${n.evenement}`;
    const g = m.get(cle) || { cle, id: 0, evenement: n.evenement, niveau: n.niveau, message: n.message, cree_le: n.cree_le, canaux: {} };
    g.id = Math.max(g.id, n.id);
    g.canaux[n.canal] = n.statut;
    m.set(cle, g);
  }
  return [...m.values()].sort((a, b) => b.id - a.id);
}

const lireLocal = (k, def) => {
  try {
    const v = localStorage.getItem(k);
    return v == null ? def : Number(v);
  } catch {
    return def;
  }
};
const ecrireLocal = (k, v) => {
  try {
    localStorage.setItem(k, String(v));
  } catch {
    /* stockage indisponible : sans importance */
  }
};

const BANDEAU = {
  ok: { titre: "Réseau normal", texte: "Aucune fuite détectée. Les débits amont et aval sont cohérents." },
  warn: { titre: "Avertissement : fuite probable", texte: "Le débit aval est inférieur au débit amont. La pression reste normale : surveillance renforcée." },
  crit: { titre: "FUITE CRITIQUE : forte perte d'eau", texte: "Débit aval en chute et pression aval sous le minimum. Intervention immédiate requise." },
};

/* ---------- composants ---------- */
function Tuile({ label, role, valeur, unite, etat, note }) {
  return (
    <div className={`tuile ${etat || ""}`}>
      <div className="tuile-tete">
        <span className="tuile-label">{label}</span>
        <span className="tuile-role">{role}</span>
      </div>
      <div className="tuile-valeur">
        <span className="num">{valeur}</span>
        <span className="unite">{unite}</span>
      </div>
      <div className="tuile-note">{note}</div>
    </div>
  );
}

function Courbe({ titre, donnees, cleAmont, cleAval, unite, seuil, seuilLabel }) {
  return (
    <section className="carte">
      <header className="carte-tete">
        <h2>{titre}</h2>
        <div className="legende">
          <span><i className="pt amont" /> Amont</span>
          <span><i className="pt aval" /> Aval</span>
        </div>
      </header>
      <div className="graphe">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={donnees} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
            <CartesianGrid stroke="var(--trait)" vertical={false} />
            <XAxis dataKey="t" tick={{ fill: "var(--muted)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--trait)" }} minTickGap={36} />
            <YAxis tick={{ fill: "var(--muted)", fontSize: 11 }} tickLine={false} axisLine={false} domain={[0, (max) => Math.ceil(max)]} tickCount={6} allowDecimals={false} unit={` ${unite}`} width={64} />
            <Tooltip
              contentStyle={{ background: "var(--panneau-2)", border: "1px solid var(--trait)", borderRadius: 8, color: "var(--texte)" }}
              labelStyle={{ color: "var(--muted)" }}
              formatter={(v, n) => [`${Number(v).toFixed(2)} ${unite}`, n]}
            />
            {seuil != null && (
              <ReferenceLine y={seuil} stroke="var(--crit)" strokeDasharray="5 4" label={{ value: seuilLabel, fill: "var(--crit)", fontSize: 11, position: "insideBottomRight" }} />
            )}
            <Line name="Amont" type="monotone" dataKey={cleAmont} stroke="var(--amont)" strokeWidth={2.2} dot={false} isAnimationActive={false} />
            <Line name="Aval" type="monotone" dataKey={cleAval} stroke="var(--aval)" strokeWidth={2.2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

const CANAUX = [
  ["web", "Web"],
  ["email", "E-mail"],
  ["whatsapp", "WhatsApp"],
];
const STATUT_TXT = { envoyee: "envoyé", simulee: "simulé", echec: "échec" };

function Canaux({ canaux }) {
  return (
    <div className="canaux">
      {CANAUX.map(([k, nom]) => (
        <span key={k} className={`canal ${canaux[k] || "absent"}`} title={canaux[k] ? STATUT_TXT[canaux[k]] : "non émis"}>
          {nom} · {canaux[k] ? STATUT_TXT[canaux[k]] : "—"}
        </span>
      ))}
    </div>
  );
}

const EVT = { ouverte: "Alerte ouverte", aggravee: "Alerte aggravée", resolue: "Alerte résolue" };

function Cloche({ groupes }) {
  const [ouvert, setOuvert] = useState(false);
  const [vu, setVu] = useState(() => lireLocal("notif_vu", 0));
  const nonLus = groupes.filter((g) => g.id > vu).length;

  const basculer = () => {
    setOuvert((o) => !o);
    if (groupes.length) {
      const m = groupes[0].id;
      setVu(m);
      ecrireLocal("notif_vu", m);
    }
  };

  return (
    <div className="cloche">
      <button className="btn-cloche" onClick={basculer} aria-label="Notifications">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.7 21a2 2 0 01-3.4 0" />
        </svg>
        {nonLus > 0 && !ouvert && <span className="badge">{nonLus}</span>}
      </button>
      {ouvert && (
        <div className="panneau-notifs">
          <div className="panneau-tete">Notifications ({groupes.length})</div>
          {groupes.length === 0 && <p className="vide">Aucune notification pour le moment.</p>}
          {groupes.map((g) => (
            <div key={g.cle} className={`notif ${g.niveau}`}>
              <div className="notif-tete">
                <strong>{EVT[g.evenement]}</strong>
                <time>{dateHeure(g.cree_le)}</time>
              </div>
              <p>{g.message}</p>
              <Canaux canaux={g.canaux} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Toasts({ groupes, pret }) {
  const [liste, setListe] = useState([]);
  const connus = useRef(null);

  useEffect(() => {
    if (!pret) return; // on attend la première réponse de l'API avant de suivre les nouveautés
    if (connus.current === null) {
      connus.current = new Set(groupes.map((g) => g.cle + g.id));
      return;
    }
    const nouveaux = groupes.filter((g) => !connus.current.has(g.cle + g.id));
    if (!nouveaux.length) return;
    nouveaux.forEach((g) => connus.current.add(g.cle + g.id));
    setListe((l) => [...nouveaux.map((g) => ({ ...g, k: g.cle + g.id })), ...l].slice(0, 4));
    nouveaux.forEach((g) => setTimeout(() => setListe((l) => l.filter((t) => t.k !== g.cle + g.id)), 8000));
  }, [groupes, pret]);

  return (
    <div className="toasts" aria-live="polite">
      {liste.map((t) => (
        <div key={t.k} className={`toast ${t.niveau}`}>
          <strong>{EVT[t.evenement]}</strong>
          <p>{t.message}</p>
          <Canaux canaux={t.canaux} />
        </div>
      ))}
    </div>
  );
}

function TableAlertes({ alertes }) {
  return (
    <section className="carte">
      <header className="carte-tete">
        <h2>Historique des alertes</h2>
        <span className="muted">{alertes.length} au total</span>
      </header>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Statut</th>
              <th>Gravité</th>
              <th>Message</th>
              <th>Écart</th>
              <th>Ouverte</th>
              <th>Résolue</th>
            </tr>
          </thead>
          <tbody>
            {alertes.length === 0 && (
              <tr><td colSpan="6" className="vide">Aucune alerte enregistrée.</td></tr>
            )}
            {alertes.map((a) => (
              <tr key={a.id}>
                <td><span className={`pastille ${a.statut}`}>{a.statut === "ouverte" ? "Ouverte" : "Résolue"}</span></td>
                <td><span className={`pastille ${gravite(a)}`}>{gravite(a) === "critique" ? "Critique" : "Avertissement"}</span></td>
                <td className="msg">{a.message}</td>
                <td className="num">{a.ecart_pct != null ? `${nb(a.ecart_pct, 0)} %` : "—"}</td>
                <td className="num">{dateHeure(a.cree_le)}</td>
                <td className="num">{a.resolue_le ? dateHeure(a.resolue_le) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* ---------- application ---------- */
export default function App() {
  const { data, etat } = useDonnees();
  const { noeuds, portions, alertes, notifications, historique } = data;

  const global = useMemo(() => etatGlobal(alertes), [alertes]);
  const groupes = useMemo(() => grouperNotifications(notifications), [notifications]);
  const portion = portions[0];

  const amont = noeuds.find((n) => n.role === "amont");
  const aval = noeuds.find((n) => n.role === "aval");
  const mA = amont?.derniere_mesure;
  const mV = aval?.derniere_mesure;
  const pMin = portion?.pression_min_aval;

  // une ligne par horodatage, avec les 4 capteurs
  const courbes = useMemo(() => {
    const par = new Map();
    for (const m of [...historique].reverse()) {
      const cle = m.horodatage;
      const l = par.get(cle) || { t: heure(m.horodatage) };
      if (m.noeud === amont?.code) {
        l.debitA = m.debit;
        l.presA = m.pression;
      } else if (m.noeud === aval?.code) {
        l.debitV = m.debit;
        l.presV = m.pression;
      }
      par.set(cle, l);
    }
    return [...par.values()];
  }, [historique, amont, aval]);

  const pressionBasse = mV && pMin != null && mV.pression < pMin;
  const b = BANDEAU[global.niveau];

  return (
    <div className={`app etat-${global.niveau}`}>
      <header className="entete">
        <div className="marque">
          <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
            <path d="M16 3C11 11 7 15.5 7 20a9 9 0 0018 0c0-4.500-4-9-9-17z" fill="var(--amont)" />
          </svg>
          <div>
            <h1>Télégestion des fuites d'eau</h1>
            <p>Réseau villageois · surveillance amont / aval</p>
          </div>
        </div>
        <div className="entete-droite">
          <span className={`lien ${etat.connecte ? "ok" : "ko"}`} title={etat.erreur || ""}>
            <i /> {etat.connecte ? `Connecté · ${heure(etat.maj)}` : "Backend injoignable"}
          </span>
          <Cloche groupes={groupes} />
        </div>
      </header>

      {!etat.connecte && (
        <div className="hors-ligne">
          Impossible de joindre le backend sur <code>{API}</code>. Vérifiez que <code>python manage.py runserver</code> tourne.
        </div>
      )}

      <div className={`bandeau ${global.niveau}`} role="status">
        <div className="bandeau-icone" aria-hidden="true">{global.niveau === "ok" ? "✓" : "!"}</div>
        <div>
          <strong>{b.titre}</strong>
          <p>{global.ouvertes[0]?.message || b.texte}</p>
        </div>
        {global.ouvertes.length > 0 && <span className="bandeau-compte">{global.ouvertes.length} alerte(s) ouverte(s)</span>}
      </div>

      <section className="tuiles">
        <Tuile label="Débitmètre 1" role="amont" valeur={nb(mA?.debit)} unite="L/min" note={amont?.en_ligne ? "en ligne" : `dernière mesure ${heure(mA?.horodatage)}`} />
        <Tuile label="Débitmètre 2" role="aval" valeur={nb(mV?.debit)} unite="L/min" etat={global.niveau !== "ok" ? global.niveau : ""} note={portion ? `écart ${nb(portion.ecart_actuel_pct, 1)} % (seuil ${portion.seuil_ecart_pct} %)` : "—"} />
        <Tuile label="Capteur de pression 1" role="amont" valeur={nb(mA?.pression)} unite="bar" note={amont?.en_ligne ? "en ligne" : `dernière mesure ${heure(mA?.horodatage)}`} />
        <Tuile label="Capteur de pression 2" role="aval" valeur={nb(mV?.pression)} unite="bar" etat={pressionBasse ? "crit" : ""} note={pMin != null ? (pressionBasse ? `sous le minimum (${pMin} bar)` : `minimum ${pMin} bar`) : "—"} />
      </section>

      <section className="carte synoptique">
        <header className="carte-tete">
          <h2>Synoptique du réseau</h2>
          <span className="muted">{portion?.nom || "—"}</span>
        </header>
        <Synoptique niveau={global.niveau} amont={amont} aval={aval} portion={portion} />
      </section>

      <div className="grille-courbes">
        <Courbe titre="Débit (L/min)" donnees={courbes} cleAmont="debitA" cleAval="debitV" unite="L/min" />
        <Courbe titre="Pression (bar)" donnees={courbes} cleAmont="presA" cleAval="presV" unite="bar" seuil={pMin} seuilLabel={pMin != null ? `minimum ${pMin} bar` : ""} />
      </div>

      <TableAlertes alertes={alertes} />

      <footer className="pied">Données rafraîchies toutes les 2 s · API {API}</footer>
      <Toasts groupes={groupes} pret={etat.maj !== null} />
    </div>
  );
}
