// Evaluate the PHASES, INDICATORS and STEP_META literals in a built page and print them as JSON (used by tests).
const fs = require("fs");
const vm = require("vm");
const html = fs.readFileSync(process.argv[2], "utf8");
function slice(startMarker, endRegex) {
  const s = html.indexOf(startMarker);
  if (s < 0) throw new Error("start marker not found: " + startMarker);
  const rest = html.slice(s);
  const m = endRegex.exec(rest);
  if (!m) throw new Error("end not found after: " + startMarker);
  return { start: s, end: s + m.index + m[0].length, text: rest.slice(0, m.index + m[0].length) };
}
const ph = slice("const PHASES = {", /\n      \};\n/);
const ind = slice("const INDICATORS = [", /\n      \];\n/);
const sm = slice("const STEP_META = [", /\n      \];\n/);
const ctx = {};
vm.createContext(ctx);
vm.runInContext(ph.text.replace("const PHASES", "PHASES") + ind.text.replace("const INDICATORS", "INDICATORS") + sm.text.replace("const STEP_META", "STEP_META"), ctx);
const out = { PHASES: ctx.PHASES, INDICATORS: ctx.INDICATORS, STEP_META: ctx.STEP_META,
  spans: { PHASES: [ph.start, ph.end], INDICATORS: [ind.start, ind.end], STEP_META: [sm.start, sm.end] } };
if (!Array.isArray(out.INDICATORS) || out.INDICATORS.length !== 16) throw new Error("expected 16 indicators, got " + (out.INDICATORS || []).length);
if (Object.keys(out.PHASES).length !== 4) throw new Error("expected 4 phases");
if (out.STEP_META.length !== 3) throw new Error("expected 3 steps");
process.stdout.write(JSON.stringify(out));
