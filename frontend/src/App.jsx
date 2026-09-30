import { useEffect, useState } from "react";
import { api } from "./api.js";
import Dashboard from "./components/Dashboard.jsx";
import History from "./components/History.jsx";
import Setup from "./components/Setup.jsx";

export default function App() {
  const [tab, setTab] = useState("dashboard");
  const [state, setState] = useState(null);
  const [offline, setOffline] = useState(false);

  // Polling simple del estado cada segundo
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const s = await api.state();
        if (alive) {
          setState(s);
          setOffline(false);
        }
      } catch {
        if (alive) setOffline(true);
      }
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="app">
      <header>
        <h1>RESTAURANT VISION</h1>
        <nav>
          <button className={tab === "dashboard" ? "active" : ""} onClick={() => setTab("dashboard")}>
            Dashboard
          </button>
          <button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}>
            Historial
          </button>
          <button className={tab === "setup" ? "active" : ""} onClick={() => setTab("setup")}>
            Configuración
          </button>
        </nav>
      </header>
      {offline && <div className="banner error">No se puede conectar con el backend (¿está iniciado en el puerto 8000?)</div>}
      {tab === "dashboard" && <Dashboard state={state} goSetup={() => setTab("setup")} />}
      {tab === "history" && <History />}
      {tab === "setup" && <Setup />}
    </div>
  );
}
