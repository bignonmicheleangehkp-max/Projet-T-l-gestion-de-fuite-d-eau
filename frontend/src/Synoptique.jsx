/** Schéma du réseau : réservoir → nœud amont → conduite → nœud aval → village. */
const COUL = { ok: "var(--ok)", warn: "var(--warn)", crit: "var(--crit)" };
const nb = (v, d = 2) => (v == null ? "—" : Number(v).toFixed(d));

function Maison({ x, y }) {
  return (
    <g transform={`translate(${x} ${y})`} fill="none" stroke="var(--muted)" strokeWidth="2" strokeLinejoin="round">
      <path d="M0 14 L14 2 L28 14 V30 H0 Z" />
      <path d="M11 30 V20 H17 V30" />
    </g>
  );
}

function Noeud({ x, titre, sous, m, couleur }) {
  return (
    <g>
      <line x1={x} y1="96" x2={x} y2="128" stroke="var(--trait)" strokeWidth="2" />
      <circle cx={x} cy="96" r="13" fill="var(--panneau)" stroke={couleur} strokeWidth="3" />
      <circle cx={x} cy="96" r="4.500" fill={couleur} />
      <text x={x} y="148" textAnchor="middle" className="syn-titre">{titre}</text>
      <text x={x} y="165" textAnchor="middle" className="syn-sous">{sous}</text>
      <text x={x} y="186" textAnchor="middle" className="syn-val">
        {nb(m?.debit)} L/min · {nb(m?.pression)} bar
      </text>
    </g>
  );
}

export default function Synoptique({ niveau, amont, aval, portion }) {
  const couleur = COUL[niveau];
  const fuite = niveau !== "ok";
  const ecart = portion?.ecart_actuel_pct;

  return (
    <div className="syn-wrap">
      <svg viewBox="0 0 900 200" role="img" aria-label="Synoptique du réseau d'eau" className={`syn ${niveau}`}>
        {/* réservoir */}
        <g>
          <rect x="30" y="52" width="92" height="88" rx="8" fill="var(--panneau-2)" stroke="var(--amont)" strokeWidth="2" />
          <rect x="34" y="92" width="84" height="44" rx="5" fill="var(--amont)" opacity="0.28" />
          <path d="M34 92 q10 -6 21 0 t21 0 t21 0 t21 0" fill="none" stroke="var(--amont)" strokeWidth="2" opacity="0.8" />
          <text x="76" y="164" textAnchor="middle" className="syn-titre">Réservoir</text>
        </g>

        {/* conduite */}
        <line x1="122" y1="96" x2="760" y2="96" stroke="var(--trait)" strokeWidth="12" strokeLinecap="round" />
        <line x1="122" y1="96" x2="760" y2="96" stroke={couleur} strokeWidth="4" strokeLinecap="round" className={`flux ${fuite ? "lent" : ""}`} />

        {/* fuite */}
        {fuite && (
          <g className="fuite" transform="translate(470 96)">
            <circle r="18" fill={couleur} opacity="0.18" className="onde" />
            <circle r="18" fill="none" stroke={couleur} strokeWidth="2" className="onde o2" />
            <path d="M0 8 C-9 22 -9 34 0 36 C9 34 9 22 0 8 Z" fill={couleur} transform="translate(0 4)" />
            <path d="M-16 6 L-26 24 M16 6 L26 24" stroke={couleur} strokeWidth="3" strokeLinecap="round" />
            <text y="-26" textAnchor="middle" className="syn-alerte" fill={couleur}>
              {niveau === "crit" ? "FUITE CRITIQUE" : "FUITE PROBABLE"}{ecart != null ? ` · écart ${nb(ecart, 0)} %` : ""}
            </text>
          </g>
        )}

        <Noeud x={250} titre="Nœud amont" sous="débitmètre 1 + pression 1" m={amont?.derniere_mesure} couleur="var(--amont)" />
        <Noeud x={690} titre="Nœud aval" sous="débitmètre 2 + pression 2" m={aval?.derniere_mesure} couleur={fuite ? couleur : "var(--aval)"} />

        {/* village */}
        <Maison x="790" y="78" />
        <Maison x="826" y="92" />
        <Maison x="802" y="52" />
        <text x="824" y="164" textAnchor="middle" className="syn-titre">Village</text>
      </svg>
    </div>
  );
}
