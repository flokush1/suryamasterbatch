import { useState } from "react";
import { searchColors, getRalPantone } from "../api";
import { Link } from "react-router-dom";

const POLYMERS = ["PE", "PP", "ABS", "SAN", "OTHER"];
const APPLICATIONS = ["N.A.", "PIPE", "FILM", "MOULDING", "CABLE", "SHOE", "ENG. POLYMER"];
const SUB_APPS = ["N.A.", "XLPE", "ZHFR", "WOVEN", "FLORO", "METALLIC"];
const COMPLIANCE_OPTS = ["NON-R", "ROHS1", "ROHS2", "REACH"];

function DeltaBadge({ de, source }) {
  if (de == null) {
    return (
      <span className="inline-block text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">
        Catalog Match
      </span>
    );
  }
  const color =
    de <= 1 ? "bg-green-100 text-green-800" :
    de <= 3 ? "bg-yellow-100 text-yellow-800" :
    de <= 6 ? "bg-orange-100 text-orange-800" :
    "bg-red-100 text-red-800";
  return (
    <span className={`inline-block text-xs font-semibold px-2 py-0.5 rounded-full ${color}`}>
      ΔE {de}
    </span>
  );
}

function labToRgb(L, a, b) {
  // LAB → XYZ (D65 illuminant)
  const fy = (L + 16) / 116;
  const fx = a / 500 + fy;
  const fz = fy - b / 200;
  const eps = 0.008856;
  const x = (fx ** 3 > eps ? fx ** 3 : (116 * fx - 16) / 903.3) * 0.95047;
  const y = (L > 903.3 * eps ? ((L + 16) / 116) ** 3 : L / 903.3) * 1.00000;
  const z = (fz ** 3 > eps ? fz ** 3 : (116 * fz - 16) / 903.3) * 1.08883;
  // XYZ → linear sRGB
  const rl =  3.2406 * x - 1.5372 * y - 0.4986 * z;
  const gl = -0.9689 * x + 1.8758 * y + 0.0415 * z;
  const bl =  0.0557 * x - 0.2040 * y + 1.0570 * z;
  // Gamma correction
  const gc = (c) => c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(Math.max(c, 0), 1 / 2.4) - 0.055;
  return [
    Math.max(0, Math.min(255, Math.round(gc(rl) * 255))),
    Math.max(0, Math.min(255, Math.round(gc(gl) * 255))),
    Math.max(0, Math.min(255, Math.round(gc(bl) * 255))),
  ];
}

function LabSwatch({ L, a, b, size = "w-10 h-10" }) {
  const [r, g, bv] = labToRgb(L, a, b);
  return (
    <div
      className={`${size} rounded border border-gray-300 flex-shrink-0`}
      style={{ backgroundColor: `rgb(${r},${g},${bv})` }}
      title={`L=${L} a=${a} b=${b}`}
    />
  );
}

function inferColorFromLab(L, a, b) {
  if (L == null) return null;
  const c = Math.sqrt((a || 0) ** 2 + (b || 0) ** 2);
  if (L > 85 && c < 15) return "white";
  if (L < 20) return "black";
  if (c < 12) return L > 60 ? "light grey" : "grey";
  const h = Math.atan2(b || 0, a || 0) * 180 / Math.PI;
  if (h >= -20 && h < 20)  return "red";
  if (h >= 20  && h < 55)  return "orange";
  if (h >= 55  && h < 100) return "yellow";
  if (h >= 100 && h < 165) return "green";
  if (h >= 165 && h < 220) return "cyan / teal";
  if (h >= 220 && h < 290) return "blue";
  return "violet / magenta";
}

