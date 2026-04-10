import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import ColorSearch from "./pages/ColorSearch";
import Products from "./pages/Products";
import ProductDetail from "./pages/ProductDetail";
import PigmentLibrary from "./pages/PigmentLibrary";
import LabData from "./pages/LabData";
import Stocks from "./pages/Stocks";

const navItems = [
  { to: "/", label: "Color Search" },
  { to: "/products", label: "Products" },
  { to: "/pigments", label: "Pigment Library" },
  { to: "/lab-data", label: "Lab Data" },
  { to: "/stocks", label: "Stocks" },
];

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col">
        <nav className="bg-indigo-700 text-white shadow">
          <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-6">
            <span className="font-bold text-lg tracking-wide">
              🎨 Surya Masterbatch
            </span>
            <div className="flex gap-4 ml-6">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) =>
                    `px-3 py-1 rounded text-sm font-medium transition ${
                      isActive ? "bg-white text-indigo-700" : "hover:bg-indigo-600"
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>
        </nav>

        <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6">
          <Routes>
            <Route path="/" element={<ColorSearch />} />
            <Route path="/products" element={<Products />} />
            <Route path="/products/:id" element={<ProductDetail />} />
            <Route path="/pigments" element={<PigmentLibrary />} />
            <Route path="/lab-data" element={<LabData />} />
            <Route path="/stocks" element={<Stocks />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
