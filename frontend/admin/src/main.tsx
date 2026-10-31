import "./index.css";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "./context/Auth";
import { ThemeProvider } from "./context/Theme";
import { ToastProvider } from "./components/Toast";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><ErrorBoundary><ThemeProvider><ToastProvider><BrowserRouter><AuthProvider><App /></AuthProvider></BrowserRouter></ToastProvider></ThemeProvider></ErrorBoundary></React.StrictMode>,
);
