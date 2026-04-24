import React from "react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, err: null };
  }

  static getDerivedStateFromError(err) {
    const msg = String(err?.message || err || "");
    // Silently ignore known browser-extension noise (MetaMask, Coinbase Wallet, etc.)
    if (
      msg.includes("MetaMask") ||
      msg.includes("chrome-extension") ||
      msg.includes("moz-extension") ||
      msg.includes("ethereum") ||
      msg.includes("web3") ||
      msg.includes("Cannot redefine property") ||
      msg.includes("Non-Error promise rejection")
    ) {
      return { hasError: false, err: null };
    }
    return { hasError: true, err };
  }

  componentDidUpdate(prevProps) {
    // Auto-reset when resetKeys change (e.g. route/tab change)
    const prev = prevProps.resetKeys || [];
    const curr = this.props.resetKeys || [];
    if (this.state.hasError && (prev.length !== curr.length || prev.some((k, i) => k !== curr[i]))) {
      this.setState({ hasError: false, err: null });
    }
  }

  componentDidCatch(err, info) {
    const msg = String(err?.message || err || "");
    if (
      msg.includes("MetaMask") ||
      msg.includes("chrome-extension") ||
      msg.includes("moz-extension") ||
      msg.includes("ethereum")
    ) {
      // swallow extension errors
      return;
    }
    // eslint-disable-next-line no-console
    console.error("CleanTec error:", err, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 p-8">
          <div className="max-w-md text-center" data-testid="error-boundary">
            <div className="overline mb-3 text-red-500">Errore inatteso</div>
            <h1 className="font-display text-2xl font-bold text-slate-900 mb-2">
              Si è verificato un problema
            </h1>
            <p className="text-slate-500 text-sm mb-6">
              Ricarica la pagina per continuare. Se il problema persiste, contatta l'amministratore.
            </p>
            <button
              onClick={() => window.location.reload()}
              className="bg-indaco hover:bg-indaco-dark text-white font-medium px-5 py-2.5 rounded-md"
              data-testid="error-reload-btn"
            >
              Ricarica
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