function getMaterialRole(r) {
  const rmType = (r.rm_type || "").toUpperCase();
  const chem   = (r.chemical_name || "").toUpperCase();
  const name   = (r.rawmaterialname || "").toUpperCase();
  const ci     = (r.ci_name || "").toUpperCase();
  const inferredColor = inferColorFromLab(r.full_tone_L, r.full_tone_a, r.full_tone_b);

  if (rmType === "PRM") {
    return { type: "Pre-mixed MB", fn: "pre-dispersed pigment", color: inferredColor || "—", badge: "bg-purple-100 text-purple-700" };
  }

  if (rmType === "PG") {
    if (chem.includes("PIGMENT WHITE") || ci.startsWith("PW")) {
      return { type: "White pigment", fn: "opacity / whitening", color: "white", badge: "bg-gray-100 text-gray-600" };
    }
    if (chem.includes("CARBON") || chem.includes("PIGMENT BLACK") || ci.startsWith("PBK")) {
      return { type: "Black pigment", fn: "shade / darkening", color: "black", badge: "bg-gray-800 text-gray-100" };
    }
    if (chem.includes("PEARL") || chem.includes("ALUMIN") || chem.includes("MICA")) {
      return { type: "Effect pigment", fn: "metallic / pearlescent", color: "metallic", badge: "bg-yellow-100 text-yellow-700" };
    }
    const c = Math.sqrt((r.full_tone_a || 0) ** 2 + (r.full_tone_b || 0) ** 2);
    const isMain = r.full_tone_L != null && c > 30;
    return { type: "Colorant", fn: isMain ? "main colorant" : "shade correction", color: inferredColor || "—", badge: "bg-red-100 text-red-700" };
  }

  if (rmType === "RM") {
    const isResin = chem.includes("POLYMER") || /LLDPE|LDPE|HDPE|PP |ABS|SAN|PVC|NYLON|MAKROLON|EVA |ENGAGE|FLEXIRENE/.test(name) || /\bMFI\b/.test(name);
    if (isResin) return { type: "Base resin", fn: "carrier / matrix", color: "natural", badge: "bg-blue-100 text-blue-700" };

    if (chem.includes("FILLER") || name.includes("CAL ") || name.includes("CACO3") || name.includes("CALCIUM") || name.includes("TALC") || name.includes("CHINA CLAY")) {
      return { type: "Filler", fn: "extender / cost reduction", color: "off-white", badge: "bg-stone-100 text-stone-600" };
    }
    if (chem.includes("WAX") || name.includes("WAX") || name.includes("VSTANOL") || name.includes("ZS") || name.includes("ZINC STEARATE") || name.includes("STEARATE")) {
      return { type: "Wax / lubricant", fn: "processing aid", color: "off-white", badge: "bg-amber-100 text-amber-700" };
    }
    if (chem.includes("MODIFIER") || name.includes("VISTAMAX") || name.includes("POE") || name.includes("ELASTOMER") || name.includes("TAFMER")) {
      return { type: "Modifier", fn: "impact / dispersion", color: "natural", badge: "bg-teal-100 text-teal-700" };
    }
    if (name.includes("OIL") || name.includes("VINTROL") || name.includes("ACID") || name.includes("ANTIOXIDANT") || name.includes("UV ") || name.includes("IRGANOX") || name.includes("IRGAFOS")) {
      return { type: "Additive", fn: "process / stabiliser", color: "off-white", badge: "bg-green-100 text-green-700" };
    }
    return { type: "Additive", fn: "—", color: "—", badge: "bg-green-100 text-green-700" };
  }

  return { type: "—", fn: "—", color: "—", badge: "bg-gray-100 text-gray-400" };
}

