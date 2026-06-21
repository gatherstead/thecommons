// Augments Vitest's `expect` with @testing-library/jest-dom matchers
// (toBeInTheDocument, etc.) so `tsc -b` type-checks the db-tier tests.
import "@testing-library/jest-dom/vitest";
