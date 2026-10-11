import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";

export default defineConfig([
  ...nextVitals,
  {
    // These newer rules prepare components for the React Compiler, which this app doesn't use. The flagged
    // patterns (a latest-state ref, resetting state when a prop changes, a per-request random greeting on the
    // server) behave correctly today, so they warn rather than fail lint until we adopt the compiler.
    rules: {
      "react-hooks/refs": "warn",
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/purity": "warn"
    }
  },
  globalIgnores([".next/**", "next-env.d.ts"])
]);
