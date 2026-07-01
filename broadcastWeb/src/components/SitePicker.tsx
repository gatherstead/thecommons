import type { PreviewResult } from "../models/broadcastModels";

export const COMING_SOON = new Set([
  "fun4raleighkids",
  "chapelboro",
  "explore_pittsboro",
  "shop_pittsboro",
]);

interface Props {
  preview: PreviewResult;
  selected: Set<string>;
  onToggle: (siteKey: string) => void;
  disabled: boolean;
}

export default function SitePicker({ preview, selected, onToggle, disabled }: Props) {
  return (
    <>
      <p className="section-note">
        Eligible calendars are checked — uncheck any you don't want. Excluded
        calendars show why routing skipped them.
      </p>
      <ul className="site-list">
        {preview.eligible.map((site) => {
          const comingSoon = COMING_SOON.has(site.site_key);
          return (
            <li key={site.site_key} className={comingSoon ? "excluded" : undefined}>
              <input
                id={`site-${site.site_key}`}
                type="checkbox"
                checked={!comingSoon && selected.has(site.site_key)}
                onChange={() => !comingSoon && onToggle(site.site_key)}
                disabled={disabled || comingSoon}
              />
              <label
                className="site-name"
                htmlFor={`site-${site.site_key}`}
                style={comingSoon ? { opacity: 0.45 } : undefined}
              >
                {site.name}
              </label>
              {comingSoon && (
                <span className="reason">— coming soon</span>
              )}
            </li>
          );
        })}
        {preview.excluded.map((site) => (
          <li key={site.site_key} className="excluded">
            <input type="checkbox" checked={false} disabled readOnly />
            <span className="site-name">{site.site_key}</span>
            <span className="reason">— {site.reason}</span>
          </li>
        ))}
      </ul>
    </>
  );
}
