// Simple i18n placeholder. Only Italian for now; structure ready for multilingua.
const TRANSLATIONS = {
  it: {
    "app.name": "CleanTec",
    "app.tagline": "Sistema integrato ERP • MES • WMS • TMS",
    "nav.dashboard": "Dashboard",
    "nav.clienti": "Clienti",
    "nav.articoli": "Articoli",
    "nav.macchine": "Macchine",
    "nav.accettazione": "Accettazione",
    "nav.lotti": "Tracciabilità Lotti",
    "nav.produzione": "Produzione (MES)",
    "nav.qualita": "Controllo Qualità",
    "nav.logistica": "Logistica",
    "nav.fatture": "Fatturazione",
    "nav.utenti": "Utenti & Sicurezza",
    "nav.touch": "Modalità Touch",
    "nav.mobile": "App Autista",
    "nav.portale": "Portale Cliente",
    "auth.login": "Accedi",
    "auth.logout": "Esci",
    "auth.email": "Email",
    "auth.password": "Password",
  },
};

let currentLang = "it";

export function t(key) {
  return (TRANSLATIONS[currentLang] && TRANSLATIONS[currentLang][key]) || key;
}

export function setLang(lang) {
  currentLang = lang;
}

export function getLang() {
  return currentLang;
}