function MLSuggestionCard({ s, rank }) {
  const colorantCount = s.n_colorants;
  const typeLabel =
    colorantCount === 1 ? "1 colorant" :
    colorantCount === 2 ? "2 colorants" : "3 colorants";
  const typeColor =
    colorantCount === 1 ? "bg-gray-100 text-gray-600" :
    colorantCount === 2 ? "bg-violet-100 text-violet-700" : "bg-fuchsia-100 text-fuchsia-700";

  return (
    <div className="border rounded-lg p-3 bg-white shadow-sm text-sm flex flex-col gap-2">
      <div className="flex items-center gap-2 flex-wrap">
        {rank != null && (
          <span className="text-xs font-bold text-gray-400 w-5 text-center">#{rank + 1}</span>
        )}
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${typeColor}`}>{typeLabel}</span>
        <span className="ml-auto text-xs text-gray-400">
          avg confidence {s.avg_confidence_pct}%
        </span>
      </div>

      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-400 border-b">
            <th className="text-left font-medium pb-0.5">Component</th>
            <th className="text-left font-medium pb-0.5">Role</th>
            <th className="text-right font-medium pb-0.5">%</th>
            <th className="text-right font-medium pb-0.5">Conf.</th>
          </tr>
        </thead>
        <tbody>
          {s.components.map((c, i) => (
            <tr key={i} className="border-t border-gray-100">
              <td className="py-0.5 pr-2 font-medium text-gray-800">
                <div className="flex items-center gap-1">
                  {c.full_tone_L != null && (
                    <LabSwatch L={c.full_tone_L} a={c.full_tone_a || 0} b={c.full_tone_b || 0} size="w-4 h-4" />
                  )}
                  {c.name}
                  {c.ci_name && <span className="text-gray-400 font-normal">· {c.ci_name}</span>}
                </div>
              </td>
              <td className="py-0.5 pr-2">
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                  c.role === "colorant" ? "bg-red-100 text-red-700" :
                  c.role === "opacity" ? "bg-gray-100 text-gray-600" :
                  "bg-blue-100 text-blue-700"
                }`}>{c.role}</span>
              </td>
              <td className="py-0.5 text-right font-semibold text-indigo-700">
                {c.pct?.toFixed(2)}%
              </td>
              <td className="py-0.5 text-right text-gray-500">
                {c.role === "colorant" ? `${c.confidence_pct}%` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ResultCard({ result, label }) {
  const [showRecipe, setShowRecipe] = useState(false);
  const lab = result.measured_lab || result.predicted_lab || {};
  return (
    <div className="border rounded-lg p-4 bg-white shadow-sm">
      <div className="flex items-start gap-3">
        {lab.L != null && <LabSwatch L={lab.L} a={lab.a} b={lab.b} />}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Link
              to={`/products/${result.product.id}`}
              className="font-semibold text-indigo-700 hover:underline"
            >
              {result.product.id} — {result.product.name}
            </Link>
            <DeltaBadge de={result.delta_e} />
            {label && (
              <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full">
                {label}
              </span>
            )}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            SLF: {result.product.slf_no || "—"} &nbsp;|&nbsp;
            Price: ₹{result.product.selling_price || "—"}/kg &nbsp;|&nbsp;
            {result.native_polymer ? `Native: ${result.native_polymer} → ${result.target_polymer}` : `Polymer: ${result.polymer}`}
          </div>
          {lab.L != null && (
            <div className="text-xs text-gray-400 mt-0.5">
              {result.source === "measured" ? "Measured" : "Predicted"} L={lab.L?.toFixed(1)} a={lab.a?.toFixed(1)} b={lab.b?.toFixed(1)}
            </div>
          )}
          {result.note && (
            <div className="text-xs text-amber-700 mt-1 italic">{result.note}</div>
          )}
        </div>
      </div>
      {result.recipe && result.recipe.length > 0 && (
        <div className="mt-2">
          <button
            className="text-xs text-indigo-600 hover:underline"
            onClick={() => setShowRecipe((v) => !v)}
          >
            {showRecipe ? "Hide recipe ▲" : `Show recipe (${result.recipe.length} items) ▼`}
          </button>
          {showRecipe && (
            <table className="mt-2 w-full text-xs border-collapse">
              <thead>
                <tr className="bg-gray-100">
                  <th className="text-left px-2 py-1">RM ID</th>
                  <th className="text-left px-2 py-1">Name</th>
                  <th className="text-left px-2 py-1">Role</th>
                  <th className="text-right px-2 py-1">Usage %</th>
                </tr>
              </thead>
              <tbody>
                {(() => {
                  const total = result.recipe.reduce((s, r) => s + (r.qtyinkg || 0), 0);
                  return result.recipe.map((r, i) => {
                    const role = getMaterialRole(r);
                    return (
                      <tr key={i} className="border-t">
                        <td className="px-2 py-1 font-mono">{r.rawmaterialid}</td>
                        <td className="px-2 py-1">{r.rawmaterialname || "—"}</td>
                        <td className="px-2 py-1">
                          <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${role.badge}`}>
                            {role.type}
                          </span>
                          <span className="ml-1 text-gray-400">{role.fn}</span>
                          {role.color && role.color !== "—" && (
                            <span className="ml-1 text-gray-400">· {role.color}</span>
                          )}
                        </td>
                        <td className="px-2 py-1 text-right">
                          {total > 0 ? ((r.qtyinkg / total) * 100).toFixed(2) + "%" : "—"}
                        </td>
                      </tr>
                    );
                  });
                })()}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

function PigmentSuggestionCard({ s, rank }) {
  const nPigments = s.pigments.length;
  const typeLabel =
    nPigments === 1 ? "Single pigment" :
    nPigments === 2 ? "2-pigment blend" : "3-pigment blend";
  const typeColor =
    nPigments === 1 ? "bg-gray-100 text-gray-600" :
    nPigments === 2 ? "bg-indigo-100 text-indigo-700" : "bg-purple-100 text-purple-700";

  return (
    <div className="border rounded-lg p-3 bg-white shadow-sm text-sm flex flex-col gap-2">
      {/* Header */}
      <div className="flex items-center gap-2 flex-wrap">
        {rank != null && (
          <span className="text-xs font-bold text-gray-400 w-5 text-center">#{rank + 1}</span>
        )}
        <DeltaBadge de={s.delta_e} />
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${typeColor}`}>{typeLabel}</span>
        {s.predicted_lab && (
          <LabSwatch L={s.predicted_lab.L} a={s.predicted_lab.a} b={s.predicted_lab.b} size="w-6 h-6" />
        )}
      </div>

      {/* Pigment list */}
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-400 border-b">
            <th className="text-left font-medium pb-0.5">Pigment</th>
            <th className="text-right font-medium pb-0.5">%</th>
            <th className="text-right font-medium pb-0.5">kg / 100 kg</th>
          </tr>
        </thead>
        <tbody>
          {s.pigments.map((p, i) => (
            <tr key={i} className="border-t border-gray-100">
              <td className="py-0.5 font-medium text-gray-800 pr-2">{p.name}</td>
              <td className="py-0.5 text-right text-gray-600">{(p.concentration * 100).toFixed(2)}%</td>
              <td className="py-0.5 text-right text-indigo-700 font-semibold">
                {p.kg_per_100kg != null ? p.kg_per_100kg.toFixed(2) : (p.concentration * 100).toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Predicted LAB */}
      <div className="text-xs text-gray-400 mt-0.5">
        Predicted L={s.predicted_lab.L} a={s.predicted_lab.a} b={s.predicted_lab.b}
      </div>
    </div>
  );
}

export default function ColorSearch() {
  const [form, setForm] = useState({
    target_L: "", target_a: "", target_b: "",
    polymer: "PE",
    application: "N.A.", sub_application: "N.A.",
    compliance: "NON-R",
    light_fastness: "", weather_fastness: "", heat_stability: "200",
    ral_pantone: "",
  });
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const payload = {
        target_L: parseFloat(form.target_L),
        target_a: parseFloat(form.target_a),
        target_b: parseFloat(form.target_b),
        polymer: form.polymer,
        application: form.application !== "N.A." ? form.application : undefined,
        sub_application: form.sub_application !== "N.A." ? form.sub_application : undefined,
        compliance: form.compliance,
        light_fastness: form.light_fastness ? parseFloat(form.light_fastness) : undefined,
        weather_fastness: form.weather_fastness ? parseFloat(form.weather_fastness) : undefined,
        heat_stability: form.heat_stability ? parseFloat(form.heat_stability) : undefined,
        ral_pantone: form.ral_pantone || undefined,
        top_n: 10,
      };
      const { data } = await searchColors(payload);
      setResults(data);
    } catch (err) {
      setError(err.response?.data?.error || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Color Search</h1>

      {/* Search Form */}
      <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow p-6 mb-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
          {["target_L", "target_a", "target_b"].map((k) => (
            <div key={k}>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                {k === "target_L" ? "L*" : k === "target_a" ? "a*" : "b*"}{" "}
                <span className="text-red-500">*</span>
              </label>
              <input
                type="number"
                step="0.01"
                required
                value={form[k]}
                onChange={(e) => set(k, e.target.value)}
                placeholder={k === "target_L" ? "0–100" : "-128–127"}
                className="w-full border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
            </div>
          ))}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Polymer <span className="text-red-500">*</span></label>
            <select value={form.polymer} onChange={(e) => set("polymer", e.target.value)}
              className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400">
              {POLYMERS.map((p) => <option key={p}>{p}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Application</label>
            <select value={form.application} onChange={(e) => set("application", e.target.value)}
              className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400">
              {APPLICATIONS.map((a) => <option key={a}>{a}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Sub-Application</label>
            <select value={form.sub_application} onChange={(e) => set("sub_application", e.target.value)}
              className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400">
              {SUB_APPS.map((a) => <option key={a}>{a}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Compliance</label>
            <select value={form.compliance} onChange={(e) => set("compliance", e.target.value)}
              className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400">
              {COMPLIANCE_OPTS.map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Min. Light Fastness</label>
            <input type="number" min="1" max="8" step="1" value={form.light_fastness}
              onChange={(e) => set("light_fastness", e.target.value)}
              placeholder="1–8"
              className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Min. Weather Fastness</label>
            <input type="number" min="1" max="5" step="1" value={form.weather_fastness}
              onChange={(e) => set("weather_fastness", e.target.value)}
              placeholder="1–5"
              className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Min. Heat Stability (°C)</label>
            <input type="number" value={form.heat_stability}
              onChange={(e) => set("heat_stability", e.target.value)}
              placeholder="200"
              className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">RAL / Pantone ref.</label>
            <input type="text" value={form.ral_pantone}
              onChange={(e) => set("ral_pantone", e.target.value)}
              placeholder="RAL 3020 or 199 C"
              className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
          </div>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-6 py-2 rounded transition disabled:opacity-50"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error && (
        <div className="bg-red-50 text-red-700 border border-red-200 rounded p-4 mb-4">
          {error}
        </div>
      )}

      {results && (
        <div className="space-y-6">
          {/* Target summary */}
          <div className="flex items-center gap-4 bg-white rounded-xl shadow p-4">
            <LabSwatch L={results.target_lab.L} a={results.target_lab.a} b={results.target_lab.b} />
            <div>
              <div className="font-semibold">Target Color</div>
              <div className="text-sm text-gray-500">
                L={results.target_lab.L} a={results.target_lab.a} b={results.target_lab.b} &nbsp;|&nbsp; Polymer: {results.polymer}
              </div>
            </div>
            {results.reference_color && (
              <div className="ml-6 flex items-center gap-3 border-l pl-6">
                {results.reference_color.hex_code && (
                  <div
                    className="w-10 h-10 rounded border border-gray-300 flex-shrink-0"
                    style={{ backgroundColor: results.reference_color.hex_code }}
                    title={results.reference_color.hex_code}
                  />
                )}
                <div className="text-sm">
                  <div className="font-medium text-gray-700">{results.reference_color.shade_code}</div>
                  <div className="text-xs text-gray-500">{results.reference_color.color_name}</div>
                  {results.reference_color.lab && (
                    <div className="text-xs text-gray-400">
                      Ref L={results.reference_color.lab.L} a={results.reference_color.lab.a} b={results.reference_color.lab.b}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Exact matches */}
          <section>
            <h2 className="text-lg font-semibold mb-2">
              Exact Matches in {results.polymer}{" "}
              <span className="text-sm font-normal text-gray-500">({results.total_exact} found)</span>
            </h2>
            {results.exact_matches.length === 0 ? (
              <p className="text-gray-500 text-sm">No existing recipes found in this polymer.</p>
            ) : (
              <div className="space-y-3">
                {results.exact_matches.map((r, i) => (
                  <ResultCard key={i} result={r} />
                ))}
              </div>
            )}
          </section>

          {/* Cross-polymer suggestions */}
          {results.cross_polymer_suggestions.length > 0 && (
            <section>
              <h2 className="text-lg font-semibold mb-2">
                Cross-Polymer Suggestions{" "}
                <span className="text-sm font-normal text-gray-500">({results.total_cross} similar in other polymers)</span>
              </h2>
              <div className="space-y-3">
                {results.cross_polymer_suggestions.map((r, i) => (
                  <ResultCard key={i} result={r} label="Cross-polymer" />
                ))}
              </div>
            </section>
          )}

          {/* K-M Pigment suggestions */}
          {results.pigment_suggestions.length > 0 && (
            <section>
              <h2 className="text-lg font-semibold mb-1">Pigment Combination Suggestions (K-M Model)</h2>
              <p className="text-xs text-gray-500 mb-3">
                Sorted by predicted ΔE · concentrations shown as % and kg per 100 kg batch ·
                verify with actual spectrophotometer reading before production
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {results.pigment_suggestions.map((s, i) => (
                  <PigmentSuggestionCard key={i} s={s} rank={i} />
                ))}
              </div>
            </section>
          )}

          {/* ML Recipe suggestions */}
          {results.ml_suggestions && results.ml_suggestions.length > 0 ? (
            <section>
              <h2 className="text-lg font-semibold mb-1">
                ML Recipe Suggestions
                <span className="ml-2 text-xs font-normal px-2 py-0.5 rounded-full bg-violet-100 text-violet-700">
                  Learned from {results.ml_status?.corpus_size || "?"} recipes ·{" "}
                  {results.ml_status?.trainable_pigments || "?"} pigment models
                </span>
              </h2>
              <p className="text-xs text-gray-500 mb-3">
                RandomForest + GradientBoosting trained on historical recipe data.
                Predictions interpolate across the colour space — not lookups.
                "Confidence" is the model's probability that this pigment belongs in the recipe.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {results.ml_suggestions.map((s, i) => (
                  <MLSuggestionCard key={i} s={s} rank={i} />
                ))}
              </div>
            </section>
          ) : results.ml_status?.status === "training" ? (
            <section>
              <div className="text-sm text-gray-400 italic border rounded-lg p-3 bg-gray-50">
                ML model is still training in the background — refresh after a moment to see ML suggestions.
              </div>
            </section>
          ) : null}
        </div>
      )}
    </div>
  );
}
