import { render, screen } from "@testing-library/react";

import { ErrorBoundary } from "./ErrorBoundary";

function BrokenComponent(): never { throw new Error("confidential failure detail"); }

describe("ErrorBoundary", () => {
  it("shows a safe fallback without raw error details", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<ErrorBoundary><BrokenComponent /></ErrorBoundary>);
    expect(screen.getByRole("heading")).toHaveTextContent("Something went wrong while loading Secure Document AI.");
    expect(screen.getByRole("button", { name: "Reload application" })).toBeVisible();
    expect(screen.queryByText(/confidential failure detail/i)).not.toBeInTheDocument();
    consoleSpy.mockRestore();
  });
});
