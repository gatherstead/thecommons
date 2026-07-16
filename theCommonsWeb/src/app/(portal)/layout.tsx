// Route-group layout for the auth portal. Kept intentionally minimal: the
// split-panel chrome lives in PortalShell, which each portal page opts into
// individually (so the tab switcher can know which tab is active per-page).
//
// Note: this still nests inside the root app/layout.tsx, so the global
// Header/Footer chrome remains in effect above/below whatever renders here.
// That's an accepted constraint for this ticket -- see ticket 29.2.
export default function PortalLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return <>{children}</>;
}
