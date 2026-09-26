import { resolveFrontendConfig } from "./config";

describe("frontend environment validation", () => {
  it("uses localhost only during development", () => {
    expect(resolveFrontendConfig(undefined, false)).toEqual({ apiBaseUrl: "http://localhost:8000", error: null });
  });

  it("requires an explicit HTTPS API origin in production", () => {
    expect(resolveFrontendConfig(undefined, true).error).toContain("must be configured");
    expect(resolveFrontendConfig("http://api.example.test", true).error).toContain("HTTPS");
    expect(resolveFrontendConfig("https://api.example.test", true)).toEqual({ apiBaseUrl: "https://api.example.test", error: null });
  });

  it("rejects credentials and paths", () => {
    expect(resolveFrontendConfig("https://user:secret@example.test", true).error).not.toBeNull();
    expect(resolveFrontendConfig("https://example.test/api", true).error).not.toBeNull();
  });
});
