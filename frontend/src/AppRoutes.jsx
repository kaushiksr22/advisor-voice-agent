import { Routes, Route } from "react-router-dom";
import App from "./App.jsx";
import SecureDetails from "./SecureDetails.jsx";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<App />} />
      <Route path="/secure" element={<SecureDetails />} />
    </Routes>
  );
}
